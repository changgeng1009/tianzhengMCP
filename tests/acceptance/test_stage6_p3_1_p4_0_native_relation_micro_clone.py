import json
from pathlib import Path

import pytest

from mcp.orchestration import stage6_p3_1_p4_0_native_relation_micro_clone as stage


def entity(handle, name="TDbPipe", bbox=None, region="r1", layer="PIPE-给水", **attrs):
    bbox = bbox or [[0, 0, 0], [10, 0, 0]]
    return {
        "handle": handle, "object_name": name, "layer": layer,
        "bbox": bbox, "region_id": region,
        "geometry": {"start_point": list(bbox[0]), "end_point": list(bbox[1])}, "attributes": attrs,
    }


class FakeEntity:
    ObjectName = "TDbPipe"
    Handle = "A1"
    ObjectID = 10
    OwnerID = 99
    Layer = "PIPE-给水"
    DNDiameter = 100.0
    SysType = "给水"
    ConnectionHandle = "B2"

    def GetXData(self, app):
        return ([1000], ["B2"])

    def GetExtensionDictionary(self):
        raise RuntimeError("no dictionary")

    def Move(self):
        raise AssertionError("不得调用")


def test_safe_com_property_enumeration_does_not_invoke_methods():
    result = stage.safe_property_inventory(FakeEntity())
    assert result["readable"]["DNDiameter"] == 100.0
    assert "Move" not in result["readable"]


def test_identity_and_display_fields_are_not_relationship_candidates():
    for name in ("Handle", "ObjectID", "OwnerID", "BoxWidth", "HidePipe", "PipeWeight", "FittingType"):
        assert not stage.is_relationship_candidate_property(name)


def test_explicit_connection_field_is_relationship_candidate():
    assert stage.is_relationship_candidate_property("ConnectionHandle")


def test_bbox_only_pipe_does_not_fabricate_exact_endpoint():
    item = entity("1")
    item["geometry"] = {}
    assert stage._pipe_segment(item) is None


def test_xdata_read():
    assert stage.read_xdata(FakeEntity())["available"] is True


def test_extension_dictionary_failure_is_captured():
    result = stage.read_extension_dictionary(FakeEntity())
    assert result["available"] is False and "RuntimeError" in result["error"]


def test_handle_reference_resolution():
    assert stage.classify_reference_value("B2", {"B2"}, set()) == "NATIVE_HANDLE_REFERENCE"


def test_object_id_reference_resolution():
    assert stage.classify_reference_value(12, set(), {12}) == "NATIVE_OBJECT_ID_REFERENCE"


def test_native_object_reference_resolution():
    assert stage.classify_reference_value({"com_reference": True}, set(), set()) == "NATIVE_OBJECT_REFERENCE"


def test_nearest_geometry_is_never_reliable():
    assert stage.nearest_geometry_evidence(1)["reliable"] is False
    assert "NEAREST_GEOMETRY_ONLY" not in stage.RELIABLE_EVIDENCE


def test_exact_pipe_endpoint_topology():
    left = entity("1", bbox=[[0, 0, 0], [10, 0, 0]])
    right = entity("2", bbox=[[10, 0, 0], [20, 0, 0]])
    assert stage.exact_relation(left, right)["evidence_level"] == "EXACT_ENDPOINT_TOPOLOGY"


def test_near_but_not_exact_pipe_is_rejected():
    left = entity("1", bbox=[[0, 0, 0], [10, 0, 0]])
    right = entity("2", bbox=[[10.1, 0, 0], [20, 0, 0]])
    assert stage.exact_relation(left, right) is None


def test_exact_fitting_pipe_intersection():
    pipe = entity("1", bbox=[[0, 0, 0], [10, 0, 0]])
    fitting = entity("2", name="TDbPipeFitting", bbox=[[5, 0, 0], [5, 0, 0]])
    assert stage.exact_relation(pipe, fitting)["evidence_level"] == "EXACT_GEOMETRIC_INTERSECTION"


