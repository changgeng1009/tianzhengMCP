from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from mcp.acceptance import stage3_1_r1_analysis as r1


ROOT = Path(__file__).resolve().parents[2]
R1_REPORT = ROOT / "reports" / "stage3_1_r1_target_scan_alignment.json"
R1_RUN_ROOT = ROOT / "artifacts" / "stage3_1_r1" / "stage3_1_r1_20260711_002112"
REPORT_JSON = ROOT / "reports" / "stage3_1_r2_geometry_acceptance.json"
REPORT_MD = ROOT / "reports" / "stage3_1_r2_geometry_acceptance.md"

PASS_STATUS = "PASS_TRANSLATION_GEOMETRY_DOMINANT"
ABSOLUTE_RESIDUAL_RATIO = 0.005
NORMALIZED_RESIDUAL_THRESHOLD = 0.005
MIN_INDEPENDENT_ANCHORS = 12
MIN_ANCHOR_TYPES = 3


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _top_level_handle(handle: str) -> str:
    return str(handle).split(":", 1)[0]


def _point_key(point: Sequence[float], precision: int = 6) -> tuple[float, float]:
    return round(float(point[0]), precision), round(float(point[1]), precision)


def _pair_key(anchor: Mapping[str, Any]) -> tuple[tuple[float, float], tuple[float, float]]:
    return _point_key(anchor["reference_point"]), _point_key(anchor["target_point"])


def _is_forbidden_anchor(anchor: Mapping[str, Any]) -> str | None:
    text = " ".join(
        str(value)
        for value in (
            anchor.get("anchor_id"),
            anchor.get("anchor_type"),
            anchor.get("layer"),
            anchor.get("source"),
            anchor.get("description"),
        )
        if value is not None
    ).lower()
    if any(token in text for token in ("title", "frame", "图框", "图签", "twt_title")):
        return "title_or_frame_anchor"
    if "seed" in text and ("stage1" in text or "stage_1" in text or "stage 1" in text):
        return "stage1_seed_line"
    return None


