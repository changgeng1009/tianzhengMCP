from __future__ import annotations


def test_geometry_utils_distance_length_overlap_and_duplicate() -> None:
    from mcp.repair_actions.geometry_utils import (
        bbox_overlap_ratio,
        distance_point_to_point,
        distance_segment_to_segment,
        is_near_duplicate_geometry,
        normalize_segment_direction,
        polyline_length,
    )

    assert distance_point_to_point([0, 0], [3, 4]) == 5.0
    assert distance_segment_to_segment([[0, 0], [10, 0]], [[0, 1], [10, 1]]) == 1.0
    assert bbox_overlap_ratio([0, 0, 10, 10], [5, 5, 15, 15]) == 0.25
    assert polyline_length([[0, 0], [3, 4], [6, 4]]) == 8.0
    assert normalize_segment_direction([[10, 0], [0, 0]]) == [[0.0, 0.0], [10.0, 0.0]]
    assert is_near_duplicate_geometry(
        {"type": "polyline", "points": [[0, 0], [10, 0]]},
        {"type": "polyline", "points": [[0.5, 0], [10.5, 0]]},
        tolerance=1.0,
    )

