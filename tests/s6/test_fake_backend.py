from __future__ import annotations

from mcp_nextgen.s6.contracts import CadOperation, CadOperationPlan, EntitySelector, EntitySpec
from mcp_nextgen.s6.fake_backend import SyntheticCadBackend


def _op(operation_id, operation, kind=None, geometry=None, selector=None, parameters=None):
    return CadOperation(operation_id, operation, EntitySpec(kind, geometry) if kind else None, selector, parameters or {})


def test_fake_backend_create_query_transform_copy_delete_save_reopen_and_idempotency():
    backend = SyntheticCadBackend(job_id="job.1", document_token="token.1")
    plan = CadOperationPlan("job.1", "token.1", (
        _op("arc.1", "CREATE_ARC", "arc", {"center": [0, 0], "radius": 50, "start_angle": 0, "end_angle": 1}),
        _op("rect.1", "CREATE_RECTANGLE", "rectangle", {"corner_a": [0, 0], "corner_b": [100, 50]}),
        _op("text.1", "CREATE_TEXT", "text", {"text": "S6", "insertion_point": [0, 0], "height": 20}),
        _op("mtext.1", "CREATE_MTEXT", "mtext", {"content": "S6 MText", "insertion_point": [0, 100], "height": 20, "width": 300}),
        _op("block.def.1", "CREATE_BLOCK_DEFINITION", "block_definition", {"name": "S6_Block", "entities": [{"kind": "line"}]}),
        _op("block.ref.1", "INSERT_BLOCK_REFERENCE", "block_reference", {"block_name": "S6_Block", "insertion_point": [200, 0], "scale": 1}),
        _op("move.1", "MOVE_ENTITY", selector=EntitySelector(operation_id="arc.1"), parameters={"displacement": [10, 0]}),
        _op("copy.1", "COPY_ENTITY", selector=EntitySelector(operation_id="text.1"), parameters={"displacement": [10, 0]}),
        _op("rotate.1", "ROTATE_ENTITY", selector=EntitySelector(operation_id="rect.1"), parameters={"base_point": [0, 0], "angle": 0.5}),
        _op("scale.1", "SCALE_ENTITY", selector=EntitySelector(operation_id="mtext.1"), parameters={"base_point": [0, 0], "scale": 2}),
        _op("delete.1", "DELETE_ENTITY", selector=EntitySelector(operation_id="copy.1")),
        CadOperation("save.1", "SAVE_SYNTHETIC_DOCUMENT"), CadOperation("close.1", "CLOSE_SYNTHETIC_DOCUMENT"), CadOperation("reopen.1", "REOPEN_SYNTHETIC_DOCUMENT"),
    ))
    result = backend.execute_plan(plan)
    assert not result.rolled_back
    assert all(item.status != "FAILED" for item in result.results)
    assert {item.entity_type for item in backend.query()} == {"arc", "rectangle", "text", "mtext", "block_definition", "block_reference"}
    replay = backend.execute_plan(plan)
    assert all(item.status == "ALREADY_APPLIED" for item in replay.results[:11])
    assert {item.entity_type for item in backend.query()} == {"arc", "rectangle", "text", "mtext", "block_definition", "block_reference"}


def test_all_or_nothing_rolls_back_failure():
    backend = SyntheticCadBackend(job_id="job.1", document_token="token.1")
    plan = CadOperationPlan("job.1", "token.1", (
        _op("arc.1", "CREATE_ARC", "arc", {"center": [0, 0], "radius": 50, "start_angle": 0, "end_angle": 1}),
        _op("bad.1", "INSERT_BLOCK_REFERENCE", "block_reference", {"block_name": "Missing", "insertion_point": [0, 0], "scale": 1}),
    ), batch_policy="all_or_nothing")
    result = backend.execute_plan(plan)
    assert result.rolled_back
    assert backend.query() == []


def test_fake_backend_style_equivalence_conflict_and_dry_run_are_explicit():
    backend = SyntheticCadBackend(job_id="job.1", document_token="token.1")
    first = CadOperationPlan("job.1", "token.1", (
        CadOperation("layer.1", "ENSURE_LAYER", parameters={"layer": {"name": "CADAGENT_S6_MVP", "color_index": 3}}),
        CadOperation("textstyle.1", "ENSURE_TEXT_STYLE", parameters={"text_style": {"name": "CADAGENT_S6_TEXT"}}),
        CadOperation("dimstyle.1", "ENSURE_DIMENSION_STYLE", parameters={"dimension_style": {"name": "CADAGENT_S6_DIM"}}),
    ))
    assert [item.status for item in backend.execute_plan(first).results] == ["CREATED", "CREATED", "CREATED"]
    equivalent = CadOperationPlan("job.1", "token.1", (
        CadOperation("layer.2", "ENSURE_LAYER", parameters={"layer": {"name": "CADAGENT_S6_MVP", "color_index": 3}}),
    ))
    assert backend.execute_plan(equivalent).results[0].status == "ALREADY_EXISTS_EQUIVALENT"
    conflict = CadOperationPlan("job.1", "token.1", (
        CadOperation("layer.3", "ENSURE_LAYER", parameters={"layer": {"name": "CADAGENT_S6_MVP", "color_index": 4}}),
    ))
    assert backend.execute_plan(conflict).results[0].status == "CONFLICT"
    dry_run = CadOperationPlan("job.1", "token.1", (
        _op("line.dry", "CREATE_LINE", "line", {"start": [0, 0], "end": [10, 0]}),
    ), dry_run=True)
    result = backend.execute_plan(dry_run)
    assert result.dry_run and result.results[0].status == "CREATED"
    assert backend.query(EntitySelector(operation_id="line.dry")) == []