def audit_anchor_independence(
    anchors: Sequence[Mapping[str, Any]],
    region_bbox: Sequence[float],
    *,
    grid_size: int = 2,
) -> dict[str, Any]:
    excluded: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for raw in anchors:
        anchor = dict(raw)
        reason = _is_forbidden_anchor(anchor)
        if reason:
            excluded.append({"anchor_id": anchor.get("anchor_id"), "reason": reason})
        else:
            eligible.append(anchor)

    deduplicated: list[dict[str, Any]] = []
    duplicate_groups: list[dict[str, Any]] = []
    by_pair: dict[tuple[tuple[float, float], tuple[float, float]], list[dict[str, Any]]] = defaultdict(list)
    for anchor in eligible:
        by_pair[_pair_key(anchor)].append(anchor)
    for group in by_pair.values():
        group = sorted(group, key=lambda item: str(item.get("anchor_id")))
        deduplicated.append(group[0])
        if len(group) > 1:
            duplicate_groups.append({
                "kind": "identical_coordinate_pair",
                "anchor_ids": [item.get("anchor_id") for item in group],
                "retained_anchor_id": group[0].get("anchor_id"),
            })

    # Corner anchors share source line entities with accepted line-midpoint anchors.
    # They are useful corroboration, but are not counted again as independent evidence.
    primary_handles = {
        handle
        for anchor in deduplicated
        if anchor.get("anchor_type") != "wall_corner"
        for handle in anchor.get("reference_handles", [])
    }
    independent: list[dict[str, Any]] = []
    correlated_groups: list[dict[str, Any]] = list(duplicate_groups)
    correlated_corners: list[dict[str, Any]] = []
    for anchor in deduplicated:
        handles = set(map(str, anchor.get("reference_handles", [])))
        if anchor.get("anchor_type") == "wall_corner" and handles & primary_handles:
            correlated_corners.append(anchor)
            continue
        independent.append(anchor)
    if correlated_corners:
        correlated_groups.append({
            "kind": "derived_corner_shares_line_entity",
            "anchor_ids": [item.get("anchor_id") for item in correlated_corners],
            "shared_reference_handles": sorted({
                handle
                for item in correlated_corners
                for handle in item.get("reference_handles", [])
                if handle in primary_handles
            }),
            "retained_anchor_id": None,
        })

    spatial = compute_spatial_coverage(independent, region_bbox, grid_size=grid_size)
    reference_pairs = [tuple(map(str, item.get("reference_handles", []))) for item in independent]
    target_pairs = [tuple(map(str, item.get("target_handles", []))) for item in independent]
    top_blocks = sorted({
        _top_level_handle(handle)
        for item in independent
        for handle in item.get("reference_handles", [])
        if handle
    })
    target_top_blocks = sorted({
        _top_level_handle(handle)
        for item in independent
        for handle in item.get("target_handles", [])
        if handle
    })
    exclusion_counts = Counter(item["reason"] for item in excluded)
    if correlated_corners:
        exclusion_counts["derived_corner_shares_line_entity"] += len(correlated_corners)
    if duplicate_groups:
        exclusion_counts["identical_coordinate_pair"] += sum(len(item["anchor_ids"]) - 1 for item in duplicate_groups)

    return {
        "raw_anchor_count": len(anchors),
        "deduplicated_anchor_count": len(deduplicated),
        "independent_anchor_count": len(independent),
        "anchor_type_counts": dict(Counter(item.get("anchor_type") for item in independent)),
        "raw_anchor_type_counts": dict(Counter(item.get("anchor_type") for item in anchors)),
        "anchor_spatial_cells": spatial["cell_counts"],
        "duplicated_anchor_count": len(eligible) - len(deduplicated),
        "correlated_anchor_groups": correlated_groups,
        "correlated_anchor_count": len(correlated_corners),
        "excluded_anchor_count": len(excluded) + len(correlated_corners) + len(eligible) - len(deduplicated),
        "exclusion_reasons": dict(exclusion_counts),
        "forbidden_anchor_exclusions": excluded,
        "reference_handle_pairing_unique": len(reference_pairs) == len(set(reference_pairs)),
        "target_handle_pairing_unique": len(target_pairs) == len(set(target_pairs)),
        "reference_top_level_block_handles": top_blocks,
        "target_top_level_block_handles": target_top_blocks,
        "all_from_one_block_reference": len(top_blocks) == 1 and len(target_top_blocks) == 1,
        "independent_anchors": independent,
        "spatial_coverage": spatial,
    }


def compute_spatial_coverage(
    anchors: Sequence[Mapping[str, Any]],
    bbox: Sequence[float],
    *,
    grid_size: int = 2,
) -> dict[str, Any]:
    if grid_size < 2:
        raise ValueError("grid_size must create at least four cells")
    xmin, ymin, xmax, ymax = map(float, bbox[:4])
    width, height = xmax - xmin, ymax - ymin
    if width <= 0 or height <= 0:
        raise ValueError("region bbox must have positive area")
    counts: Counter[str] = Counter()
    for anchor in anchors:
        x, y = map(float, anchor["reference_point"][:2])
        column = min(grid_size - 1, max(0, int((x - xmin) / width * grid_size)))
        row = min(grid_size - 1, max(0, int((y - ymin) / height * grid_size)))
        counts[f"r{row}c{column}"] += 1
    total_cells = grid_size * grid_size
    occupied = len(counts)
    maximum_ratio = max(counts.values(), default=0) / max(len(anchors), 1)
    coverage_ratio = occupied / total_cells
    return {
        "grid": f"{grid_size}x{grid_size}",
        "occupied_spatial_cells": occupied,
        "total_spatial_cells": total_cells,
        "spatial_coverage_ratio": round(coverage_ratio, 6),
        "maximum_anchor_cluster_ratio": round(maximum_ratio, 6),
        "cell_counts": dict(sorted(counts.items())),
        "passed": occupied >= 3 and coverage_ratio >= 0.60 and maximum_ratio <= 0.70,
    }


