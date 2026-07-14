from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any


@dataclass(frozen=True)
class SemanticMatch:
    reference: dict[str, Any]
    current: dict[str, Any]
    distance: float


class SemanticEntityMatcher:
    def __init__(self, match_tolerance: float = 100.0) -> None:
        self.match_tolerance = float(match_tolerance)

    def find_best_match(
        self,
        reference: dict[str, Any],
        current_entities: list[dict[str, Any]],
        used_current_handles: set[str],
    ) -> SemanticMatch | None:
        candidates: list[tuple[float, int, int, dict[str, Any]]] = []
        for current in current_entities:
            current_handle = entity_handle(current)
            if current_handle in used_current_handles:
                continue
            if entity_type(reference) != entity_type(current):
                continue
            distance = geometry_distance(reference, current)
            if distance > self.match_tolerance:
                continue
            system_penalty = 0 if reference.get("system_type") == current.get("system_type") else 1
            layer_penalty = 0 if reference.get("layer") == current.get("layer") else 1
            candidates.append((distance, system_penalty, layer_penalty, current))

        if not candidates:
            return None

        distance, _system_penalty, _layer_penalty, current = min(
            candidates,
            key=lambda item: (item[0], item[1], item[2], entity_handle(item[3])),
        )
        return SemanticMatch(reference=reference, current=current, distance=round(distance, 6))


def entity_type(entity: dict[str, Any]) -> str:
    return str(entity.get("semantic_type") or entity.get("type") or "")


def entity_handle(entity: dict[str, Any]) -> str:
    return str(entity.get("handle") or entity.get("id") or "")


def pipe_entities(model: dict[str, Any]) -> list[dict[str, Any]]:
    entities = list(model.get("entities", []))
    entities.extend(model.get("pipes", []))
    return [entity for entity in entities if entity_type(entity) == "pipe"]


def normalized_diameter(entity: dict[str, Any]) -> str | None:
    diameter = entity.get("diameter")
    if isinstance(diameter, dict):
        value = diameter.get("normalized")
    else:
        value = diameter
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def geometry_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    a_points = entity_points(a)
    b_points = entity_points(b)
    if len(a_points) >= 2 and len(b_points) >= 2:
        return _line_distance(a_points[:2], b_points[:2])
    if a_points and b_points:
        return _point_distance(a_points[0], b_points[0])
    return float("inf")


def entity_points(entity: dict[str, Any]) -> list[tuple[float, float]]:
    inferred = entity.get("inferred_geometry", {})
    start = _point_from_sequence(inferred.get("start_point"))
    end = _point_from_sequence(inferred.get("end_point"))
    if start is not None and end is not None:
        return [start, end]

    center = _point_from_sequence(inferred.get("center"))
    if center is not None:
        return [center]

    geometry = entity.get("geometry", {})
    raw_points = geometry.get("points", [])
    points = [_point_from_mapping(point) for point in raw_points if isinstance(point, dict)]
    points = [point for point in points if point is not None]
    if points:
        return points

    bbox = entity.get("bounding_box")
    bbox_center = _center_from_bounding_box(bbox)
    return [bbox_center] if bbox_center is not None else []


def _line_distance(
    a_points: list[tuple[float, float]],
    b_points: list[tuple[float, float]],
) -> float:
    forward = max(
        _point_distance(a_points[0], b_points[0]),
        _point_distance(a_points[1], b_points[1]),
    )
    reverse = max(
        _point_distance(a_points[0], b_points[1]),
        _point_distance(a_points[1], b_points[0]),
    )
    return min(forward, reverse)


def _point_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def _point_from_sequence(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None


def _point_from_mapping(value: dict[str, Any]) -> tuple[float, float] | None:
    try:
        return (float(value["x"]), float(value["y"]))
    except (KeyError, TypeError, ValueError):
        return None


def _center_from_bounding_box(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 5:
        return None
    try:
        return ((float(value[0]) + float(value[3])) / 2, (float(value[1]) + float(value[4])) / 2)
    except (TypeError, ValueError):
        return None
