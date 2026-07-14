from __future__ import annotations

from math import hypot
from typing import Any


Point3D = tuple[float, float, float]


def entity_handle(entity: dict[str, Any]) -> str:
    return str(entity.get("handle") or entity.get("id") or "")


def semantic_type(entity: dict[str, Any]) -> str:
    return str(entity.get("semantic_type") or entity.get("type") or "")


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


def diameter_source(entity: dict[str, Any]) -> str | None:
    diameter = entity.get("diameter")
    if isinstance(diameter, dict):
        value = diameter.get("source")
        return str(value) if value is not None else None
    return None


def pipe_endpoints(entity: dict[str, Any]) -> tuple[Point3D, Point3D] | None:
    geometry = entity.get("inferred_geometry", {})
    start = point3d(geometry.get("start_point"))
    end = point3d(geometry.get("end_point"))
    if start is not None and end is not None:
        return start, end

    points = entity.get("geometry", {}).get("points", [])
    if isinstance(points, list) and len(points) >= 2:
        start = point_from_mapping(points[0])
        end = point_from_mapping(points[1])
        if start is not None and end is not None:
            return start, end
    return None


def entity_center(entity: dict[str, Any]) -> Point3D | None:
    geometry = entity.get("inferred_geometry", {})
    center = point3d(geometry.get("center"))
    if center is not None:
        return center

    bbox = entity.get("bounding_box")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 6:
        try:
            return (
                (float(bbox[0]) + float(bbox[3])) / 2,
                (float(bbox[1]) + float(bbox[4])) / 2,
                (float(bbox[2]) + float(bbox[5])) / 2,
            )
        except (TypeError, ValueError):
            return None
    return None


def point3d(value: Any) -> Point3D | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        z = float(value[2]) if len(value) >= 3 else 0.0
        return (float(value[0]), float(value[1]), z)
    except (TypeError, ValueError):
        return None


def point_from_mapping(value: Any) -> Point3D | None:
    if not isinstance(value, dict):
        return None
    try:
        return (float(value["x"]), float(value["y"]), float(value.get("z", 0.0)))
    except (KeyError, TypeError, ValueError):
        return None


def distance(a: Point3D, b: Point3D) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def point_to_list(point: Point3D) -> list[float]:
    return [float(point[0]), float(point[1]), float(point[2])]