def _fit_translation(anchors: Sequence[Mapping[str, Any]]) -> list[float]:
    return [
        median(float(item["target_point"][axis]) - float(item["reference_point"][axis]) for item in anchors)
        for axis in (0, 1)
    ]


def _holdout_record(
    name: str,
    training: Sequence[Mapping[str, Any]],
    validation: Sequence[Mapping[str, Any]],
    selected_translation: Sequence[float],
    region_diagonal: float,
) -> dict[str, Any]:
    if not training or not validation:
        return {
            "name": name,
            "available": False,
            "training_anchor_count": len(training),
            "validation_anchor_count": len(validation),
            "passed": False,
            "reason": "empty training or validation group",
        }
    fitted = _fit_translation(training)
    residuals = [
        math.dist(
            [float(item["reference_point"][0]) + fitted[0], float(item["reference_point"][1]) + fitted[1]],
            list(map(float, item["target_point"][:2])),
        )
        for item in validation
    ]
    median_residual = median(residuals)
    max_residual = max(residuals)
    normalized_max = max_residual / max(region_diagonal, 1e-9)
    deviation = math.dist(list(map(float, fitted)), list(map(float, selected_translation[:2])))
    absolute_threshold = region_diagonal * ABSOLUTE_RESIDUAL_RATIO
    passed = max_residual <= absolute_threshold and normalized_max <= NORMALIZED_RESIDUAL_THRESHOLD and deviation <= absolute_threshold
    return {
        "name": name,
        "available": True,
        "training_anchor_count": len(training),
        "validation_anchor_count": len(validation),
        "fitted_translation": fitted,
        "validation_median_residual": median_residual,
        "validation_max_residual": max_residual,
        "normalized_validation_max_residual": normalized_max,
        "translation_deviation_from_selected": deviation,
        "absolute_residual_threshold": absolute_threshold,
        "normalized_residual_threshold": NORMALIZED_RESIDUAL_THRESHOLD,
        "passed": passed,
    }


def deterministic_holdouts(
    anchors: Sequence[Mapping[str, Any]],
    selected_translation: Sequence[float],
    region_diagonal: float,
    region_bbox: Sequence[float] | None = None,
) -> dict[str, Any]:
    ordered = sorted(anchors, key=lambda item: str(item.get("anchor_id")))
    grouped_results = []
    patterns = (
        ("split_mod5_01", {0, 1}),
        ("split_mod5_13", {1, 3}),
        ("split_mod5_24", {2, 4}),
    )
    for name, held_mods in patterns:
        validation = [item for index, item in enumerate(ordered) if index % 5 in held_mods]
        training = [item for index, item in enumerate(ordered) if index % 5 not in held_mods]
        grouped_results.append(_holdout_record(name, training, validation, selected_translation, region_diagonal))

    type_results = []
    for anchor_type in sorted({str(item.get("anchor_type")) for item in ordered}):
        validation = [item for item in ordered if item.get("anchor_type") == anchor_type]
        training = [item for item in ordered if item.get("anchor_type") != anchor_type]
        type_results.append(_holdout_record(f"leave_type:{anchor_type}", training, validation, selected_translation, region_diagonal))

    cell_results = []
    if region_bbox:
        by_cell = _anchors_by_cell(ordered, region_bbox)
        for cell in sorted(by_cell):
            validation = by_cell[cell]
            validation_ids = {id(item) for item in validation}
            training = [item for item in ordered if id(item) not in validation_ids]
            cell_results.append(_holdout_record(f"leave_cell:{cell}", training, validation, selected_translation, region_diagonal))

    valid_results = [item for item in grouped_results + type_results + cell_results if item.get("available")]
    return {
        "deterministic_split_results": grouped_results,
        "leave_one_type_out_results": type_results,
        "leave_one_spatial_cell_out_results": cell_results,
        "all_valid_holdouts_passed": bool(valid_results) and all(item["passed"] for item in valid_results),
        "valid_holdout_count": len(valid_results),
    }


