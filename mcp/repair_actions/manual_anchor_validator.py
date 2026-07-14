from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.repair_actions.geometry_localizer import SAFETY_FLAGS


ALLOWED_COORDINATE_SPACES = {"target_sandbox_cad_space", "verified_transformed_reference_space"}
FORBIDDEN_GEOMETRY_SOURCES = {
    "guessed_geometry",
    "default_origin",
    "hardcoded_coordinate",
    "pdf_page_size_only",
}
GEOMETRY_SOURCE = "user_confirmed_cad_coordinate"
MIN_CONFIDENCE = 0.80
DANGEROUS_TOKENS = {"sendcommand", "hsxg", "hzgx", "gxlj", "tsaveas", "tgbatplots", "dcsz"}


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_manual_anchor_requests(path: str | Path) -> list[dict[str, Any]]:
    data = load_json(path)
    return list(data.get("requests") or [])


def build_capture_instructions(requests: list[dict[str, Any]]) -> str:
    first = requests[0] if requests else {}
    task_id = first.get("task_id") or "<task_id>"
    object_type = first.get("object_type") or "text/title"
    return f"""# S1-ANCHOR 人工 CAD 坐标采集说明

## 目标

为 `{task_id}` 采集可执行 CAD 坐标。对象类型：`{object_type}`。

## 采集位置

- 只允许在 sandbox copy 或 reference copy 中采集。
- 不得在 source DWG 上操作。
- 不得保存 DWG。
- 不得执行 SendCommand 或任何天正命令。

## 优先采集内容

1. 优先采集 `insert_point`，格式为 `[x, y, z]`。
2. 如果无法采集 `insert_point`，采集文字或标题区域 `bbox`，格式为 `[[min_x, min_y, min_z], [max_x, max_y, max_z]]`。
3. 如果涉及 reference 到 target 的坐标变换，采集至少两组 `reference_to_target_anchor_points`。

## 填写文件

请把采集结果填写到：

`artifacts/repair_tasks/s1_anchor_user_input.json`

可从模板复制：

`artifacts/repair_tasks/s1_anchor_user_input_template.json`

## 必填约束

- `coordinate_space` 必须是 `target_sandbox_cad_space` 或 `verified_transformed_reference_space`。
- `provided_by_user` 必须是 `true`。
- `source_dwg_used` 必须是 `false`。
- 不要填写猜测坐标、默认原点、PDF 页面坐标或硬编码占位坐标。
"""


def build_user_input_template(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": "S1-ANCHOR",
        "task_id": request.get("task_id"),
        "object_type": "text/title",
        "user_provided_geometry": {
            "insert_point": None,
            "bbox": None,
            "reference_to_target_anchor_points": [],
        },
        "coordinate_space": "target_sandbox_cad_space",
        "provided_by_user": True,
        "source_dwg_used": False,
        "notes": "",
    }


def validate_user_anchor_input(requests: list[dict[str, Any]], user_input: dict[str, Any] | None) -> dict[str, Any]:
    if not requests:
        return _validation(False, "manual anchor request missing", None, None)
    if user_input is None:
        return _validation(False, "user input file missing", None, requests[0])

    request = requests[0]
    if user_input.get("task_id") != request.get("task_id"):
        return _validation(False, "task_id does not match manual anchor request", user_input, request)
    if _contains_dangerous_token(user_input) or _contains_dangerous_token(request):
        return _validation(False, "SendCommand or Tianzheng command is forbidden", user_input, request)
    request_type = str(request.get("classification") or request.get("source_item_type") or request.get("task_type") or "direct_com_create")
    if request_type == "review_only":
        return _validation(False, "review_only item cannot become executable", user_input, request)
    if request_type == "blocked_invalid_task":
        return _validation(False, "blocked_invalid_task cannot enter anchor workflow", user_input, request)

    if user_input.get("source_dwg_used") is True:
        return _validation(False, "source DWG must not be used", user_input, request)
    if user_input.get("provided_by_user") is not True:
        return _validation(False, "provided_by_user must be true", user_input, request)

    coordinate_space = user_input.get("coordinate_space")
    if coordinate_space not in ALLOWED_COORDINATE_SPACES:
        return _validation(False, "coordinate_space is missing or not allowed", user_input, request)

    source = user_input.get("geometry_source")
    if source in FORBIDDEN_GEOMETRY_SOURCES:
        return _validation(False, f"forbidden geometry source: {source}", user_input, request)
    if source and source != GEOMETRY_SOURCE:
        return _validation(False, "geometry_source must be user_confirmed_cad_coordinate", user_input, request)

    geometry = dict(user_input.get("user_provided_geometry") or {})
    insert_point = geometry.get("insert_point")
    bbox = geometry.get("bbox")
    anchors = geometry.get("reference_to_target_anchor_points") or []

    if _looks_like_pdf_page_geometry(geometry, coordinate_space):
        return _validation(False, "PDF page coordinates are not CAD-space geometry", user_input, request)

    if insert_point is not None:
        if not _valid_point(insert_point):
            return _validation(False, "insert_point is null, zero, or invalid", user_input, request)
        return _validation(True, "", user_input, request, cad_geometry={"type": "point", "insert_point": _point3(insert_point)})

    if bbox is not None:
        if not _valid_bbox(bbox):
            return _validation(False, "bbox is invalid, zero-area, or min/max reversed", user_input, request)
        return _validation(True, "", user_input, request, cad_geometry={"type": "bbox", "bbox": _bbox3(bbox)})

    if anchors:
        return _validation(False, "anchor points provided without transformed CAD geometry", user_input, request)

    return _validation(False, "insert_point or bbox is required", user_input, request)