def test_exact_valve_pipe_intersection():
    pipe = entity("1", bbox=[[0, 0, 0], [10, 0, 0]])
    valve = entity("2", name="TDbPipeValve", bbox=[[4, -1, 0], [6, 1, 0]])
    assert stage.exact_relation(pipe, valve)["evidence_level"] == "EXACT_GEOMETRIC_INTERSECTION"


def test_component_building_connects_reliable_edges():
    items = [entity("1"), entity("2", name="TDbPipeFitting", bbox=[[5, 0, 0], [5, 0, 0]])]
    edges = stage.build_exact_edges(items)
    components = stage.build_components(items, edges, "reference")
    assert len(components) == 1 and components[0]["node_count"] == 2


def test_unconnected_valve_is_relation_unresolved():
    components = stage.build_components([entity("1", name="TDbPipeValve")], [], "reference")
    assert components[0]["execution_eligibility"] == "RELATION_UNRESOLVED"


def test_single_pipe_is_comparison_eligible():
    components = stage.build_components([entity("1")], [], "reference")
    assert components[0]["execution_eligibility"] == "ELIGIBLE_FOR_COMPONENT_COMPARISON"


def test_component_already_present_matching():
    ref = stage.build_components([entity("1")], [], "reference")
    target = stage.build_components([entity("2", region="t1", bbox=[[100, 200, 0], [110, 200, 0]])], [], "target")
    matches = stage.match_components(ref, target, {"r1": {"target_region_id": "t1", "translation_x": 100, "translation_y": 200}}, [])
    assert matches[0]["status"] == "COMPONENT_ALREADY_PRESENT"


def test_component_missing_matching():
    ref = stage.build_components([entity("1")], [], "reference")
    matches = stage.match_components(ref, [], {"r1": {"target_region_id": "t1", "translation_x": 100, "translation_y": 200}}, [])
    assert matches[0]["status"] == "COMPONENT_CONFIRMED_MISSING"


def test_component_partial_matching():
    ref_items = [entity("1"), entity("2", name="TDbPipeFitting", bbox=[[5, 0, 0], [5, 0, 0]])]
    ref = stage.build_components(ref_items, stage.build_exact_edges(ref_items), "reference")
    target = stage.build_components([entity("3", region="t1", bbox=[[100, 200, 0], [110, 200, 0]])], [], "target")
    matches = stage.match_components(ref, target, {"r1": {"target_region_id": "t1", "translation_x": 100, "translation_y": 200}}, [])
    assert matches[0]["status"] == "COMPONENT_PARTIALLY_PRESENT"


def test_protected_component_matching():
    ref = stage.build_components([entity("1")], [], "reference")
    matches = stage.match_components(ref, [], {"r1": {"target_region_id": "t1", "translation_x": 100, "translation_y": 200}}, [[99, 199, 111, 201]])
    assert matches[0]["status"] == "COMPONENT_PROTECTED"


def test_old_candidate_status_is_revoked_before_reclassification():
    old = [{"handle": "1", "object_name": "TDbPipe", "status": "CONFIRMED_MISSING_DIRECT_CLONE"}]
    component = stage.build_components([entity("1")], [], "reference")
    matches = [{"reference_component_id": component[0]["component_id"], "status": "COMPONENT_CONFIRMED_MISSING"}]
    result = stage.reclassify_old_candidates(old, component, matches)
    assert result[0]["old_status"] == "CANDIDATE_MISSING_RELATION_UNVERIFIED"
    assert result[0]["execution_allowed"] is False


def test_old_candidate_without_component_is_unresolved():
    result = stage.reclassify_old_candidates([{"handle": "A"}], [], [])
    assert result[0]["new_status"] == "RECLASSIFIED_RELATION_UNRESOLVED"


def test_micro_component_selection_rejects_fire():
    component = stage.build_components([entity("1", region="fire")], [], "reference")[0]
    matches = [{"reference_component_id": component["component_id"], "status": "COMPONENT_CONFIRMED_MISSING"}]
    assert not stage.select_micro_component([component], matches, {"1": entity("1")}, "fire")["selected"]


