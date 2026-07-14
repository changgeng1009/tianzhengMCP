from __future__ import annotations

from execution.models import ExecutionPlan, Operation
from execution.validation import (
    MAPPING_REQUIRED_MESSAGE,
    validate_mapped_execution_plan,
)


def _mapped_operation(**overrides):
    data = {
        "id": "op_line",
        "action": "add_line",
        "entity_type": "pipe",
        "geometry": {
            "coordinate_system": "cad_world",
            "start": [0.0, 0.0, 0.0],
            "end": [5000.0, 0.0, 0.0],
        },
        "layer": "0",
        "reason": "mapped cad_world line",
        "source_diff_id": "diff_line",
        "risk_level": "low",
        "requires_confirmation": True,
        "mapping_confidence": 0.98,
        "calibration_id": "cal_test",
        "transform_type": "affine",
    }
    data.update(overrides)
    return Operation(**data)


def _plan(operation):
    return ExecutionPlan(id="plan_mapped", operations=[operation])


def test_cad_world_coordinates_with_mapping_metadata_are_valid():
    result = validate_mapped_execution_plan(_plan(_mapped_operation()))

    assert result["valid"] is True
    assert result["message"] == "OK"


def test_normalized_coordinates_are_rejected_before_execution():
    operation = _mapped_operation(
        geometry={
            "coordinate_system": "normalized",
            "start": [0.0, 0.0, 0.0],
            "end": [0.5, 0.0, 0.0],
        }
    )

    result = validate_mapped_execution_plan(_plan(operation))

    assert result["valid"] is False
    assert result["message"] == MAPPING_REQUIRED_MESSAGE


def test_image_pixel_coordinates_are_rejected_before_execution():
    operation = _mapped_operation(
        geometry={
            "coordinate_system": "image_pixel",
            "start": [10.0, 10.0, 0.0],
            "end": [500.0, 10.0, 0.0],
        }
    )

    result = validate_mapped_execution_plan(_plan(operation))

    assert result["valid"] is False
    assert result["message"] == MAPPING_REQUIRED_MESSAGE


def test_missing_mapping_confidence_is_rejected():
    operation = _mapped_operation(mapping_confidence=None)

    result = validate_mapped_execution_plan(_plan(operation))

    assert result["valid"] is False
    assert result["message"] == MAPPING_REQUIRED_MESSAGE


def test_missing_calibration_id_is_rejected():
    operation = _mapped_operation(calibration_id="")

    result = validate_mapped_execution_plan(_plan(operation))

    assert result["valid"] is False
    assert result["message"] == MAPPING_REQUIRED_MESSAGE


def test_missing_transform_type_is_rejected():
    operation = _mapped_operation(transform_type="")

    result = validate_mapped_execution_plan(_plan(operation))

    assert result["valid"] is False
    assert result["message"] == MAPPING_REQUIRED_MESSAGE


def test_add_text_without_position_is_rejected_before_execution():
    operation = _mapped_operation(
        action="add_text",
        entity_type="Text",
        geometry={
            "coordinate_system": "cad_world",
            "text": "Missing position",
            "height": 250.0,
        },
    )

    result = validate_mapped_execution_plan(_plan(operation))

    assert result["valid"] is False
    assert result["message"] == MAPPING_REQUIRED_MESSAGE


def test_add_polyline_without_points_is_rejected_before_execution():
    operation = _mapped_operation(
        action="add_polyline",
        entity_type="Polyline",
        geometry={
            "coordinate_system": "cad_world",
            "points": [],
        },
    )

    result = validate_mapped_execution_plan(_plan(operation))

    assert result["valid"] is False
    assert result["message"] == MAPPING_REQUIRED_MESSAGE


def test_out_of_bounds_coordinates_mark_high_risk_and_block_by_default():
    operation = _mapped_operation(
        geometry={
            "coordinate_system": "cad_world",
            "start": [0.0, 0.0, 0.0],
            "end": [150000.0, 0.0, 0.0],
        }
    )

    result = validate_mapped_execution_plan(_plan(operation))

    assert result["valid"] is False
    assert result["requires_extra_confirmation"] is True
    assert operation.risk_level.value == "high"
