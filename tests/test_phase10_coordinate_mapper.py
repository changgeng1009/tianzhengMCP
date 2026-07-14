from __future__ import annotations


def test_coordinate_mapper_normalizes_points_and_bbox() -> None:
    from mcp.vision.coordinate_mapper import CoordinateMapper

    mapper = CoordinateMapper(image_width=200, image_height=100)

    assert mapper.image_to_normalized([100, 50]) == [0.5, 0.5]
    assert mapper.normalized_to_image([0.25, 0.75]) == [50.0, 75.0]
    assert mapper.image_bbox_to_normalized([0, 0, 100, 50]) == [0.0, 0.0, 0.5, 0.5]
    assert mapper.metadata() == {
        "coordinate_space": "normalized_image",
        "image_size": [200, 100],
        "scale_status": "unknown",
    }

