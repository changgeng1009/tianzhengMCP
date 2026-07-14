from __future__ import annotations


def _model(entities: list[dict]):
    return {
        "source": "semantic_model",
        "entities": entities,
        "summary": {"total": len(entities)},
    }


def _pipe(
    handle: str,
    x1: float = 0.0,
    y1: float = 0.0,
    x2: float = 1000.0,
    y2: float = 0.0,
    diameter: str = "DN100",
    system_type: str = "消防",
    layer: str = "PIPE-消防",
):
    return {
        "handle": handle,
        "object_name": "TDbPipe",
        "semantic_type": "pipe",
        "system_type": system_type,
        "layer": layer,
        "diameter": {
            "raw": diameter,
            "normalized": diameter,
            "source": "TDbPipe.DNDiameter",
            "confidence": 0.95,
            "requires_confirmation": False,
        },
        "bounding_box": [x1, y1, 0.0, x2, y2, 0.0],
        "inferred_geometry": {
            "orientation": "horizontal" if y1 == y2 else "diagonal",
            "start_point": [x1, y1, 0.0],
            "end_point": [x2, y2, 0.0],
            "length": abs(x2 - x1),
            "source": "bounding_box_inference",
        },
    }


def test_identical_pipe_has_no_diff():
    from semantic_diff.diff_engine import SemanticDiffEngine

    result = SemanticDiffEngine(match_tolerance=50.0).compare(
        current_model=_model([_pipe("cur")]),
        reference_model=_model([_pipe("ref")]),
    )

    assert result == {
        "add_pipe": [],
        "remove_pipe": [],
        "modify_pipe": [],
        "move_pipe": [],
        "diameter_mismatch": [],
        "system_mismatch": [],
    }


def test_reference_only_pipe_outputs_add_pipe():
    from semantic_diff.diff_engine import SemanticDiffEngine

    result = SemanticDiffEngine().compare(
        current_model=_model([]),
        reference_model=_model([_pipe("ref_missing")]),
    )

    assert result["add_pipe"][0]["pipe_handle"] == "ref_missing"
    assert result["add_pipe"][0]["reference_diameter"] == "DN100"


def test_current_only_pipe_outputs_remove_pipe():
    from semantic_diff.diff_engine import SemanticDiffEngine

    result = SemanticDiffEngine().compare(
        current_model=_model([_pipe("cur_extra")]),
        reference_model=_model([]),
    )

    assert result["remove_pipe"][0]["pipe_handle"] == "cur_extra"
    assert result["remove_pipe"][0]["automatic_execution_allowed"] is False


def test_pipe_diameter_mismatch_outputs_modify_and_high_severity_mismatch():
    from semantic_diff.diff_engine import SemanticDiffEngine

    result = SemanticDiffEngine(match_tolerance=50.0).compare(
        current_model=_model([_pipe("cur", diameter="DN100")]),
        reference_model=_model([_pipe("ref", diameter="DN200")]),
    )

    assert result["diameter_mismatch"] == [
        {
            "pipe_handle": "cur",
            "reference_pipe_handle": "ref",
            "current": "DN100",
            "reference": "DN200",
            "severity": "high",
        }
    ]
    assert result["modify_pipe"][0]["change_type"] == "diameter_mismatch"


def test_pipe_system_mismatch_outputs_system_mismatch():
    from semantic_diff.diff_engine import SemanticDiffEngine

    result = SemanticDiffEngine(match_tolerance=50.0).compare(
        current_model=_model([_pipe("cur", system_type="给水", layer="PIPE-给水")]),
        reference_model=_model([_pipe("ref", system_type="消防", layer="PIPE-消防")]),
    )

    assert result["system_mismatch"] == [
        {
            "pipe_handle": "cur",
            "reference_pipe_handle": "ref",
            "current": "给水",
            "reference": "消防",
            "severity": "high",
        }
    ]
    assert result["modify_pipe"][0]["change_type"] == "system_mismatch"


def test_pipe_move_beyond_threshold_but_inside_match_tolerance_outputs_move():
    from semantic_diff.diff_engine import SemanticDiffEngine

    result = SemanticDiffEngine(match_tolerance=500.0, move_tolerance=20.0).compare(
        current_model=_model([_pipe("cur", x1=100.0, x2=1100.0)]),
        reference_model=_model([_pipe("ref", x1=0.0, x2=1000.0)]),
    )

    assert result["move_pipe"][0]["pipe_handle"] == "cur"
    assert result["move_pipe"][0]["reference_pipe_handle"] == "ref"
    assert result["move_pipe"][0]["distance"] == 100.0


def test_nearest_geometry_match_is_used_when_multiple_candidates_exist():
    from semantic_diff.diff_engine import SemanticDiffEngine

    result = SemanticDiffEngine(match_tolerance=500.0).compare(
        current_model=_model(
            [
                _pipe("cur_far", x1=300.0, x2=1300.0),
                _pipe("cur_near", x1=5.0, x2=1005.0),
            ]
        ),
        reference_model=_model([_pipe("ref", diameter="DN150")]),
    )

    assert result["diameter_mismatch"][0]["pipe_handle"] == "cur_near"
    assert result["remove_pipe"][0]["pipe_handle"] == "cur_far"


def test_non_pipe_entities_are_ignored_by_pipe_diff_result():
    from semantic_diff.diff_engine import SemanticDiffEngine

    valve = {
        "handle": "valve1",
        "semantic_type": "valve",
        "object_name": "TDbPipeValve",
        "system_type": "消防",
        "layer": "VALVE_消防",
    }

    result = SemanticDiffEngine().compare(
        current_model=_model([valve]),
        reference_model=_model([]),
    )

    assert result["remove_pipe"] == []
