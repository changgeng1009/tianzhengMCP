from __future__ import annotations


def test_symbol_classifier_confidence_gate_and_template_id() -> None:
    from mcp.vision_templates.models import TemplateMatch
    from mcp.vision_templates.symbol_classifier import classify_symbols_from_matches

    symbols = classify_symbols_from_matches(
        [
            TemplateMatch("low", "s_low", "sprinkler", [0, 0, 1, 1], [0.5, 0.5], 0.5, "fixture", "img"),
            TemplateMatch("review", "v_mid", "valve", [0, 0, 1, 1], [0.5, 0.5], 0.7, "fixture", "img"),
            TemplateMatch("high", "f_high", "fitting", [0, 0, 1, 1], [0.5, 0.5], 0.9, "fixture", "img"),
        ]
    )

    assert [symbol.symbol_id for symbol in symbols] == ["sym_review", "sym_high"]
    assert symbols[0].metadata["confidence_band"] == "review"
    assert symbols[1].metadata["confidence_band"] == "high"
    assert symbols[1].matched_template_id == "f_high"

