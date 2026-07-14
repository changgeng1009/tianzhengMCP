from __future__ import annotations

import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

import numpy as np


KNOWN_ORDINARY_TYPES = {
    "AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline",
    "AcDbBlockReference", "AcDbText", "AcDbMText", "AcDbCircle", "AcDbArc",
    "AcDbHatch", "AcDbLeader", "AcDbMLeader", "AcDbViewport", "AcDbPoint",
}
TITLE_LAYER_MARKERS = ("title", "图框", "图签", "twt_title", "图幅")
TITLE_TEXT_MARKERS = (
    "图号", "图幅", "比例", "设计", "审核", "校对", "日期", "工程名称",
    "课程设计", "班级", "学号", "签名", "手签名", "学校",
)
PUMP_TEXT_MARKERS = ("泵房大样", "水泵房大样", "消防泵房大样", "泵房")


def build_object_inventory(scan: Mapping[str, Any]) -> dict[str, Any]:
    model_entities = [item for item in scan.get("entities", []) if item.get("owner_layout") == "Model"]
    paper_entities = [item for item in scan.get("entities", []) if item.get("owner_layout") == "Paper"]
    counts = Counter(str(item.get("object_name") or "UNKNOWN") for item in scan.get("entities", []))
    tdb = Counter(name for name, count in counts.items() for _ in range(count) if name.startswith("TDb"))
    ordinary = Counter(name for name, count in counts.items() for _ in range(count) if _is_known_ordinary(name))
    unknown = Counter(name for name, count in counts.items() for _ in range(count) if not name.startswith("TDb") and not _is_known_ordinary(name))
    scanned_total = len(scan.get("entities", []))
    return {
        "modelspace_count": len(model_entities),
        "paperspace_count": len(paper_entities),
        "scanned_entity_count": scanned_total,
        "object_name_counts": dict(sorted(counts.items())),
        "tdb_object_counts": dict(sorted(tdb.items())),
        "ordinary_object_counts": dict(sorted(ordinary.items())),
        "unknown_object_counts": dict(sorted(unknown.items())),
        "objects_without_bbox": sum(item.get("bbox") is None for item in scan.get("entities", [])),
        "objects_with_read_errors": sum(bool(item.get("read_errors")) for item in scan.get("entities", [])),
        "classification_sum": sum(counts.values()),
        "classification_sum_matches_scan": sum(counts.values()) == scanned_total,
        "tdb_drawing_name_count": counts.get("TDbDrawingName", 0),
        "tdb_equipment_count": sum(count for name, count in counts.items() if name.startswith("TDb") and name != "TDbDrawingName"),
    }


def confirm_target_scan(inventory: Mapping[str, Any], block_audit: Mapping[str, Any]) -> dict[str, Any]:
    if not inventory.get("classification_sum_matches_scan"):
        status = "TARGET_SCAN_INCOMPLETE"
        reason = "ObjectName classification sum does not equal scanned entity count"
    elif int(block_audit.get("proxy_count", 0)) > 0:
        status = "TARGET_SCAN_PARTIAL_PROXY_LIMITED"
        reason = "proxy objects prevent complete semantic inspection"
    elif int(block_audit.get("xref_count", 0)) > 0 and not block_audit.get("virtual_expansion_performed"):
        status = "TARGET_SCAN_PARTIAL_XREF_LIMITED"
        reason = "xref content exists but was not available to read-only virtual inspection"
    elif block_audit.get("virtual_expansion_required") and block_audit.get("virtual_entity_count", 0) > 0:
        status = "TARGET_SCAN_CONFIRMED_BLOCK_CONTAINED"
        reason = "top-level count is accurate and substantial visible content is contained in block definitions"
    elif block_audit.get("virtual_expansion_required") and not block_audit.get("virtual_expansion_performed"):
        status = "TARGET_SCAN_UNDETERMINED"
        reason = "a substantive block requires inspection but its definition could not be read"
    else:
        status = "TARGET_SCAN_CONFIRMED_SPARSE"
        reason = "top-level classification is complete; no proxy/xref/substantive hidden block explains additional content"
    return {
        "status": status,
        "top_level_entity_count": inventory.get("scanned_entity_count"),
        "classification_sum": inventory.get("classification_sum"),
        "classification_sum_matches_scan": inventory.get("classification_sum_matches_scan"),
        "modelspace_count": inventory.get("modelspace_count"),
        "paperspace_count": inventory.get("paperspace_count"),
        "tdb_drawing_name_only": inventory.get("tdb_drawing_name_count") == 1 and inventory.get("tdb_equipment_count") == 0,
        "top_level_count_basically_credible": status not in {"TARGET_SCAN_INCOMPLETE", "TARGET_SCAN_UNDETERMINED"},
        "reason": reason,
        "evidence": {
            "object_name_counts": inventory.get("object_name_counts", {}),
            "block_reference_count": block_audit.get("block_reference_count", 0),
            "block_definition_count": block_audit.get("block_definition_count", 0),
            "xref_count": block_audit.get("xref_count", 0),
            "proxy_count": block_audit.get("proxy_count", 0),
            "nested_block_detected": block_audit.get("nested_block_detected", False),
            "virtual_expansion_required": block_audit.get("virtual_expansion_required", False),
            "virtual_entity_count": block_audit.get("virtual_entity_count", 0),
        },
    }


