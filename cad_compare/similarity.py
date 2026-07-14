from __future__ import annotations

from math import hypot
from typing import Any


def points(entity: dict[str, Any]) -> list[dict[str, float]]:
    return [
        {"x": float(point.get("x", 0.0)), "y": float(point.get("y", 0.0))}
        for point in entity.get("geometry", {}).get("points", [])
        if isinstance(point, dict)
    ]


def point_distance(a: dict[str, float], b: dict[str, float]) -> float:
    return hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def max_point_distance(a_points: list[dict[str, float]], b_points: list[dict[str, float]]) -> float:
    if len(a_points) != len(b_points) or not a_points:
        return float("inf")
    forward = max(point_distance(a, b) for a, b in zip(a_points, b_points, strict=True))
    reverse = max(point_distance(a, b) for a, b in zip(a_points, reversed(b_points), strict=True))
    return min(forward, reverse)


def entity_text(entity: dict[str, Any]) -> str:
    return str(entity.get("properties", {}).get("text") or "").strip()
