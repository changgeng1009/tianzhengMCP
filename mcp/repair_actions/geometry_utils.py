from __future__ import annotations

import math
from typing import Any


def distance_point_to_point(p1: list[float], p2: list[float]) -> float:
    try:
        return round(math.hypot(float(p1[0]) - float(p2[0]), float(p1[1]) - float(p2[1])), 6)
    except Exception:
        return float("inf")


def distance_segment_to_segment(seg1: list[list[float]], seg2: list[list[float]]) -> float:
    try:
        a1, a2 = seg1[0], seg1[-1]
        b1, b2 = seg2[0], seg2[-1]
        return round(
            min(
                distance_point_to_segment(a1, b1, b2),
                distance_point_to_segment(a2, b1, b2),
                distance_point_to_segment(b1, a1, a2),
                distance_point_to_segment(b2, a1, a2),
            ),
            6,
        )
    except Exception:
        return float("inf")


def distance_point_to_segment(point: list[float], start: list[float], end: list[float]) -> float:
    px, py = float(point[0]), float(point[1])
    x1, y1 = float(start[0]), float(start[1])
    x2, y2 = float(end[0]), float(end[1])
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return distance_point_to_point(point, start)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    projection = [x1 + t * dx, y1 + t * dy]
    return distance_point_to_point([px, py], projection)


def bbox_overlap_ratio(bbox1: list[float], bbox2: list[float]) -> float:
    try:
        x_left = max(float(bbox1[0]), float(bbox2[0]))
        y_top = max(float(bbox1[1]), float(bbox2[1]))
        x_right = min(float(bbox1[2]), float(bbox2[2]))
        y_bottom = min(float(bbox1[3]), float(bbox2[3]))
        if x_right <= x_left or y_bottom <= y_top:
            return 0.0
        overlap = (x_right - x_left) * (y_bottom - y_top)
        area1 = abs((float(bbox1[2]) - float(bbox1[0])) * (float(bbox1[3]) - float(bbox1[1])))
        return round(overlap / area1, 6) if area1 else 0.0
    except Exception:
        return 0.0


def polyline_length(points: list[list[float]]) -> float:
    try:
        return round(sum(distance_point_to_point(points[index], points[index + 1]) for index in range(len(points) - 1)), 6)
    except Exception:
        return 0.0


def normalize_segment_direction(points: list[list[float]]) -> list[list[float]]:
    if len(points) < 2:
        return points
    start = [float(points[0][0]), float(points[0][1])]
    end = [float(points[-1][0]), float(points[-1][1])]
    return [start, end] if tuple(start) <= tuple(end) else [end, start]


def is_near_duplicate_geometry(geom1: dict[str, Any], geom2: dict[str, Any], tolerance: float) -> bool:
    points1 = _points_from_geometry(geom1)
    points2 = _points_from_geometry(geom2)
    if len(points1) < 2 or len(points2) < 2:
        return False
    a = normalize_segment_direction(points1)
    b = normalize_segment_direction(points2)
    return (
        distance_point_to_point(a[0], b[0]) <= tolerance
        and distance_point_to_point(a[-1], b[-1]) <= tolerance
    )


def geometry_confidence_score(reference_geom: dict[str, Any], target_geom: dict[str, Any]) -> float:
    distance = distance_segment_to_segment(_points_from_geometry(reference_geom), _points_from_geometry(target_geom))
    if distance == float("inf"):
        return 0.0
    return round(max(0.0, 1.0 - distance / 100.0), 4)


def _points_from_geometry(geometry: dict[str, Any]) -> list[list[float]]:
    if "points" in geometry:
        return [[float(point[0]), float(point[1])] for point in geometry.get("points", [])]
    if "start" in geometry and "end" in geometry:
        return [
            [float(geometry["start"][0]), float(geometry["start"][1])],
            [float(geometry["end"][0]), float(geometry["end"][1])],
        ]
    return []
