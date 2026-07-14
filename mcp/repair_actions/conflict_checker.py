from __future__ import annotations

from mcp.repair_actions.geometry_utils import is_near_duplicate_geometry
from mcp.repair_actions.models import RepairAction, RepairPlanV2


def check_repair_action_conflicts(
    repair_plan: RepairPlanV2,
    target_graph: dict,
    options: dict | None = None,
) -> RepairPlanV2:
    options = options or {}
    tolerance = float(options.get("tolerance", 10.0))
    clean: list[RepairAction] = []
    review = list(repair_plan.review_actions)
    rejected = list(repair_plan.rejected_actions)

    for action in repair_plan.actions:
        if action.target_space != "cad_modelspace" or not action.geometry:
            rejected.append(_mark(action, "invalid_geometry_or_space"))
            continue
        if action.action_type == "add_pipe" and _duplicates_pipe(action, target_graph.get("pipes", []), tolerance):
            review.append(_mark(action, "duplicate_existing_pipe", auto_execute=False))
            continue
        clean.append(action)

    return RepairPlanV2(
        repair_plan.plan_id,
        repair_plan.source_reference_graph_id,
        repair_plan.target_graph_id,
        clean,
        review,
        rejected,
        repair_plan.confidence,
        repair_plan.warnings,
        repair_plan.errors,
        repair_plan.metadata,
    )


def _duplicates_pipe(action: RepairAction, pipes: list[dict], tolerance: float) -> bool:
    for pipe in pipes:
        target_geom = {"start": pipe.get("start"), "end": pipe.get("end")}
        if is_near_duplicate_geometry(action.geometry, target_geom, tolerance):
            return True
    return False


def _mark(action: RepairAction, conflict: str, auto_execute: bool = False) -> RepairAction:
    metadata = dict(action.metadata)
    metadata["conflict"] = conflict
    return RepairAction(**{**action.to_dict(), "auto_execute": auto_execute, "metadata": metadata})

