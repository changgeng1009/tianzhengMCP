from __future__ import annotations


def test_cv_provider_optional_template_store_adds_template_symbols(monkeypatch) -> None:
    from mcp.vision import cv_provider
    from mcp.vision.cv_provider import CVVisionProvider
    from mcp.vision_templates.models import VisionTemplate
    from mcp.vision_templates.template_store import VisionTemplateStore

    monkeypatch.setattr(cv_provider, "is_opencv_available", lambda: False)
    store = VisionTemplateStore()
    store.register_template(
        VisionTemplate(
            template_id="sprinkler_fixture",
            template_type="sprinkler",
            name="fixture sprinkler",
            expected_symbol_type="sprinkler_candidate",
            enabled=True,
        )
    )
    provider = CVVisionProvider(template_store=store, template_match_threshold=0.85)
    result = provider.parse_png(
        "fixture.png",
        metadata={
            "allow_missing_fixture": True,
            "template_fixture_matches": [
                {"template_id": "sprinkler_fixture", "bbox": [10, 10, 20, 20], "confidence": 0.9}
            ],
        },
    )

    graph = result.semantic_graph.to_dict()

    assert graph["sprinklers"][0]["metadata"]["matched_template_id"] == "sprinkler_fixture"
    assert graph["symbols"][0]["metadata"]["method"] == "fixture"


def test_cv_provider_template_library_disabled_preserves_old_behavior(monkeypatch) -> None:
    from mcp.vision import cv_provider
    from mcp.vision.cv_provider import CVVisionProvider

    monkeypatch.setattr(cv_provider, "is_opencv_available", lambda: False)
    result = CVVisionProvider(use_template_library=False).parse_png(
        "fixture.png",
        metadata={"allow_missing_fixture": True, "fixture_elements": []},
    )

    assert all("template" not in warning.lower() for warning in result.warnings)

