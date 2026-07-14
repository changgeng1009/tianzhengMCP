from __future__ import annotations

from pathlib import Path

from mcp.acceptance import stage3_2_missing_detection as stage3_2


def _line(handle: str, x1: float, y1: float, x2: float, y2: float, *, layer: str = "0") -> dict:
    return {
        "handle": handle,
        "object_name": "AcDbLine",
        "entity_name": "AcDbLine",
        "layer": layer,
        "bbox": [[min(x1, x2), min(y1, y2), 0.0], [max(x1, x2), max(y1, y2), 0.0]],
        "geometry": {"start_point": [x1, y1, 0.0], "end_point": [x2, y2, 0.0]},
    }


def _bbox_entity(handle: str, name: str, x: float, y: float, *, layer: str = "TDB") -> dict:
    return {
        "handle": handle,
        "object_name": name,
        "entity_name": name,
        "layer": layer,
        "bbox": [[x, y, 0.0], [x + 10, y + 10, 0.0]],
        "geometry": {},
    }


def test_stage1_seed_line_is_excluded() -> None:
    seed = _line("135BE", 0, 0, 10, 0, layer="MCP_S1_VALIDATION")
    kept, excluded = stage3_2.filter_detection_entities(
        [seed, _line("A", 0, 0, 0, 10)], seed_handle="135BE", seed_layer="MCP_S1_VALIDATION"
    )
    assert len(kept) == 1
    assert excluded[0]["reason"] == "stage1_seed_line"


def test_title_frame_and_tdb_drawing_name_are_excluded() -> None:
    entities = [
        _bbox_entity("T", "AcDbText", 0, 0, layer="TWT_TITLE"),
        _bbox_entity("D", "TDbDrawingName", 20, 0),
    ]
    kept, excluded = stage3_2.filter_detection_entities(entities, seed_handle="S", seed_layer="SEED")
    assert kept == []
    assert len(excluded) == 2


def test_exact_transformed_geometry_matches_one_to_one() -> None:
    reference = [_line("R1", 0, 0, 100, 0), _line("R2", 0, 10, 100, 10)]
    target = [_line("T1", 50, 25, 150, 25), _line("T2", 50, 35, 150, 35)]
    result = stage3_2.one_to_one_match(reference, target, [50, 25])
    assert len(result["matches"]) == 2
    assert result["missing_reference_entities"] == []
    assert result["target_only_entities"] == []


def test_unmatched_reference_is_missing() -> None:
    result = stage3_2.one_to_one_match([_line("R", 0, 0, 100, 0)], [], [50, 25])
    assert [item["handle"] for item in result["missing_reference_entities"]] == ["R"]


def test_compound_line_match_is_detected_as_ambiguous() -> None:
    reference = _line("R", 0, 0, 100, 0)
    target = [_line("T1", 50, 25, 100, 25), _line("T2", 100, 25, 150, 25)]
    classified = stage3_2.classify_missing_entities([reference], target, [50, 25])
    assert classified["ambiguous_tasks"][0]["classification"] == "AMBIGUOUS_MATCH"
    assert classified["repair_task_drafts"] == []


def test_complete_high_confidence_line_generates_draft() -> None:
    classified = stage3_2.classify_missing_entities([_line("R", 0, 0, 100, 0)], [], [50, 25])
    draft = classified["repair_task_drafts"][0]
    assert draft["classification"] == "MISSING_HIGH_CONFIDENCE"
    assert draft["confidence"] >= 0.95
    assert draft["route"] == "direct_com_candidate"
    assert draft["target_wcs_geometry"]["start_point"] == [50.0, 25.0, 0.0]
    assert draft["execution_allowed"] is False


def test_tdb_object_is_manual_only() -> None:
    classified = stage3_2.classify_missing_entities([_bbox_entity("P", "TDbPipe", 0, 0)], [], [50, 25])
    assert len(classified["tianzheng_manual_tasks"]) == 1
    assert classified["repair_task_drafts"] == []
    assert classified["tianzheng_manual_tasks"][0]["execution_allowed"] is False


def test_circle_is_blocked_outside_automatic_whitelist() -> None:
    circle = _bbox_entity("C", "AcDbCircle", 0, 0, layer="0")
    circle["geometry"] = {"center": [5, 5, 0], "radius": 5.0}
    classified = stage3_2.classify_missing_entities([circle], [], [50, 25])
    assert classified["blocked_tasks"][0]["classification"] == "BLOCKED_UNSUPPORTED_OBJECT"
    assert classified["repair_task_drafts"] == []


def test_repair_draft_has_no_automatic_fallback() -> None:
    draft = stage3_2.classify_missing_entities([_line("R", 0, 0, 100, 0)], [], [50, 25])["repair_task_drafts"][0]
    assert draft["preferred_backend"] == "com"
    assert draft["allowed_backends"] == ["com"]
    assert draft["execution_backend_class"] == "ComCadBackend"
    assert draft["automatic_fallback"] is False
    assert draft["fallback_policy"] == "block"


def test_stage3_2_module_does_not_connect_to_cad_or_mutate_drawings() -> None:
    source = Path(stage3_2.__file__).read_text(encoding="utf-8")
    forbidden = (
        "win32com", "GetActiveObject", "Dispatch(", "Documents.Open", "AddLine(",
        "AddText(", "AddPolyline(", "AddCircle(", "SendCommand(", ".Save(",
        "SaveAs(", "CopyObjects(", "Close(True)", "NETLOAD",
    )
    assert not any(token in source for token in forbidden)
    assert all(value is False for value in stage3_2._safety_flags().values())
