from __future__ import annotations

import pytest


def test_normalize_point_accepts_two_or_three_values():
    from cad.geometry import normalize_point

    assert normalize_point([1, 2]) == [1.0, 2.0, 0.0]
    assert normalize_point((1, 2, 3)) == [1.0, 2.0, 3.0]


def test_coordinates_to_points_supports_flat_xy_and_xyz_values():
    from cad.geometry import coordinates_to_points

    assert coordinates_to_points([0, 0, 10, 0]) == [
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
    ]
    assert coordinates_to_points([0, 0, 1, 10, 0, 1]) == [
        [0.0, 0.0, 1.0],
        [10.0, 0.0, 1.0],
    ]


def test_bounding_box_from_points_uses_cad_world_coordinate_system():
    from cad.geometry import bounding_box_from_points

    assert bounding_box_from_points([[0, 2, 0], [10, -1, 0]]) == {
        "x_min": 0.0,
        "y_min": -1.0,
        "x_max": 10.0,
        "y_max": 2.0,
        "coordinate_system": "cad_world",
    }


def test_coordinates_to_points_rejects_unsupported_coordinate_count():
    from cad.geometry import coordinates_to_points

    with pytest.raises(ValueError):
        coordinates_to_points([0, 1, 2, 3, 4])
