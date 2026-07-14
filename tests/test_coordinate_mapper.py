from copy import deepcopy


def _plan() -> dict:
    return {
        "id": "plan_test",
        "confirmed": False,
        "previewed": False,
        "active_document": None,
        "risk_level": "low",
        "operation_count": 2,
        "operations": [
            {
                "id": "op_line",
                "action": "add_line",
                "entity_type": "pipe",
                "geometry": {
                    "coordinate_system": "normalized",
                    "start": [0.0, 0.0, 0.0],
                    "end": [1.0, 0.0, 0.0],
                },
                "layer": "0",
                "reason": "测试线。",
                "source_diff_id": "diff_line",
                "risk_level": "low",
                "requires_confirmation": True,
                "status": "pending",
                "executable": True,
                "result": {},
            },
            {
                "id": "op_poly",
                "action": "add_polyline",
                "entity_type": "window",
                "geometry": {
                    "coordinate_system": "normalized",
                    "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
                },
                "layer": "0",
                "reason": "测试多段线。",
                "source_diff_id": "diff_poly",
                "risk_level": "low",
                "requires_confirmation": True,
                "status": "pending",
                "executable": True,
                "result": {},
            },
            {
                "id": "op_move",
                "action": "move_entity",
                "entity_type": "fixture",
                "geometry": {
                    "coordinate_system": "normalized",
                    "from": {"x_min": 0.0, "y_min": 0.0, "x_max": 0.1, "y_max": 0.1},
                    "to": {"x_min": 0.2, "y_min": 0.3, "x_max": 0.4, "y_max": 0.5},
                },
                "layer": "0",
                "reason": "测试移动。",
                "source_diff_id": "diff_move",
                "risk_level": "medium",
                "requires_confirmation": True,
                "status": "pending",
                "executable": False,
                "result": {},
            },
        ],
    }


def _calibration() -> dict:
    return {
        "id": "cal_2pt",
        "source_system": "normalized",
        "reasonable_cad_bounds": {"x_min": -1000, "y_min": -1000, "x_max": 10000, "y_max": 10000},
        "points": [
            {"reference_point": [0.0, 0.0], "cad_world_point": [100.0, 200.0, 0.0]},
            {"reference_point": [1.0, 0.0], "cad_world_point": [4100.0, 200.0, 0.0]},
        ],
    }


def test_mapper_preserves_original_coordinates_and_writes_cad_world() -> None:
    from coordinate.calibration import CalibrationSet
    from coordinate.mapper import ExecutionPlanCoordinateMapper

    mapped = ExecutionPlanCoordinateMapper(
        CalibrationSet.from_dict(_calibration())
    ).map_execution_plan(_plan())

    line = mapped["operations"][0]
    assert line["geometry"]["original_coordinate_system"] == "normalized"
    assert line["geometry"]["original_geometry"]["start"] == [0.0, 0.0, 0.0]
    assert line["geometry"]["coordinate_system"] == "cad_world"
    assert line["geometry"]["start"] == [100.0, 200.0, 0.0]
    assert line["geometry"]["end"] == [4100.0, 200.0, 0.0]
    assert line["mapping_confidence"] == 0.95
    assert line["calibration_id"] == "cal_2pt"
    assert line["transform_type"] == "similarity"


def test_mapper_converts_move_from_to_boxes_to_cad_world_points() -> None:
    from coordinate.calibration import CalibrationSet
    from coordinate.mapper import ExecutionPlanCoordinateMapper

    mapped = ExecutionPlanCoordinateMapper(
        CalibrationSet.from_dict(_calibration())
    ).map_execution_plan(_plan())

    move = mapped["operations"][2]
    assert move["geometry"]["from_points"] == [
        [100.0, 200.0, 0.0],
        [500.0, 200.0, 0.0],
        [500.0, 600.0, 0.0],
        [100.0, 600.0, 0.0],
    ]
    assert move["geometry"]["to_points"] == [
        [900.0, 1400.0, 0.0],
        [1700.0, 1400.0, 0.0],
        [1700.0, 2200.0, 0.0],
        [900.0, 2200.0, 0.0],
    ]


def test_mapper_marks_out_of_bounds_as_high_risk() -> None:
    from coordinate.calibration import CalibrationSet
    from coordinate.mapper import ExecutionPlanCoordinateMapper

    calibration = _calibration()
    calibration["reasonable_cad_bounds"] = {"x_min": 0, "y_min": 0, "x_max": 500, "y_max": 500}

    mapped = ExecutionPlanCoordinateMapper(
        CalibrationSet.from_dict(calibration)
    ).map_execution_plan(_plan())

    assert mapped["risk_level"] == "high"
    assert mapped["operations"][0]["risk_level"] == "high"
    assert "outside reasonable CAD bounds" in mapped["operations"][0]["mapping_warnings"][0]


def test_mapper_rejects_uncalibrated_execution_plan() -> None:
    from coordinate.mapper import ExecutionPlanCoordinateMapper

    mapper = ExecutionPlanCoordinateMapper(calibration=None)

    result = mapper.map_execution_plan(deepcopy(_plan()))

    assert result["success"] is False
    assert result["message"] == "Coordinate mapping is not calibrated."