def _anchors_by_cell(
    anchors: Sequence[Mapping[str, Any]],
    bbox: Sequence[float],
) -> dict[str, list[Mapping[str, Any]]]:
    xmin, ymin, xmax, ymax = map(float, bbox[:4])
    xmid = (xmin + xmax) / 2
    ymid = (ymin + ymax) / 2
    result: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in anchors:
        x, y = map(float, item["reference_point"][:2])
        result[f"r{int(y >= ymid)}c{int(x >= xmid)}"].append(item)
    return dict(result)


def directional_geometry_overlap(
    reference_features: Sequence[Mapping[str, Any]],
    target_features: Sequence[Mapping[str, Any]],
    matrix: Sequence[Sequence[float]],
    region_diagonal: float,
) -> dict[str, Any]:
    matrix_array = np.asarray(matrix, dtype=float)
    threshold = region_diagonal * ABSOLUTE_RESIDUAL_RATIO
    pairs: list[tuple[float, float, int, int]] = []
    for reference_index, reference in enumerate(reference_features):
        transformed = r1._apply_matrix(matrix_array, reference["point"])
        for target_index, target in enumerate(target_features):
            similarity = r1._feature_similarity(reference, target)
            distance = math.dist(transformed, target["point"])
            if similarity >= 0.80 and distance <= threshold:
                pairs.append((distance, -similarity, reference_index, target_index))
    pairs.sort()
    used_reference: set[int] = set()
    used_target: set[int] = set()
    matched: list[tuple[int, int, float, float]] = []
    for distance, negative_similarity, reference_index, target_index in pairs:
        if reference_index in used_reference or target_index in used_target:
            continue
        used_reference.add(reference_index)
        used_target.add(target_index)
        matched.append((reference_index, target_index, distance, -negative_similarity))

    matched_reference_counts = Counter(reference_features[i]["feature_type"] for i, _, _, _ in matched)
    matched_target_counts = Counter(target_features[j]["feature_type"] for _, j, _, _ in matched)
    reference_counts = Counter(item["feature_type"] for item in reference_features)
    target_counts = Counter(item["feature_type"] for item in target_features)
    type_ratios = {
        feature_type: round(matched_target_counts[feature_type] / max(target_counts[feature_type], 1), 6)
        for feature_type in sorted(target_counts)
    }
    long_line_pairs = [pair for pair in matched if target_features[pair[1]]["feature_type"] == "long_line_midpoint"]
    orientation_scores = [
        r1._orientation_similarity(reference_features[i]["signature"], target_features[j]["signature"])
        for i, j, _, _ in long_line_pairs
    ]
    length_scores = [
        r1._ratio_score(reference_features[i]["signature"].get("length"), target_features[j]["signature"].get("length"))
        for i, j, _, _ in long_line_pairs
    ]
    target_ratio = len(used_target) / max(len(target_features), 1)
    reference_ratio = len(used_reference) / max(len(reference_features), 1)
    orientation = sum(orientation_scores) / max(len(orientation_scores), 1)
    length = sum(length_scores) / max(len(length_scores), 1)
    directional_score = 0.70 * target_ratio + 0.15 * orientation + 0.15 * length
    return {
        "matching_method": "greedy_one_to_one_same_type_signature_ge_0.80_and_distance_within_stage3_1_threshold",
        "absolute_match_threshold": threshold,
        "matched_feature_count": len(matched),
        "reference_feature_count": len(reference_features),
        "target_feature_count": len(target_features),
        "target_to_reference_overlap": round(target_ratio, 6),
        "reference_to_target_overlap": round(reference_ratio, 6),
        "target_geometry_explained_by_reference_ratio": round(target_ratio, 6),
        "target_feature_counts": dict(target_counts),
        "reference_feature_counts": dict(reference_counts),
        "matched_target_feature_counts": dict(matched_target_counts),
        "matched_reference_feature_counts": dict(matched_reference_counts),
        "target_long_lines_explained_ratio": type_ratios.get("long_line_midpoint"),
        "target_wall_corners_explained_ratio": type_ratios.get("wall_corner"),
        "target_rectangle_centers_explained_ratio": type_ratios.get("rectangle_center"),
        "target_block_insertions_explained_ratio": type_ratios.get("unique_block_insertion"),
        "target_feature_type_explained_ratios": type_ratios,
        "orientation_agreement": round(orientation, 6),
        "line_length_agreement": round(length, 6),
        "directional_overlap_score": round(directional_score, 6),
        "maximum_match_residual": max((pair[2] for pair in matched), default=None),
        "passed": target_ratio >= 0.80 and orientation >= 0.90 and length >= 0.80,
    }


