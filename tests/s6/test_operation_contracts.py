from __future__ import annotations

import math

import pytest

from mcp_nextgen.s6.contracts import (
    BoundingBox, CadOperation, CadOperationPlan, CadOperationValidationError,
    CadOperationResult, DimensionStyleSpec, EntitySelector, EntitySnapshot, EntitySpec, GeometryTolerance,
    LayerSpec, LineweightSpec, Point3, TextStyleSpec, Transformation, Vector3,
)


def _entity(kind: str, geometry: dict):
    return EntitySpec(kind, geometry)


@pytest.mark.parametrize(("kind", "geometry"), [
    ("arc", {"center": [0, 0], "radius": 100, "start_angle": 0, "end_angle": 1}),
    ("rectangle", {"corner_a": [0, 0], "corner_b": [10, 20]}),
    ("text", {"text": "S6", "insertion_point": [0, 0], "height": 100}),
    ("mtext", {"content": "S6\\nMText", "insertion_point": [0, 0], "height": 100, "width": 500}),
    ("block_definition", {"name": "S6_Block", "entities": [{"kind": "line"}]}),
    ("block_reference", {"block_name": "S6_Block", "insertion_point": [0, 0], "scale": 1}),
])
def test_s6_entity_specs_are_pure_json_contracts(kind, geometry):
    value = _entity(kind, geometry)
    assert value.to_dict()["entity_type"] == kind


def test_nonfinite_and_degenerate_geometry_fail_closed():
    with pytest.raises(CadOperationValidationError):
        _entity("arc", {"center": [0, 0], "radius": math.nan, "start_angle": 0, "end_angle": 1})
    with pytest.raises(CadOperationValidationError):
        _entity("rectangle", {"corner_a": [0, 0], "corner_b": [0, 1]})
    with pytest.raises(CadOperationValidationError):
        _entity("text", {"text": "", "insertion_point": [0, 0], "height": 1})


def test_plan_hash_and_task_projection_are_stable():
    op = CadOperation("arc.1", "CREATE_ARC", _entity("arc", {"center": [0, 0], "radius": 10, "start_angle": 0, "end_angle": 1}))
    first = CadOperationPlan("job.1", "token.1", (op,))
    second = CadOperationPlan("job.1", "token.1", (op,))
    assert first.plan_hash == second.plan_hash
    assert first.to_execution_tasks()[0]["task_id"] == "arc.1"


def test_plan_rejects_duplicate_or_unknown_dependencies():
    op = CadOperation("arc.1", "CREATE_ARC", _entity("arc", {"center": [0, 0], "radius": 10, "start_angle": 0, "end_angle": 1}))
    with pytest.raises(CadOperationValidationError):
        CadOperationPlan("job.1", "token.1", (op, op))
    orphan = CadOperation("arc.2", "CREATE_ARC", _entity("arc", {"center": [0, 0], "radius": 10, "start_angle": 0, "end_angle": 1}), depends_on=("missing.1",))
    with pytest.raises(CadOperationValidationError):
        CadOperationPlan("job.1", "token.1", (orphan,))


def test_modification_operations_require_scoped_selector_and_parameters():
    with pytest.raises(CadOperationValidationError):
        CadOperation("move.1", "MOVE_ENTITY")
    move = CadOperation("move.1", "MOVE_ENTITY", selector=EntitySelector(operation_id="arc.1"), parameters={"displacement": [1, 2, 0]})
    assert move.parameters["displacement"]["x"] == "1"


def test_geometry_models_are_serializable_and_fail_closed():
    box = BoundingBox(Point3(0, 0), Point3(1, 2, 3))
    assert box.to_dict()["maximum"]["z"] == 3
    assert GeometryTolerance().close(1.0, 1.0 + 1e-10)
    assert Transformation(Vector3(1, 2), rotation_radians=0.5, scale=2).to_dict()["scale"] == 2
    with pytest.raises(CadOperationValidationError):
        BoundingBox(Point3(1, 0), Point3(0, 1))
    with pytest.raises(CadOperationValidationError):
        Transformation(scale=0)


def test_style_models_reject_paths_and_invalid_values():
    assert LayerSpec("CADAGENT_S6_MVP", color_index=3).to_dict()["color_index"] == 3
    assert TextStyleSpec("S6_Text").font == "txt.shx"
    assert DimensionStyleSpec("S6_Dim").name == "S6_Dim"
    assert LineweightSpec(-1).value == -1
    with pytest.raises(CadOperationValidationError):
        TextStyleSpec("S6_Text", r"C:\fonts\unsafe.shx")
    with pytest.raises(CadOperationValidationError):
        LayerSpec("S6", color_index=0)


def test_operation_result_round_trips_through_append_only_json_journal():
    result = CadOperationResult("arc.1", "CREATED", (EntitySnapshot("A1", "arc", "CADAGENT_S6_MVP", {"center":{"x":0,"y":0,"z":0},"radius":2,"start_angle":0,"end_angle":1}, "arc.1"),))
    restored = CadOperationResult.from_dict(result.to_dict())
    assert restored.to_dict() == result.to_dict()
