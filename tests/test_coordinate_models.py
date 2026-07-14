import pytest


def test_coordinate_models_keep_systems_explicit() -> None:
    from coordinate.models import CoordinateSystem, Point2D, Point3D, BoundingBox

    normalized = Point2D(0.25, 0.4, CoordinateSystem.NORMALIZED)
    cad = Point3D(1000, 2000, 0, CoordinateSystem.CAD_WORLD)
    box = BoundingBox(0.2, 0.3, 0.4, 0.5, CoordinateSystem.NORMALIZED)

    assert normalized.to_list() == [0.25, 0.4]
    assert cad.to_list() == [1000.0, 2000.0, 0.0]
    assert box.to_points()[0].coordinate_system == CoordinateSystem.NORMALIZED


def test_normalized_point_rejects_out_of_range_values() -> None:
    from coordinate.models import CoordinateSystem, Point2D

    with pytest.raises(ValueError, match="normalized"):
        Point2D(1.25, 0.4, CoordinateSystem.NORMALIZED)


def test_mapping_result_records_confidence_and_calibration() -> None:
    from coordinate.models import CoordinateSystem, MappingResult, Point2D, Point3D

    result = MappingResult(
        original=Point2D(0.25, 0.4, CoordinateSystem.NORMALIZED),
        mapped=Point3D(1000, 2000, 0, CoordinateSystem.CAD_WORLD),
        mapping_confidence=0.98,
        calibration_id="cal_sample",
        transform_type="similarity",
    )

    assert result.to_dict()["mapping_confidence"] == 0.98
    assert result.to_dict()["calibration_id"] == "cal_sample"
    assert result.to_dict()["mapped"]["coordinate_system"] == "cad_world"