def decide_geometry_acceptance(
    *,
    target_scan_status: str,
    region_correspondence_confirmed: bool,
    local_bbox_overlap: float,
    anchor_audit: Mapping[str, Any],
    holdouts: Mapping[str, Any],
    overlap: Mapping[str, Any],
    transform: Mapping[str, Any],
    confidence: float,
    hashes_intact: bool,
    safety_passed: bool,
    text_anchor_absence_expected: bool,
    repair_task_generated: bool,
    text_anchor_count: int = 0,
) -> tuple[str, bool, list[str]]:
    blockers: list[str] = []
    if target_scan_status != "TARGET_SCAN_CONFIRMED_BLOCK_CONTAINED":
        blockers.append("target scan not confirmed block-contained")
    if not region_correspondence_confirmed or local_bbox_overlap < 0.95:
        blockers.append("pump-room region correspondence or bbox overlap insufficient")
    if int(anchor_audit.get("independent_anchor_count", 0)) < MIN_INDEPENDENT_ANCHORS:
        blockers.append("fewer than 12 independent non-text anchors")
    if len(anchor_audit.get("anchor_type_counts", {})) < MIN_ANCHOR_TYPES:
        blockers.append("fewer than three independent anchor types")
    if not anchor_audit.get("spatial_coverage", {}).get("passed"):
        blockers.append("independent-anchor spatial coverage failed")
    if anchor_audit.get("all_from_one_block_reference"):
        blockers.append("all independent anchors originate from one top-level BlockReference pair")
    if anchor_audit.get("forbidden_anchor_exclusions"):
        blockers.append("forbidden title/frame/seed evidence remained in accepted anchors")
    if not holdouts.get("all_valid_holdouts_passed"):
        blockers.append("holdout validation unstable")
    if not overlap.get("passed"):
        blockers.append("directional target-to-reference overlap insufficient")
    parameters = transform.get("transform_parameters") or {}
    if transform.get("transform_type") != "translation" or abs(float(parameters.get("rotation_radians", 1))) > 1e-9 or abs(float(parameters.get("scale", 0)) - 1) > 1e-9:
        blockers.append("translation-only rotation/scale model not supported")
    if confidence < 0.72:
        blockers.append("alignment confidence below 0.72")
    if not hashes_intact or not safety_passed:
        blockers.append("hash or safety integrity failed")
    if repair_task_generated:
        blockers.append("repair task generated")
    if text_anchor_count == 0 and not text_anchor_absence_expected:
        blockers.append("text-anchor absence is not explained")

    if not blockers:
        status = "PASS_TRANSLATION_MIXED_EVIDENCE" if text_anchor_count > 0 else PASS_STATUS
        return status, True, []
    if any("holdout" in item for item in blockers):
        return "PARTIAL_HOLDOUT_UNSTABLE", False, blockers
    if any("directional" in item for item in blockers):
        return "PARTIAL_DIRECTIONAL_OVERLAP_INSUFFICIENT", False, blockers
    if any("anchor" in item or "BlockReference" in item for item in blockers):
        return "PARTIAL_GEOMETRY_EVIDENCE_CORRELATED", False, blockers
    return "BLOCKED_ARTIFACTS_INSUFFICIENT", False, blockers


