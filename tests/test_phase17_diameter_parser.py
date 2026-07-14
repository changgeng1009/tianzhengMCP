from __future__ import annotations


def test_parse_diameter_text_supports_common_formats() -> None:
    from mcp.vision_templates.diameter_parser import parse_diameter_text

    assert parse_diameter_text("DN50").normalized == "DN50"
    assert parse_diameter_text("DN 50").normalized == "DN50"
    assert parse_diameter_text("De75").normalized == "De75"
    assert parse_diameter_text("φ100").normalized == "Φ100"
    assert parse_diameter_text("100").confidence < 0.7
    assert parse_diameter_text("abc") is None

