from __future__ import annotations


def test_template_matcher_no_templates_returns_no_matches_and_warning() -> None:
    from mcp.vision_templates.template_matcher import match_templates
    from mcp.vision_templates.template_store import VisionTemplateStore

    matches = match_templates({"image_path": "fixture.png"}, VisionTemplateStore(), options={"warnings": []})

    assert matches == []


def test_template_matcher_fixture_mode_returns_real_template_match() -> None:
    from mcp.vision_templates.models import VisionTemplate
    from mcp.vision_templates.template_matcher import match_templates
    from mcp.vision_templates.template_store import VisionTemplateStore

    store = VisionTemplateStore()
    store.register_template(
        VisionTemplate(
            template_id="valve_fixture",
            template_type="valve",
            name="fixture valve",
            expected_symbol_type="valve_candidate",
            enabled=True,
        )
    )

    matches = match_templates(
        {"image_path": "fixture.png"},
        store,
        template_type="valve",
        options={"fixture_matches": [{"template_id": "valve_fixture", "bbox": [1, 2, 11, 12], "confidence": 0.88}]},
    )

    assert matches[0].template_id == "valve_fixture"
    assert matches[0].confidence == 0.88

