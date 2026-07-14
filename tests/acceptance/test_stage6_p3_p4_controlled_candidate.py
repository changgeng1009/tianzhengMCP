import json
from pathlib import Path

import pytest

from mcp.orchestration import stage6_p3_p4_controlled_candidate as stage


def entity(name="TDbPipe", handle="1", layer="PIPE-给水", bbox=None, **attrs):
    return {
        "handle": handle, "object_name": name, "layer": layer,
        "bbox": bbox or [[10, 10, 0], [20, 20, 0]],
        "geometry": {"start_point": [10, 10, 0], "end_point": [20, 20, 0]},
        "attributes": attrs,
    }


def transform():
    return {
        "semantic_key": "x", "reference_region_id": "r1", "target_region_id": "t1",
        "transform_type": "translation_only", "translation_x": 100, "translation_y": 200,
        "scale": 1.0, "rotation": 0.0, "final_status": "ALIGNMENT_VERIFIED",
    }


def test_transform_manifest_requires_seven_unique_translation_only():
    values = []
    for index in range(7):
        item = transform() | {"semantic_key": str(index), "reference_region_id": f"r{index}", "target_region_id": f"t{index}"}
        values.append(item)
    assert stage.validate_transform_manifest({"count": 7, "transforms": values}) == []
    values[1]["target_region_id"] = values[0]["target_region_id"]
    assert "duplicate_target_region_binding" in stage.validate_transform_manifest({"count": 7, "transforms": values})


def test_calibration_and_anchor_rejected():
    values = [transform() | {"semantic_key": str(i), "reference_region_id": f"r{i}", "target_region_id": f"t{i}"} for i in range(7)]
    payload = {"count": 7, "transforms": values, "path": "锚点校准.dwg"}
    assert "calibration_or_anchor_reference_forbidden" in stage.validate_transform_manifest(payload)
    assert stage.classify_entity(entity(name="AcDbText", layer="MCP_ANCHOR", text="B1_FIX"))["professional"] is False


@pytest.mark.parametrize("name,expected", [("TDbPipe", "PROFESSIONAL_GEOMETRY"), ("TDbPipeValve", "PROFESSIONAL_SYMBOL"), ("TDbDimension2", "PROFESSIONAL_ANNOTATION")])
def test_professional_classification(name, expected):
    assert stage.classify_entity(entity(name=name))["entity_class"] == expected


def test_building_frame_and_unrelated_text_excluded():
    assert stage.classify_entity(entity(name="AcDbLine", layer="建筑墙线"))["professional"] is False
    assert stage.classify_entity(entity(name="AcDbLine", layer="图框"))["entity_class"] == "FRAME_OR_TITLE"
    assert stage.classify_entity(entity(name="AcDbText", layer="文字", text="房间"))["entity_class"] == "GENERAL_TEXT"


def test_equivalent_and_missing_detection_with_spatial_index():
    ref = entity()
    tgt = entity(handle="2", bbox=[[110, 210, 0], [120, 220, 0]])
    regions_r = [{"region_id": "r1", "frame_bbox": [0, 0, 100, 100]}]
    regions_t = [{"region_id": "t1", "frame_bbox": [100, 200, 200, 300]}]
    result = stage.detect_missing([ref], [tgt], [transform()], regions_r, regions_t, [])
    assert len(result["already_present"]) == 1
    result = stage.detect_missing([ref], [], [transform()], regions_r, regions_t, [])
    assert len(result["missing"]) == 1


def test_ambiguous_and_protected_are_not_direct():
    unstable = entity(bbox=None)
    unstable["bbox"] = None
    regions_r = [{"region_id": "r1", "frame_bbox": [0, 0, 100, 100]}]
    regions_t = [{"region_id": "t1", "frame_bbox": [100, 200, 200, 300]}]
    result = stage.detect_missing([unstable], [], [transform()], regions_r, regions_t, [])
    assert not result["missing"]
    protected = stage.detect_missing([entity()], [], [transform()], regions_r, regions_t, [[105, 205, 125, 225]])
    assert not protected["missing"]
    assert protected["excluded"][0]["status"] == "EXCLUDED_PROTECTED_REGION"


def test_boundary_crossing_is_review_only():
    ref = entity(bbox=[[90, 90, 0], [120, 120, 0]])
    regions_r = [{"region_id": "r1", "frame_bbox": [0, 0, 130, 130]}]
    regions_t = [{"region_id": "t1", "frame_bbox": [100, 200, 200, 300]}]
    result = stage.detect_missing([ref], [], [transform()], regions_r, regions_t, [])
    assert not result["missing"] and result["review_only"]


