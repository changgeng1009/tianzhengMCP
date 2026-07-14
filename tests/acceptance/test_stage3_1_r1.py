from __future__ import annotations

from pathlib import Path

from mcp.acceptance import stage3_1_r1_analysis as analysis
from mcp.acceptance import stage3_1_r1_target_scan_alignment as runner


def _entity(handle: str, name: str, x: float, y: float, *, role: str, text: str | None = None, end: tuple[float, float] | None = None, layer: str = "PUMP") -> dict:
    geometry = {"insertion_point": [x, y, 0.0]}
    bbox = [[x, y, 0.0], [x + 10, y + 10, 0.0]]
    if end:
        geometry = {"start_point": [x, y, 0.0], "end_point": [end[0], end[1], 0.0]}
        bbox = [[min(x, end[0]), min(y, end[1]), 0.0], [max(x, end[0]), max(y, end[1]), 0.0]]
    return {
        "document_role": role, "handle": handle, "object_name": name,
        "entity_name": name, "layer": layer, "owner_layout": "Model",
        "bbox": bbox, "geometry": geometry,
        "attributes": ({"text": text, "height": 300.0} if text is not None else {}),
        "read_errors": [], "coordinate_space": "cad_wcs",
    }


def _scan(role: str, dx: float = 0.0, dy: float = 0.0) -> dict:
    entities = [
        _entity("T1", "AcDbText", 0 + dx, -800 + dy, role=role, text="泵房大样"),
        _entity("L1", "AcDbLine", 0 + dx, 0 + dy, role=role, end=(2000 + dx, 0 + dy)),
        _entity("L2", "AcDbLine", 0 + dx, 0 + dy, role=role, end=(0 + dx, 1500 + dy)),
        _entity("L3", "AcDbLine", 0 + dx, 1500 + dy, role=role, end=(2000 + dx, 1500 + dy)),
        _entity("P1", "AcDbPolyline", 500 + dx, 400 + dy, role=role),
    ]
    return {"document_role": role, "entities": entities}


def _region(role: str, dx: float = 0.0, dy: float = 0.0) -> dict:
    return {
        "role": role, "status": "SELECTED", "bbox": [-100 + dx, -900 + dy, 2100 + dx, 1600 + dy],
        "centroid": [1000 + dx, 350 + dy], "width": 2200.0, "height": 2500.0,
        "diagonal": 3330.165, "region_confidence": 0.9,
    }


def test_object_name_classification_sum_matches_scan() -> None:
    inventory = analysis.build_object_inventory(_scan("target"))
    assert inventory["classification_sum"] == inventory["scanned_entity_count"] == 5
    assert inventory["classification_sum_matches_scan"] is True


def test_51_entity_inventory_is_fully_classified() -> None:
    entities = []
    counts = {"AcDbLine": 16, "AcDbPolyline": 3, "AcDbText": 20, "AcDbBlockReference": 11, "TDbDrawingName": 1}
    for name, count in counts.items():
        entities.extend(_entity(f"{name}-{i}", name, i * 10.0, 0.0, role="target") for i in range(count))
    inventory = analysis.build_object_inventory({"entities": entities})
    assert inventory["object_name_counts"] == counts
    assert inventory["classification_sum"] == 51


def test_tdb_drawing_name_is_not_equipment() -> None:
    inventory = analysis.build_object_inventory({"entities": [_entity("D", "TDbDrawingName", 0, 0, role="target")]})
    assert inventory["tdb_drawing_name_count"] == 1
    assert inventory["tdb_equipment_count"] == 0


def test_sparse_scan_confirmation_without_hidden_content() -> None:
    inventory = analysis.build_object_inventory(_scan("target"))
    result = analysis.confirm_target_scan(inventory, {
        "proxy_count": 0, "xref_count": 0, "virtual_expansion_required": False,
        "block_reference_count": 0, "block_definition_count": 0,
        "nested_block_detected": False,
    })
    assert result["status"] == "TARGET_SCAN_CONFIRMED_SPARSE"
    assert result["top_level_count_basically_credible"] is True


