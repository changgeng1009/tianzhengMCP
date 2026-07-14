from __future__ import annotations

from mcp.repair_actions.models import RepairAction, RepairPlanV2


def validate_repair_plan_v2(
    repair_plan: RepairPlanV2,
    target_graph: dict,
    options: dict | None = None,
) -> dict:
    auto: list[dict] = []
    review: list[dict] = [action.to_dict() for action in repair_plan.review_actions]
    rejected: list[dict] = [action.to_dict() for action in repair_plan.rejected_actions]
    warnings: list[str] = list(repair_plan.warnings)
    errors: list[str] = []

    for action in repair_plan.actions:
        problems = _problems(action)
        if problems:
            rejected.append(action.to_dict())
            errors.extend(problems)
            continue
        if action.confidence >= 0.85 and action.auto_execute:
            auto.append(action.to_dict())
        elif action.confidence >= 0.6:
            review.append(action.to_dict())
        else:
            rejected.append(action.to_dict())

    return {
        "valid": not errors,
        "auto_executable": auto,
        "review_required": review,
        "rejected": rejected,
        "warnings": warnings,
        "errors": errors,
        "confidence": repair_plan.confidence,
    }


def _problems(action: RepairAction) -> list[str]:
    problems: list[str] = []
    if action.target_space != "cad_modelspace":
        problems.append(f"{action.action_id}: target_space must be cad_modelspace")
    if action.action_type == "add_pipe" and not action.dn:
        problems.append(f"{action.action_id}: missing dn")
    if not action.system:
        problems.append(f"{action.action_id}: missing system")
    if not action.geometry:
        problems.append(f"{action.action_id}: missing geometry")
    return problems

