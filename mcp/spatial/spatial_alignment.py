from __future__ import annotations

from typing import Any

from mcp.spatial.alignment_validator import validate_alignment
from mcp.spatial.anchor_extractor import extract_reference_anchors, extract_target_anchors
from mcp.spatial.anchor_matcher import match_anchors
from mcp.spatial.graph_mapper import map_reference_graph_to_target_space
from mcp.spatial.models import AnchorPair, AnchorPoint, Point2D, SpatialAlignmentResult, Transform2D
from mcp.spatial.transform import TransformEstimator


def align_reference_graph_to_target(
    reference_graph: dict[str, Any],
    target_graph: dict[str, Any],
    manual_anchor_pairs: list | None = None,
    options: dict | None = None,
) -> SpatialAlignmentResult:
    options = options or {}
    warnings: list[str] = []
    errors: list[str] = []
    reference_anchors = extract_reference_anchors(reference_graph)
    target_anchors = extract_target_anchors(target_graph)

    if manual_anchor_pairs:
        anchor_pairs, manual_summary = manual_anchor_pairs_from_scenario(
            manual_anchor_pairs,
            reference_graph=reference_graph,
            target_graph=target_graph,
        )
        warnings.extend(manual_summary.get("warnings", []))
    else:
        manual_summary = {"used_manual_anchors": False, "manual_anchor_count": 0, "warnings": []}
        anchor_pairs = match_anchors(reference_anchors, target_anchors, options)
        if not anchor_pairs:
            warnings.append("automatic anchor matching produced no pairs")

    transform = TransformEstimator().estimate_from_anchor_pairs(anchor_pairs)
    if transform.transform_type == "unknown":
        warnings.append("transform unavailable")

    aligned_graph = map_reference_graph_to_target_space(reference_graph, transform)
    validation = validate_alignment(aligned_graph, target_graph, transform)
    warnings.extend(validation["warnings"])
    errors.extend(validation["errors"])

    return SpatialAlignmentResult(
        reference_graph_id=str(reference_graph.get("id", "reference_graph")),
        target_graph_id=str(target_graph.get("id", "target_graph")),
        transform=transform,
        aligned_reference_graph=aligned_graph,
        anchor_pairs=anchor_pairs,
        confidence=validation["confidence"],
        warnings=list(dict.fromkeys(warnings)),
        errors=errors,
        metadata={
            "reference_anchor_count": len(reference_anchors),
            "target_anchor_count": len(target_anchors),
            "manual_anchor_summary": manual_summary,
            "validation": validation,
        },
    )


def manual_anchor_pairs_from_scenario(
    manual_anchor_pairs: list[dict[str, Any]],
    reference_graph: dict[str, Any] | None = None,
    target_graph: dict[str, Any] | None = None,
) -> tuple[list[AnchorPair], dict[str, Any]]:
    reference_graph = reference_graph or {}
    target_graph = target_graph or {}
    warnings: list[str] = []
    pairs = []
    for index, item in enumerate(manual_anchor_pairs):
        try:
            pairs.append(_manual_pair(item, index, reference_graph, target_graph))
        except Exception as exc:
            warnings.append(f"invalid manual anchor pair {index}: {exc}")
    if not pairs:
        warnings.append("manual anchor pairs provided but none were valid")
    if len(pairs) == 1:
        warnings.append("manual anchor pair count is 1; translation-only transform")
    if len(pairs) >= 2:
        warnings.append("similarity transform requested but current estimator uses conservative translation")
    return pairs, {
        "used_manual_anchors": bool(pairs),
        "manual_anchor_count": len(pairs),
        "warnings": warnings,
    }


def _manual_pair(item: dict[str, Any], index: int) -> AnchorPair:
    return _manual_pair(item, index, {}, {})


def _manual_pair(
    item: dict[str, Any],
    index: int,
    reference_graph: dict[str, Any],
    target_graph: dict[str, Any],
) -> AnchorPair:
    if "reference_point" in item:
        ref_xy = _convert_reference_point(item, reference_graph)
        target_xy = _convert_target_point(item, target_graph)
        label = str(item.get("label") or f"manual_{index}")
    else:
        ref_point = item["reference"]
        target_point = item["target"]
        ref_xy = [float(ref_point["x"]), float(ref_point["y"])]
        target_xy = [float(target_point["x"]), float(target_point["y"])]
        label = f"manual_{index}"
    ref = AnchorPoint(
        f"manual_reference_{index}",
        "reference",
        Point2D(float(ref_xy[0]), float(ref_xy[1])),
        label,
        "manual_anchor",
        float(item.get("confidence", 0.8)),
        {"label": label, "space": item.get("reference_space", "image_pixel")},
    )
    target = AnchorPoint(
        f"manual_target_{index}",
        "target",
        Point2D(float(target_xy[0]), float(target_xy[1])),
        label,
        "manual_anchor",
        float(item.get("confidence", 0.8)),
        {"label": label, "space": item.get("target_space", "cad_modelspace")},
    )
    return AnchorPair(ref, target, float(item.get("confidence", 0.8)), list(item.get("reason", ["manual"])))


def _convert_reference_point(item: dict[str, Any], reference_graph: dict[str, Any]) -> list[float]:
    point = [float(value) for value in item["reference_point"][:2]]
    if item.get("reference_space") == "normalized_image":
        width, height = _image_size(reference_graph)
        return [point[0] * width, point[1] * height]
    return point


def _convert_target_point(item: dict[str, Any], target_graph: dict[str, Any]) -> list[float]:
    point = [float(value) for value in item["target_point"][:2]]
    return point


def _image_size(reference_graph: dict[str, Any]) -> list[float]:
    metadata = reference_graph.get("metadata", {})
    if metadata.get("image_size"):
        return [float(metadata["image_size"][0]), float(metadata["image_size"][1])]
    diagnostics = metadata.get("diagnostics", {})
    if diagnostics.get("image_size"):
        return [float(diagnostics["image_size"][0]), float(diagnostics["image_size"][1])]
    return [1.0, 1.0]