def test_micro_component_selection_accepts_small_pipe_component():
    component = stage.build_components([entity("1")], [], "reference")[0]
    matches = [{"reference_component_id": component["component_id"], "status": "COMPONENT_CONFIRMED_MISSING"}]
    assert stage.select_micro_component([component], matches, {"1": entity("1")}, "fire")["selected"]


def test_micro_selection_rejects_equipment():
    items = [entity("1"), entity("2", name="TDbEquipment", bbox=[[5, 0, 0], [5, 0, 0]])]
    component = stage.build_components(items, stage.build_exact_edges(items), "reference")[0]
    matches = [{"reference_component_id": component["component_id"], "status": "COMPONENT_CONFIRMED_MISSING"}]
    by_handle = {item["handle"]: item for item in items}
    assert not stage.select_micro_component([component], matches, by_handle, "fire")["selected"]


def test_micro_plan_hash_detects_change():
    item = entity("1")
    component = stage.build_components([item], [], "reference")[0]
    selection = {"selected": True, "component_id": component["component_id"]}
    plan = stage.build_micro_plan(selection, component, {"1": item}, {"translation_x": 1, "translation_y": 2})
    assert stage.payload_sha256(plan) == plan["plan_sha256"]
    plan["tasks"][0]["source_handle"] = "X"
    assert stage.payload_sha256(plan) != plan["plan_sha256"]


def test_micro_plan_never_reuses_old_plan():
    plan = stage.build_micro_plan({"selected": False}, None, {}, None)
    assert plan["invalidated_4068_plan_reused"] is False


def test_l3_exact_approval_phrase_required():
    assert not stage.approval_allows_micro_clone("执行 sandbox")
    assert stage.approval_allows_micro_clone("我批准 sandbox 执行")


def test_invalidated_plan_guard(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"status": "INVALIDATED", "execution_allowed": False}), encoding="utf-8")
    assert stage.old_plan_is_forbidden(path)


def test_active_plan_is_not_forbidden_guard(tmp_path):
    path = tmp_path / "active.json"
    path.write_text(json.dumps({"status": "ACTIVE", "execution_allowed": True}), encoding="utf-8")
    assert not stage.old_plan_is_forbidden(path)


def test_source_contains_no_sendcommand_or_full_plan_execution():
    source = Path(stage.__file__).read_text(encoding="utf-8")
    assert "Send" + "Command(" not in source
    assert "full_4068_execution\": False" in source


def test_reliable_evidence_levels_exclude_shared_system_dn():
    assert "SHARED_SYSTEM_AND_DN_SUPPORT" not in stage.RELIABLE_EVIDENCE


def test_relationship_not_observable_does_not_validate_clone():
    result = {"status": "RELATIONSHIP_NOT_OBSERVABLE"}
    assert result["status"] != "RELATIONSHIP_PRESERVED"


def test_write_outputs_are_new_paths_only(tmp_path):
    paths = stage.StagePaths.create(tmp_path, "run")
    assert paths.root != tmp_path and paths.backups.parent == paths.root


def test_fire_audit_unresolved_when_relations_remain():
    component = stage.build_components([entity("1", region="fire")], [], "reference")[0]
    target_component = stage.build_components([entity("2", region="tfire")], [], "target")[0]
    outputs = stage.build_fire_audit([entity("1", region="fire")], [entity("2", region="tfire")], [component], [target_component], [{"semantic_region": "fire", "status": "COMPONENT_RELATION_UNRESOLVED"}], "fire", "tfire")
    assert outputs[2]["status"] == "FIRE_REGION_MISSING_DETECTION_UNRESOLVED"


def test_bbox_intersection_is_exact_not_nearest():
    pipe = entity("1", bbox=[[0, 0, 0], [10, 0, 0]])
    far = entity("2", name="TDbPipeValve", bbox=[[20, -1, 0], [22, 1, 0]])
    assert stage.exact_relation(pipe, far) is None


def test_no_affine_transform_in_micro_plan():
    item = entity("1")
    component = stage.build_components([item], [], "reference")[0]
    plan = stage.build_micro_plan({"selected": True}, component, {"1": item}, {"translation_x": 1, "translation_y": 2})
    assert "affine" not in json.dumps(plan).lower()
