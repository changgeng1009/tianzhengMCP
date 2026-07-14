from __future__ import annotations


def test_template_evaluation_calculates_precision_and_recall() -> None:
    from mcp.vision_templates.evaluation import evaluate_template_detection
    from mcp.vision_templates.models import ClassifiedSymbol

    result = evaluate_template_detection(
        [
            ClassifiedSymbol("s1", "sprinkler_candidate", [0, 0, 10, 10], [5, 5], 0.9, "tpl1", "fixture"),
            ClassifiedSymbol("s2", "sprinkler_candidate", [100, 100, 110, 110], [105, 105], 0.8, "tpl1", "fixture"),
        ],
        [{"symbol_type": "sprinkler_candidate", "bbox": [0, 0, 10, 10]}],
    )

    assert result.true_positive == 1
    assert result.false_positive == 1
    assert result.false_negative == 0
    assert result.precision == 0.5
    assert result.recall == 1.0


def test_template_evaluation_empty_expected_warns_not_fails() -> None:
    from mcp.vision_templates.evaluation import evaluate_template_detection

    result = evaluate_template_detection([], [])

    assert result.warnings

