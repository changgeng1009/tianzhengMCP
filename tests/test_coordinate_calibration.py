import pytest


def test_two_point_calibration_builds_similarity_transform() -> None:
    from coordinate.calibration import CalibrationSet

    calibration = CalibrationSet.from_dict(
        {
            "id": "cal_2pt",
            "source_system": "normalized",
            "points": [
                {"reference_point": [0.0, 0.0], "cad_world_point": [100.0, 200.0, 0.0]},
                {"reference_point": [1.0, 0.0], "cad_world_point": [4100.0, 200.0, 0.0]},
            ],
        }
    )

    transform = calibration.build_transform()
    result = transform.map_xy(0.25, 0.5)

    assert result == [1100.0, 2200.0, 0.0]
    assert transform.transform_type == "similarity"


def test_three_point_calibration_builds_affine_transform() -> None:
    from coordinate.calibration import CalibrationSet

    calibration = CalibrationSet.from_dict(
        {
            "id": "cal_3pt",
            "source_system": "normalized",
            "points": [
                {"reference_point": [0.0, 0.0], "cad_world_point": [100.0, 200.0, 0.0]},
                {"reference_point": [1.0, 0.0], "cad_world_point": [4100.0, 200.0, 0.0]},
                {"reference_point": [0.0, 1.0], "cad_world_point": [100.0, 2200.0, 0.0]},
            ],
        }
    )

    transform = calibration.build_transform()
    result = transform.map_xy(0.25, 0.5)

    assert result == [1100.0, 1200.0, 0.0]
    assert transform.transform_type == "affine"


def test_calibration_requires_at_least_two_points() -> None:
    from coordinate.calibration import CalibrationSet

    calibration = CalibrationSet.from_dict(
        {
            "id": "bad_cal",
            "source_system": "normalized",
            "points": [
                {"reference_point": [0.0, 0.0], "cad_world_point": [100.0, 200.0, 0.0]},
            ],
        }
    )

    with pytest.raises(ValueError, match="at least 2"):
        calibration.build_transform()