def test_substantive_block_content_is_reported_without_claiming_sparse() -> None:
    inventory = analysis.build_object_inventory(_scan("target"))
    result = analysis.confirm_target_scan(inventory, {
        "proxy_count": 0, "xref_count": 0, "virtual_expansion_required": True,
        "virtual_expansion_performed": True, "virtual_entity_count": 80,
        "block_reference_count": 1, "block_definition_count": 1,
        "nested_block_detected": False,
    })
    assert result["status"] == "TARGET_SCAN_CONFIRMED_BLOCK_CONTAINED"


def test_proxy_and_xref_limitations_are_explicit() -> None:
    inventory = analysis.build_object_inventory(_scan("target"))
    proxy = analysis.confirm_target_scan(inventory, {"proxy_count": 1, "xref_count": 0, "virtual_expansion_required": False})
    xref = analysis.confirm_target_scan(inventory, {"proxy_count": 0, "xref_count": 1, "virtual_expansion_required": False, "virtual_expansion_performed": False})
    assert proxy["status"] == "TARGET_SCAN_PARTIAL_PROXY_LIMITED"
    assert xref["status"] == "TARGET_SCAN_PARTIAL_XREF_LIMITED"


def test_no_virtual_expansion_when_audit_does_not_require_it() -> None:
    result = analysis.confirm_target_scan(analysis.build_object_inventory(_scan("target")), {
        "proxy_count": 0, "xref_count": 0, "virtual_expansion_required": False,
    })
    assert result["status"] == "TARGET_SCAN_CONFIRMED_SPARSE"


def test_duplicate_text_is_not_directly_matched_without_non_text_consensus() -> None:
    classification = {
        "records": [
            {"role": "reference", "handle": "R", "normalized_text": "设备", "category": "duplicate_text", "point": [0, 0], "height": 300, "rotation": 0},
            {"role": "target", "handle": "T", "normalized_text": "设备", "category": "duplicate_text", "point": [100, 50], "height": 300, "rotation": 0},
        ]
    }
    result = analysis.disambiguate_text_anchors(classification, None, 10.0)
    assert result["accepted_count"] == 0
    assert result["decisions"][0]["rejection_reason"] == "no non-text translation consensus"


def test_title_block_text_is_excluded_from_high_weight_anchors() -> None:
    reference = {"entities": [_entity("R", "AcDbText", 0, 0, role="reference", text="图号 S-01")]}
    target = {"entities": [_entity("T", "AcDbText", 100, 50, role="target", text="图号 S-01")]}
    result = analysis.classify_text_anchors(reference, target, _region("reference"), _region("target", 100, 50))
    assert all(item["category"] == "title_block_text" for item in result["records"])
    assert all(item["high_weight_allowed"] is False for item in result["records"])


def test_low_information_text_is_downweighted() -> None:
    reference = {"entities": [_entity("R", "AcDbText", 0, 0, role="reference", text="1:50")]}
    target = {"entities": [_entity("T", "AcDbText", 100, 50, role="target", text="1:50")]}
    result = analysis.classify_text_anchors(reference, target, _region("reference"), _region("target", 100, 50))
    assert all(item["category"] == "low_information_text" for item in result["records"])


def test_unmatched_unique_text_does_not_increase_confidence() -> None:
    confidence = analysis.build_confidence_breakdown(
        reference_region=_region("reference"),
        target_region=_region("target"),
        target_scan_confirmation={"status": "TARGET_SCAN_CONFIRMED_SPARSE"},
        text_classification={"records": [{"category": "globally_unique_text"}, {"category": "globally_unique_text"}]},
        text_disambiguation={"accepted_count": 0, "duplicate_accepted_count": 0, "decisions": []},
        non_text_anchors=[],
        transform_evaluation={},
        geometry_validation={"geometry_overlap_score": 0.0},
    )
    component = next(item for item in confidence["components"] if item["name"] == "unique_text_anchor_score")
    assert component["score"] == 0.0


def test_wall_corner_non_text_anchor_candidates_are_created() -> None:
    candidates = analysis.build_non_text_anchor_candidates(
        _scan("reference"), _scan("target", 100, 50),
        _region("reference"), _region("target", 100, 50),
    )
    assert any(item["anchor_type"] == "wall_corner" for item in candidates)


def test_long_line_anchor_candidates_are_created() -> None:
    candidates = analysis.build_non_text_anchor_candidates(
        _scan("reference"), _scan("target", 100, 50),
        _region("reference"), _region("target", 100, 50),
    )
    assert any(item["anchor_type"] == "long_line_midpoint" for item in candidates)


