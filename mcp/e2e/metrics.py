from __future__ import annotations

from typing import Any

from mcp.e2e.models import E2EMetrics, E2ERunResult, E2EScenario


def calculate_e2e_metrics(
    scenario: E2EScenario,
    result: E2ERunResult | dict,
) -> E2EMetrics:
    data = result.to_dict() if isinstance(result, E2ERunResult) else dict(result)
    repair_plan = dict(data.get("repair_plan_v2") or {})
    actions = list(repair_plan.get("actions") or [])
    review = list(repair_plan.get("review_actions") or [])
    rejected = list(repair_plan.get("rejected_actions") or [])
    writeback = dict(data.get("writeback_result") or {})
    reread = dict(data.get("reread_verification") or {})
    confidences = [float(action.get("confidence") or 0.0) for action in actions]
    generated = len(actions)
    expected = len(scenario.expected_missing)
    confirmed = len(reread.get("confirmed_entities") or [])
    derived: dict[str, Any] = {}
    if expected:
        derived["approximate_recall"] = min(1.0, generated / expected)
        derived["approximate_precision"] = min(1.0, expected / generated) if generated else 0.0
    false_positive = max(0, generated - expected) / generated if generated and expected else 0.0
    return E2EMetrics(
        detected_missing_count=len((data.get("missing_result") or {}).get("true_missing", [])),
        generated_action_count=generated,
        auto_executable_count=sum(1 for action in actions if action.get("auto_execute", True)),
        review_required_count=len(review),
        rejected_count=len(rejected),
        writeback_success_count=len(writeback.get("created_entities") or []),
        writeback_failed_count=len(writeback.get("failed_actions") or []),
        reread_confirmed_count=confirmed,
        false_positive_estimate=false_positive,
        confidence_average=sum(confidences) / len(confidences) if confidences else 0.0,
        warnings_count=len(data.get("warnings") or []),
        errors_count=len(data.get("errors") or []),
        metadata={"derived": derived},
    )

