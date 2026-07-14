from __future__ import annotations


def test_text_semantics_extracts_diameters_systems_and_labels() -> None:
    from mcp.vision_templates.text_semantics import extract_text_semantics

    result = extract_text_semantics(
        [
            {"id": "t1", "text": "DN50 喷淋管", "confidence": 0.9},
            {"id": "t2", "text": "A栋", "confidence": 0.8},
            {"id": "t3", "text": "图例 给水管", "confidence": 0.85},
        ]
    )

    assert result["diameters"][0]["normalized"] == "DN50"
    assert result["systems"][0]["system_type"] == "sprinkler"
    assert result["building_labels"][0]["text"] == "A栋"
    assert result["legends"][0]["text"].startswith("图例")


def test_text_semantics_empty_ocr_returns_warning() -> None:
    from mcp.vision_templates.text_semantics import extract_text_semantics

    result = extract_text_semantics([])

    assert result["warnings"]

