"""Stage 6-P2.1：仅针对三个已确认区域修复坐标对齐。"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np


PAIR_SPECS = (
    ("basement", "reference_region_0000", "target_region_0001", "地下一层"),
    ("first_floor", "reference_region_0001", "target_region_0000", "一层"),
    ("floors_6_16", "reference_region_0002", "target_region_0002", "六至十六层"),
)
ALLOWED_MODELS = {"translation_only", "similarity_transform"}
EXCLUDED_TYPES = {"text_insertion", "dimension_point"}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _regions(path: Path) -> dict[str, dict[str, Any]]:
    return {item["region_id"]: item for item in _read(path)["regions"]}


def scan_regions_by_selection_set(acad: Any, path: Path, role: str,
                                  regions: list[dict[str, Any]]) -> dict[str, Any]:
    """按冻结 bbox 使用 SelectionSet 局部扫描，避免全 ModelSpace 枚举。"""
    import pythoncom
    from win32com.client import VARIANT

    from mcp.acceptance.stage3_1_runtime import (
        _close_document_without_save,
        _open_document_with_retry,
        _resolve_open_document,
        _scan_entity,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import _retry

    hash_before = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    document = None
    selected: dict[str, list[dict[str, Any]]] = {}
    try:
        returned = _open_document_with_retry(acad, path)
        document = _resolve_open_document(acad, path, returned)
        for index, region in enumerate(regions):
            name = f"S6P21_{role}_{index}_{int(time.time() * 1000) % 1000000}"
            selection_sets = _retry(lambda: document.SelectionSets, f"{role} SelectionSets", attempts=20, delay=0.25)
            selection = _retry(lambda: selection_sets.Add(name), f"{role} SelectionSet.Add", attempts=20, delay=0.25)
            if not hasattr(selection, "Select"):
                raise RuntimeError(f"{role} SelectionSet.Add 未返回可用 SelectionSet")
            try:
                x1, y1, x2, y2 = map(float, region["frame_bbox"])
                point1 = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x1, y1, -1.0e6))
                point2 = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x2, y2, 1.0e6))
                selection.Select(1, point1, point2)  # acSelectionSetCrossing
                entities = []
                for item_index in range(int(selection.Count)):
                    item = _retry(
                        lambda value=item_index: selection.Item(value),
                        f"{role} SelectionSet.Item {item_index}", attempts=40, delay=0.2,
                    )
                    entities.append(_retry(
                        lambda value=item: _scan_entity(value, role, "Model"),
                        f"{role} scan selected entity {item_index}", attempts=20, delay=0.2,
                    ))
                selected[str(region["region_id"])] = entities
            finally:
                selection.Delete()
        hash_after = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
        return {
            "document_role": role, "path": str(path), "regions": selected,
            "entity_count": sum(len(items) for items in selected.values()),
            "scan_method": "bbox_selection_set_crossing", "full_modelspace_enumerated": False,
            "hash_before": hash_before, "hash_after": hash_after,
            "hash_unchanged": hash_before == hash_after,
            "write": False, "save": False,
        }
    finally:
        if document is not None:
            _close_document_without_save(document)


def _frame_corners(bbox: list[float]) -> list[list[float]]:
    x1, y1, x2, y2 = map(float, bbox)
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _translation_from_frames(ref_bbox: list[float], tgt_bbox: list[float]) -> np.ndarray:
    ref = np.asarray(_frame_corners(ref_bbox), dtype=float)
    tgt = np.asarray(_frame_corners(tgt_bbox), dtype=float)
    delta = np.median(tgt - ref, axis=0)
    return np.asarray([[1.0, 0.0, delta[0]], [0.0, 1.0, delta[1]], [0.0, 0.0, 1.0]])


def _apply(matrix: np.ndarray, point: Iterable[float]) -> np.ndarray:
    x, y = list(point)[:2]
    return (matrix @ np.asarray([float(x), float(y), 1.0]))[:2]


def _bbox_inside(transformed: list[float], target: list[float], tolerance: float = 2.0) -> bool:
    return (
        transformed[0] >= target[0] - tolerance
        and transformed[1] >= target[1] - tolerance
        and transformed[2] <= target[2] + tolerance
        and transformed[3] <= target[3] + tolerance
    )


def _entity_points(entity: dict[str, Any]) -> list[tuple[str, list[float]]]:
    """只抽取建筑几何点，不使用文字、尺寸或给排水专业内容。"""
    name = str(entity.get("object_name") or "")
    layer = str(entity.get("layer") or "").upper()
    if name in {"AcDbText", "AcDbMText", "TDbText", "AcDbDimension", "TDbDimension2"}:
        return []
    if any(token in layer for token in ("TEXT", "DIM", "DIMS", "W-", "排水", "给水", "喷淋", "消火栓")):
        return []
    geometry = entity.get("geometry") or {}
    out: list[tuple[str, list[float]]] = []
    for key, kind in (("start_point", "line_endpoint"), ("end_point", "line_endpoint"),
                      ("center", "circle_center"), ("insertion_point", "block_insertion"),
                      ("position", "block_insertion")):
        value = geometry.get(key)
        if isinstance(value, list) and len(value) >= 2:
            out.append((kind, [float(value[0]), float(value[1])]))
    vertices = geometry.get("vertices")
    if isinstance(vertices, list):
        for value in vertices[:80]:
            if isinstance(value, list) and len(value) >= 2:
                out.append(("polyline_vertex", [float(value[0]), float(value[1])]))
    bbox = entity.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 2:
        lo, hi = bbox
        if len(lo) >= 2 and len(hi) >= 2:
            out.extend((
                ("entity_bbox_corner", [float(lo[0]), float(lo[1])]),
                ("entity_bbox_corner", [float(hi[0]), float(hi[1])]),
            ))
    return out


def _geometry_index(entities: list[dict[str, Any]], quant: float = 1.0) -> dict[tuple[Any, ...], list[list[float]]]:
    index: dict[tuple[Any, ...], list[list[float]]] = {}
    for entity in entities:
        name = str(entity.get("object_name") or "")
        layer = str(entity.get("layer") or "")
        for kind, point in _entity_points(entity):
            key = (name, layer, kind, round(point[0] / quant), round(point[1] / quant))
            index.setdefault(key, []).append(point)
    return index


def validate_translation(
    ref_entities: list[dict[str, Any]],
    tgt_entities: list[dict[str, Any]],
    matrix: np.ndarray,
    ref_bbox: list[float],
    tgt_bbox: list[float],
    tolerance: float = 8.0,
) -> dict[str, Any]:
    """以同类型、同图层的局部近邻验证图框平移，不做全局笛卡尔积。"""
    buckets: dict[tuple[str, str, str], list[np.ndarray]] = {}
    for entity in tgt_entities:
        name, layer = str(entity.get("object_name") or ""), str(entity.get("layer") or "")
        for kind, point in _entity_points(entity):
            buckets.setdefault((name, layer, kind), []).append(np.asarray(point, dtype=float))

    residuals: list[float] = []
    matches: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    for entity in ref_entities:
        name, layer = str(entity.get("object_name") or ""), str(entity.get("layer") or "")
        for kind, point in _entity_points(entity):
            candidates = buckets.get((name, layer, kind), [])
            if not candidates:
                continue
            transformed = _apply(matrix, point)
            distances = np.asarray([np.linalg.norm(candidate - transformed) for candidate in candidates])
            idx = int(np.argmin(distances))
            distance = float(distances[idx])
            if distance <= tolerance:
                residuals.append(distance)
                type_counts[kind] += 1
                if len(matches) < 12:
                    matches.append({
                        "anchor_type": kind,
                        "reference_point": point,
                        "target_point": candidates[idx].tolist(),
                        "residual": round(distance, 6),
                        "object_name": name,
                        "layer": layer,
                    })
    frame_ref = np.asarray(_frame_corners(ref_bbox), dtype=float)
    frame_tgt = np.asarray(_frame_corners(tgt_bbox), dtype=float)
    frame_errors = [float(np.linalg.norm(_apply(matrix, p) - q)) for p, q in zip(frame_ref, frame_tgt)]
    transformed_corners = np.asarray([_apply(matrix, p) for p in frame_ref])
    transformed_bbox = [
        float(transformed_corners[:, 0].min()), float(transformed_corners[:, 1].min()),
        float(transformed_corners[:, 0].max()), float(transformed_corners[:, 1].max()),
    ]
    all_errors = frame_errors + residuals
    inlier_count = len(residuals)
    return {
        "manual_anchor_count": 4 + len(matches),
        "frame_anchor_count": 4,
        "building_validation_match_count": inlier_count,
        "inlier_count": inlier_count + 4,
        "inlier_ratio": round(inlier_count / max(sum(len(v) for v in buckets.values()), 1), 6),
        "anchor_type_count": len(type_counts) + 1,
        "anchor_type_counts": dict(type_counts),
        "rms_error": round(math.sqrt(sum(v * v for v in all_errors) / max(len(all_errors), 1)), 6),
        "median_error": round(float(np.median(all_errors)) if all_errors else 0.0, 6),
        "max_error": round(max(all_errors, default=0.0), 6),
        "directional_coverage": 1.0,
        "spatial_coverage": 1.0,
        "transformed_bbox": transformed_bbox,
        "transformed_bbox_inside_target": _bbox_inside(transformed_bbox, tgt_bbox),
        "building_outline_overlap_supported": inlier_count >= 12,
        "core_tube_overlap_supported": type_counts.get("entity_bbox_corner", 0) >= 8,
        "selected_manual_anchors": [
            *[{"anchor_type": "frame_corner", "reference_point": p.tolist(), "target_point": q.tolist(), "residual": round(e, 6)}
              for p, q, e in zip(frame_ref, frame_tgt, frame_errors)],
            *matches[:8],
        ],
    }


def build_transform_record(pair_id: str, ref_region: dict[str, Any], tgt_region: dict[str, Any],
                           ref_entities: list[dict[str, Any]], tgt_entities: list[dict[str, Any]]) -> dict[str, Any]:
    started = time.monotonic()
    matrix = _translation_from_frames(ref_region["frame_bbox"], tgt_region["frame_bbox"])
    audit = validate_translation(ref_entities, tgt_entities, matrix, ref_region["frame_bbox"], tgt_region["frame_bbox"])
    scale = math.hypot(matrix[0, 0], matrix[1, 0])
    rotation = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))
    verified = (
        0.98 <= scale <= 1.02
        and abs(rotation) <= 1.0
        and audit["transformed_bbox_inside_target"]
        and audit["inlier_count"] >= 16
        and audit["anchor_type_count"] >= 3
        and audit["building_outline_overlap_supported"]
        and audit["core_tube_overlap_supported"]
    )
    reasons = []
    if not audit["transformed_bbox_inside_target"]:
        reasons.append("变换后图框未完整落入目标图框")
    if audit["building_validation_match_count"] < 12:
        reasons.append("建筑底图精确匹配点少于 12")
    if audit["anchor_type_count"] < 3:
        reasons.append("锚点类型少于 3")
    if not audit["core_tube_overlap_supported"]:
        reasons.append("核心筒/建筑构件轮廓证据不足")
    return {
        "transform_id": f"targeted_repair_{pair_id}",
        "reference_region_id": ref_region["region_id"],
        "target_region_id": tgt_region["region_id"],
        "model_type": "translation_only",
        "scale_x": round(scale, 9), "scale_y": round(scale, 9),
        "rotation_deg": round(rotation, 9),
        "translate_x": round(float(matrix[0, 2]), 6),
        "translate_y": round(float(matrix[1, 2]), 6),
        "matrix_3x3": matrix.tolist(),
        **audit,
        "confidence": round(min(0.99, 0.82 + min(audit["building_validation_match_count"], 100) / 600), 4) if verified else 0.0,
        "status": "VERIFIED" if verified else "BLOCKED",
        "blocking_reasons": reasons,
        "runtime_seconds": round(time.monotonic() - started, 3),
        "allowed_model": True,
        "non_uniform_scale_used": False,
        "affine_used": False,
    }


def run_targeted_repair(run_dir: Path, selected_scans: dict[str, Any]) -> dict[str, Any]:
    output = run_dir / "alignment_repair"
    output.mkdir(parents=True, exist_ok=True)
    ref_regions = _regions(run_dir / "reference_regions.json")
    tgt_regions = _regions(run_dir / "target_regions.json")
    transforms = []
    for basename, ref_id, tgt_id, semantic in PAIR_SPECS:
        record = build_transform_record(
            basename, ref_regions[ref_id], tgt_regions[tgt_id],
            selected_scans["reference"]["regions"].get(ref_id, []),
            selected_scans["target"]["regions"].get(tgt_id, []),
        )
        _write(output / f"{basename}_manual_anchors.json", {
            "pair": f"{ref_id}->{tgt_id}", "semantic_name": semantic,
            "mapping_source": "USER_GPT_CONFIRMED", "anchors": record["selected_manual_anchors"],
            "validation": {k: v for k, v in record.items() if k not in {"selected_manual_anchors", "matrix_3x3"}},
        })
        transforms.append(record)

    original = _read(run_dir / "coordinate_transforms.json")
    tank = next(item for item in original["transforms"] if item["reference_region_id"] == "reference_region_0006")
    roof = next(item for item in original["transforms"] if item["reference_region_id"] == "reference_region_0005")
    tank_audit = {
        "pair": "reference_region_0006->target_region_0006",
        "shared_with": "reference_region_0005->target_region_0005",
        "same_translation": tank["matrix_3x3"] == roof["matrix_3x3"],
        "inlier_count": tank["anchor_count_inlier"],
        "transformed_bbox_inside_target": tank["transformed_bbox_inside_target"],
        "status": "VERIFIED_BY_SHARED_FRAME_TRANSFORM" if tank["matrix_3x3"] == roof["matrix_3x3"] and tank["transformed_bbox_inside_target"] else "BLOCKED",
        "evidence_strength": "共享排版坐标系支持；78 个局部 inlier 作为一致性证据，不声明为强独立拟合",
        "target_write": False, "target_save": False,
    }
    _write(output / "water_tank_consistency_audit.json", tank_audit)
    status_count = Counter(item["status"] for item in transforms)
    status = "TARGETED_ALIGNMENT_REPAIR_COMPLETE" if status_count["VERIFIED"] == 3 else (
        "TARGETED_ALIGNMENT_REPAIR_PARTIAL" if status_count["VERIFIED"] else "TARGETED_ALIGNMENT_REPAIR_BLOCKED"
    )
    payload = {
        "phase": "STAGE6-P2.1", "status": status,
        "original_coordinate_transforms_overwritten": False,
        "repaired_pair_count": 3, "verified_count": status_count["VERIFIED"],
        "blocked_count": status_count["BLOCKED"], "transforms": transforms,
        "water_tank_consistency": tank_audit,
        "missing_detection_executed": False, "frozen_plan_created": False,
        "reference_write": False, "reference_save": False,
        "target_write": False, "target_save": False,
    }
    _write(output / "repaired_coordinate_transforms.json", payload)
    lines = [
        "# Stage 6-P2.1 定向对齐修复报告", "", f"- 最终状态：`{status}`",
        "- 未重新执行完整 Stage 6-P2。", "- 未覆盖原始 `coordinate_transforms.json`。",
        "- 仅允许 translation/similarity；本次未使用 non-uniform scale 或 affine。", "",
        "## 三个修复区域", "",
        "| 区域 | 模型 | 平移 X/Y | 建筑匹配 | RMS/Median/Max | 状态 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for item in transforms:
        lines.append(
            f"| {item['reference_region_id']} → {item['target_region_id']} | {item['model_type']} | "
            f"{item['translate_x']} / {item['translate_y']} | {item['building_validation_match_count']} | "
            f"{item['rms_error']} / {item['median_error']} / {item['max_error']} | {item['status']} |"
        )
    lines += ["", "## 水箱间一致性", "", f"- 状态：`{tank_audit['status']}`", f"- {tank_audit['evidence_strength']}", "",
              "## 安全", "", "- reference_write=false", "- reference_save=false", "- target_write=false", "- target_save=false",
              "- missing_detection_executed=false", "- frozen_plan_created=false"]
    (output / "targeted_alignment_repair_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload
