from __future__ import annotations

from copy import deepcopy
from typing import Any

from mcp.repair_actions.geometry_utils import distance_point_to_point
from mcp.repair_actions.models import RepairAction, RepairPlanV2


def snap_repair_actions_to_target_graph(
    repair_plan: RepairPlanV2,
    target_graph: dict[str, Any],
    options: dict | None = None,
) -> RepairPlanV2:
    options = options or {}
    tolerance = float(options.get("tolerance", 10.0))
    nodes = [_xy(node.get("position")) for node in target_graph.get("nodes", []) if node.get("position")]
    actions = [_snap_action(action, nodes, tolerance) for action in repair_plan.actions]
    return RepairPlanV2(
        repair_plan.plan_id,
        repair_plan.source_reference_graph_id,
        repair_plan.target_graph_id,
        actions,
        repair_plan.review_actions,
        repair_plan.rejected_actions,
        repair_plan.confidence,
        repair_plan.warnings,
        repair_plan.errors,
        repair_plan.metadata,
    )


def _snap_action(action: RepairAction, nodes: list[list[float]], tolerance: float) -> RepairAction:
    geometry = deepcopy(action.geometry)
    metadata = dict(action.metadata)
    metadata["original_geometry"] = deepcopy(action.geometry)
    metadata["snap_applied"] = False
    if action.action_type == "add_pipe" and geometry.get("points"):
        new_points = []
        for point in geometry["points"]:
            snapped = _nearest(point, nodes, tolerance)
            if snapped != point:
                metadata["snap_applied"] = True
            new_points.append(snapped)
        geometry["points"] = new_points
    return RepairAction(
        **{**action.to_dict(), "geometry": geometry, "metadata": metadata}
    )


def _nearest(point: list[float], nodes: list[list[float]], tolerance: float) -> list[float]:
    if not nodes:
        return point
    nearest = min(nodes, key=lambda node: distance_point_to_point(point, node))
    return nearest if distance_point_to_point(point, nearest) <= tolerance else point


def _xy(value: Any) -> list[float]:
    return [float(value[0]), float(value[1])]

