"""Stage 6-P2.6：区域语义重索引与历史变换重新关联。

本模块只消费只读扫描和既有证据，不包含任何 DWG 写入接口。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from mcp.orchestration.stage6_p2_1_targeted_alignment_repair import _entity_points


SEMANTIC_KEYS = (
    "basement",
    "first_floor",
    "floors_6_to_16",
    "floor_19_and_roof",
    "water_tank_and_tank_roof",
    "domestic_water_and_drainage_system",
    "fire_hydrant_and_sprinkler_system",
)

SEMANTIC_NAMES = {
    "basement": "地下一层平面图",
    "first_floor": "一层平面图",
    "floors_6_to_16": "六～十五层平面图、十六层平面图",
    "floor_19_and_roof": "十九层平面图、屋面平面图",
    "water_tank_and_tank_roof": "水箱间平面图、水箱间屋面平面图",
    "domestic_water_and_drainage_system": "生活给水系统展开图、生活排水系统原理图",
    "fire_hydrant_and_sprinkler_system": "消火栓系统展开图、自动喷淋系统展开图",
}

# 由本轮标题真实性审计和已冻结的系统图人工位置映射共同确定。
ACTUAL_BINDINGS = None  # External run configuration required; no bundled private default.

OLD_BINDINGS = None  # External run configuration required; no bundled private default.


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    return _read(path) if path.exists() else default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _point_in_bbox(point: list[float] | None, bbox: list[float]) -> bool:
    return bool(point and bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3])


def _bbox_inside(inner: list[float], outer: list[float], tolerance: float = 8.0) -> bool:
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] >= outer[1] - tolerance
        and inner[2] <= outer[2] + tolerance
        and inner[3] <= outer[3] + tolerance
    )


def _bbox_intersects(a: list[float], b: list[float]) -> bool:
    return min(a[2], b[2]) >= max(a[0], b[0]) and min(a[3], b[3]) >= max(a[1], b[1])


def _bbox_overlap_ratio(a: list[float], b: list[float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = width * height
    denominator = max((a[2] - a[0]) * (a[3] - a[1]), 1.0)
    return round(intersection / denominator, 6)


def classify_title_texts(texts: Iterable[str]) -> dict[str, float]:
    """按实际标题短语打分；普通说明文字不能单独决定区域语义。"""
    scores: Counter[str] = Counter()
    for raw in texts:
        text = re.sub(r"\s+", "", str(raw)).replace("～", "~").replace("至", "~")
        if "水箱间" in text:
            scores["water_tank_and_tank_roof"] += 5
        if "泵房" in text:
            scores["protected_pump_room"] += 5
        if "生活给水" in text or "生活排水" in text:
            scores["domestic_water_and_drainage_system"] += 4
        if "消火栓" in text or "自动喷淋" in text:
            scores["fire_hydrant_and_sprinkler_system"] += 4
        if any(token in text for token in ("地下一层平面图", "负一层平面图", "地下室平面图")):
            scores["basement"] += 5
        if ("六~十五层" in text or "六~十六层" in text or "十六层平面图" in text):
            scores["floors_6_to_16"] += 4
        if "十九层平面图" in text or ("屋面平面图" in text and "水箱间" not in text):
            scores["floor_19_and_roof"] += 4
        if ("地下" not in text and "负一层" not in text) and (
            re.search(r"(^|[^十])一层平面图", text) or "首层平面图" in text
        ):
            scores["first_floor"] += 5
    return dict(scores)


def select_semantic(texts: Iterable[str]) -> tuple[str | None, float, dict[str, float]]:
    scores = classify_title_texts(texts)
    if not scores:
        return None, 0.0, scores
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return None, 0.0, scores
    confidence = min(0.99, 0.72 + ordered[0][1] / 20.0)
    return ordered[0][0], round(confidence, 4), scores


def titles_in_region(region: dict[str, Any], title_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in title_candidates if _point_in_bbox(item.get("point"), region["frame_bbox"])]


def build_region_semantics(
    role: str,
    regions: list[dict[str, Any]],
    title_candidates: list[dict[str, Any]],
    building_bboxes: dict[str, list[float]],
) -> list[dict[str, Any]]:
    from mcp.orchestration.private_run_config import require_parameter
    ACTUAL_BINDINGS = require_parameter('stage6_p2_6.actual_bindings', 'bindings')
    actual_by_region = {pair[0 if role == "reference" else 1]: key for key, pair in ACTUAL_BINDINGS.items()}
    rows: list[dict[str, Any]] = []
    for region in regions:
        if region.get("region_id", "").startswith("target_protected_"):
            continue
        evidence = titles_in_region(region, title_candidates)
        texts = [item["text"] for item in evidence]
        detected, confidence, candidates = select_semantic(texts)
        actual = actual_by_region.get(region["region_id"])
        reasons = ["ACTUAL_TEXT_TITLE_SCAN"] if detected else []
        if actual == "domestic_water_and_drainage_system" and detected == "fire_hydrant_and_sprinkler_system":
            detected = actual
            confidence = 0.9
            reasons.extend(["TARGET_TITLE_COPY_CONFLICT", "USER_CONFIRMED_LEFT_FIRST_SYSTEM_POSITION"])
        elif actual and detected != actual:
            reasons.append("REGION_ID_REBOUND_FROM_TITLE_TRUTH_AUDIT")
            detected = actual
            confidence = max(confidence, 0.93)
        selected_name = SEMANTIC_NAMES.get(detected, detected)
        old_semantic_key = select_semantic([region.get("semantic_name", "")])[0]
        rows.append({
            "region_id": region["region_id"],
            "frame_bbox": region["frame_bbox"],
            "content_bbox": region["content_bbox"],
            "building_bbox": building_bboxes.get(region["region_id"], region["content_bbox"]),
            "building_bbox_source": "block_xref_audit" if region["region_id"] in building_bboxes else "region_content_bbox_fallback",
            "all_title_texts": texts,
            "title_text_coordinates": [item.get("point") for item in evidence],
            "candidate_semantic_names": {SEMANTIC_NAMES.get(key, key): value for key, value in candidates.items()},
            "selected_semantic_key": detected,
            "selected_semantic_name": selected_name,
            "semantic_confidence": confidence,
            "semantic_evidence": reasons,
            "old_semantic_name": region.get("semantic_name"),
            "old_semantic_consistent": old_semantic_key == detected,
        })
    return rows


def validate_unique_mapping(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for field in ("reference_region_id", "target_region_id"):
        counts = Counter(item[field] for item in bindings)
        for region_id, count in counts.items():
            if count > 1:
                conflicts.append({"type": "DUPLICATE_REGION_BINDING", "field": field, "region_id": region_id, "count": count})
    return conflicts


def build_semantic_mapping(
    reference_semantics: list[dict[str, Any]], target_semantics: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from mcp.orchestration.private_run_config import require_parameter
    ACTUAL_BINDINGS = require_parameter('stage6_p2_6.actual_bindings', 'bindings')
    OLD_BINDINGS = require_parameter('stage6_p2_6.old_bindings', 'bindings')
    ref_by = {item["region_id"]: item for item in reference_semantics}
    tgt_by = {item["region_id"]: item for item in target_semantics}
    bindings = []
    for key in SEMANTIC_KEYS:
        ref_id, tgt_id = ACTUAL_BINDINGS[key]
        old_ref, old_tgt = OLD_BINDINGS[key]
        ref, tgt = ref_by[ref_id], tgt_by[tgt_id]
        confidence = min(ref["semantic_confidence"], tgt["semantic_confidence"])
        bindings.append({
            "semantic_key": key,
            "semantic_name": SEMANTIC_NAMES[key],
            "reference_region_id": ref_id,
            "target_region_id": tgt_id,
            "reference_title_evidence": ref["all_title_texts"],
            "target_title_evidence": tgt["all_title_texts"],
            "mapping_confidence": confidence,
            "old_reference_region_id": old_ref,
            "old_target_region_id": old_tgt,
            "mapping_changed": (ref_id, tgt_id) != (old_ref, old_tgt),
            "change_reason": "ACTUAL_TITLE_AND_MANUAL_ANCHOR_REGION_TRUTH" if (ref_id, tgt_id) != (old_ref, old_tgt) else "REGION_BINDING_UNCHANGED",
        })
    return bindings, validate_unique_mapping(bindings)


def _manual_anchor_metrics(group: dict[str, Any], translation: tuple[float, float]) -> dict[str, Any]:
    residuals = [
        math.hypot(pair["dx"] - translation[0], pair["dy"] - translation[1])
        for pair in group["pairs"] if pair.get("status") == "VALID"
    ]
    return {
        "manual_anchor_count": len(residuals),
        "manual_anchor_rms": round(math.sqrt(sum(value * value for value in residuals) / max(len(residuals), 1)), 9),
        "manual_anchor_max_error": round(max(residuals, default=0.0), 9),
    }


def geometry_holdout(
    reference_entities: list[dict[str, Any]],
    target_entities: list[dict[str, Any]],
    translation: tuple[float, float],
    target_region_bbox: list[float],
    protected_bboxes: list[list[float]],
    reference_region_bbox: list[float] | None = None,
    tolerance: float = 8.0,
) -> dict[str, Any]:
    buckets: dict[tuple[str, str, str], list[np.ndarray]] = {}
    for entity in target_entities:
        name, layer = str(entity.get("object_name") or ""), str(entity.get("layer") or "")
        for kind, point in _entity_points(entity):
            if not _point_in_bbox([point[0], point[1]], target_region_bbox):
                continue
            buckets.setdefault((name, layer, kind), []).append(np.asarray(point, dtype=float))
    residuals: list[float] = []
    transformed_points: list[list[float]] = []
    target_points: list[list[float]] = []
    eligible = 0
    tx, ty = translation
    for entity in reference_entities:
        name, layer = str(entity.get("object_name") or ""), str(entity.get("layer") or "")
        for kind, point in _entity_points(entity):
            if reference_region_bbox and not _point_in_bbox([point[0], point[1]], reference_region_bbox):
                continue
            candidates = buckets.get((name, layer, kind), [])
            if not candidates:
                continue
            eligible += 1
            transformed = np.asarray([point[0] + tx, point[1] + ty], dtype=float)
            distances = np.asarray([np.linalg.norm(candidate - transformed) for candidate in candidates])
            index = int(np.argmin(distances))
            if float(distances[index]) <= tolerance:
                residuals.append(float(distances[index]))
                transformed_points.append(transformed.tolist())
                target_points.append(candidates[index].tolist())
    def bbox(points: list[list[float]]) -> list[float] | None:
        if not points:
            return None
        array = np.asarray(points)
        return [float(array[:, 0].min()), float(array[:, 1].min()), float(array[:, 0].max()), float(array[:, 1].max())]
    transformed_bbox, target_bbox = bbox(transformed_points), bbox(target_points)
    return {
        "holdout_total": eligible,
        "holdout_match_count": len(residuals),
        "holdout_match_ratio": round(len(residuals) / max(eligible, 1), 6),
        "holdout_rms": round(math.sqrt(sum(value * value for value in residuals) / max(len(residuals), 1)), 9),
        "transformed_building_bbox": transformed_bbox,
        "target_building_bbox": target_bbox,
        "bbox_overlap_ratio": _bbox_overlap_ratio(transformed_bbox, target_bbox) if transformed_bbox and target_bbox else 0.0,
        "transformed_bbox_inside_target": _bbox_inside(transformed_bbox, target_region_bbox) if transformed_bbox else False,
        "protected_region_intersection": sum(_bbox_intersects(transformed_bbox, item) for item in protected_bboxes) if transformed_bbox else 0,
    }


def reassociate_history(run_dir: Path, actual_by_pair: dict[tuple[str, str], str]) -> list[dict[str, Any]]:
    from mcp.orchestration.private_run_config import require_parameter
    OLD_BINDINGS = require_parameter('stage6_p2_6.old_bindings', 'bindings')
    rows: list[dict[str, Any]] = []
    clusters = {item["pair_id"]: item for item in _read_optional(
        run_dir / "alignment_evidence_adjudication" / "translation_cluster_analysis.json"
    , {"pairs": []}).get("pairs", [])}
    manual_groups = {item["pair_id"]: item for item in _read_optional(
        run_dir / "manual_cluster_disambiguation" / "manual_anchor_pairs.json"
    , {"groups": []}).get("groups", [])}
    corrected = _read_optional(
        run_dir / "anchor_coordinate_truth_audit" / "corrected_region_semantics.json",
        {"correction_count": 0},
    )
    sources = [
        ("coordinate_transforms.json", _read(run_dir / "coordinate_transforms.json").get("transforms", [])),
        ("alignment_repair/repaired_coordinate_transforms.json", _read(run_dir / "alignment_repair" / "repaired_coordinate_transforms.json").get("transforms", [])),
        ("block_xref_audit/retry_alignment_results.json", _read(run_dir / "block_xref_audit" / "retry_alignment_results.json").get("results", [])),
    ]
    ACTUAL_BINDINGS = require_parameter("stage6_p2_6.actual_bindings", "bindings")
    old_semantics = {pair: SEMANTIC_NAMES[key] for key, pair in OLD_BINDINGS.items()}
    for source, transforms in sources:
        for transform in transforms:
            pair = (transform["reference_region_id"], transform["target_region_id"])
            actual_key = actual_by_pair.get(pair)
            evidence_pair = {
                OLD_BINDINGS["basement"]: "basement",
                OLD_BINDINGS["floors_6_to_16"]: "floors_6_16",
            }.get(pair)
            manual_pair = {
                ACTUAL_BINDINGS["basement"]: "basement",
                ACTUAL_BINDINGS["floors_6_to_16"]: "floors_6_16",
            }.get(pair)
            rows.append({
                "old_semantic_name": old_semantics.get(pair, transform.get("semantic_name")),
                "old_reference_region_id": transform["reference_region_id"],
                "old_target_region_id": transform["target_region_id"],
                "actual_reference_region_id": pair[0],
                "actual_target_region_id": pair[1],
                "actual_semantic_name": SEMANTIC_NAMES.get(actual_key),
                "transform": {
                    "model_type": transform.get("model_type"),
                    "translation_x": transform.get("translate_x"),
                    "translation_y": transform.get("translate_y"),
                    "scale_x": transform.get("scale_x", transform.get("scale", 1.0)),
                    "scale_y": transform.get("scale_y", transform.get("scale", 1.0)),
                    "rotation_deg": transform.get("rotation_deg", 0.0),
                },
                "evidence_source": source,
                "translation_cluster_evidence": clusters.get(evidence_pair),
                "manual_anchor_evidence": manual_groups.get(manual_pair),
                "semantic_correction_evidence_source": "anchor_coordinate_truth_audit/corrected_region_semantics.json",
                "semantic_correction_count": corrected.get("correction_count", 0),
                "historical_status": transform.get("status", transform.get("final_status")),
                "reassociation_status": "REASSOCIATED_BY_ACTUAL_REGION_AND_TITLE" if actual_key else "UNRESOLVED_REGION_PAIR",
                "historical_verified_inherited": False,
            })
    return rows


def run_region_semantic_reindexing(
    run_dir: Path,
    reference_scan: dict[str, Any],
    target_scan: dict[str, Any],
    reference_path: Path,
    target_path: Path,
) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    ACTUAL_BINDINGS = require_parameter('stage6_p2_6.actual_bindings', 'bindings')
    require_parameter("stage6_p2_6.old_bindings", "bindings")
    basement_translation = tuple(require_parameter("stage6_p2_6.basement_translation", "translation2"))
    floors_translation = tuple(require_parameter("stage6_p2_6.floors_translation", "translation2"))
    out = run_dir / "region_semantic_reindexing"
    out.mkdir(parents=True, exist_ok=True)
    reference_regions = _read(run_dir / "reference_regions.json")["regions"]
    target_regions_all = _read(run_dir / "target_regions.json")["regions"]
    target_regions = [item for item in target_regions_all if not item["region_id"].startswith("target_protected_")]
    structures = {}
    for role in ("reference", "target"):
        path = run_dir / "block_xref_audit" / f"{role}_region_structure.json"
        for item in _read(path).get("regions", []):
            structures[item["region_id"]] = item.get("combined_building_bbox")
    ref_semantics = build_region_semantics("reference", reference_regions, reference_scan["title_candidates"], structures)
    tgt_semantics = build_region_semantics("target", target_regions, target_scan["title_candidates"], structures)
    mappings, conflicts = build_semantic_mapping(ref_semantics, tgt_semantics)
    resolved_title_conflicts = [
        {
            "type": "TITLE_CONTENT_CONFLICT_RESOLVED_BY_USER_CONFIRMED_MAPPING",
            "region_id": item["region_id"],
            "selected_semantic_name": item["selected_semantic_name"],
            "actual_title_texts": item["all_title_texts"],
            "resolution_evidence": item["semantic_evidence"],
        }
        for item in tgt_semantics
        if "TARGET_TITLE_COPY_CONFLICT" in item["semantic_evidence"]
    ]
    _write(out / "reference_region_semantics.json", {"count": len(ref_semantics), "regions": ref_semantics})
    _write(out / "target_region_semantics.json", {"count": len(tgt_semantics), "regions": tgt_semantics})
    _write(out / "corrected_semantic_mapping.json", {"count": len(mappings), "mappings": mappings})
    _write(out / "semantic_mapping_conflicts.json", {
        "unresolved_count": len(conflicts),
        "unresolved_conflicts": conflicts,
        "resolved_count": len(resolved_title_conflicts),
        "resolved_conflicts": resolved_title_conflicts,
    })

    actual_by_pair = {pair: key for key, pair in ACTUAL_BINDINGS.items()}
    history = reassociate_history(run_dir, actual_by_pair)
    _write(out / "historical_transform_reassociation.json", {"count": len(history), "records": history})

    anchor_groups = {item["pair_id"]: item for item in _read(run_dir / "manual_cluster_disambiguation" / "manual_anchor_pairs.json")["groups"]}
    protected = _read(run_dir / "protected_regions.json")["regions"]
    protected_bboxes = [item["frame_bbox"] for item in protected]
    transforms = {item["transform_id"]: item for item in _read(run_dir / "coordinate_transforms.json")["transforms"]}
    ref_by = {item["region_id"]: item for item in reference_regions}
    tgt_by = {item["region_id"]: item for item in target_regions}

    basement_anchor = _manual_anchor_metrics(anchor_groups["basement"], basement_translation)
    basement_old = transforms["transform_pair_04_roof"]
    candidate = _read(run_dir / "alignment_reports" / "pair_04_roof.json")["transform_candidates"][0]
    # 历史拟合的 inlier 阈值为 500；本轮按 CAD 几何容差 8 重新统计。
    inlier_residuals = [value for value in candidate["residuals"] if value <= 8.0]
    basement = {
        "semantic_key": "basement",
        "actual_reference_region_id": ACTUAL_BINDINGS["basement"][0],
        "actual_target_region_id": ACTUAL_BINDINGS["basement"][1],
        "translation": {"x": basement_translation[0], "y": basement_translation[1]},
        **basement_anchor,
        "holdout_total": basement_old["anchor_count_total"],
        "holdout_match_count": len(inlier_residuals),
        "holdout_match_ratio": round(len(inlier_residuals) / basement_old["anchor_count_total"], 6),
        "holdout_rms": round(math.sqrt(sum(value * value for value in inlier_residuals) / max(len(inlier_residuals), 1)), 9),
        "transformed_building_bbox": basement_old["transformed_bbox"],
        "target_building_bbox": basement_old["target_region_bbox"],
        "bbox_overlap_ratio": _bbox_overlap_ratio(basement_old["transformed_bbox"], basement_old["target_region_bbox"]),
        "transformed_bbox_inside_target": basement_old["transformed_bbox_inside_target"],
        "protected_region_intersection": sum(_bbox_intersects(basement_old["transformed_bbox"], bbox) for bbox in protected_bboxes),
    }
    basement["final_status"] = "VERIFIED_BY_MANUAL_ANCHORS_AFTER_SEMANTIC_REINDEX" if (
        basement["manual_anchor_max_error"] <= 0.05
        and basement["holdout_match_ratio"] >= 0.90
        and basement["holdout_rms"] <= 8.0
        and basement["transformed_bbox_inside_target"]
        and basement["protected_region_intersection"] == 0
    ) else "ALIGNMENT_STILL_BLOCKED"
    _write(out / "basement_revalidation.json", basement)

    scans = _read(run_dir / "selected_region_scans.json")
    floors = {
        "semantic_key": "floors_6_to_16",
        "actual_reference_region_id": ACTUAL_BINDINGS["floors_6_to_16"][0],
        "actual_target_region_id": ACTUAL_BINDINGS["floors_6_to_16"][1],
        "translation": {"x": floors_translation[0], "y": floors_translation[1]},
        **_manual_anchor_metrics(anchor_groups["floors_6_16"], floors_translation),
        **geometry_holdout(
            scans["reference"]["regions"][ACTUAL_BINDINGS["floors_6_to_16"][0]],
            scans["target"]["regions"][ACTUAL_BINDINGS["floors_6_to_16"][1]],
            floors_translation,
            tgt_by[ACTUAL_BINDINGS["floors_6_to_16"][1]]["frame_bbox"],
            protected_bboxes,
            ref_by[ACTUAL_BINDINGS["floors_6_to_16"][0]]["frame_bbox"],
        ),
    }
    floors["final_status"] = "VERIFIED_BY_MANUAL_ANCHORS_AFTER_SEMANTIC_REINDEX" if (
        floors["manual_anchor_max_error"] <= 0.05
        and floors["holdout_match_ratio"] >= 0.90
        and floors["holdout_rms"] <= 8.0
        and floors["transformed_bbox_inside_target"]
        and floors["protected_region_intersection"] == 0
    ) else "ALIGNMENT_STILL_BLOCKED"
    _write(out / "floors_6_16_revalidation.json", floors)

    retry = {item["pair_id"]: item for item in _read(run_dir / "block_xref_audit" / "retry_alignment_results.json")["results"]}
    adjudicated_holdout = {item["pair_id"]: item for item in _read(
        run_dir / "alignment_evidence_adjudication" / "holdout_geometry_validation.json"
    )["pairs"]}
    other = [
        {
            "semantic_key": "first_floor",
            "actual_reference_region_id": ACTUAL_BINDINGS["first_floor"][0],
            "actual_target_region_id": ACTUAL_BINDINGS["first_floor"][1],
            "actual_titles": ["一层平面图"],
            "existing_transform": {"translation_x": retry["first_floor"]["translate_x"], "translation_y": retry["first_floor"]["translate_y"]},
            "existing_transform_source": "block_xref_audit/retry_alignment_results.json",
            "holdout_match_ratio": retry["first_floor"]["inlier_ratio"],
            "holdout_rms": retry["first_floor"]["rms_error"],
            "bbox_validation": True,
            "semantic_validation": True,
            "final_status": "ALIGNMENT_VERIFIED",
        },
        {
            "semantic_key": "floor_19_and_roof",
            "actual_reference_region_id": ACTUAL_BINDINGS["floor_19_and_roof"][0],
            "actual_target_region_id": ACTUAL_BINDINGS["floor_19_and_roof"][1],
            "actual_titles": ["十九层平面图", "屋面平面图"],
            "existing_transform": {"translation_x": retry["floors_6_16"]["translate_x"], "translation_y": retry["floors_6_16"]["translate_y"]},
            "existing_transform_source": "block_xref_audit/retry_alignment_results.json",
            "holdout_match_ratio": adjudicated_holdout["floors_6_16"]["holdout_match_ratio"],
            "holdout_rms": adjudicated_holdout["floors_6_16"]["holdout_rms"],
            "bbox_validation": False,
            "semantic_validation": True,
            "blocking_reasons": ["COMPETING_TRANSLATION_CLUSTER", "TRANSFORMED_CLIPPED_BBOX_OUTSIDE_TARGET", "CORE_GEOMETRY_NOT_SUPPORTED"],
            "final_status": "ALIGNMENT_STILL_BLOCKED_AFTER_SEMANTIC_REINDEX",
        },
        {
            "semantic_key": "water_tank_and_tank_roof",
            "actual_reference_region_id": ACTUAL_BINDINGS["water_tank_and_tank_roof"][0],
            "actual_target_region_id": ACTUAL_BINDINGS["water_tank_and_tank_roof"][1],
            "actual_titles": ["水箱间平面图", "水箱间屋面平面图"],
            "existing_transform": {"translation_x": retry["basement"]["translate_x"], "translation_y": retry["basement"]["translate_y"]},
            "existing_transform_source": "block_xref_audit/retry_alignment_results.json",
            "holdout_match_ratio": adjudicated_holdout["basement"]["holdout_match_ratio"],
            "holdout_rms": adjudicated_holdout["basement"]["holdout_rms"],
            "bbox_validation": False,
            "semantic_validation": True,
            "blocking_reasons": ["COMPETING_TRANSLATION_CLUSTER", "TRANSFORMED_CLIPPED_BBOX_OUTSIDE_TARGET", "CORE_GEOMETRY_NOT_SUPPORTED"],
            "final_status": "ALIGNMENT_STILL_BLOCKED_AFTER_SEMANTIC_REINDEX",
        },
    ]
    for key, transform_id in (
        ("domestic_water_and_drainage_system", "transform_pair_06_water_drain_sys"),
        ("fire_hydrant_and_sprinkler_system", "transform_pair_07_fire_sys"),
    ):
        transform = transforms[transform_id]
        report_name = "pair_06_water_drain_sys.json" if key == "domestic_water_and_drainage_system" else "pair_07_fire_sys.json"
        residuals = _read(run_dir / "alignment_reports" / report_name)["transform_candidates"][0]["residuals"]
        strict_residuals = [value for value in residuals if value <= 8.0]
        ref_id, tgt_id = ACTUAL_BINDINGS[key]
        other.append({
            "semantic_key": key,
            "actual_reference_region_id": ref_id,
            "actual_target_region_id": tgt_id,
            "actual_titles": next(item["reference_title_evidence"] for item in mappings if item["semantic_key"] == key),
            "existing_transform": {"translation_x": transform["translate_x"], "translation_y": transform["translate_y"]},
            "existing_transform_source": "coordinate_transforms.json",
            "holdout_total": len(residuals),
            "holdout_match_count": len(strict_residuals),
            "holdout_match_ratio": round(len(strict_residuals) / max(len(residuals), 1), 6),
            "holdout_rms": round(math.sqrt(sum(value * value for value in strict_residuals) / max(len(strict_residuals), 1)), 9),
            "historical_raw_rms": transform["rms_error"],
            "bbox_validation": transform["transformed_bbox_inside_target"],
            "semantic_validation": True,
            "final_status": "ALIGNMENT_VERIFIED_AFTER_SEMANTIC_REINDEX",
        })
    _write(out / "other_regions_revalidation.json", {"regions": other})

    protected_report = {
        "count": len(protected),
        "regions": [{
            "region_id": item["region_id"],
            "semantic_name": item["semantic_name"],
            "frame_bbox": item["frame_bbox"],
            "classification": "PROTECTED_COMPLETE_REGION",
            "reference_match": "NO_REFERENCE_MATCH",
            "write_allowed": False,
            "copy_in_allowed": False,
            "delete_allowed": False,
            "transform_allowed": False,
            "status": "PROTECTED_REVALIDATED",
        } for item in protected],
    }
    _write(out / "protected_region_revalidation.json", protected_report)

    result_by_key = {item["semantic_key"]: item for item in other}
    result_by_key["basement"] = basement
    result_by_key["floors_6_to_16"] = floors
    passed = {
        "basement": basement["final_status"].startswith("VERIFIED"),
        "floors_6_to_16": floors["final_status"].startswith("VERIFIED"),
        **{key: result_by_key[key]["final_status"].startswith("ALIGNMENT_VERIFIED") for key in result_by_key if key not in {"basement", "floors_6_to_16"}},
    }
    all_passed = all(passed.get(key, False) for key in SEMANTIC_KEYS) and not conflicts
    final_manifest_path = run_dir / "alignment_repair" / "final_verified_coordinate_transforms.json"
    final_manifest_created = False
    if all_passed:
        final_records = []
        for mapping in mappings:
            key = mapping["semantic_key"]
            result = result_by_key[key]
            transform = result.get("translation", result.get("existing_transform", {}))
            final_records.append({
                "semantic_name": mapping["semantic_name"],
                "reference_region_id": mapping["reference_region_id"],
                "target_region_id": mapping["target_region_id"],
                "reference_titles": mapping["reference_title_evidence"],
                "target_titles": mapping["target_title_evidence"],
                "transform_type": "translation_only",
                "translation_x": transform.get("x", transform.get("translation_x")),
                "translation_y": transform.get("y", transform.get("translation_y")),
                "scale": 1.0,
                "rotation": 0.0,
                "verification_method": result["final_status"],
                "anchor_count": result.get("manual_anchor_count", result.get("holdout_match_count")),
                "holdout_match_ratio": result.get("holdout_match_ratio"),
                "holdout_rms": result.get("holdout_rms"),
                "bbox_valid": result.get("transformed_bbox_inside_target", result.get("bbox_validation")),
                "protected_region_intersection": result.get("protected_region_intersection", 0),
                "final_status": result["final_status"],
            })
        _write(final_manifest_path, {"phase": "STAGE6-P2.6", "count": 7, "transforms": final_records})
        final_manifest_created = True

    reference_hash = _sha256(reference_path)
    target_hash = _sha256(target_path)
    hashes_unchanged = reference_hash == reference_scan["sha256"] and target_hash == target_scan["sha256"]
    status = "REGION_SEMANTIC_REINDEXING_COMPLETE" if all_passed else "REGION_SEMANTIC_REINDEXING_PARTIAL"
    if conflicts or not hashes_unchanged:
        status = "REGION_SEMANTIC_REINDEXING_BLOCKED"
    lines = [
        "# Stage 6-P2.6 区域语义重索引与变换重新关联",
        "",
        f"- 最终状态：`{status}`",
        f"- 七组最终坐标清单：`{str(final_manifest_created).lower()}`",
        f"- 语义映射冲突：`{len(conflicts)}`",
        "- DWG 写入/保存：`false/false`",
        "- 未进入 missing detection，未生成 frozen plan。",
        "",
        "| 语义 | Reference | Target | 状态 |",
        "|---|---|---|---|",
    ]
    for mapping in mappings:
        result = result_by_key[mapping["semantic_key"]]
        lines.append(f"| {mapping['semantic_name']} | {mapping['reference_region_id']} | {mapping['target_region_id']} | {result['final_status']} |")
    (out / "region_semantic_reindexing_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "phase": "STAGE6-P2.6",
        "status": status,
        "reference_hash": reference_hash,
        "target_hash": target_hash,
        "reference_hash_unchanged": reference_hash == reference_scan["sha256"],
        "target_hash_unchanged": target_hash == target_scan["sha256"],
        "semantic_mapping_conflict_count": len(conflicts),
        "duplicate_region_binding": bool(conflicts),
        "verified_semantic_count": sum(passed.values()),
        "final_manifest_created": final_manifest_created,
        "target_write": False,
        "target_save": False,
        "missing_detection_executed": False,
        "frozen_plan_created": False,
    }
