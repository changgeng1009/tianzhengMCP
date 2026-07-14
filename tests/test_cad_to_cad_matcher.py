from __future__ import annotations


def _line(entity_id: str, x2: float = 1000.0):
    return {
        "id": entity_id,
        "type": "line",
        "geometry": {
            "coordinate_system": "cad_world",
            "points": [
                {"x": 0.0, "y": 0.0, "coordinate_system": "cad_world"},
                {"x": x2, "y": 0.0, "coordinate_system": "cad_world"},
            ],
        },
        "properties": {},
    }


def _text(entity_id: str, text: str, x: float = 0.0):
    return {
        "id": entity_id,
        "type": "text",
        "geometry": {
            "coordinate_system": "cad_world",
            "points": [{"x": x, "y": 0.0, "coordinate_system": "cad_world"}],
        },
        "properties": {"text": text},
    }


def test_same_line_within_tolerance_matches():
    from cad_compare.matcher import EntityMatcher

    matcher = EntityMatcher(tolerance=1.0)

    assert matcher.is_match(_line("ref", 1000.0), _line("cur", 1000.5)) is True


def test_text_at_same_position_matches_even_if_content_differs_for_modify_detection():
    from cad_compare.matcher import EntityMatcher

    matcher = EntityMatcher(tolerance=1.0)

    assert matcher.is_match(_text("ref", "DN200"), _text("cur", "DN150")) is True
