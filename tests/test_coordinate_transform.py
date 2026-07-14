from coordinate.models import CoordinateSystem, Point2D
from coordinate.transform import CoordinateTransform


def test_normalized_to_cad_world_with_similarity_transform() -> None:
    transform = CoordinateTransform.similarity(
        source_system=CoordinateSystem.NORMALIZED,
        scale=4000.0,
        rotation_degrees=0.0,
        translate=(100.0, 200.0),
        calibration_id="cal_2pt",
    )

    result = transform.map_point(Point2D(0.25, 0.5, CoordinateSystem.NORMALIZED))

    assert result.mapped.to_list() == [1100.0, 2200.0, 0.0]
    assert result.transform_type == "similarity"


def test_image_pixel_to_normalized_uses_image_size() -> None:
    transform = CoordinateTransform.image_to_normalized(
        image_width=2000,
        image_height=1000,
        calibration_id="image_size",
    )

    result = transform.map_point(Point2D(500, 250, CoordinateSystem.IMAGE_PIXEL))

    assert result.mapped.to_list() == [0.25, 0.25, 0.0]
    assert result.mapped.coordinate_system == CoordinateSystem.NORMALIZED


def test_image_pixel_to_cad_world_composes_image_and_cad_transform() -> None:
    image_transform = CoordinateTransform.image_to_normalized(2000, 1000, "img")
    cad_transform = CoordinateTransform.similarity(
        source_system=CoordinateSystem.NORMALIZED,
        scale=4000.0,
        rotation_degrees=0.0,
        translate=(100.0, 200.0),
        calibration_id="cal_2pt",
    )

    normalized = image_transform.map_point(Point2D(500, 250, CoordinateSystem.IMAGE_PIXEL)).mapped
    result = cad_transform.map_point(Point2D(normalized.x, normalized.y, CoordinateSystem.NORMALIZED))

    assert result.mapped.to_list() == [1100.0, 1200.0, 0.0]


def test_cad_world_to_normalized_inverse_similarity() -> None:
    transform = CoordinateTransform.similarity(
        source_system=CoordinateSystem.NORMALIZED,
        scale=4000.0,
        rotation_degrees=0.0,
        translate=(100.0, 200.0),
        calibration_id="cal_2pt",
    )

    result = transform.inverse_map_point(1100.0, 2200.0)

    assert result.to_list() == [0.25, 0.5]