def test_dependency_graph_and_frozen_plan_hash():
    pipe = entity(handle="10") | {"reference_region_id": "r1", "target_region_id": "t1", "entity_class": "PROFESSIONAL_GEOMETRY", "transform": {"type": "translation_only", "x": 100, "y": 200}, "expected_target_bbox": [110, 210, 120, 220], "confidence": .95}
    valve = entity(name="TDbPipeValve", handle="11", bbox=[[12, 12, 0], [14, 14, 0]]) | {"reference_region_id": "r1", "target_region_id": "t1", "entity_class": "PROFESSIONAL_SYMBOL", "transform": {"type": "translation_only", "x": 100, "y": 200}, "expected_target_bbox": [112, 212, 114, 214], "confidence": .95}
    graph = stage.build_dependency_graph([pipe, valve])
    plan = stage.build_frozen_plan([pipe, valve], graph, {})
    assert plan["task_count"] == 2
    assert stage.payload_sha256(plan) == plan["plan_sha256"]
    assert plan["tasks"][1]["dependency_ids"]


def test_candidate_copy_hashes_match_and_never_overwrite(tmp_path, synthetic_cad_factory):
    target = synthetic_cad_factory(tmp_path / "target.dwg")
    candidate = synthetic_cad_factory(tmp_path / "candidate.dwg", create=False)
    backup = synthetic_cad_factory(tmp_path / "backup.dwg", create=False)
    result = stage.create_candidate_copy(target, candidate, backup)
    assert len(set(result.values())) == 1
    with pytest.raises(FileExistsError): stage.create_candidate_copy(target, candidate, backup)


def test_plan_does_not_allow_expansion():
    assert stage.build_frozen_plan([], {"nodes": [], "edges": []}, {})["no_plan_expansion_allowed"] is True


def test_write_api_is_candidate_guarded_and_sendcommand_forbidden():
    source = Path(stage.__file__).read_text(encoding="utf-8")
    assert "SendCommand" not in source
    assert "candidate_doc.Save()" in source
    assert "source_doc.Save" not in source
    assert "candidate_doc.Close(False)" in source
    assert "source_doc.Close(False)" in source
    assert "shutil.copy2(backup_path, candidate_path)" in source


def test_input_hash_gate_passes_exact_values():
    assert stage.validate_input_hashes("aa", "AA", "bb", "BB") == []


def test_input_hash_gate_rejects_reference_and_target():
    assert stage.validate_input_hashes("x", "a", "y", "b") == ["reference_hash_mismatch", "target_hash_mismatch"]


def test_autocad_instance_empty_water_supply_is_safe():
    assert not stage.autocad_instance_conflict({"caption": "T30天正给排水", "document_count": 0, "documents": []})


def test_autocad_instance_unrelated_or_open_document_conflicts():
    assert stage.autocad_instance_conflict({"caption": "天正暖通", "document_count": 0, "documents": []})
    assert stage.autocad_instance_conflict({"caption": "T30天正给排水", "document_count": 1, "documents": [{}]})


def test_anchor_block_reference_is_excluded():
    item = entity(name="AcDbBlockReference", layer="MCP_ANCHOR", effective_name="MCP_ANCHOR_POINT")
    assert stage.is_anchor_entity(item)
    assert not stage.classify_entity(item)["professional"]


def test_tdb_frame_object_is_excluded():
    result = stage.classify_entity(entity(name="TDbDrawingName", layer="TWT_TITLE"))
    assert result["entity_class"] == "FRAME_OR_TITLE" and not result["direct_clone_supported"]


def test_handle_difference_does_not_make_equivalent_geometry_missing():
    assert stage.equivalent_entity(entity(handle="A"), entity(handle="B", bbox=[[110, 210, 0], [120, 220, 0]]), 100, 200)


def test_dn_difference_rejects_equivalence():
    left = entity(dn_diameter=100)
    right = entity(handle="B", bbox=[[110, 210, 0], [120, 220, 0]], dn_diameter=150)
    assert not stage.equivalent_entity(left, right, 100, 200)


def test_professional_text_requires_association_and_is_not_direct():
    result = stage.classify_entity(entity(name="AcDbText", layer="DIM_给水", text="DN100"))
    assert result["entity_class"] == "PROFESSIONAL_ANNOTATION"
    assert result["direct_clone_supported"] is False


def test_plan_hash_detects_task_tampering():
    plan = stage.build_frozen_plan([], {"nodes": [], "edges": []}, {})
    original = plan["plan_sha256"]
    plan["tasks"].append({"task_id": "plan_outside"})
    assert stage.payload_sha256(plan) != original


def test_snapshot_comparison_detects_deleted_modified_and_unexpected():
    before = {"handles": ["1", "2"], "signatures": {"1": {"x": 1}, "2": {"x": 2}}}
    after = {"handles": ["1", "3", "4"], "signatures": {"1": {"x": 9}, "3": {}, "4": {}}}
    result = stage.compare_snapshots(before, after, ["3"])
    assert result == {"existing_deleted": ["2"], "unexpected_new": ["4"], "existing_modified": ["1"]}


def test_snapshot_comparison_accepts_only_planned_new_handles():
    before = {"handles": ["1"], "signatures": {"1": {"x": 1}}}
    after = {"handles": ["1", "2"], "signatures": {"1": {"x": 1}, "2": {}}}
    assert stage.compare_snapshots(before, after, ["2"]) == {"existing_deleted": [], "unexpected_new": [], "existing_modified": []}