def test_translation_delta_clustering_finds_primary_consensus() -> None:
    candidates = [
        {"candidate_delta": [100, 50], "anchor_type": "wall_corner"},
        {"candidate_delta": [101, 49], "anchor_type": "long_line_midpoint"},
        {"candidate_delta": [100, 51], "anchor_type": "rectangle_center"},
        {"candidate_delta": [900, 800], "anchor_type": "long_line_midpoint"},
    ]
    result = analysis.cluster_translation_deltas(candidates, 5.0)
    assert result["primary_cluster"]["size"] == 3
    assert result["primary_cluster"]["center"] == [100.0, 50.0]


def test_text_only_alignment_cannot_select_transform() -> None:
    text = [{
        "anchor_id": "T", "reference_point": [0, 0], "target_point": [100, 50],
        "reference_handles": ["R"], "target_handles": ["T"], "candidate_delta": [100, 50],
    }]
    result = analysis.evaluate_transforms(text, [], _region("reference"), _region("target", 100, 50))
    assert result["selected"] is None


def test_non_text_translation_is_retained_as_candidate_but_not_passed() -> None:
    non_text = [
        {"anchor_id": f"N{i}", "reference_point": point, "target_point": [point[0] + 100, point[1] + 50],
         "reference_handles": [f"R{i}"], "target_handles": [f"T{i}"], "candidate_delta": [100, 50]}
        for i, point in enumerate(([0, 0], [1000, 0], [0, 1000]))
    ]
    result = analysis.evaluate_transforms([], non_text, _region("reference"), _region("target", 100, 50))
    assert result["selected"] is None
    assert result["best_geometric_candidate"]["transform_type"] == "translation"

    status, allowed, blockers = analysis.decide_final_status(
        {"status": "TARGET_SCAN_CONFIRMED_BLOCK_CONTAINED"},
        _region("reference"), _region("target", 100, 50), result,
        {"geometry_overlap_score": 0.9},
        {"final_confidence": 0.9, "pass_threshold": 0.72},
    )
    assert status == "PARTIAL_LOW_CONFIDENCE"
    assert allowed is False
    assert any("text anchor" in item for item in blockers)


def test_geometry_overlap_supports_consistent_translation() -> None:
    matrix = [[1, 0, 100], [0, 1, 50], [0, 0, 1]]
    result = analysis.validate_geometry_overlap(
        _scan("reference"), _scan("target", 100, 50),
        _region("reference"), _region("target", 100, 50), matrix,
    )
    assert result["geometry_overlap_score"] >= 0.55
    assert result["matched_long_line_count"] >= 2


def test_absolute_and_normalized_residual_gates_both_apply() -> None:
    status, allowed, blockers = analysis.decide_final_status(
        {"status": "TARGET_SCAN_CONFIRMED_SPARSE"}, _region("reference"), _region("target"),
        {
            "non_text_anchor_count": 2, "absolute_residual_threshold": 10.0,
            "selected": {"transform_type": "translation", "max_residual": 20.0, "normalized_max_residual": 0.001, "leave_one_out_stability": 1.0},
        },
        {"geometry_overlap_score": 0.8},
        {"final_confidence": 0.8, "pass_threshold": 0.72},
    )
    assert status == "PARTIAL_LOW_CONFIDENCE"
    assert allowed is False
    assert any("residual" in item for item in blockers)


def test_runner_never_generates_repair_tasks_or_enters_stage3_2_by_default() -> None:
    report = runner._base_report("run", Path("reference.dwg"), Path("target.dwg"), runner._safety_flags(), None)
    assert report["repair_task_generated"] is False
    assert report["stage3_2_executed"] is False
    assert report["stage3_2_allowed"] is False
    assert report["copy_hashes_unchanged"] is None


def test_runner_has_no_save_command_or_entity_mutation_calls() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    forbidden = (
        "AddLine", "AddText", "AddPolyline", "AddCircle", "SendCommand",
        ".Save(", "SaveAs", "CopyObjects", "Explode(", "Close(True)", "NETLOAD",
    )
    assert not any(token in source for token in forbidden)
    assert "_close_document_without_save" in source


def test_all_stage_safety_flags_default_false() -> None:
    flags = runner._safety_flags()
    assert flags
    assert all(value is False for value in flags.values())