def build_validation_outputs(requests: list[dict[str, Any]], user_input: dict[str, Any] | None) -> dict[str, Any]:
    validation = validate_user_anchor_input(requests, user_input)
    executable: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    if validation["valid"]:
        request = requests[0]
        executable.append(
            {
                "task_id": request.get("task_id"),
                "object_type": "text/title",
                "action": "AddText",
                "cad_geometry": validation["cad_geometry"],
                "geometry_source": GEOMETRY_SOURCE,
                "geometry_confidence": MIN_CONFIDENCE,
                "execution_allowed": True,
                "coordinate_space": user_input.get("coordinate_space") if user_input else None,
                "source_dwg_used": False,
                "sendcommand_used": False,
                "tianzheng_command_executed": False,
            }
        )
    else:
        request = requests[0] if requests else {}
        blocked.append(
            {
                "task_id": request.get("task_id"),
                "object_type": request.get("object_type") or "text/title",
                "block_reason": validation["reason"],
                "required_user_input": request.get("required_user_input") or [],
                "execution_allowed": False,
            }
        )

    return {
        "validation": validation,
        "executable_direct_com_tasks": executable,
        "blocked_tasks": blocked,
        "safety": dict(SAFETY_FLAGS),
    }


def _validation(
    valid: bool,
    reason: str,
    user_input: dict[str, Any] | None,
    request: dict[str, Any] | None,
    *,
    cad_geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "valid": valid,
        "reason": reason,
        "task_id": (user_input or {}).get("task_id") or (request or {}).get("task_id"),
        "geometry_source": GEOMETRY_SOURCE if valid else None,
        "geometry_confidence": MIN_CONFIDENCE if valid else 0.0,
        "cad_geometry": cad_geometry,
    }


def _valid_point(value: Any) -> bool:
    numbers = _point_numbers(value)
    if len(numbers) not in (2, 3):
        return False
    return not all(abs(number) < 1e-9 for number in numbers)


def _valid_bbox(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    first = _point_numbers(value[0])
    second = _point_numbers(value[1])
    if len(first) not in (2, 3) or len(second) not in (2, 3):
        return False
    min_x, min_y = first[0], first[1]
    max_x, max_y = second[0], second[1]
    if max_x <= min_x or max_y <= min_y:
        return False
    return (max_x - min_x) * (max_y - min_y) > 0


def _point_numbers(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return []


def _point3(value: list[Any]) -> list[float]:
    numbers = _point_numbers(value)
    if len(numbers) == 2:
        numbers.append(0.0)
    return numbers[:3]


def _bbox3(value: list[Any]) -> list[list[float]]:
    return [_point3(value[0]), _point3(value[1])]


def _looks_like_pdf_page_geometry(geometry: dict[str, Any], coordinate_space: str | None) -> bool:
    if coordinate_space == "pdf_page_space":
        return True
    keys = {key for key, value in geometry.items() if value is not None}
    return bool(keys) and keys <= {"page", "width", "height", "reference_to_target_anchor_points"}


def _contains_dangerous_token(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return any(token in text for token in DANGEROUS_TOKENS)
