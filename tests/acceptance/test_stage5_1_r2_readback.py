from __future__ import annotations

from pathlib import Path

from mcp.acceptance import stage5_1_r2_readback as r2


def test_bbox_anchor_and_dimensions_are_deterministic() -> None:
    bbox = [[10, 20, 0], [30, 50, 10]]
    assert r2._bbox_center(bbox) == [20, 35, 5]
    assert r2._bbox_dimensions(bbox) == [20, 30, 10]


def test_single_interface_derives_unique_direction() -> None:
    graph = {
        "nodes": [
            {"task_id": "pump", "object_name": "TDbPump", "target_wcs_bbox": [[0, 0, 0], [10, 10, 0]]},
            {"task_id": "pipe", "object_name": "TDbPipe", "target_wcs_bbox": [[10, 5, 0], [20, 5, 0]]},
        ],
        "edges": [{"source_id": "pump", "target_id": "pipe", "edge_type": "EQUIPMENT_INTERFACE"}],
    }
    node = {**graph["nodes"][0], "custom_properties": {}}
    result = r2.derive_device_geometry(node, graph)
    assert result["orientation_unique"] is True
    assert result["orientation_vector"] == [1.0, 0.0, 0.0]


def test_direct_lrotation_overrides_ambiguous_interfaces() -> None:
    graph = {
        "nodes": [{"task_id": "pump", "object_name": "TDbPump", "target_wcs_bbox": [[0, 0, 0], [10, 10, 0]]}],
        "edges": [],
    }
    result = r2.derive_device_geometry({**graph["nodes"][0], "custom_properties": {}}, graph, {"LRotation": 0.0})
    assert result["orientation_unique"] is True
    assert result["orientation_source"] == "direct_rotation_or_angle"


def test_annotation_hidden_properties_form_stable_signatures() -> None:
    vpipe = r2.annotation_display_signature("TDbVPipeDim", {"VPipeNum": "9", "VPipeFloorType": "A-JL-1"})
    leader = r2.annotation_leader_signature("TDbSymbMultiLeader", {"ArrowSize": "3.5", "LayoutRotation": 0.0}, [[0, 0, 0], [1, 1, 0]])
    assert vpipe == {"VPipeFloorType": "A-JL-1", "VPipeNum": "9"}
    assert leader is not None


def test_dimension_bbox_cannot_fabricate_display_or_leader() -> None:
    assert r2.annotation_display_signature("TDbDimension2", {"DimStyle": "A"}) is None
    assert r2.annotation_leader_signature("TDbDimension2", {"LayoutRotation": 0.0}, [[0, 0, 0], [10, 1, 0]]) is None


def test_symmetric_opposite_interfaces_block_direction() -> None:
    graph = {
        "nodes": [
            {"task_id": "pump", "object_name": "TDbPump", "target_wcs_bbox": [[0, 0, 0], [10, 10, 0]]},
            {"task_id": "left", "object_name": "TDbPipe", "target_wcs_bbox": [[-10, 5, 0], [0, 5, 0]]},
            {"task_id": "right", "object_name": "TDbPipe", "target_wcs_bbox": [[10, 5, 0], [20, 5, 0]]},
        ],
        "edges": [
            {"source_id": "pump", "target_id": "left", "edge_type": "EQUIPMENT_INTERFACE"},
            {"source_id": "pump", "target_id": "right", "edge_type": "EQUIPMENT_INTERFACE"},
        ],
    }
    result = r2.derive_device_geometry({**graph["nodes"][0], "custom_properties": {}}, graph)
    assert result["orientation_unique"] is False
    assert result["orientation_vector"] is None


def test_annotation_multiple_equal_candidates_are_ambiguous() -> None:
    node = {"task_id": "annotation"}
    graph = {"edges": [
        {"source_id": "annotation", "target_id": "a", "edge_type": "ANNOTATES_OBJECT", "distance": 10},
        {"source_id": "annotation", "target_id": "b", "edge_type": "ANNOTATES_OBJECT", "distance": 10},
    ]}
    result = r2.derive_annotation_target(node, graph)
    assert result["target_unique"] is False
    assert result["derived_target_id"] is None


def test_fingerprint_excludes_handle_and_object_id() -> None:
    node = {"task_id": "x"}
    scan = {"object_name": "TDbEquipment", "layer": "E", "bbox": [[0, 0, 0], [1, 1, 0]]}
    semantic = {"properties": {"ObjectID": 1, "Handle": "A", "Width": 1}, "xdata": None, "extension_dictionary": None}
    fingerprint = r2.stable_fingerprint(node, scan, semantic, {})
    assert "ObjectID" not in fingerprint["stable_properties"]
    assert "Handle" not in fingerprint["stable_properties"]


def test_required_policy_never_fabricates_unreadable_match() -> None:
    assert "BLOCKED_REQUIRED_FIELD_UNREADABLE" in Path(r2.__file__).read_text(encoding="utf-8")
    assert "critical_fields_may_be_downgraded\": False" in Path(r2.__file__).read_text(encoding="utf-8")


def test_r2_binds_reference_node_by_poc_primary_handle() -> None:
    source = Path(r2.__file__).read_text(encoding="utf-8")
    assert 'graph_by_handle[poc_results[object_name]["primary_reference_handle"]]' in source


def test_dimension_dictionary_audit_never_calls_explode() -> None:
    source = Path(r2.__file__).read_text(encoding="utf-8")
    function = source[source.index("def audit_dimension_named_dictionaries"):]
    assert ".Explode(" not in function
    assert '"analysis_copy_saved": False' in function
