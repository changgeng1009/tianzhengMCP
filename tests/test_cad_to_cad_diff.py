from __future__ import annotations


def _model(kind: str, entities: list[dict]):
    return {"source": {"kind": kind}, "entities": entities, "global_uncertainties": []}


def _line(entity_id: str, x: float = 0.0, layer: str = "A-PIPE"):
    return {
        "id": entity_id,
        "handle": entity_id,
        "type": "line",
        "layer": layer,
        "geometry": {
            "coordinate_system": "cad_world",
            "points": [
                {"x": x, "y": 0.0, "coordinate_system": "cad_world"},
                {"x": x + 1000.0, "y": 0.0, "coordinate_system": "cad_world"},
            ],
        },
        "properties": {"layer": layer},
        "confidence": 1.0,
    }


def _text(entity_id: str, text: str, x: float = 0.0):
    return {
        "id": entity_id,
        "handle": entity_id,
        "type": "text",
        "layer": "A-TEXT",
        "geometry": {
            "coordinate_system": "cad_world",
            "points": [{"x": x, "y": 0.0, "coordinate_system": "cad_world"}],
        },
        "properties": {"text": text, "layer": "A-TEXT"},
        "confidence": 1.0,
    }


def test_identical_line_does_not_output_add():
    from cad_compare.diff_engine import CADToCADDiffEngine

    diff = CADToCADDiffEngine(tolerance=1.0).compare(
        _model("reference_dwg", [_line("ref")]),
        _model("current_autocad", [_line("cur")]),
    )

    assert diff["summary"]["add"] == 0
    assert diff["items"] == []


def test_missing_reference_line_outputs_add():
    from cad_compare.diff_engine import CADToCADDiffEngine

    diff = CADToCADDiffEngine().compare(
        _model("reference_dwg", [_line("ref")]),
        _model("current_autocad", []),
    )

    assert diff["summary"]["add"] == 1
    assert diff["items"][0]["operation"] == "add"
    assert diff["items"][0]["entity"]["source"] == "reference_dwg"


def test_small_coordinate_error_within_tolerance_does_not_duplicate_line():
    from cad_compare.diff_engine import CADToCADDiffEngine

    diff = CADToCADDiffEngine(tolerance=2.0).compare(
        _model("reference_dwg", [_line("ref", x=0.0)]),
        _model("current_autocad", [_line("cur", x=1.0)]),
    )

    assert diff["summary"]["add"] == 0


def test_same_text_does_not_output_add():
    from cad_compare.diff_engine import CADToCADDiffEngine

    diff = CADToCADDiffEngine().compare(
        _model("reference_dwg", [_text("ref_text", "DN200")]),
        _model("current_autocad", [_text("cur_text", "DN200")]),
    )

    assert diff["items"] == []


def test_different_text_outputs_modify():
    from cad_compare.diff_engine import CADToCADDiffEngine

    diff = CADToCADDiffEngine().compare(
        _model("reference_dwg", [_text("ref_text", "DN200")]),
        _model("current_autocad", [_text("cur_text", "DN150")]),
    )

    assert diff["items"][0]["operation"] == "modify"
    assert diff["items"][0]["changes"]["properties"]["to"]["text"] == "DN200"


def test_same_text_moved_beyond_tolerance_outputs_move():
    from cad_compare.diff_engine import CADToCADDiffEngine

    diff = CADToCADDiffEngine(tolerance=1.0).compare(
        _model("reference_dwg", [_text("ref_text", "DN200", x=100.0)]),
        _model("current_autocad", [_text("cur_text", "DN200", x=0.0)]),
    )

    assert diff["summary"]["move"] == 1
    assert diff["items"][0]["operation"] == "move"


def test_extra_current_entity_outputs_delete_suggestion_only():
    from cad_compare.diff_engine import CADToCADDiffEngine

    diff = CADToCADDiffEngine().compare(
        _model("reference_dwg", []),
        _model("current_autocad", [_line("cur_extra")]),
    )

    assert diff["items"][0]["operation"] == "delete_suggestion"
    assert diff["items"][0]["automatic_execution_allowed"] is False


def test_diff_result_can_convert_to_execution_plan_preview():
    from cad_compare.diff_engine import CADToCADDiffEngine

    engine = CADToCADDiffEngine()
    diff = engine.compare(
        _model("reference_dwg", [_line("ref_missing")]),
        _model("current_autocad", []),
    )
    preview = engine.build_execution_plan_preview(diff)

    assert preview["previewed"] is True
    assert preview["operations"][0]["action"] == "add_line"
    assert preview["operations"][0]["executable"] is True


def test_delete_suggestion_is_not_executable_in_execution_plan_preview():
    from cad_compare.diff_engine import CADToCADDiffEngine

    engine = CADToCADDiffEngine()
    diff = engine.compare(
        _model("reference_dwg", []),
        _model("current_autocad", [_line("cur_extra")]),
    )
    preview = engine.build_execution_plan_preview(diff)

    assert preview["operations"][0]["action"] == "delete_suggestion"
    assert preview["operations"][0]["executable"] is False
