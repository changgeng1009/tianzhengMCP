from __future__ import annotations

from pathlib import Path

from mcp.orchestration import stage5_mvp2 as stage5
from mcp.acceptance import stage5_2_native_clone_poc as poc
from mcp.acceptance import stage5_2_component_clone_poc as component_poc


def _paths(tmp_path: Path) -> stage5.Stage5Paths:
    root = tmp_path / "stage5_test"
    paths = stage5.Stage5Paths(
        "stage5_test", root, root / "copies", root / "archive", root / "inventory",
        root / "poc", root / "qa", root / "convergence", root / "previews",
    )
    paths.create()
    return paths


def test_stage5_safety_defaults_prohibit_writes_and_commands() -> None:
    safety = stage5._safety()
    assert safety["autocad_connected"] is False
    assert safety["dwg_modified"] is False
    assert safety["dwg_saved"] is False
    assert safety["copyobjects_used"] is False
    assert safety["sendcommand_used"] is False
    assert safety["tianzheng_command_executed"] is False
    assert safety["production_d1_allowed"] is False


def test_bbox_distance_detects_intersection_and_separation() -> None:
    assert stage5._bbox_distance([[0, 0, 0], [10, 10, 0]], [[5, 5, 0], [15, 15, 0]]) == 0
    assert stage5._bbox_distance([[0, 0, 0], [10, 10, 0]], [[13, 14, 0], [20, 20, 0]]) == 5


def test_semantic_groups_cover_fixed_sample_types() -> None:
    assert stage5._semantic_group("TDbPipe") == "pipe"
    assert stage5._semantic_group("TDbPipeValve") == "valve"
    assert stage5._semantic_group("TDbPipeFitting") == "fitting"
    assert stage5._semantic_group("TDbPump") == "pump"
    assert stage5._semantic_group("TDbWaterTank") == "water_tank"
    assert stage5._semantic_group("TDbDimension2") == "professional_annotation"


def test_topological_order_places_dependencies_first() -> None:
    nodes = ["pump", "pipe", "valve"]
    edges = [
        {"dependency_id": "pump", "dependent_id": "pipe"},
        {"dependency_id": "pipe", "dependent_id": "valve"},
    ]
    order, cycles = stage5._topological_order(nodes, edges, {"pump": 10, "pipe": 20, "valve": 40})
    assert cycles == []
    assert order == ["pump", "pipe", "valve"]


def test_topological_cycle_is_reported_not_hidden() -> None:
    nodes = ["a", "b"]
    edges = [
        {"dependency_id": "a", "dependent_id": "b"},
        {"dependency_id": "b", "dependent_id": "a"},
    ]
    order, cycles = stage5._topological_order(nodes, edges, {"a": 1, "b": 2})
    assert set(order) == {"a", "b"}
    assert cycles == [["a", "b"]]


def test_inventory_requires_stage5_0_pass(tmp_path: Path) -> None:
    result = stage5.build_tdb_inventory(_paths(tmp_path))
    assert result["status"] == "BLOCKED_STAGE5_0_NOT_PASS"
    assert result["safety_flags"]["autocad_connected"] is False


def test_pipe_poc_candidate_requires_real_axis_geometry_and_properties() -> None:
    valid = {
        "task_id": "pipe_1", "classification": "REQUIRED_MISSING", "object_name": "TDbPipe",
        "target_wcs_geometry": {"bbox": [[10, 20, 0], [30, 20, 0]]},
        "sys_type": "消防", "dn": 100, "connected_objects": [],
    }
    invalid = {
        **valid, "task_id": "pipe_0", "target_wcs_geometry": {"bbox": [[0, 0, 0], [0, 0, 0]]},
    }
    assert poc.select_pipe_poc_candidate([invalid, valid])["task_id"] == "pipe_1"


def test_pipe_record_rejects_acdbline_degradation() -> None:
    candidate = {
        "target_wcs_geometry": {"bbox": [[10, 20, 0], [30, 20, 0]]},
        "sys_type": "消防", "dn": 100, "layer": "PIPE-消防",
    }
    record = {
        "object_name": "AcDbLine", "bbox": [[10, 20, 0], [30, 20, 0]], "layer": "PIPE-消防",
        "attributes": {"sys_type": "消防", "dn_diameter": 100},
    }
    qa = poc.validate_pipe_record(record, candidate)
    assert qa["passed"] is False
    assert qa["native_type_preserved"] is False


def test_pipe_record_requires_system_dn_geometry_and_layer() -> None:
    candidate = {
        "target_wcs_geometry": {"bbox": [[10, 20, 0], [30, 20, 0]]},
        "sys_type": "消防", "dn": 100, "layer": "PIPE-消防",
    }
    record = {
        "object_name": "TDbPipe", "bbox": [[10, 20, 0], [30, 20, 0]], "layer": "PIPE-消防",
        "attributes": {"sys_type": "消防", "dn_diameter": 100},
    }
    assert poc.validate_pipe_record(record, candidate)["passed"] is True
    assert poc.validate_pipe_record({**record, "bbox": [[0, 0, 0], [1, 0, 0]]}, candidate)["passed"] is False


def test_component_bundle_requires_native_type_and_attached_pipe() -> None:
    pipe = {
        "task_id": "pipe", "object_name": "TDbPipe", "layer": "PIPE-消防", "sys_type": "消防", "dn": 100,
        "target_wcs_geometry": {"bbox": [[0, 0, 0], [10, 0, 0]]},
    }
    valve = {
        "task_id": "valve", "object_name": "TDbPipeValve", "layer": "VALVE_消防",
        "target_wcs_geometry": {"bbox": [[4, -1, 0], [6, 1, 0]]},
    }
    records = [
        {"handle": "1", "object_name": "TDbPipe", "layer": "PIPE-消防", "bbox": [[0, 0, 0], [10, 0, 0]], "attributes": {"sys_type": "消防", "dn_diameter": 100}},
        {"handle": "2", "object_name": "TDbPipeValve", "layer": "VALVE_消防", "bbox": [[4, -1, 0], [6, 1, 0]], "attributes": {}},
    ]
    assert component_poc.validate_component_bundle(valve, [pipe], records)["passed"] is True
    degraded = [records[0], {**records[1], "object_name": "AcDbBlockReference"}]
    assert component_poc.validate_component_bundle(valve, [pipe], degraded)["passed"] is False


def test_selective_clone_plan_never_allows_whole_modelspace() -> None:
    source = Path(stage5.__file__).read_text(encoding="utf-8")
    assert '"whole_modelspace_clone_allowed": False' in source
    assert '"unrelated_design_dependencies_allowed": False' in source


def test_stage5_never_enables_production_d1() -> None:
    assert stage5._safety()["production_d1_allowed"] is False