def select_pump_region(
    scan: Mapping[str, Any],
    block_audit: Mapping[str, Any],
    role: str,
) -> dict[str, Any]:
    entities = list(scan.get("entities", [])) + list(block_audit.get("virtual_entities", []))
    titles = [item for item in entities if _is_pump_title(item)]
    title = max(titles, key=lambda item: _text_height(item), default=None)
    substantive_blocks = [
        item for item in block_audit.get("block_references", [])
        if item.get("substantive_definition") and _bbox2(item.get("bbox"))
    ]
    evidence: list[str] = []
    selected_entities: list[Mapping[str, Any]] = []
    if substantive_blocks:
        block = max(substantive_blocks, key=lambda item: item.get("definition_entity_count", 0))
        bbox = _bbox2(block.get("bbox"))
        assert bbox is not None
        selected_entities = [item for item in entities if _inside_bbox(item, bbox)]
        evidence.extend(["substantive_block_bbox", f"block_handle:{block.get('handle')}"])
    elif title is not None:
        title_point = _center(title)
        usable = [item for item in entities if _center(item) is not None and not _is_title_noise_entity(item)]
        if title_point and usable:
            ordered = sorted(usable, key=lambda item: math.dist(title_point, _center(item) or title_point))
            selected_entities = ordered[: min(240, max(12, int(len(ordered) * 0.7)))]
        bbox = _aggregate_bbox(selected_entities)
        evidence.append("pump_title_neighborhood")
    else:
        bbox = None

    if bbox is None:
        return {
            "role": role,
            "status": "NOT_FOUND",
            "bbox": None,
            "centroid": None,
            "width": None,
            "height": None,
            "diagonal": None,
            "entity_count": 0,
            "ordinary_geometry_count": 0,
            "text_count": 0,
            "dimension_count": 0,
            "block_count": 0,
            "tdb_count": 0,
            "selection_evidence": [],
            "region_confidence": 0.0,
            "whole_drawing_extents_used": False,
        }
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    title_records = [item for item in titles if _inside_bbox(item, bbox) or title is item]
    counts = Counter(item.get("object_name") for item in selected_entities)
    confidence = min(0.95, 0.45 + (0.25 if title else 0.0) + (0.2 if substantive_blocks else 0.0))
    return {
        "role": role,
        "status": "SELECTED",
        "bbox": bbox,
        "centroid": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
        "width": width,
        "height": height,
        "diagonal": math.hypot(width, height),
        "entity_count": len(selected_entities),
        "ordinary_geometry_count": sum(_is_geometry_entity(item) for item in selected_entities),
        "text_count": sum(_is_text(item) for item in selected_entities),
        "dimension_count": sum("Dimension" in str(item.get("object_name")) for item in selected_entities),
        "block_count": counts.get("AcDbBlockReference", 0),
        "tdb_count": sum(str(name).startswith("TDb") for name in counts.elements()),
        "selection_evidence": evidence + [f"pump_title_handle:{item.get('handle')}" for item in title_records],
        "region_confidence": round(confidence, 6),
        "whole_drawing_extents_used": False,
    }


def classify_text_anchors(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
) -> dict[str, Any]:
    reference_all = [item for item in reference_scan.get("entities", []) if _is_text(item)]
    target_all = [item for item in target_scan.get("entities", []) if _is_text(item)]
    reference_local = [item for item in reference_all if _inside_bbox(item, reference_region.get("bbox")) or _is_pump_title(item)]
    target_local = [item for item in target_all if _inside_bbox(item, target_region.get("bbox")) or _is_pump_title(item)]
    ref_global = Counter(_normalized_text(item) for item in reference_all)
    target_global = Counter(_normalized_text(item) for item in target_all)
    ref_region_counts = Counter(_normalized_text(item) for item in reference_local)
    target_region_counts = Counter(_normalized_text(item) for item in target_local)
    records = []
    for role, local, global_counts, region_counts in (
        ("reference", reference_local, ref_global, ref_region_counts),
        ("target", target_local, target_global, target_region_counts),
    ):
        for item in local:
            normalized = _normalized_text(item)
            category = _text_category(item, normalized, global_counts, region_counts)
            records.append({
                "role": role,
                "handle": item.get("handle"),
                "original_text": _raw_text(item),
                "normalized_text": normalized,
                "category": category,
                "duplicate_status": category == "duplicate_text",
                "height": _text_height(item),
                "rotation": item.get("geometry", {}).get("rotation"),
                "bbox": item.get("bbox"),
                "point": _center(item),
                "high_weight_allowed": category in {"globally_unique_text", "region_unique_text"},
            })
    return {
        "reference_text_count": len(reference_local),
        "target_text_count": len(target_local),
        "records": records,
        "category_counts": dict(Counter(item["category"] for item in records)),
    }


