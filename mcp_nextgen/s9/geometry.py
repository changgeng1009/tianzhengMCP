"""Deterministic geometry checks for S9 route validation.

Small on purpose. S9 needs to prove that constraints genuinely take part in planning and
verification; it is not the place to build a spatial engine. Everything here is 2D
axis-aligned in the XY plane, which is what the MVP scenario needs.
"""
from __future__ import annotations

from typing import Sequence

from mcp_nextgen.s9.contracts import Point

Segment = tuple[Point, Point]
Box = tuple[Point, Point]


def normalise_box(box: Box) -> tuple[float, float, float, float]:
    (x0, y0, _z0), (x1, y1, _z1) = box
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def point_in_box(point: Point, box: Box, *, tolerance: float = 0.0) -> bool:
    x0, y0, x1, y1 = normalise_box(box)
    return (x0 - tolerance <= point[0] <= x1 + tolerance
            and y0 - tolerance <= point[1] <= y1 + tolerance)


def segment_length(segment: Segment) -> float:
    (ax, ay, az), (bx, by, bz) = segment
    return ((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2) ** 0.5


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return (min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def segments_intersect(first: Segment, second: Segment) -> bool:
    a, b = first
    c, d = second
    o1, o2, o3, o4 = (_orientation(a, b, c), _orientation(a, b, d),
                      _orientation(c, d, a), _orientation(c, d, b))
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    # Collinear touching cases.
    if o1 == 0 and _on_segment(a, b, c):
        return True
    if o2 == 0 and _on_segment(a, b, d):
        return True
    if o3 == 0 and _on_segment(c, d, a):
        return True
    if o4 == 0 and _on_segment(c, d, b):
        return True
    return False


def segment_intersects_box(segment: Segment, box: Box) -> bool:
    """True when the segment enters the box, including merely touching its boundary.

    Touching counts: a pipe grazing the edge of a forbidden zone is not something S9 should
    quietly accept.
    """
    x0, y0, x1, y1 = normalise_box(box)
    a, b = segment
    if point_in_box(a, box) or point_in_box(b, box):
        return True
    corners = [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)]
    edges = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    return any(segments_intersect(segment, edge) for edge in edges)


def polyline_segments(points: Sequence[Point]) -> list[Segment]:
    return [(points[i], points[i + 1]) for i in range(len(points) - 1)]


def polyline_intersects_box(points: Sequence[Point], box: Box) -> bool:
    return any(segment_intersects_box(s, box) for s in polyline_segments(points))


def polyline_within_box(points: Sequence[Point], box: Box, *, tolerance: float = 0.0) -> bool:
    return all(point_in_box(p, box, tolerance=tolerance) for p in points)


def find_zero_length_segments(points: Sequence[Point], minimum: float) -> list[int]:
    return [i for i, s in enumerate(polyline_segments(points)) if segment_length(s) < minimum]


def find_duplicate_segments(points: Sequence[Point]) -> list[int]:
    """Indexes of segments that repeat an earlier one, in either direction."""
    seen: set[frozenset[Point]] = set()
    duplicates: list[int] = []
    for index, (a, b) in enumerate(polyline_segments(points)):
        key = frozenset((a, b))
        if key in seen:
            duplicates.append(index)
        seen.add(key)
    return duplicates


def distance(a: Point, b: Point) -> float:
    return segment_length((a, b))
