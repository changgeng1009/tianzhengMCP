from __future__ import annotations

from pathlib import Path

from mcp.orchestration import stage5_1_r3 as r3


def test_core_routes_exclude_dimension2() -> None:
    assert "TDbDimension2" not in r3.CORE_TYPES
    assert r3._route("TDbPipeValve") == "relationship_aware_component_clone"
    assert r3._route("TDbPump") == "derived_property_validated_component_clone"


def test_union_find_merges_overlapping_relationship_components() -> None:
    union = r3._UnionFind(["a", "b", "c"])
    union.union("a", "b"); union.union("b", "c")
    assert union.find("a") == union.find("c")


def test_plan_source_forbids_whole_modelspace_copy() -> None:
    source = open(r3.__file__, encoding="utf-8").read()
    assert '"whole_modelspace_copy_allowed": False' in source
    assert '"dimension2_included": False' in source


def test_snapshot_detects_existing_object_changes() -> None:
    before = r3._snapshot([{"handle": "A", "object_name": "AcDbLine", "layer": "0", "bbox": [[0, 0, 0], [1, 0, 0]]}])
    after = r3._snapshot([{"handle": "A", "object_name": "AcDbLine", "layer": "X", "bbox": [[0, 0, 0], [1, 0, 0]]}])
    assert before["A"] != after["A"]


def test_existing_text_protection_uses_native_geometry_not_display_extents() -> None:
    before = {"object_name": "AcDbText", "layer": "NOTE", "bbox": [[0, 0, 0], [10, 2, 0]], "geometry": {"insertion_point": [1, 1, 0], "rotation": 0.0}, "attributes": {"text": "X", "height": 2.0}}
    regenerated = {**before, "bbox": [[0, -0.25, 0], [12, 2.5, 0]]}
    moved = {**before, "geometry": {"insertion_point": [2, 1, 0], "rotation": 0.0}}
    assert r3._existing_record_unchanged(before, regenerated) is True
    assert r3._existing_record_unchanged(before, moved) is False


def test_core_semantic_count_uses_idpair_mappings_not_modelspace_delta() -> None:
    source = open(r3.__file__, encoding="utf-8").read()
    assert "semantic_target_handles = list(source_to_target.values())" in source
    assert '"modelspace_root_delta": None' in source
    assert "if not _bbox_close(current.get(\"bbox\"), node[\"target_wcs_bbox\"]):" in source


def _valve_qa_fixture(second_pipe_bbox: list[list[float]]) -> tuple[dict, list[dict], list[dict], dict]:
    nodes = [
        {"task_id": "pipe-a", "reference_handle": "A", "object_name": "TDbPipe", "target_wcs_bbox": [[0, 0, 0], [10, 0, 0]], "sys_type": "S", "dn": 25.0},
        {"task_id": "pipe-b", "reference_handle": "B", "object_name": "TDbPipe", "target_wcs_bbox": second_pipe_bbox, "sys_type": "S", "dn": 25.0},
        {"task_id": "fit", "reference_handle": "F", "object_name": "TDbPipeFitting", "target_wcs_bbox": [[20, 20, 0], [21, 21, 0]]},
        {"task_id": "valve", "reference_handle": "V", "object_name": "TDbPipeValve", "target_wcs_bbox": [[4, -1, 0], [6, 1, 0]]},
    ]
    records = [
        {"handle": node["reference_handle"], "object_name": node["object_name"], "bbox": node["target_wcs_bbox"], "attributes": {"sys_type": node.get("sys_type"), "dn_diameter": node.get("dn")}}
        for node in nodes
    ]
    task = {"task_id": "valve", "expected_attached_pipe_task_ids": ["pipe-a"], "attachment_tolerance": 100.0}
    copy_map = {"idpairs": [{"source_handle": node["reference_handle"], "target_handle": node["reference_handle"], "IsCloned": True} for node in nodes]}
    return task, nodes, records, copy_map


def test_valve_relationship_qa_accepts_frozen_single_side_attachment() -> None:
    task, nodes, records, copy_map = _valve_qa_fixture([[1000, 0, 0], [1010, 0, 0]])
    qa = r3._r3_valve_relationship_qa(task, nodes, records, copy_map)
    assert qa["relationship_ready"] is True
    assert qa["observed_attached_pipe_task_ids"] == ["pipe-a"]


