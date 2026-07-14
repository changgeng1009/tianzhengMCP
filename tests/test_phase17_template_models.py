from __future__ import annotations


def test_vision_template_models_are_json_serializable() -> None:
    from mcp.vision_templates.models import (
        ClassifiedSymbol,
        ParsedDiameter,
        TemplateEvaluationResult,
        TemplateMatch,
        VisionTemplate,
    )

    template = VisionTemplate(
        template_id="sprinkler_upright",
        template_type="sprinkler",
        name="直立型喷头",
        image_path="templates/sprinkler.png",
        bbox=[0, 0, 10, 10],
        keypoints=[[5, 5]],
        expected_symbol_type="sprinkler_candidate",
        confidence_baseline=0.8,
        enabled=False,
    )
    match = TemplateMatch("m1", "sprinkler_upright", "sprinkler", [0, 0, 10, 10], [5, 5], 0.91, "fixture", "img.png")
    symbol = ClassifiedSymbol("s1", "sprinkler_candidate", [0, 0, 10, 10], [5, 5], 0.91, "sprinkler_upright", "fixture")
    diameter = ParsedDiameter("DN50", "DN50", 50, "DN", 0.95, "txt1")
    evaluation = TemplateEvaluationResult("sample1", 1, 1, 1, 0, 0, 1.0, 1.0, 0.91)

    assert template.to_dict()["enabled"] is False
    assert match.to_dict()["method"] == "fixture"
    assert symbol.to_dict()["matched_template_id"] == "sprinkler_upright"
    assert diameter.to_dict()["normalized"] == "DN50"
    assert evaluation.to_dict()["precision"] == 1.0


def test_template_store_register_query_disable_and_export() -> None:
    from mcp.vision_templates.models import VisionTemplate
    from mcp.vision_templates.template_store import VisionTemplateStore

    store = VisionTemplateStore()
    store.register_template(
        VisionTemplate(
            template_id="valve_gate",
            template_type="valve",
            name="闸阀",
            expected_symbol_type="valve_candidate",
            enabled=True,
        )
    )
    store.disable_template("valve_gate")

    assert store.get_template("valve_gate").enabled is False
    assert store.list_templates("valve")[0].template_id == "valve_gate"
    assert store.export_templates_json()["templates"][0]["template_id"] == "valve_gate"

