from __future__ import annotations

import math
from typing import Any

from tianzheng.diameter_label_reader import extract_pipe_diameter_labels


DEFAULT_ASSOCIATION_TOLERANCE = 500.0


def build_pipe_diameter_association_model(
    semantic_model: dict[str, Any],
    *,
    tolerance: float = DEFAULT_ASSOCIATION_TOLERANCE,
) -> dict[str, Any]:
    entities = list(semantic_model.get("entities", []))
    pipes = [entity for entity in entities if entity.get("semantic_type") == "pipe"]
    labels = extract_pipe_diameter_labels(entities)
    associations = associate_diameter_labels_to_pipes(pipes, labels, tolerance=tolerance)
    matched_label_ids = {
        candidate["label_id"]
        for association in associations
        for candidate in association.get("diameter_candidates", [])
    }
    usable_labels = [label for label in labels if label.get("normalized_diameter")]
    return {
        "source": "tianzheng_diameter_association",
        "active_document": semantic_model.get("active_document"),
        "selection_count": semantic_model.get("selection_count", len(entities)),
        "summary": {
            "pipes": len(pipes),
            "diameter_labels": len(labels),
            "associations": len(associations),
            "unmatched_pipes": sum(
                1 for association in associations if not association.get("diameter_candidates")
            ),
            "unmatched_labels": sum(
                1 for label in usable_labels if label.get("label_id") not in matched_label_ids
            ),
            "need_user_confirmation": sum(
                1 for association in associations if association.get("status") == "need_user_confirmation"
            )
            + sum(1 for label in labels if label.get("status") == "need_user_confirmation"),
        },
        "diameter_labels": labels,
        "pipe_associations": associations,
    }


def associate_diameter_labels_to_pipes(
    pipes: list[dict[str, Any]],
    diameter_labels: list[dict[str, Any]],
    *,
    tolerance: float = DEFAULT_ASSOCIATION_TOLERANCE,
) -> list[dict[str, Any]]:
    usable_labels = [label for label in diameter_labels if label.get("normalized_diameter")]
    associations: list[dict[str, Any]] = []
    for pipe in pipes:
        candidates = []
        for label in usable_labels:
            distance = distance_label_to_pipe(label, pipe)
            if distance <= tolerance:
                candidates.append(
                    {
                        "diameter": label.get("normalized_diameter"),
                        "label_handle": label.get("source_object", {}).get("handle"),
                        "label_id": label.get("label_id"),
                        "distance": distance,
                        "confidence": _confidence(distance, tolerance),
                        "reason": "nearest_label_to_pipe",
                    }
                )
        candidates.sort(key=lambda item: item["distance"])
        associations.append(
            {
                "pipe_handle": pipe.get("handle"),
                "pipe_layer": pipe.get("layer"),
                "pipe_system_type": pipe.get("system_type", "unknown"),
                "pipe_inferred_geometry": pipe.get("inferred_geometry", {}),
                "diameter_candidates": candidates,
                "selected_diameter": None,
                "status": "need_user_confirmation",
            }
        )
    return associations


def distance_label_to_pipe(label: dict[str, Any], pipe: dict[str, Any]) -> float:
    point = _label_point(label)
    start, end = _pipe_segment(pipe)
    if point is None or start is None or end is None:
        return float("inf")
    return _distance_point_to_segment_2d(point, start, end)


def _label_point(label: dict[str, Any]) -> list[float] | None:
    position = label.get("position")
    if isinstance(position, list | tuple) and len(position) >= 2:
        return [float(position[0]), float(position[1]), float(position[2]) if len(position) > 2 else 0.0]
    bbox = label.get("bounding_box")
    return _bbox_center(bbox)


def _pipe_segment(pipe: dict[str, Any]) -> tuple[list[float] | None, list[float] | None]:
    geometry = pipe.get("inferred_geometry", {})
    start = _point_or_none(geometry.get("start_point"))
    end = _point_or_none(geometry.get("end_point"))
    if start is not None and end is not None:
        return start, end
    bbox = pipe.get("bounding_box")
    if bbox and len(bbox) >= 6:
        values = [float(value) for value in bbox[:6]]
        return [values[0], values[1], values[2]], [values[3], values[4], values[5]]
    return None, None


def _distance_point_to_segment_2d(point: list[float], start: list[float], end: list[float]) -> float:
    px, py = point[0], point[1]
    sx, sy = start[0], start[1]
    ex, ey = end[0], end[1]
    dx = ex - sx
    dy = ey - sy
    if dx == 0 and dy == 0:
        return math.hypot(px - sx, py - sy)
    t = ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    closest_x = sx + t * dx
    closest_y = sy + t * dy
    return math.hypot(px - closest_x, py - closest_y)


def _confidence(distance: float, tolerance: float) -> float:
    if math.isinf(distance) or tolerance <= 0:
        return 0.0
    return round(max(0.0, min(1.0, 1.0 - distance / tolerance)), 3)


def _bbox_center(bbox: Any) -> list[float] | None:
    if not bbox or len(bbox) < 6:
        return None
    values = [float(value) for value in bbox[:6]]
    return [
        (values[0] + values[3]) / 2.0,
        (values[1] + values[4]) / 2.0,
        (values[2] + values[5]) / 2.0,
    ]


def _point_or_none(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) < 2:
        return None
    return [
        float(value[0]),
        float(value[1]),
        float(value[2]) if len(value) > 2 else 0.0,
    ]