def _safety_flags() -> dict[str, bool]:
    return {
        "autocad_connected": False,
        "dwg_opened": False,
        "dwg_rescanned": False,
        "safe_copy_created": False,
        "dwg_saved": False,
        "entities_created": False,
        "entities_modified": False,
        "entities_deleted": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "repair_task_generated": False,
        "stage3_2_executed": False,
        "production_d1_allowed": False,
    }


def _text_absence_expected(r1_report: Mapping[str, Any], text_classification: Mapping[str, Any]) -> tuple[bool, list[str]]:
    records = text_classification.get("records", [])
    accepted = int(r1_report.get("accepted_text_anchor_count", 0))
    scan_confirmed = r1_report.get("target_scan_status") == "TARGET_SCAN_CONFIRMED_BLOCK_CONTAINED"
    reasons = [
        "reference title and target title differ",
        "target drawing is incomplete and lacks professional annotations",
        "low-information 栓泵/喷泵 labels were excluded from safe pairing",
        "title-block text was excluded from primary evidence",
    ]
    unique_titles = {item.get("normalized_text") for item in records if item.get("category") in {"globally_unique_text", "region_unique_text"}}
    expected = accepted == 0 and scan_confirmed and len(unique_titles) >= 2
    return expected, reasons


def run_stage3_1_r2(
    *,
    r1_report_path: Path = R1_REPORT,
    run_root: Path = R1_RUN_ROOT,
    report_json_path: Path = REPORT_JSON,
    report_md_path: Path = REPORT_MD,
    test_results: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    required = [
        r1_report_path,
        run_root / "non_text_anchor_candidates.json",
        run_root / "translation_delta_clusters.json",
        run_root / "transform_candidates.json",
        run_root / "geometry_overlap_validation.json",
        run_root / "confidence_breakdown.json",
        run_root / "selected_transform.json",
        run_root / "reference_scan.json",
        run_root / "target_scan.json",
        run_root / "reference_region.json",
        run_root / "target_region.json",
        run_root / "reference_block_audit.json",
        run_root / "target_block_audit.json",
        run_root / "text_anchor_classification.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        report = {
            "phase": "STAGE3.1-R2-GEOMETRY-ONLY-ALIGNMENT-ACCEPTANCE",
            "previous_status": None,
            "acceptance_rule_changed": True,
            "evidence_mode": "UNAVAILABLE",
            "final_status": "BLOCKED_ARTIFACTS_INSUFFICIENT",
            "stage3_2_allowed": False,
            "missing_artifacts": missing,
            "repair_task_generated": False,
            "stage3_2_executed": False,
            "production_d1_allowed": False,
            "safety_flags": _safety_flags(),
        }
        write_json(report_json_path, report)
        report_md_path.write_text(_render_markdown(report), encoding="utf-8")
        return report

    previous = read_json(r1_report_path)
    anchor_payload = read_json(run_root / "non_text_anchor_candidates.json")
    reference_region = read_json(run_root / "reference_region.json")
    target_region = read_json(run_root / "target_region.json")
    selected_transform_artifact = read_json(run_root / "selected_transform.json")
    selected_transform = (
        selected_transform_artifact.get("selected")
        or selected_transform_artifact.get("best_geometric_candidate")
        or selected_transform_artifact
    )
    text_classification = read_json(run_root / "text_anchor_classification.json")
    anchors = anchor_payload.get("accepted", [])
    anchor_audit = audit_anchor_independence(anchors, reference_region["bbox"], grid_size=2)
    independent = anchor_audit.pop("independent_anchors")
    translation = selected_transform["transform_parameters"]["translation"]
    holdouts = deterministic_holdouts(
        independent,
        translation,
        float(reference_region["diagonal"]),
        reference_region["bbox"],
    )

    reference_scan = read_json(run_root / "reference_scan.json")
    target_scan = read_json(run_root / "target_scan.json")
    reference_audit = read_json(run_root / "reference_block_audit.json")
    target_audit = read_json(run_root / "target_block_audit.json")
    reference_features = r1._non_text_features(r1._region_entities(reference_scan, reference_region, reference_audit))
    target_features = r1._non_text_features(r1._region_entities(target_scan, target_region, target_audit))
    overlap = directional_geometry_overlap(
        reference_features,
        target_features,
        selected_transform["transform_parameters"]["matrix"],
        float(target_region["diagonal"]),
    )
    text_expected, text_reasons = _text_absence_expected(previous, text_classification)
    safety = _safety_flags()
    hashes_intact = bool(previous.get("source_hashes_unchanged") and previous.get("copy_hashes_unchanged") and previous.get("copy_hashes_match_sources"))
    final_status, stage3_2_allowed, blockers = decide_geometry_acceptance(
        target_scan_status=str(previous.get("target_scan_status")),
        region_correspondence_confirmed=reference_region.get("status") == "SELECTED" and target_region.get("status") == "SELECTED",
        local_bbox_overlap=float(previous.get("geometry_overlap_validation", {}).get("local_bbox_overlap", 0.0)),
        anchor_audit=anchor_audit,
        holdouts=holdouts,
        overlap=overlap,
        transform=selected_transform,
        confidence=float(previous.get("alignment_confidence", 0.0)),
        hashes_intact=hashes_intact,
        safety_passed=not any(safety.values()),
        text_anchor_absence_expected=text_expected,
        repair_task_generated=False,
        text_anchor_count=int(previous.get("accepted_text_anchor_count", 0)),
    )
    report = {
        "phase": "STAGE3.1-R2-GEOMETRY-ONLY-ALIGNMENT-ACCEPTANCE",
        "previous_status": previous.get("stage3_1_r1_final_status"),
        "acceptance_rule_changed": True,
        "evidence_mode": "GEOMETRY_DOMINANT",
        "text_anchor_absence_expected": text_expected,
        "text_anchor_absence_reasons": text_reasons,
        "accepted_text_anchor_count": int(previous.get("accepted_text_anchor_count", 0)),
        "raw_anchor_count": anchor_audit["raw_anchor_count"],
        "deduplicated_anchor_count": anchor_audit["deduplicated_anchor_count"],
        "independent_anchor_count": anchor_audit["independent_anchor_count"],
        "anchor_type_counts": anchor_audit["anchor_type_counts"],
        "anchor_independence_audit": anchor_audit,
        "spatial_coverage": anchor_audit["spatial_coverage"],
        "holdout_results": holdouts["deterministic_split_results"],
        "leave_one_type_out_results": holdouts["leave_one_type_out_results"],
        "leave_one_spatial_cell_out_results": holdouts["leave_one_spatial_cell_out_results"],
        "all_holdouts_passed": holdouts["all_valid_holdouts_passed"],
        "directional_overlap": overlap,
        "target_to_reference_overlap": overlap["target_to_reference_overlap"],
        "reference_to_target_overlap": overlap["reference_to_target_overlap"],
        "selected_translation": translation,
        "rotation_radians": selected_transform["transform_parameters"]["rotation_radians"],
        "scale": selected_transform["transform_parameters"]["scale"],
        "residual_statistics": {
            "median": selected_transform.get("median_residual"),
            "mean": selected_transform.get("mean_residual"),
            "p95": selected_transform.get("p95_residual"),
            "max": selected_transform.get("max_residual"),
            "normalized_median": selected_transform.get("normalized_median_residual"),
            "normalized_max": selected_transform.get("normalized_max_residual"),
        },
        "confidence": float(previous.get("alignment_confidence", 0.0)),
        "confidence_threshold": 0.72,
        "hash_integrity_passed": hashes_intact,
        "final_status": final_status,
        "stage3_1_final_status": final_status,
        "stage3_2_allowed": stage3_2_allowed,
        "acceptance_blockers": blockers,
        "repair_task_generated": False,
        "stage3_2_executed": False,
        "production_d1_allowed": False,
        "deepseek_external_environment_reported_available": True,
        "deepseek_codex_subprocess_available": False,
        "deepseek_closure_deferred": True,
        "safety_flags": safety,
        "tests": dict(test_results or {}),
        "input_artifacts": [str(path) for path in required],
    }
    write_json(report_json_path, report)
    report_md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _render_markdown(report: Mapping[str, Any]) -> str:
    if report.get("missing_artifacts"):
        return "\n".join([
            "# Stage 3.1-R2 Geometry-Only Alignment Acceptance",
            "",
            f"- final_status: {report['final_status']}",
            "- stage3_2_allowed: false",
            "- missing_artifacts:",
            *[f"  - {path}" for path in report["missing_artifacts"]],
            "",
        ])
    spatial = report["spatial_coverage"]
    overlap = report["directional_overlap"]
    audit = report["anchor_independence_audit"]
    lines = [
        "# Stage 3.1-R2 Geometry-Only Alignment Acceptance",
        "",
        "## 1. Acceptance Amendment",
        f"- previous_status: {report['previous_status']}",
        "- acceptance_rule_changed: true",
        "- evidence_mode: GEOMETRY_DOMINANT",
        f"- text_anchor_absence_expected: {str(report['text_anchor_absence_expected']).lower()}",
        "",
        "## 2. Anchor Independence",
        f"- raw / deduplicated / independent: {report['raw_anchor_count']} / {report['deduplicated_anchor_count']} / {report['independent_anchor_count']}",
        f"- independent anchor types: {json.dumps(report['anchor_type_counts'], ensure_ascii=False)}",
        f"- all_from_one_block_reference: {str(audit['all_from_one_block_reference']).lower()}",
        f"- exclusion_reasons: {json.dumps(audit['exclusion_reasons'], ensure_ascii=False)}",
        "",
        "## 3. Spatial Coverage",
        f"- occupied / total cells: {spatial['occupied_spatial_cells']} / {spatial['total_spatial_cells']}",
        f"- coverage ratio: {spatial['spatial_coverage_ratio']}",
        f"- maximum cluster ratio: {spatial['maximum_anchor_cluster_ratio']}",
        f"- passed: {str(spatial['passed']).lower()}",
        "",
        "## 4. Independent Validation",
        f"- deterministic holdouts passed: {str(all(item.get('passed') for item in report['holdout_results'])).lower()}",
        f"- leave-one-type-out passed: {str(all(item.get('passed') for item in report['leave_one_type_out_results'])).lower()}",
        f"- leave-one-spatial-cell-out passed: {str(all(item.get('passed') for item in report['leave_one_spatial_cell_out_results'])).lower()}",
        "",
        "## 5. Directional Geometry Overlap",
        f"- target_to_reference_overlap: {overlap['target_to_reference_overlap']}",
        f"- reference_to_target_overlap: {overlap['reference_to_target_overlap']}",
        f"- orientation_agreement: {overlap['orientation_agreement']}",
        f"- line_length_agreement: {overlap['line_length_agreement']}",
        f"- directional_overlap_score: {overlap['directional_overlap_score']}",
        "",
        "## 6. Transform and Decision",
        f"- selected_translation: {report['selected_translation']}",
        f"- rotation_radians: {report['rotation_radians']}",
        f"- scale: {report['scale']}",
        f"- confidence: {report['confidence']} (threshold {report['confidence_threshold']})",
        f"- final_status: {report['final_status']}",
        f"- stage3_2_allowed: {str(report['stage3_2_allowed']).lower()}",
        f"- blockers: {json.dumps(report['acceptance_blockers'], ensure_ascii=False)}",
        "",
        "## 7. Safety",
        *[f"- {key}: {str(value).lower()}" for key, value in report["safety_flags"].items()],
        "",
        "## 8. Tests",
        *[f"- {key}: {value}" for key, value in report.get("tests", {}).items()],
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_stage3_1_r2()
    print(json.dumps({
        "final_status": result["final_status"],
        "stage3_2_allowed": result["stage3_2_allowed"],
        "independent_anchor_count": result.get("independent_anchor_count"),
    }, ensure_ascii=False))