def build_non_text_anchor_candidates(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
    reference_block_audit: Mapping[str, Any] | None = None,
    target_block_audit: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    reference_entities = _region_entities(reference_scan, reference_region, reference_block_audit)
    target_entities = _region_entities(target_scan, target_region, target_block_audit)
    reference_features = _non_text_features(reference_entities)
    target_features = _non_text_features(target_entities)
    candidates: list[dict[str, Any]] = []
    for reference in reference_features:
        for target in target_features:
            score = _feature_similarity(reference, target)
            if score < 0.82:
                continue
            candidates.append({
                "anchor_id": f"nontext_{len(candidates) + 1:05d}",
                "anchor_type": reference["feature_type"],
                "reference_handles": reference["handles"],
                "target_handles": target["handles"],
                "reference_point": reference["point"],
                "target_point": target["point"],
                "candidate_delta": [
                    target["point"][0] - reference["point"][0],
                    target["point"][1] - reference["point"][1],
                ],
                "geometry_signature": {
                    "reference": reference["signature"],
                    "target": target["signature"],
                    "similarity": score,
                },
                "neighborhood_evidence": {},
                "confidence": round(0.55 + 0.4 * score, 6),
            })
    return candidates


def cluster_translation_deltas(candidates: list[Mapping[str, Any]], tolerance: float) -> dict[str, Any]:
    if not candidates:
        return {
            "cluster_count": 0, "primary_cluster": None, "outlier_deltas": [],
            "tolerance": tolerance,
        }
    points = [list(map(float, item["candidate_delta"][:2])) for item in candidates]
    visited: set[int] = set()
    clusters: list[list[int]] = []
    for seed in range(len(points)):
        if seed in visited:
            continue
        cluster = {seed}
        frontier = [seed]
        visited.add(seed)
        while frontier:
            current = frontier.pop()
            for index, point in enumerate(points):
                if index in visited:
                    continue
                if math.dist(points[current], point) <= tolerance:
                    visited.add(index)
                    cluster.add(index)
                    frontier.append(index)
        clusters.append(sorted(cluster))
    records = []
    for cluster_id, indexes in enumerate(sorted(clusters, key=len, reverse=True), start=1):
        values = np.array([points[index] for index in indexes], dtype=float)
        center = np.median(values, axis=0)
        spread = [float(np.linalg.norm(value - center)) for value in values]
        records.append({
            "cluster_id": f"delta_cluster_{cluster_id:04d}",
            "center": center.tolist(),
            "size": len(indexes),
            "spread": {
                "median": float(np.median(spread)),
                "max": float(np.max(spread)),
                "p95": float(np.percentile(spread, 95)),
            },
            "candidate_indexes": indexes,
            "anchor_type_counts": dict(Counter(candidates[index]["anchor_type"] for index in indexes)),
        })
    primary = records[0]
    primary_indexes = set(primary["candidate_indexes"])
    return {
        "cluster_count": len(records),
        "clusters": records,
        "primary_cluster": primary,
        "outlier_deltas": [points[index] for index in range(len(points)) if index not in primary_indexes],
        "tolerance": tolerance,
    }


def select_non_text_anchors(
    candidates: list[Mapping[str, Any]],
    cluster: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not cluster:
        return []
    center = cluster["center"]
    indexes = cluster.get("candidate_indexes", [])
    ranked = sorted(
        (candidates[index] for index in indexes),
        key=lambda item: (math.dist(item["candidate_delta"], center), -float(item["confidence"])),
    )
    used_reference: set[tuple[str, ...]] = set()
    used_target: set[tuple[str, ...]] = set()
    selected = []
    for item in ranked:
        reference_key = tuple(map(str, item["reference_handles"]))
        target_key = tuple(map(str, item["target_handles"]))
        if reference_key in used_reference or target_key in used_target:
            continue
        used_reference.add(reference_key)
        used_target.add(target_key)
        selected.append(dict(item, accepted=True, cluster_distance=math.dist(item["candidate_delta"], center)))
    return selected


def disambiguate_text_anchors(
    classification: Mapping[str, Any],
    primary_delta: list[float] | None,
    tolerance: float,
) -> dict[str, Any]:
    reference = defaultdict(list)
    target = defaultdict(list)
    for item in classification.get("records", []):
        (reference if item["role"] == "reference" else target)[item["normalized_text"]].append(item)
    decisions = []
    accepted = []
    for normalized in sorted(set(reference) & set(target)):
        ref_items, target_items = reference[normalized], target[normalized]
        duplicate = len(ref_items) != 1 or len(target_items) != 1
        pairs = []
        for ref in ref_items:
            for tgt in target_items:
                if not ref.get("point") or not tgt.get("point"):
                    continue
                delta = [tgt["point"][0] - ref["point"][0], tgt["point"][1] - ref["point"][1]]
                height_score = _ratio_score(ref.get("height"), tgt.get("height"))
                rotation_score = _angle_score(ref.get("rotation"), tgt.get("rotation"))
                delta_distance = math.dist(delta, primary_delta) if primary_delta else math.inf
                relative_score = max(0.0, 1.0 - delta_distance / max(tolerance, 1e-9)) if primary_delta else 0.0
                neighborhood_score = (height_score + rotation_score) / 2
                pairs.append((relative_score + neighborhood_score, ref, tgt, delta, neighborhood_score, relative_score))
        pairs.sort(key=lambda item: item[0], reverse=True)
        used_ref: set[str] = set()
        used_target: set[str] = set()
        for _, ref, tgt, delta, neighborhood_score, relative_score in pairs:
            category_blocked = ref["category"] in {"title_block_text", "drawing_frame_text", "low_information_text"} or tgt["category"] in {"title_block_text", "drawing_frame_text", "low_information_text"}
            conflict = str(ref["handle"]) in used_ref or str(tgt["handle"]) in used_target
            accepted_pair = bool(
                primary_delta
                and not category_blocked
                and not conflict
                and relative_score >= 0.5
                and neighborhood_score >= 0.6
            )
            reason = None
            if category_blocked:
                reason = "title/frame/low-information text is not a high-weight anchor"
            elif primary_delta is None:
                reason = "no non-text translation consensus"
            elif conflict:
                reason = "one-to-many conflict"
            elif relative_score < 0.5:
                reason = "candidate delta is outside the non-text translation cluster"
            elif neighborhood_score < 0.6:
                reason = "text height/rotation neighborhood mismatch"
            decision = {
                "reference_handle": ref["handle"],
                "target_handle": tgt["handle"],
                "normalized_text": normalized,
                "duplicate_status": duplicate,
                "neighborhood_score": round(neighborhood_score, 6),
                "relative_position_score": round(relative_score, 6),
                "candidate_delta": delta,
                "accepted": accepted_pair,
                "rejection_reason": reason,
            }
            decisions.append(decision)
            if accepted_pair:
                used_ref.add(str(ref["handle"]))
                used_target.add(str(tgt["handle"]))
                accepted.append({
                    "anchor_id": f"text_{len(accepted) + 1:04d}",
                    "anchor_type": "duplicate_text_disambiguated" if duplicate else "unique_text",
                    "reference_handles": [ref["handle"]],
                    "target_handles": [tgt["handle"]],
                    "reference_point": ref["point"],
                    "target_point": tgt["point"],
                    "candidate_delta": delta,
                    "confidence": round(0.5 + 0.25 * neighborhood_score + 0.25 * relative_score, 6),
                })
    return {
        "decisions": decisions,
        "accepted_anchors": accepted,
        "accepted_count": len(accepted),
        "rejected_count": sum(not item["accepted"] for item in decisions),
        "duplicate_accepted_count": sum(item["accepted"] and item["duplicate_status"] for item in decisions),
    }


def evaluate_transforms(
    text_anchors: list[Mapping[str, Any]],
    non_text_anchors: list[Mapping[str, Any]],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
) -> dict[str, Any]:
    anchors = [dict(item, evidence_kind="text") for item in text_anchors] + [dict(item, evidence_kind="non_text") for item in non_text_anchors]
    if not anchors:
        return {"candidates": [], "selected": None, "reason": "no accepted anchors"}
    reference = np.array([item["reference_point"][:2] for item in anchors], dtype=float)
    target = np.array([item["target_point"][:2] for item in anchors], dtype=float)
    diagonal = max(float(reference_region.get("diagonal") or 1.0), float(target_region.get("diagonal") or 1.0), 1.0)
    absolute_threshold = min(1000.0, diagonal * 0.005)
    matrices = {
        "identity": np.eye(3),
        "translation": _translation_matrix(reference, target),
        "rigid": _procrustes_matrix(reference, target, allow_scale=False) if len(anchors) >= 2 else None,
        "similarity": _procrustes_matrix(reference, target, allow_scale=True) if len(anchors) >= 2 else None,
    }
    records = []
    for name, matrix in matrices.items():
        if matrix is None:
            records.append(_unavailable_transform(name, len(anchors), "at least two anchors required"))
            continue
        records.append(_transform_record(name, matrix, anchors, reference, target, diagonal, absolute_threshold))
    geometric_eligible = [
        item for item in records
        if item["inlier_count"] >= 3 and item["non_text_anchor_count"] >= 2
    ]
    best_geometric = min(
        geometric_eligible,
        key=lambda item: (_complexity(item["transform_type"]), item["median_residual"]),
        default=None,
    )
    eligible = [
        item for item in records
        if item["inlier_count"] >= 3 and item["text_anchor_count"] >= 1 and item["non_text_anchor_count"] >= 2
    ]
    selected = min(eligible, key=lambda item: (_complexity(item["transform_type"]), item["median_residual"]), default=None)
    return {
        "anchor_count": len(anchors),
        "text_anchor_count": len(text_anchors),
        "non_text_anchor_count": len(non_text_anchors),
        "absolute_residual_threshold": absolute_threshold,
        "normalized_residual_threshold": absolute_threshold / diagonal,
        "candidates": records,
        "best_geometric_candidate": best_geometric,
        "selected": selected,
        "reason": "simplest supported model with text and at least two non-text anchors" if selected else "no model passed mixed-evidence gates",
    }


def validate_geometry_overlap(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
    matrix: list[list[float]] | None,
    reference_block_audit: Mapping[str, Any] | None = None,
    target_block_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not matrix:
        return _empty_geometry_validation("transform unavailable")
    ref_features = _non_text_features(_region_entities(reference_scan, reference_region, reference_block_audit))
    target_features = _non_text_features(_region_entities(target_scan, target_region, target_block_audit))
    matrix_array = np.array(matrix, dtype=float)
    line_matches = []
    block_matches = 0
    corner_matches = 0
    motif_count = 0
    orientation_scores = []
    length_scores = []
    residuals = []
    used_targets: set[int] = set()
    for ref in ref_features:
        transformed = _apply_matrix(matrix_array, ref["point"])
        best = None
        for index, target in enumerate(target_features):
            if index in used_targets or ref["feature_type"] != target["feature_type"]:
                continue
            similarity = _feature_similarity(ref, target)
            if similarity < 0.75:
                continue
            distance = math.dist(transformed, target["point"])
            score = distance / max(similarity, 1e-9)
            if best is None or score < best[0]:
                best = (score, index, target, distance, similarity)
        if best is None:
            continue
        _, index, target, distance, similarity = best
        used_targets.add(index)
        residuals.append(distance)
        motif_count += 1
        if ref["feature_type"] == "long_line_midpoint":
            line_matches.append((ref, target))
            orientation_scores.append(_orientation_similarity(ref["signature"], target["signature"]))
            length_scores.append(_ratio_score(ref["signature"].get("length"), target["signature"].get("length")))
        elif ref["feature_type"] == "wall_corner":
            corner_matches += 1
        elif ref["feature_type"] == "unique_block_insertion":
            block_matches += 1
    diagonal = max(float(target_region.get("diagonal") or 1.0), 1.0)
    nearest = statistics.median(residuals) if residuals else math.inf
    residual_score = max(0.0, 1.0 - nearest / max(diagonal * 0.01, 1e-9)) if math.isfinite(nearest) else 0.0
    orientation = statistics.mean(orientation_scores) if orientation_scores else 0.0
    length = statistics.mean(length_scores) if length_scores else 0.0
    bbox_overlap = _transformed_bbox_overlap(reference_region.get("bbox"), target_region.get("bbox"), matrix_array)
    coverage = min(1.0, motif_count / max(len(target_features), 1))
    score = 0.35 * residual_score + 0.2 * orientation + 0.15 * length + 0.15 * bbox_overlap + 0.15 * coverage
    return {
        "geometry_nearest_neighbor_residual": nearest if math.isfinite(nearest) else None,
        "line_orientation_agreement": round(orientation, 6),
        "line_length_agreement": round(length, 6),
        "corner_match_count": corner_matches,
        "block_insertion_match_count": block_matches,
        "local_bbox_overlap": round(bbox_overlap, 6),
        "shared_geometry_motif_count": motif_count,
        "geometry_overlap_score": round(score, 6),
        "matched_long_line_count": len(line_matches),
        "reference_feature_count": len(ref_features),
        "target_feature_count": len(target_features),
        "reason": None,
    }


def build_confidence_breakdown(
    *,
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
    target_scan_confirmation: Mapping[str, Any],
    text_classification: Mapping[str, Any],
    text_disambiguation: Mapping[str, Any],
    non_text_anchors: list[Mapping[str, Any]],
    transform_evaluation: Mapping[str, Any],
    geometry_validation: Mapping[str, Any],
) -> dict[str, Any]:
    selected = transform_evaluation.get("selected") or transform_evaluation.get("best_geometric_candidate") or {}
    scan_status = target_scan_confirmation.get("status")
    scan_score = {
        "TARGET_SCAN_CONFIRMED_SPARSE": 1.0,
        "TARGET_SCAN_CONFIRMED_BLOCK_CONTAINED": 0.9,
        "TARGET_SCAN_PARTIAL_PROXY_LIMITED": 0.4,
        "TARGET_SCAN_PARTIAL_XREF_LIMITED": 0.4,
        "TARGET_SCAN_UNDETERMINED": 0.2,
        "TARGET_SCAN_INCOMPLETE": 0.0,
    }.get(scan_status, 0.0)
    region_score = min(float(reference_region.get("region_confidence", 0)), float(target_region.get("region_confidence", 0)))
    unique_candidate_count = sum(item["category"] in {"globally_unique_text", "region_unique_text"} for item in text_classification.get("records", []))
    accepted_unique_count = max(0, int(text_disambiguation.get("accepted_count", 0)) - int(text_disambiguation.get("duplicate_accepted_count", 0)))
    unique_score = min(1.0, accepted_unique_count / 2)
    duplicate_total = sum(item.get("duplicate_status") for item in text_disambiguation.get("decisions", []))
    duplicate_score = (
        text_disambiguation.get("duplicate_accepted_count", 0) / duplicate_total if duplicate_total else 0.0
    )
    non_text_score = min(1.0, len(non_text_anchors) / 4)
    inlier_ratio = selected.get("inlier_count", 0) / max(selected.get("anchor_count", 0), 1)
    residual_score = max(0.0, 1.0 - float(selected.get("normalized_max_residual", 1.0)) / 0.005) if selected else 0.0
    coverage_score = float(selected.get("spatial_coverage", 0.0)) if selected else 0.0
    stability_score = max(0.0, 1.0 - float(selected.get("leave_one_out_stability", math.inf)) / max(float(transform_evaluation.get("absolute_residual_threshold", 1.0)), 1e-9)) if selected else 0.0
    geometry_score = float(geometry_validation.get("geometry_overlap_score", 0.0))
    components = [
        ("region_correspondence_score", region_score, 0.12, "both selected local regions"),
        ("target_scan_confidence", scan_score, 0.12, scan_status),
        ("unique_text_anchor_score", unique_score, 0.08, f"accepted unique anchors={accepted_unique_count}; candidates={unique_candidate_count}"),
        ("duplicate_text_disambiguation_score", duplicate_score, 0.06, f"accepted={text_disambiguation.get('duplicate_accepted_count', 0)}/{duplicate_total}"),
        ("non_text_anchor_score", non_text_score, 0.18, f"accepted non-text anchors={len(non_text_anchors)}"),
        ("inlier_ratio_score", inlier_ratio, 0.10, f"inliers={selected.get('inlier_count', 0)}/{selected.get('anchor_count', 0)}"),
        ("residual_score", residual_score, 0.12, f"normalized max={selected.get('normalized_max_residual') if selected else None}"),
        ("spatial_coverage_score", coverage_score, 0.07, "inlier reference-point coverage"),
        ("transform_stability_score", stability_score, 0.07, f"leave-one-out={selected.get('leave_one_out_stability') if selected else None}"),
        ("geometry_overlap_score", geometry_score, 0.08, "ordinary geometry overlap validation"),
    ]
    records = [
        {"name": name, "score": round(max(0.0, min(1.0, score)), 6), "weight": weight, "weighted_score": round(max(0.0, min(1.0, score)) * weight, 6), "evidence": evidence}
        for name, score, weight, evidence in components
    ]
    return {
        "components": records,
        "weight_sum": round(sum(item["weight"] for item in records), 6),
        "final_confidence": round(sum(item["weighted_score"] for item in records), 6),
        "pass_threshold": 0.72,
    }


def decide_final_status(
    target_scan_confirmation: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
    transform_evaluation: Mapping[str, Any],
    geometry_validation: Mapping[str, Any],
    confidence: Mapping[str, Any],
) -> tuple[str, bool, list[str]]:
    blockers: list[str] = []
    scan_status = str(target_scan_confirmation.get("status"))
    if scan_status == "TARGET_SCAN_INCOMPLETE":
        return "BLOCKED_TARGET_SCAN_INCOMPLETE", False, ["target scan classification is incomplete"]
    if scan_status in {"TARGET_SCAN_PARTIAL_PROXY_LIMITED", "TARGET_SCAN_PARTIAL_XREF_LIMITED", "TARGET_SCAN_UNDETERMINED"}:
        blockers.append("target scan remains limited")
    if reference_region.get("status") != "SELECTED" or target_region.get("status") != "SELECTED":
        return "BLOCKED_DIFFERENT_DETAIL", False, ["corresponding pump-room regions were not selected"]
    selected = transform_evaluation.get("selected")
    geometric_candidate = transform_evaluation.get("best_geometric_candidate")
    if int(transform_evaluation.get("non_text_anchor_count", 0)) < 2 or (not selected and not geometric_candidate):
        return "BLOCKED_NO_NON_TEXT_EVIDENCE", False, blockers + ["fewer than two reliable non-text anchors"]
    candidate = selected or geometric_candidate
    if not selected:
        blockers.append("primary translation cluster lacks an accepted text anchor")
    geometry_score = float(geometry_validation.get("geometry_overlap_score", 0.0))
    if geometry_score < 0.55:
        blockers.append("geometry overlap score below 0.55")
    if float(confidence.get("final_confidence", 0.0)) < float(confidence.get("pass_threshold", 0.72)):
        blockers.append("alignment confidence below threshold")
    if candidate.get("normalized_max_residual", 1.0) > 0.005 or candidate.get("max_residual", math.inf) > transform_evaluation.get("absolute_residual_threshold", 0.0):
        blockers.append("absolute or normalized residual gate failed")
    if candidate.get("leave_one_out_stability", math.inf) > transform_evaluation.get("absolute_residual_threshold", 0.0):
        blockers.append("leave-one-out stability gate failed")
    if blockers:
        return ("PARTIAL_SCAN_LIMITED" if "target scan remains limited" in blockers else "PARTIAL_LOW_CONFIDENCE"), False, blockers
    status = {
        "identity": "PASS_IDENTITY_REFINED",
        "translation": "PASS_TRANSLATION_REFINED",
        "rigid": "PASS_RIGID_REFINED",
        "similarity": "PASS_SIMILARITY_REFINED",
    }[candidate["transform_type"]]
    return status, True, []


def _is_known_ordinary(name: str) -> bool:
    return name in KNOWN_ORDINARY_TYPES or "Dimension" in name


def _is_text(item: Mapping[str, Any]) -> bool:
    return item.get("object_name") in {"AcDbText", "AcDbMText"} or "text" in item.get("attributes", {}) or "mtext_contents" in item.get("attributes", {})


def _raw_text(item: Mapping[str, Any]) -> str:
    return str(item.get("attributes", {}).get("text") or item.get("attributes", {}).get("mtext_contents") or "")


def _normalized_text(item: Mapping[str, Any]) -> str:
    value = unicodedata.normalize("NFKC", _raw_text(item)).replace("\u3000", " ").strip()
    return re.sub(r"\s+", " ", value)


def _text_height(item: Mapping[str, Any]) -> float:
    try:
        return float(item.get("attributes", {}).get("height") or 0.0)
    except Exception:
        return 0.0


def _text_category(item: Mapping[str, Any], normalized: str, global_counts: Counter, region_counts: Counter) -> str:
    layer = str(item.get("layer") or "").casefold()
    lowered = normalized.casefold()
    if any(marker in layer for marker in TITLE_LAYER_MARKERS):
        return "drawing_frame_text"
    if any(marker.casefold() in lowered for marker in TITLE_TEXT_MARKERS):
        return "title_block_text"
    if len(normalized) <= 2 or re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalized) or re.fullmatch(r"\d+[:：]\d+", normalized):
        return "low_information_text"
    if global_counts[normalized] == 1:
        return "globally_unique_text"
    if region_counts[normalized] == 1:
        return "region_unique_text"
    return "duplicate_text"


def _is_pump_title(item: Mapping[str, Any]) -> bool:
    text = _normalized_text(item)
    return _is_text(item) and any(marker in text for marker in PUMP_TEXT_MARKERS)


def _is_title_noise_entity(item: Mapping[str, Any]) -> bool:
    layer = str(item.get("layer") or "").casefold()
    return any(marker in layer for marker in TITLE_LAYER_MARKERS) or (_is_text(item) and _text_category(item, _normalized_text(item), Counter({_normalized_text(item): 1}), Counter({_normalized_text(item): 1})) in {"title_block_text", "drawing_frame_text", "low_information_text"})


def _center(item: Mapping[str, Any]) -> list[float] | None:
    bbox = _bbox2(item.get("bbox"))
    if bbox:
        return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    geometry = item.get("geometry", {})
    for key in ("insertion_point", "insert_point", "center", "start_point", "end_point"):
        value = geometry.get(key)
        if isinstance(value, list) and len(value) >= 2:
            return [float(value[0]), float(value[1])]
    return None


def _bbox2(value: Any) -> list[float] | None:
    try:
        if isinstance(value, list) and len(value) == 2:
            return [float(value[0][0]), float(value[0][1]), float(value[1][0]), float(value[1][1])]
        if isinstance(value, list) and len(value) >= 4:
            return [float(value[0]), float(value[1]), float(value[2]), float(value[3])]
    except Exception:
        return None
    return None


def _inside_bbox(item: Mapping[str, Any], value: Any) -> bool:
    bbox = _bbox2(value)
    point = _center(item)
    return bool(bbox and point and bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3])


def _aggregate_bbox(items: Iterable[Mapping[str, Any]]) -> list[float] | None:
    points = [point for item in items if (point := _center(item))]
    if not points:
        return None
    return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]


