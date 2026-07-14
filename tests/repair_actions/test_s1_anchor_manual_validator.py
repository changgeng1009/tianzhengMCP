from __future__ import annotations

import json
from pathlib import Path

from mcp.repair_actions.manual_anchor_validator import (
    GEOMETRY_SOURCE,
    build_capture_instructions,
    build_user_input_template,
    build_validation_outputs,
    load_manual_anchor_requests,
    validate_user_anchor_input,
)
from mcp.repair_actions.geometry_localizer import SAFETY_FLAGS


def _write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _request() -> dict:
    return {
        "task_id": "mvp1_task_208c4ccc9f",
        "object_type": "text",
        "required_user_input": ["insert_point", "bbox"],
    }


def _user_input(**overrides: object) -> dict:
    data = {
        "phase": "S1-ANCHOR",
        "task_id": "mvp1_task_208c4ccc9f",
        "object_type": "text/title",
        "user_provided_geometry": {
            "insert_point": [100.0, 200.0, 0.0],
            "bbox": None,
            "reference_to_target_anchor_points": [],
        },
        "coordinate_space": "target_sandbox_cad_space",
        "provided_by_user": True,
        "source_dwg_used": False,
        "notes": "",
    }
    data.update(overrides)
    return data


def test_can_read_manual_anchor_request(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "manual.json", {"requests": [_request()]})

    requests = load_manual_anchor_requests(path)

    assert len(requests) == 1
    assert requests[0]["task_id"] == "mvp1_task_208c4ccc9f"


def test_can_generate_user_capture_instructions() -> None:
    instructions = build_capture_instructions([_request()])

    assert "s1_anchor_user_input.json" in instructions
    assert "不得在 source DWG 上操作" in instructions
    assert "insert_point" in instructions


def test_can_generate_user_input_template() -> None:
    template = build_user_input_template(_request())

    assert template["phase"] == "S1-ANCHOR"
    assert template["task_id"] == "mvp1_task_208c4ccc9f"
    assert template["user_provided_geometry"]["insert_point"] is None


def test_missing_user_coordinates_is_partial_blocked() -> None:
    outputs = build_validation_outputs([_request()], None)

    assert outputs["executable_direct_com_tasks"] == []
    assert len(outputs["blocked_tasks"]) == 1
    assert "missing" in outputs["validation"]["reason"]


def test_insert_point_null_is_blocked() -> None:
    user_input = _user_input(user_provided_geometry={"insert_point": None, "bbox": None})

    result = validate_user_anchor_input([_request()], user_input)

    assert result["valid"] is False


def test_insert_point_zero_is_blocked() -> None:
    user_input = _user_input(user_provided_geometry={"insert_point": [0, 0, 0], "bbox": None})

    result = validate_user_anchor_input([_request()], user_input)

    assert result["valid"] is False
    assert "zero" in result["reason"]


def test_zero_area_bbox_is_blocked() -> None:
    user_input = _user_input(user_provided_geometry={"insert_point": None, "bbox": [[1, 1, 0], [1, 5, 0]]})

    result = validate_user_anchor_input([_request()], user_input)

    assert result["valid"] is False
    assert "bbox" in result["reason"]


def test_pdf_page_coordinates_are_blocked() -> None:
    user_input = _user_input(
        coordinate_space="pdf_page_space",
        user_provided_geometry={"page": 1, "width": 2384, "height": 3370},
    )

    result = validate_user_anchor_input([_request()], user_input)

    assert result["valid"] is False


def test_task_id_mismatch_is_blocked() -> None:
    result = validate_user_anchor_input([_request()], _user_input(task_id="wrong"))

    assert result["valid"] is False
    assert "task_id" in result["reason"]


def test_review_only_does_not_enter_executable() -> None:
    request = dict(_request())
    request["task_type"] = "review_only"

    result = validate_user_anchor_input([request], _user_input())

    assert result["valid"] is False


def test_sendcommand_tianzheng_task_does_not_enter_executable() -> None:
    user_input = _user_input(notes="SendCommand hsxg")

    result = validate_user_anchor_input([_request()], user_input)

    assert result["valid"] is False
    assert "forbidden" in result["reason"]


def test_valid_target_sandbox_insert_point_generates_executable_task() -> None:
    outputs = build_validation_outputs([_request()], _user_input())

    assert len(outputs["executable_direct_com_tasks"]) == 1
    task = outputs["executable_direct_com_tasks"][0]
    assert task["execution_allowed"] is True
    assert task["cad_geometry"]["insert_point"] == [100.0, 200.0, 0.0]


def test_geometry_source_is_user_confirmed_cad_coordinate() -> None:
    outputs = build_validation_outputs([_request()], _user_input())

    assert outputs["executable_direct_com_tasks"][0]["geometry_source"] == GEOMETRY_SOURCE
    assert outputs["executable_direct_com_tasks"][0]["geometry_confidence"] >= 0.80


def test_safety_flags_remain_false() -> None:
    outputs = build_validation_outputs([_request()], None)

    assert outputs["safety"] == SAFETY_FLAGS
    assert all(value is False for value in outputs["safety"].values())
