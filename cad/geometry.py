from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def normalize_point(value: Any) -> list[float]:
    values = _to_list(value)
    if len(values) < 2:
        raise ValueError("point requires at least x and y")
    return [
        float(values[0]),
        float(values[1]),
        float(values[2]) if len(values) > 2 else 0.0,
    ]


def coordinates_to_points(values: Any) -> list[list[float]]:
    coordinates = [float(value) for value in _to_list(values)]
    if not coordinates:
        return []
    if len(coordinates) % 3 == 0:
        step = 3
    elif len(coordinates) % 2 == 0:
        step = 2
    else:
        raise ValueError("coordinates length must be divisible by 2 or 3")

    points: list[list[float]] = []
    for index in range(0, len(coordinates), step):
        point = coordinates[index : index + step]
        points.append(normalize_point(point))
    return points


def bounding_box_from_points(points: list[list[float]]) -> dict[str, Any] | None:
    if not points:
        return None
    normalized = [normalize_point(point) for point in points]
    xs = [point[0] for point in normalized]
    ys = [point[1] for point in normalized]
    return {
        "x_min": min(xs),
        "y_min": min(ys),
        "x_max": max(xs),
        "y_max": max(ys),
        "coordinate_system": "cad_world",
    }


def read_bounding_box(entity: Any, fallback_points: list[list[float]] | None = None) -> dict[str, Any] | None:
    try:
        raw = entity.GetBoundingBox()
        if isinstance(raw, tuple | list) and len(raw) == 2:
            min_point = normalize_point(raw[0])
            max_point = normalize_point(raw[1])
            return {
                "x_min": min(min_point[0], max_point[0]),
                "y_min": min(min_point[1], max_point[1]),
                "x_max": max(min_point[0], max_point[0]),
                "y_max": max(min_point[1], max_point[1]),
                "coordinate_system": "cad_world",
            }
    except Exception:
        logger.info("GetBoundingBox failed; falling back to geometry points", exc_info=True)
    return bounding_box_from_points(fallback_points or [])


def _to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "value"):
        return list(value.value)
    return list(value)