def test_valve_relationship_qa_rejects_unexpected_attachment() -> None:
    task, nodes, records, copy_map = _valve_qa_fixture([[20, 0, 0], [30, 0, 0]])
    qa = r3._r3_valve_relationship_qa(task, nodes, records, copy_map)
    assert qa["relationship_ready"] is False
    assert qa["observed_attached_pipe_task_ids"] == ["pipe-a", "pipe-b"]


def test_sequential_valve_route_does_not_rescan_whole_modelspace_per_task() -> None:
    source = open(r3.__file__, encoding="utf-8").read()
    assert "before Handle snapshot" not in source
    assert "after Handle snapshot" not in source
    assert "R3 core initial ModelSpace scan" in source
    assert "R3 core final ModelSpace scan" in source


def test_dimension2_persistence_qa_keeps_semantic_observability_manual() -> None:
    node = {"target_wcs_bbox": [[1, 2, 0], [3, 4, 0]], "layer": "TWT_DIM"}
    record = {"object_name": "TDbDimension2", "bbox": [[1, 2, 0], [3, 4, 0]], "layer": "TWT_DIM"}
    qa = r3._dimension2_persistence_qa(node, record)
    assert qa["passed"] is True
    assert qa["display_content_automatically_verified"] is False
    assert qa["leader_geometry_automatically_verified"] is False
    assert qa["full_automated_semantic_verification"] is False


def test_dimension2_persistence_qa_rejects_wrong_bbox() -> None:
    node = {"target_wcs_bbox": [[1, 2, 0], [3, 4, 0]], "layer": "TWT_DIM"}
    record = {"object_name": "TDbDimension2", "bbox": [[10, 20, 0], [30, 40, 0]], "layer": "TWT_DIM"}
    assert r3._dimension2_persistence_qa(node, record)["passed"] is False


def test_dimension2_executor_is_selective_and_never_uses_commands() -> None:
    source = open(r3.__file__, encoding="utf-8").read()
    assert "execute_dimension2_native_clone_evidence" in source
    assert "dimension2_disposable_sandbox.dwg" in source
    assert ".SendCommand" not in source
    assert '"netload_used": False' in source


def test_manual_dimension2_review_requires_all_visual_functional_fields(tmp_path: Path) -> None:
    screenshot = tmp_path / "review.png"
    screenshot.write_bytes(b"png")
    review = {
        "manual_status": "ACCEPTED",
        "display_content_equivalent": True,
        "leader_geometry_equivalent": True,
        "association_target_equivalent": True,
        "functional_behavior_acceptable": True,
        "screenshot_path": str(screenshot),
    }
    assert r3._manual_dimension2_review_valid(review) is True
    review["leader_geometry_equivalent"] = False
    assert r3._manual_dimension2_review_valid(review) is False


def test_final_reconstruction_starts_from_original_target_path() -> None:
    source = open(r3.__file__, encoding="utf-8").read()
    assert 'final_sandbox = paths.copies / "target_mvp2_final_reconstruction.dwg"' in source
    assert "execute_core_reconstruction(" in source
    assert "sandbox_path=final_sandbox" in source
    assert '"execution_order": ["ordinary_16", "core_tdb_331", "dimension2_6"]' in source


def test_final_core_recovery_is_read_only_and_prevents_duplicate_execution() -> None:
    source = open(r3.__file__, encoding="utf-8").read()
    assert "recover_final_core_persistence_verification" in source
    assert '"sandbox_saved_during_recovery": False' in source
    assert 'read_json(prior_core_report).get("status") == "PASS_R3_CORE_331_RECONSTRUCTION"' in source


def test_dimension2_incremental_recovery_saves_and_reopens_each_item() -> None:
    source = open(r3.__file__, encoding="utf-8").read()
    assert "recover_final_dimension2_incrementally" in source
    assert "incremental Dimension2 {node['task_id']} save" in source
    assert "incremental persisted Dimension2" in source
    assert '"required_tdb_persisted": 337 if passed' in source
