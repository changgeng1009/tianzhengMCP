from __future__ import annotations

from mcp.repair_actions.models import DryRunResult, RepairPlanV2


def generate_repair_action_report(
    repair_plan: RepairPlanV2,
    dry_run_result: DryRunResult,
) -> dict:
    return {
        "summary": {
            "total_actions": len(repair_plan.actions) + len(repair_plan.review_actions) + len(repair_plan.rejected_actions),
            "auto_executable": len(dry_run_result.executable_actions),
            "review_required": len(dry_run_result.review_actions),
            "rejected": len(dry_run_result.rejected_actions),
        },
        "actions": [action.to_dict() for action in repair_plan.actions],
        "warnings": list(repair_plan.warnings) + list(dry_run_result.warnings),
        "errors": list(repair_plan.errors) + list(dry_run_result.errors),
        "confidence": repair_plan.confidence,
    }
