"""Stage 6-P2.7：用新增人工锚点裁决剩余两个区域。

DWG 仅用于读取指定 MCP_ANCHOR 文本；几何验证完全使用既有 P2.2/P2.3 产物。
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from mcp.orchestration.stage6_p2_3_alignment_evidence_adjudication import (
    _bbox_intersects,
    cross_frame_audit,
    holdout_validation,
)
from mcp.orchestration.stage6_p2_5_1_anchor_coordinate_truth_audit import (
    _safe,
    extract_entity_text,
    parse_text_properties,
    point_in_bbox,
)


FLOOR19_IDS = ("F19_ROOF_FIX_01", "F19_ROOF_FIX_02", "F19_ROOF_FIX_03")
TANK_IDS = ("TANK_FIX_01", "TANK_FIX_02", "TANK_FIX_03")
ANCHOR_IDS = frozenset((*FLOOR19_IDS, *TANK_IDS))
CAD_TOLERANCE = 20.0

GROUPS = {
    "floor_19_and_roof": {
        "anchor_ids": FLOOR19_IDS,
        "reference_region_id": "reference_region_0002",
        "target_region_id": "target_region_0002",
        "cluster_pair_id": "floors_6_16",
        "semantic_name": "十九层平面图、屋面平面图",
    },
    "water_tank_and_tank_roof": {
        "anchor_ids": TANK_IDS,
        "reference_region_id": "reference_region_0000",
        "target_region_id": "target_region_0001",
        "cluster_pair_id": "basement",
        "semantic_name": "水箱间平面图、水箱间屋面平面图",
    },
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_named_anchors_readonly(acad: Any, path: Path, role: str) -> dict[str, Any]:
    """只读取指定锚点；不调用任何 DWG 写入或保存接口。"""
    from mcp.acceptance.stage3_1_runtime import (
        _close_document_without_save,
        _open_document_with_retry,
        _resolve_open_document,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import _retry

    before = _sha256(path)
    stat = path.stat()
    document = None
    anchors: list[dict[str, Any]] = []
    try:
        returned = _open_document_with_retry(acad, path)
        document = _resolve_open_document(acad, path, returned)
        # AutoCAD 2026 偶尔对 late-bound Item(index) 返回 <unknown> 代理；
        # 通过 COM 集合枚举只取得实体代理，不读取非锚点几何。
        entities = _retry(lambda: list(document.ModelSpace), f"{role} ModelSpace enumeration", attempts=10, delay=0.5)
        count = len(entities)
        for entity in entities:
            name = str(_safe(entity, "ObjectName", ""))
            if name != "AcDbText":
                continue
            layer = str(_safe(entity, "Layer", ""))
            if layer.upper() != "MCP_ANCHOR":
                continue
            anchor_id = extract_entity_text(entity).upper()
            if anchor_id not in ANCHOR_IDS:
                continue
            row = parse_text_properties(entity)
            row["anchor_id"] = anchor_id
            row["role"] = role
            anchors.append(row)
        after = _sha256(path)
        return {
            "role": role,
            "full_path": str(_safe(document, "FullName", str(path))),
            "document_name": str(_safe(document, "Name", path.name)),
            "file_size": stat.st_size,
            "modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "modelspace_entity_count": count,
            "sha256": before,
            "hash_after": after,
            "hash_unchanged": before == after,
            "anchors": anchors,
            "target_write": False,
            "target_save": False,
        }
    finally:
        if document is not None:
            _close_document_without_save(document)


def pair_named_anchors(
    reference_anchors: list[dict[str, Any]],
    target_anchors: list[dict[str, Any]],
    anchor_ids: Iterable[str],
) -> dict[str, Any]:
    ref_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tgt_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in reference_anchors:
        ref_groups[item["anchor_id"]].append(item)
    for item in target_anchors:
        tgt_groups[item["anchor_id"]].append(item)
    pairs, errors = [], []
    for anchor_id in anchor_ids:
        refs, tgts = ref_groups[anchor_id], tgt_groups[anchor_id]
        if len(refs) != 1 or len(tgts) != 1:
            errors.append({
                "anchor_id": anchor_id,
                "reference_count": len(refs),
                "target_count": len(tgts),
                "reason": "MISSING_OR_DUPLICATE_ANCHOR",
            })
            continue
        ref, tgt = refs[0], tgts[0]
        rp, tp = ref["effective_anchor_point"], tgt["effective_anchor_point"]
        pairs.append({
            "anchor_id": anchor_id,
            "reference_handle": ref["handle"],
            "target_handle": tgt["handle"],
            "reference_point": rp,
            "target_point": tp,
            "dx": float(tp[0] - rp[0]),
            "dy": float(tp[1] - rp[1]),
            "reference_alignment": ref["alignment_name"],
            "target_alignment": tgt["alignment_name"],
            "status": "VALID",
        })
    return {"pairs": pairs, "errors": errors}


def region_precheck(
    pairs: list[dict[str, Any]],
    reference_region: dict[str, Any],
    target_region: dict[str, Any],
    expected_semantic_name: str,
) -> dict[str, Any]:
    rows, errors = [], []
    for pair in pairs:
        ref_inside = point_in_bbox(pair["reference_point"], reference_region["frame_bbox"])
        tgt_inside = point_in_bbox(pair["target_point"], target_region["frame_bbox"])
        if not ref_inside or not tgt_inside:
            errors.append({"anchor_id": pair["anchor_id"], "reference_inside": ref_inside, "target_inside": tgt_inside})
        rows.append({
            "anchor_id": pair["anchor_id"],
            "reference_region_id": reference_region["region_id"] if ref_inside else None,
            "target_region_id": target_region["region_id"] if tgt_inside else None,
            "reference_inside": ref_inside,
            "target_inside": tgt_inside,
        })
    semantic_valid = (
        reference_region["selected_semantic_name"] == expected_semantic_name
        and target_region["selected_semantic_name"] == expected_semantic_name
    )
    return {
        "anchors": rows,
        "expected_semantic_name": expected_semantic_name,
        "reference_actual_title_texts": reference_region["all_title_texts"],
        "target_actual_title_texts": target_region["all_title_texts"],
        "semantic_valid": semantic_valid,
        "errors": errors,
        "passed": len(pairs) >= 2 and not errors and semantic_valid,
    }


def manual_translation_metrics(pairs: list[dict[str, Any]], region_bbox: list[float]) -> dict[str, Any]:
    dx = float(np.median([item["dx"] for item in pairs]))
    dy = float(np.median([item["dy"] for item in pairs]))
    residuals = [math.hypot(item["dx"] - dx, item["dy"] - dy) for item in pairs]
    xs = [item["reference_point"][0] for item in pairs]
    ys = [item["reference_point"][1] for item in pairs]
    cx = (region_bbox[0] + region_bbox[2]) / 2
    cy = (region_bbox[1] + region_bbox[3]) / 2
    cells = {(int(x >= cx), int(y >= cy)) for x, y in zip(xs, ys)}
    rows = []
    for item, residual in zip(pairs, residuals):
        rows.append({**item, "residual_to_group_median": round(residual, 9)})
    return {
        "pairs": rows,
        "manual_translation": {"x": dx, "y": dy},
        "manual_anchor_count": len(pairs),
        "manual_anchor_rms": round(math.sqrt(sum(value * value for value in residuals) / max(len(residuals), 1)), 9),
        "manual_anchor_max_error": round(max(residuals, default=float("inf")), 9),
        "reference_x_span": max(xs, default=0.0) - min(xs, default=0.0),
        "reference_y_span": max(ys, default=0.0) - min(ys, default=0.0),
        "spatial_cell_count": len(cells),
        "spatially_distributed": len(cells) >= 2 and (max(xs, default=0.0) - min(xs, default=0.0)) > 1000 and (max(ys, default=0.0) - min(ys, default=0.0)) > 1000,
    }


def score_candidate_clusters(
    manual: dict[str, Any],
    clusters: list[dict[str, Any]],
) -> dict[str, Any]:
    pairs = manual["pairs"]
    candidates = [
        {
            "cluster_id": f"historical_cluster_{index + 1}",
            "translation_x": item["dx_median"],
            "translation_y": item["dy_median"],
            "historical_cluster_ratio": item["ratio"],
        }
        for index, item in enumerate(clusters)
    ]
    manual_candidate = {
        "cluster_id": "manual_anchor_median",
        "translation_x": manual["manual_translation"]["x"],
        "translation_y": manual["manual_translation"]["y"],
        "historical_cluster_ratio": None,
    }
    if not any(math.hypot(item["translation_x"] - manual_candidate["translation_x"], item["translation_y"] - manual_candidate["translation_y"]) <= CAD_TOLERANCE for item in candidates):
        candidates.append(manual_candidate)
    scored = []
    for item in candidates:
        residuals = [math.hypot(pair["dx"] - item["translation_x"], pair["dy"] - item["translation_y"]) for pair in pairs]
        scored.append({
            **item,
            "manual_anchor_rms": math.sqrt(sum(value * value for value in residuals) / max(len(residuals), 1)),
            "manual_anchor_max_error": max(residuals, default=float("inf")),
        })
    scored.sort(key=lambda item: (item["manual_anchor_rms"], item["manual_anchor_max_error"]))
    selected = scored[0]
    runner_up = scored[1] if len(scored) > 1 else None
    separation = (runner_up["manual_anchor_rms"] - selected["manual_anchor_rms"]) if runner_up else float("inf")
    return {
        "candidates": scored,
        "selected_translation": {"x": selected["translation_x"], "y": selected["translation_y"]},
        "runner_up_translation": {"x": runner_up["translation_x"], "y": runner_up["translation_y"]} if runner_up else None,
        "manual_anchor_rms": selected["manual_anchor_rms"],
        "manual_anchor_max_error": selected["manual_anchor_max_error"],
        "runner_up_error": runner_up["manual_anchor_rms"] if runner_up else None,
        "cluster_separation_margin": separation,
        "competing_cluster_remaining": bool(runner_up and separation <= CAD_TOLERANCE),
    }


def _load_fingerprints(path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            item = json.loads(line)
            result[(item["role"], item["region_id"])].append(item)
    return result


def evaluate_group(
    config: dict[str, Any],
    pairs: list[dict[str, Any]],
    precheck: dict[str, Any],
    cluster_record: dict[str, Any],
    fingerprints: dict[tuple[str, str], list[dict[str, Any]]],
    fingerprint_matches: dict[str, Any],
    structures: dict[str, dict[str, Any]],
    protected_bboxes: list[list[float]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ref_id, tgt_id = config["reference_region_id"], config["target_region_id"]
    manual = manual_translation_metrics(pairs, structures[ref_id]["region_bbox"])
    scores = score_candidate_clusters(manual, cluster_record["clusters"])
    selected = scores["selected_translation"]
    match_group = next(item for item in fingerprint_matches["pairs"] if item["pair_id"] == config["cluster_pair_id"])
    used_ids = {item["reference"]["fingerprint_id"] for item in match_group["matches"]}
    ref_cross = cross_frame_audit(fingerprints[("reference", ref_id)], structures[ref_id]["region_bbox"])
    tgt_cross = cross_frame_audit(fingerprints[("target", tgt_id)], structures[tgt_id]["region_bbox"])
    holdout = holdout_validation(
        fingerprints[("reference", ref_id)],
        fingerprints[("target", tgt_id)],
        used_ids,
        selected["x"], selected["y"],
        ref_cross["clipped_building_bbox"],
        tgt_cross["clipped_building_bbox"],
    )
    transformed_bbox = holdout["transformed_clipped_bbox"]
    protected_intersection = sum(_bbox_intersects(transformed_bbox, bbox) for bbox in protected_bboxes)
    core_supported = holdout["core_geometry_overlap"] >= 0.5
    passed = (
        precheck["passed"]
        and manual["manual_anchor_count"] >= 2
        and manual["spatially_distributed"]
        and scores["manual_anchor_max_error"] <= CAD_TOLERANCE
        and scores["cluster_separation_margin"] > CAD_TOLERANCE
        and holdout["holdout_match_ratio"] >= 0.90
        and holdout["holdout_rms"] is not None
        and holdout["holdout_rms"] <= CAD_TOLERANCE
        and holdout["clipped_bbox_overlap_ratio"] >= 0.70
        and protected_intersection == 0
    )
    validation = {
        "semantic_key": next(key for key, value in GROUPS.items() if value is config),
        "semantic_name": config["semantic_name"],
        "reference_region_id": ref_id,
        "target_region_id": tgt_id,
        **manual,
        **scores,
        "holdout_total": holdout["holdout_total_count"],
        "holdout_match_count": holdout["holdout_match_count"],
        "holdout_match_ratio": holdout["holdout_match_ratio"],
        "holdout_rms": holdout["holdout_rms"],
        "transformed_building_bbox": transformed_bbox,
        "target_building_bbox": tgt_cross["clipped_building_bbox"],
        "bbox_overlap_ratio": holdout["clipped_bbox_overlap_ratio"],
        "transformed_bbox_inside_target": holdout["transformed_clipped_bbox_inside_target"],
        "core_geometry_supported": core_supported,
        "protected_region_intersection": protected_intersection,
        "final_status": "VERIFIED_BY_MANUAL_ANCHORS_AFTER_SEMANTIC_REINDEX" if passed else "ALIGNMENT_STILL_BLOCKED",
    }
    return validation, scores


def _final_manifest_records(run_dir: Path, validations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    p26 = run_dir / "region_semantic_reindexing"
    basement = _read(p26 / "basement_revalidation.json")
    floors = _read(p26 / "floors_6_16_revalidation.json")
    others = {item["semantic_key"]: item for item in _read(p26 / "other_regions_revalidation.json")["regions"]}
    sources = {
        "basement": basement,
        "first_floor": others["first_floor"],
        "floors_6_to_16": floors,
        "floor_19_and_roof": validations["floor_19_and_roof"],
        "water_tank_and_tank_roof": validations["water_tank_and_tank_roof"],
        "domestic_water_and_drainage_system": others["domestic_water_and_drainage_system"],
        "fire_hydrant_and_sprinkler_system": others["fire_hydrant_and_sprinkler_system"],
    }
    mapping = {item["semantic_key"]: item for item in _read(p26 / "corrected_semantic_mapping.json")["mappings"]}
    retry_results = {
        item["pair_id"]: item
        for item in _read(run_dir / "block_xref_audit" / "retry_alignment_results.json")["results"]
    }
    records = []
    for key in (
        "basement", "first_floor", "floors_6_to_16", "floor_19_and_roof",
        "water_tank_and_tank_roof", "domestic_water_and_drainage_system",
        "fire_hydrant_and_sprinkler_system",
    ):
        source, bound = sources[key], mapping[key]
        transform = source.get("selected_translation", source.get("translation", source.get("existing_transform", {})))
        retry = retry_results.get(key, {})
        records.append({
            "semantic_key": key,
            "semantic_name": bound["semantic_name"],
            "reference_region_id": bound["reference_region_id"],
            "target_region_id": bound["target_region_id"],
            "translation_x": transform.get("x", transform.get("translation_x")),
            "translation_y": transform.get("y", transform.get("translation_y")),
            "transform_type": "translation_only",
            "scale": 1.0,
            "rotation": 0.0,
            "verification_method": source["final_status"],
            "anchor_count": source.get(
                "manual_anchor_count",
                source.get("holdout_match_count", retry.get("inlier_count")),
            ),
            "holdout_match_ratio": source.get("holdout_match_ratio"),
            "holdout_rms": source.get("holdout_rms"),
            "bbox_valid": source.get("transformed_bbox_inside_target", source.get("bbox_validation")),
            "bbox_overlap_ratio": source.get("bbox_overlap_ratio"),
            "protected_region_intersection": source.get("protected_region_intersection", 0),
            "final_status": source["final_status"],
        })
    return records


def run_remaining_disambiguation(
    run_dir: Path,
    reference_scan: dict[str, Any],
    target_scan: dict[str, Any],
) -> dict[str, Any]:
    out = run_dir / "remaining_region_manual_disambiguation"
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "anchor_scan.json", {"reference": reference_scan, "target": target_scan})

    p26 = run_dir / "region_semantic_reindexing"
    ref_regions = {item["region_id"]: item for item in _read(p26 / "reference_region_semantics.json")["regions"]}
    tgt_regions = {item["region_id"]: item for item in _read(p26 / "target_region_semantics.json")["regions"]}
    cluster_by = {item["pair_id"]: item for item in _read(run_dir / "alignment_evidence_adjudication" / "translation_cluster_analysis.json")["pairs"]}
    fingerprint_matches = _read(run_dir / "block_xref_audit" / "fingerprint_matches.json")
    fingerprints = _load_fingerprints(run_dir / "block_xref_audit" / "local_geometry_fingerprints.jsonl")
    structures: dict[str, dict[str, Any]] = {}
    for role in ("reference", "target"):
        for item in _read(run_dir / "block_xref_audit" / f"{role}_region_structure.json")["regions"]:
            structures[item["region_id"]] = item
    protected_bboxes = [item["frame_bbox"] for item in _read(run_dir / "protected_regions.json")["regions"]]

    all_prechecks, all_pairs, all_scores, validations = {}, {}, {}, {}
    for key, config in GROUPS.items():
        paired = pair_named_anchors(reference_scan["anchors"], target_scan["anchors"], config["anchor_ids"])
        precheck = region_precheck(
            paired["pairs"], ref_regions[config["reference_region_id"]], tgt_regions[config["target_region_id"]], config["semantic_name"]
        )
        precheck["pair_errors"] = paired["errors"]
        if paired["errors"]:
            precheck["passed"] = False
        all_prechecks[key], all_pairs[key] = precheck, paired
        if precheck["passed"]:
            validation, scores = evaluate_group(
                config, paired["pairs"], precheck, cluster_by[config["cluster_pair_id"]], fingerprints,
                fingerprint_matches, structures, protected_bboxes,
            )
        else:
            validation = {
                "semantic_key": key,
                "semantic_name": config["semantic_name"],
                "reference_region_id": config["reference_region_id"],
                "target_region_id": config["target_region_id"],
                "final_status": "ANCHOR_PLACEMENT_WRONG" if paired["pairs"] else "MANUAL_ANCHOR_MISSING_OR_DUPLICATE",
            }
            scores = {"candidates": []}
        validations[key], all_scores[key] = validation, scores

    _write(out / "anchor_region_precheck.json", {"groups": all_prechecks})
    _write(out / "manual_anchor_pairs.json", {"groups": all_pairs})
    _write(out / "candidate_cluster_scores.json", {"groups": all_scores})
    _write(out / "floor19_roof_validation.json", validations["floor_19_and_roof"])
    _write(out / "water_tank_validation.json", validations["water_tank_and_tank_roof"])

    passed = [key for key, value in validations.items() if value["final_status"].startswith("VERIFIED")]
    if len(passed) == 2:
        status = "REMAINING_REGION_DISAMBIGUATION_COMPLETE"
    elif len(passed) == 1:
        status = "REMAINING_REGION_DISAMBIGUATION_PARTIAL"
    else:
        status = "REMAINING_REGION_DISAMBIGUATION_BLOCKED"
    final_manifest_created = False
    if len(passed) == 2:
        records = _final_manifest_records(run_dir, validations)
        final_dir = run_dir / "alignment_repair"
        _write(final_dir / "final_verified_coordinate_transforms.json", {
            "phase": "STAGE6-P2.7",
            "status": "ALL_SEVEN_COORDINATE_TRANSFORMS_VERIFIED",
            "count": 7,
            "transforms": records,
            "target_write": False,
            "target_save": False,
            "missing_detection_executed": False,
            "frozen_plan_created": False,
        })
        lines = ["# 七组最终坐标变换", "", "| 语义 | Reference | Target | Translation | 验证状态 |", "|---|---|---|---|---|"]
        for item in records:
            lines.append(f"| {item['semantic_name']} | {item['reference_region_id']} | {item['target_region_id']} | ({item['translation_x']}, {item['translation_y']}) | {item['final_status']} |")
        (final_dir / "final_verified_coordinate_transforms.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        final_manifest_created = True

    hashes_unchanged = reference_scan["hash_unchanged"] and target_scan["hash_unchanged"]
    if not hashes_unchanged:
        status = "REMAINING_REGION_DISAMBIGUATION_BLOCKED"
    report_lines = [
        "# Stage 6-P2.7 剩余区域人工裁决",
        "",
        f"- 最终状态：`{status}`",
        f"- 七组最终清单：`{str(final_manifest_created).lower()}`",
        "- DWG 写入/保存：`false/false`",
        "- 未进入 missing detection，未生成 frozen plan。",
        "",
        "| 区域 | 人工平移 | Hold-out | BBox overlap | 状态 |",
        "|---|---|---:|---:|---|",
    ]
    for key in ("floor_19_and_roof", "water_tank_and_tank_roof"):
        item = validations[key]
        report_lines.append(
            f"| {item['semantic_name']} | {item.get('selected_translation')} | {item.get('holdout_match_ratio')} | {item.get('bbox_overlap_ratio')} | {item['final_status']} |"
        )
    (out / "remaining_region_manual_disambiguation_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return {
        "phase": "STAGE6-P2.7",
        "status": status,
        "verified_group_count": len(passed),
        "final_manifest_created": final_manifest_created,
        "reference_hash_unchanged": reference_scan["hash_unchanged"],
        "target_hash_unchanged": target_scan["hash_unchanged"],
        "target_write": False,
        "target_save": False,
        "missing_detection_executed": False,
        "frozen_plan_created": False,
    }