def _is_geometry_entity(item: Mapping[str, Any]) -> bool:
    name = str(item.get("object_name") or "")
    return name in {"AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline", "AcDbCircle", "AcDbArc", "AcDbBlockReference"}


def _region_entities(scan: Mapping[str, Any], region: Mapping[str, Any], audit: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    entities = list(scan.get("entities", []))
    if audit:
        entities.extend(audit.get("virtual_entities", []))
    return [item for item in entities if _inside_bbox(item, region.get("bbox")) and not _is_title_noise_entity(item)]


def _non_text_features(entities: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    lines: list[tuple[Mapping[str, Any], list[float], list[float]]] = []
    for item in entities:
        name = item.get("object_name")
        geometry = item.get("geometry", {})
        if name == "AcDbLine" and geometry.get("start_point") and geometry.get("end_point"):
            start = list(map(float, geometry["start_point"][:2]))
            end = list(map(float, geometry["end_point"][:2]))
            length = math.dist(start, end)
            angle = _canonical_angle(math.atan2(end[1] - start[1], end[0] - start[0]))
            lines.append((item, start, end))
            if length >= 500:
                features.append({
                    "feature_type": "long_line_midpoint",
                    "handles": [str(item.get("handle"))],
                    "point": [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2],
                    "signature": {"length": length, "angle": angle, "orientation": _orientation_bucket(angle)},
                })
        elif name in {"AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline"}:
            bbox = _bbox2(item.get("bbox"))
            if bbox and bbox[2] > bbox[0] and bbox[3] > bbox[1]:
                features.append({
                    "feature_type": "rectangle_center",
                    "handles": [str(item.get("handle"))],
                    "point": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
                    "signature": {"width": bbox[2] - bbox[0], "height": bbox[3] - bbox[1]},
                })
        elif name == "AcDbBlockReference":
            point = _center(item)
            block_name = item.get("attributes", {}).get("effective_name") or item.get("attributes", {}).get("name")
            if point and block_name and point != [0.0, 0.0]:
                features.append({
                    "feature_type": "unique_block_insertion",
                    "handles": [str(item.get("handle"))],
                    "point": point,
                    "signature": {"name": str(block_name)},
                })
        elif name == "AcDbCircle" and geometry.get("center"):
            features.append({
                "feature_type": "circle_center",
                "handles": [str(item.get("handle"))],
                "point": list(map(float, geometry["center"][:2])),
                "signature": {"radius": float(geometry.get("radius") or 0.0)},
            })
    features.extend(_line_corners(lines))
    return features


def _line_corners(lines: list[tuple[Mapping[str, Any], list[float], list[float]]]) -> list[dict[str, Any]]:
    corners = []
    for index, (left, a1, a2) in enumerate(lines):
        for right, b1, b2 in lines[index + 1:]:
            point = _segment_intersection(a1, a2, b1, b2)
            if point is None:
                continue
            left_angle = _canonical_angle(math.atan2(a2[1] - a1[1], a2[0] - a1[0]))
            right_angle = _canonical_angle(math.atan2(b2[1] - b1[1], b2[0] - b1[0]))
            angle = abs(left_angle - right_angle)
            angle = min(angle, math.pi - angle)
            if abs(angle - math.pi / 2) > math.radians(5):
                continue
            corners.append({
                "feature_type": "wall_corner",
                "handles": [str(left.get("handle")), str(right.get("handle"))],
                "point": point,
                "signature": {"angle": math.pi / 2},
            })
    return corners


def _segment_intersection(a1: list[float], a2: list[float], b1: list[float], b2: list[float]) -> list[float] | None:
    x1, y1 = a1; x2, y2 = a2; x3, y3 = b1; x4, y4 = b2
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denominator
    if -1e-8 <= t <= 1 + 1e-8 and -1e-8 <= u <= 1 + 1e-8:
        return [x1 + t * (x2 - x1), y1 + t * (y2 - y1)]
    return None


def _feature_similarity(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    if left["feature_type"] != right["feature_type"]:
        return 0.0
    l_sig, r_sig = left["signature"], right["signature"]
    if left["feature_type"] == "long_line_midpoint":
        return 0.55 * _ratio_score(l_sig.get("length"), r_sig.get("length")) + 0.45 * _orientation_similarity(l_sig, r_sig)
    if left["feature_type"] == "rectangle_center":
        direct = (_ratio_score(l_sig.get("width"), r_sig.get("width")) + _ratio_score(l_sig.get("height"), r_sig.get("height"))) / 2
        swapped = (_ratio_score(l_sig.get("width"), r_sig.get("height")) + _ratio_score(l_sig.get("height"), r_sig.get("width"))) / 2
        return max(direct, swapped)
    if left["feature_type"] == "unique_block_insertion":
        return 1.0 if l_sig.get("name") == r_sig.get("name") else 0.0
    if left["feature_type"] == "circle_center":
        return _ratio_score(l_sig.get("radius"), r_sig.get("radius"))
    if left["feature_type"] == "wall_corner":
        return 1.0
    return 0.0


def _ratio_score(left: Any, right: Any) -> float:
    try:
        left_value, right_value = abs(float(left)), abs(float(right))
        return 1.0 - abs(left_value - right_value) / max(left_value, right_value, 1e-9)
    except Exception:
        return 0.0


def _angle_score(left: Any, right: Any) -> float:
    try:
        difference = abs(_canonical_angle(float(left)) - _canonical_angle(float(right)))
        difference = min(difference, math.pi - difference)
        return max(0.0, 1.0 - difference / math.radians(5))
    except Exception:
        return 0.0


def _orientation_similarity(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    return _angle_score(left.get("angle"), right.get("angle"))


def _orientation_bucket(angle: float) -> str:
    if min(abs(angle), abs(math.pi - angle)) <= math.radians(5):
        return "horizontal"
    if abs(angle - math.pi / 2) <= math.radians(5):
        return "vertical"
    return "diagonal"


def _canonical_angle(angle: float) -> float:
    return angle % math.pi


def _translation_matrix(reference: np.ndarray, target: np.ndarray) -> np.ndarray:
    delta = np.median(target - reference, axis=0)
    matrix = np.eye(3)
    matrix[:2, 2] = delta
    return matrix


def _procrustes_matrix(reference: np.ndarray, target: np.ndarray, allow_scale: bool) -> np.ndarray:
    ref_center, target_center = reference.mean(axis=0), target.mean(axis=0)
    ref_zero, target_zero = reference - ref_center, target - target_center
    u, singular, vt = np.linalg.svd(ref_zero.T @ target_zero)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    scale = float(np.sum(singular) / np.sum(ref_zero ** 2)) if allow_scale and np.sum(ref_zero ** 2) else 1.0
    matrix = np.eye(3)
    matrix[:2, :2] = scale * rotation
    matrix[:2, 2] = target_center - scale * (rotation @ ref_center)
    return matrix


def _transform_record(
    name: str,
    matrix: np.ndarray,
    anchors: list[Mapping[str, Any]],
    reference: np.ndarray,
    target: np.ndarray,
    diagonal: float,
    threshold: float,
) -> dict[str, Any]:
    predicted = (matrix @ np.column_stack([reference, np.ones(len(reference))]).T).T[:, :2]
    residuals = np.linalg.norm(predicted - target, axis=1)
    inliers = [index for index, value in enumerate(residuals) if value <= threshold]
    inlier_values = residuals[inliers] if inliers else residuals
    reference_inliers = reference[inliers] if inliers else reference
    coverage = _point_coverage(reference_inliers, diagonal)
    stability = _leave_one_out_stability(name, anchors, reference, target)
    text_count = sum(anchors[index]["evidence_kind"] == "text" for index in inliers)
    non_text_count = sum(anchors[index]["evidence_kind"] == "non_text" for index in inliers)
    return {
        "transform_type": name,
        "anchor_count": len(anchors),
        "text_anchor_count": text_count,
        "non_text_anchor_count": non_text_count,
        "inlier_count": len(inliers),
        "outlier_count": len(anchors) - len(inliers),
        "inlier_indexes": inliers,
        "median_residual": float(np.median(inlier_values)),
        "mean_residual": float(np.mean(inlier_values)),
        "p95_residual": float(np.percentile(inlier_values, 95)),
        "max_residual": float(np.max(inlier_values)),
        "normalized_median_residual": float(np.median(inlier_values) / diagonal),
        "normalized_max_residual": float(np.max(inlier_values) / diagonal),
        "spatial_coverage": coverage,
        "leave_one_out_stability": stability,
        "transform_parameters": {
            "matrix": matrix.tolist(),
            "translation": [float(matrix[0, 2]), float(matrix[1, 2])],
            "rotation_radians": math.atan2(float(matrix[1, 0]), float(matrix[0, 0])),
            "scale": math.hypot(float(matrix[0, 0]), float(matrix[1, 0])),
        },
        "rejection_reason": None if len(inliers) >= 3 and text_count >= 1 and non_text_count >= 2 else "mixed-evidence inlier gate failed",
    }


def _unavailable_transform(name: str, count: int, reason: str) -> dict[str, Any]:
    return {
        "transform_type": name, "anchor_count": count, "text_anchor_count": 0,
        "non_text_anchor_count": 0, "inlier_count": 0, "outlier_count": count,
        "median_residual": None, "mean_residual": None, "p95_residual": None,
        "max_residual": None, "normalized_median_residual": None,
        "normalized_max_residual": None, "spatial_coverage": 0.0,
        "leave_one_out_stability": None, "transform_parameters": None,
        "rejection_reason": reason,
    }


def _leave_one_out_stability(name: str, anchors: list[Mapping[str, Any]], reference: np.ndarray, target: np.ndarray) -> float:
    if len(anchors) < 4:
        return math.inf
    matrices = []
    for omitted in range(len(anchors)):
        ref = np.delete(reference, omitted, axis=0)
        tgt = np.delete(target, omitted, axis=0)
        if name == "identity":
            matrix = np.eye(3)
        elif name == "translation":
            matrix = _translation_matrix(ref, tgt)
        elif name == "rigid":
            matrix = _procrustes_matrix(ref, tgt, False)
        else:
            matrix = _procrustes_matrix(ref, tgt, True)
        matrices.append(matrix)
    translations = np.array([[matrix[0, 2], matrix[1, 2]] for matrix in matrices])
    center = np.median(translations, axis=0)
    return float(np.max(np.linalg.norm(translations - center, axis=1)))


def _point_coverage(points: np.ndarray, diagonal: float) -> float:
    if len(points) < 2:
        return 0.0
    spread = math.hypot(float(np.ptp(points[:, 0])), float(np.ptp(points[:, 1])))
    return min(1.0, spread / max(diagonal * 0.5, 1e-9))


def _complexity(name: str) -> int:
    return {"identity": 0, "translation": 1, "rigid": 2, "similarity": 3}.get(name, 99)


def _apply_matrix(matrix: np.ndarray, point: list[float]) -> list[float]:
    value = matrix @ np.array([float(point[0]), float(point[1]), 1.0])
    return [float(value[0]), float(value[1])]


def _transformed_bbox_overlap(reference_bbox: Any, target_bbox: Any, matrix: np.ndarray) -> float:
    reference = _bbox2(reference_bbox)
    target = _bbox2(target_bbox)
    if not reference or not target:
        return 0.0
    corners = [
        _apply_matrix(matrix, [reference[0], reference[1]]),
        _apply_matrix(matrix, [reference[0], reference[3]]),
        _apply_matrix(matrix, [reference[2], reference[1]]),
        _apply_matrix(matrix, [reference[2], reference[3]]),
    ]
    transformed = [min(p[0] for p in corners), min(p[1] for p in corners), max(p[0] for p in corners), max(p[1] for p in corners)]
    intersection = max(0.0, min(transformed[2], target[2]) - max(transformed[0], target[0])) * max(0.0, min(transformed[3], target[3]) - max(transformed[1], target[1]))
    union = (transformed[2] - transformed[0]) * (transformed[3] - transformed[1]) + (target[2] - target[0]) * (target[3] - target[1]) - intersection
    return intersection / union if union > 0 else 0.0


def _empty_geometry_validation(reason: str) -> dict[str, Any]:
    return {
        "geometry_nearest_neighbor_residual": None,
        "line_orientation_agreement": 0.0,
        "line_length_agreement": 0.0,
        "corner_match_count": 0,
        "block_insertion_match_count": 0,
        "local_bbox_overlap": 0.0,
        "shared_geometry_motif_count": 0,
        "geometry_overlap_score": 0.0,
        "matched_long_line_count": 0,
        "reference_feature_count": 0,
        "target_feature_count": 0,
        "reason": reason,
    }
