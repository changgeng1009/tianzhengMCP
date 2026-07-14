from __future__ import annotations

from mcp.spatial.models import AnchorPair, AnchorPoint


PRIORITY = {
    "building_centroid": 4,
    "building_bbox_corner": 3,
    "pipe_endpoint": 2,
    "sprinkler_center": 2,
    "valve_center": 2,
    "text_label_center": 1,
    "graph_node": 1,
}


def match_anchors(
    reference_anchors: list[AnchorPoint],
    target_anchors: list[AnchorPoint],
    options: dict | None = None,
) -> list[AnchorPair]:
    options = options or {}
    min_confidence = float(options.get("min_pair_confidence", 0.35))
    pairs: list[AnchorPair] = []
    used_target_ids: set[str] = set()

    for reference in sorted(reference_anchors, key=lambda anchor: -PRIORITY.get(anchor.element_type, 0)):
        candidates = [
            target for target in target_anchors
            if target.anchor_id not in used_target_ids and _compatible(reference, target)
        ]
        if not candidates:
            continue
        target = max(candidates, key=lambda item: _pair_confidence(reference, item))
        confidence = _pair_confidence(reference, target)
        if confidence < min_confidence:
            continue
        used_target_ids.add(target.anchor_id)
        pairs.append(
            AnchorPair(
                reference_anchor=reference,
                target_anchor=target,
                confidence=confidence,
                reason=["element_type_match"],
            )
        )
    return pairs


def _compatible(reference: AnchorPoint, target: AnchorPoint) -> bool:
    if reference.element_type == target.element_type:
        return True
    if reference.element_type == "pipe_endpoint" and target.element_type == "graph_node":
        return True
    return False


def _pair_confidence(reference: AnchorPoint, target: AnchorPoint) -> float:
    base = min(reference.confidence, target.confidence) * 0.8
    if reference.element_id == target.element_id:
        base += 0.1
    return round(min(base, 0.9), 4)
