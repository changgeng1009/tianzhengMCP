from __future__ import annotations

from mcp.repair_actions.geometry_utils import is_near_duplicate_geometry
from mcp.repair_actions.models import RepairAction, RepairPlanV2


def optimize_repair_plan_v2(
    repair_plan: RepairPlanV2,
    target_graph: dict,
    options: dict | None = None,
) -> RepairPlanV2:
    options = options or {}
    tolerance = float(options.get("tolerance", 1.0))
    optimized: list[RepairAction] = []
    removed: list[str] = []
    for action in repair_plan.actions:
        duplicate = next(
            (
                existing
                for existing in optimized
                if action.action_type == existing.action_type
                and action.system == existing.system
                and action.dn == existing.dn
                and is_near_duplicate_geometry(action.geometry, existing.geometry, tolerance)
            ),
            None,
        )
        if duplicate:
            removed.append(action.action_id)
            continue
        optimized.append(action)
    metadata = dict(repair_plan.metadata)
    metadata["removed_duplicate_actions"] = removed
    return RepairPlanV2(
        repair_plan.plan_id,
        repair_plan.source_reference_graph_id,
        repair_plan.target_graph_id,
        optimized,
        repair_plan.review_actions,
        repair_plan.rejected_actions,
        repair_plan.confidence,
        repair_plan.warnings,
        repair_plan.errors,
        metadata,
    )

