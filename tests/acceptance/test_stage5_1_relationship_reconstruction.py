from __future__ import annotations

from pathlib import Path

from mcp.orchestration import stage5_1_relationship_reconstruction as stage51
from mcp.recognition import stage5_1_relationship_probe as probe
from mcp.recognition import stage5_1_component_builder as components
from mcp.acceptance import stage5_1_valve_component_diagnostics as valve_diagnostics
from mcp.acceptance import stage5_1_remaining_capability_poc as remaining_poc


def test_stage51_safety_defaults_protect_sources_and_production() -> None:
    safety = stage51.safety_flags()
    assert safety["source_reference_opened"] is False
    assert safety["source_target_opened"] is False
    assert safety["source_modified"] is False
    assert safety["whole_modelspace_copyobjects_used"] is False
    assert safety["sendcommand_used"] is False
    assert safety["production_d1_allowed"] is False


def test_stage51_paths_create_required_directories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(stage51, "RUNS_ROOT", tmp_path)
    paths = stage51.Stage51Paths.build("stage5_1_test")
    paths.create()
    for field, value in paths.__dict__.items():
        if field != "run_id":
            assert value.is_dir()


def test_stage51_checkpoint_sequence_is_relationship_aware() -> None:
    assert stage51.CHECKPOINTS[:4] == (
        "INPUT_AND_HISTORY_FROZEN", "RELATIONSHIP_GRAPH_COMPLETE", "COMPONENTS_COMPLETE", "VALVE_RELATIONSHIP_VERIFIED",
    )
    assert stage51.CHECKPOINTS[-1] == "FINALIZED"


def test_relationship_source_never_promotes_geometry_to_native() -> None:
    assert probe.relation_type("TDbPipeValve", "TDbPipe", 0.0) == "VALVE_BELONGS_TO_PIPE"
    assert probe.relation_type("TDbPipeValve", "TDbPipe", 101.0) is None


def test_relation_component_builder_uses_only_topology_edges() -> None:
    nodes = ["a", "b", "c"]
    edges = [
        {"source_id": "a", "target_id": "b", "edge_type": "CONNECTED_TO"},
        {"source_id": "b", "target_id": "c", "edge_type": "ANNOTATES_OBJECT"},
    ]
    components = probe._component_sets(nodes, edges)
    assert ["a", "b"] in components
    assert ["c"] in components


def test_component_risk_blocks_valve_without_pipe() -> None:
    risk, reasons = components._component_risk([
        {"object_name": "TDbPipeValve", "native_reference_candidates": []},
    ])
    assert risk == "BLOCKED_RELATIONSHIP_EVIDENCE"
    assert reasons


def test_component_order_is_not_object_name_bulk_sort() -> None:
    values = [
        {"component_id": "pipe", "required_object_ids": ["p"], "object_name_counts": {"TDbPipe": 1}},
        {"component_id": "equipment", "required_object_ids": ["e"], "object_name_counts": {"TDbPump": 1}},
    ]
    assert components._component_order(values) == ["equipment", "pipe"]


def test_valve_subject_requires_two_pipes_and_fitting() -> None:
    graph = {
        "nodes": [
            {"task_id": "v", "reference_handle": "1", "object_name": "TDbPipeValve", "target_wcs_bbox": [[4, -1, 0], [6, 1, 0]], "layer": "VALVE_消防"},
            {"task_id": "p1", "reference_handle": "2", "object_name": "TDbPipe", "target_wcs_bbox": [[0, 0, 0], [5, 0, 0]]},
            {"task_id": "p2", "reference_handle": "3", "object_name": "TDbPipe", "target_wcs_bbox": [[5, 0, 0], [10, 0, 0]]},
            {"task_id": "f", "reference_handle": "4", "object_name": "TDbPipeFitting", "target_wcs_bbox": [[5, 0, 0], [5, 0, 0]]},
        ],
        "edges": [
            {"source_id": "v", "target_id": "p1", "edge_type": "VALVE_BELONGS_TO_PIPE"},
            {"source_id": "v", "target_id": "p2", "edge_type": "VALVE_BELONGS_TO_PIPE"},
            {"source_id": "f", "target_id": "p1", "edge_type": "FITTING_JOINS_PIPE"},
        ],
        "components": [{"component_id": "c", "node_ids": ["v", "p1", "p2", "f"]}],
    }
    subject = valve_diagnostics.select_valve_diagnostic_subject(graph)
    assert subject["valve"]["task_id"] == "v"
    assert len(subject["pipes"]) == 2
    assert len(subject["fittings"]) == 1


def test_valve_variants_are_six_independent_packages() -> None:
    subject = {
        "valve": {"task_id": "v", "reference_handle": "1"},
        "pipes": [{"task_id": "p1", "reference_handle": "2"}, {"task_id": "p2", "reference_handle": "3"}],
        "fittings": [{"task_id": "f", "reference_handle": "4"}],
        "component": {"node_ids": ["v", "p1", "p2", "f"]},
    }
    graph = {"nodes": [subject["valve"], *subject["pipes"], *subject["fittings"]]}
    variants = valve_diagnostics.build_valve_variants(subject, graph)
    assert len(variants) == 6
    assert len({variant["variant_id"] for variant in variants}) == 6
    assert variants[0]["expected_handles"] == ["1"]


def test_remaining_capability_types_cover_devices_and_annotations() -> None:
    assert set(remaining_poc.REMAINING_TYPES) == {
        "TDbPump", "TDbEquipment", "TDbWaterTank", "TDbDimension2", "TDbVPipeDim", "TDbSymbMultiLeader",
    }


def test_property_evidence_does_not_treat_missing_required_fields_as_verified() -> None:
    package = {
        "primary": {
            "task_id": "pump", "reference_handle": "1", "object_name": "TDbPump", "layer": "PUMP",
            "custom_properties": {"Width": 1000}, "readable_properties": ["Width"], "target_wcs_bbox": [[0, 0, 0], [1, 1, 0]],
        },
        "dependencies": [],
        "nodes": [{
            "task_id": "pump", "reference_handle": "1", "object_name": "TDbPump", "layer": "PUMP",
            "custom_properties": {"Width": 1000}, "readable_properties": ["Width"], "target_wcs_bbox": [[0, 0, 0], [1, 1, 0]],
        }],
    }
    records = [{"handle": "A", "object_name": "TDbPump", "layer": "PUMP", "bbox": [[0, 0, 0], [1, 1, 0]]}]
    semantics = {"pump": {"custom_properties": {"Width": 1000}, "text": None, "measurement": None}}
    copy_map = {"idpairs": [{"source_handle": "1", "IsCloned": True}]}
    result = remaining_poc.evaluate_capability_package(package, records, semantics, copy_map)
    assert result["core_passed"] is True
    assert result["required_fields_complete"] is False


def test_test_evidence_gate_rejects_empty_or_failed_results() -> None:
    assert stage51._tests_passed({"full": "123 passed"}) is True
    assert stage51._tests_passed({}) is False
    assert stage51._tests_passed({"full": "1 failed, 122 passed"}) is False
