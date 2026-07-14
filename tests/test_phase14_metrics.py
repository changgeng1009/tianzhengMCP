from __future__ import annotations


def test_metrics_counts_actions_warnings_errors_and_expected_missing() -> None:
    from mcp.e2e.metrics import calculate_e2e_metrics
    from mcp.e2e.models import E2EScenario

    scenario = E2EScenario(
        scenario_id="scn1",
        name="场景",
        reference_sources=[],
        target_dwg_path="target.dwg",
        expected_missing=[{"id": "p1"}, {"id": "p2"}],
    )
    result = {
        "repair_plan_v2": {
            "actions": [{"confidence": 0.9}, {"confidence": 0.8}],
            "review_actions": [{}],
            "rejected_actions": [{}],
        },
        "writeback_result": {"created_entities": [{"handle": "H1"}], "failed_actions": [{}]},
        "reread_verification": {"confirmed_entities": [{"handle": "H1"}]},
        "warnings": ["w1"],
        "errors": [],
    }

    metrics = calculate_e2e_metrics(scenario, result)

    assert metrics.generated_action_count == 2
    assert metrics.review_required_count == 1
    assert metrics.reread_confirmed_count == 1
    assert metrics.to_dict()["approximate_recall"] == 1.0

