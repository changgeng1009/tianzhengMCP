from __future__ import annotations

from mcp.repair_actions.action_validator import validate_repair_plan_v2
from mcp.repair_actions.models import DryRunResult, RepairPlanV2


def dry_run_repair_plan(
    repair_plan: RepairPlanV2,
    target_graph: dict,
    options: dict | None = None,
) -> DryRunResult:
    validation = validate_repair_plan_v2(repair_plan, target_graph, options)
    simulated = [
        {
            "action_id": action["action_id"],
            "action_type": action["action_type"],
            "geometry": action["geometry"],
            "dry_run": True,
        }
        for action in validation["auto_executable"]
    ]
    return DryRunResult(
        valid=validation["valid"],
        executable_actions=validation["auto_executable"],
        review_actions=validation["review_required"],
        rejected_actions=validation["rejected"],
        simulated_entities=simulated,
        warnings=validation["warnings"],
        errors=validation["errors"],
        metrics={
            "auto_executable": len(validation["auto_executable"]),
            "review_required": len(validation["review_required"]),
            "rejected": len(validation["rejected"]),
        },
    )

