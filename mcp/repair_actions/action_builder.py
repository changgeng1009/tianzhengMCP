from __future__ import annotations

from typing import Any
from uuid import uuid4

from mcp.repair_actions.models import RepairAction, RepairPlanV2


TYPE_MAP = {
    "pipe": "add_pipe",
    "sprinkler": "add_sprinkler",
    "valve": "add_valve",
    "fitting": "add_fitting",
}


def build_repair_actions(
    missing_result: dict[str, Any],
    aligned_reference_graph: dict[str, Any],
    target_graph: dict[str, Any],
    options: dict | None = None,
) -> RepairPlanV2:
    actions: list[RepairAction] = []
    review: list[RepairAction] = []
    rejected: list[RepairAction] = []
    warnings: list[str] = []

    for item in missing_result.get("true_missing", []):
        action = _action_from_missing(item, warnings)
        if action.confidence >= 0.85:
            actions.append(action)
        elif action.confidence >= 0.60:
            action.auto_execute = False
            review.append(action)
        else:
            action.auto_execute = False
            rejected.append(action)

    confidence_values = [action.confidence for action in actions + review + rejected]
    return RepairPlanV2(
        plan_id=f"repair_plan_v2_{uuid4().hex[:8]}",
        source_reference_graph_id=str(aligned_reference_graph.get("id", "aligned_reference_graph")),
        target_graph_id=str(target_graph.get("id", "target_graph")),
        actions=actions,
        review_actions=review,
        rejected_actions=rejected,
        confidence=round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 1.0,
        warnings=warnings,
        errors=[],
        metadata={"source": "coordinate_repair_actions"},
    )


def build_review_only_repair_actions(
    missing_result: dict[str, Any],
    aligned_reference_graph: dict[str, Any],
    target_graph: dict[str, Any],
    options: dict | None = None,
) -> RepairPlanV2:
    actions: list[RepairAction] = []
    warnings: list[str] = []
    for item in missing_result.get("true_missing", []) + missing_result.get("uncertain", []):
        action = _action_from_missing(item, warnings)
        action.auto_execute = False
        action.validation_status = "review_required"
        action.confidence = min(float(action.confidence), 0.84)
        action.reason = (
            "generated from low-confidence PDF/DWG primitive fallback; manual review required"
        )
        action.metadata = {**dict(action.metadata), "review_only": True, "fallback_generated": True}
        actions.append(action)
    confidence_values = [action.confidence for action in actions]
    return RepairPlanV2(
        plan_id=f"repair_plan_v2_{uuid4().hex[:8]}",
        source_reference_graph_id=str(aligned_reference_graph.get("id", "aligned_reference_graph")),
        target_graph_id=str(target_graph.get("id", "target_graph")),
        actions=[],
        review_actions=actions,
        rejected_actions=[],
        confidence=round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 1.0,
        warnings=warnings,
        errors=[],
        metadata={"source": "coordinate_repair_actions", "review_only": True},
    )


def _action_from_missing(item: dict[str, Any], warnings: list[str]) -> RepairAction:
    element = item["element"]
    element_type = item["element_type"]
    mapped = element.get("mapped_geometry", {})
    confidence = float(item.get("confidence", element.get("mapped_confidence", 0.0)))
    geometry = _action_geometry(element_type, mapped)
    system = element.get("system_type") or element.get("system")
    dn = element.get("dn")
    if element_type == "pipe" and not dn:
        warnings.append(f"pipe action missing dn: {element.get('id')}")
    if not system:
        warnings.append(f"action missing system: {element.get('id')}")
    return RepairAction(
        action_id=f"act_{element.get('source_element_id') or element.get('id')}",
        action_type=TYPE_MAP.get(element_type, "review_only"),
        target_space="cad_modelspace",
        geometry=geometry,
        system=system,
        dn=dn,
        layer=element.get("layer"),
        source_element_id=str(element.get("source_element_id") or element.get("id")),
        source_type="aligned_reference_graph",
        confidence=confidence,
        auto_execute=confidence >= 0.85,
        reason=item.get("reason", f"missing {element_type} detected from aligned reference graph"),
        validation_status="pending",
        warnings=[],
        metadata={"element_type": element_type},
    )


def _action_geometry(element_type: str, mapped: dict[str, Any]) -> dict[str, Any]:
    if element_type == "pipe":
        return {"type": "polyline", "points": [_xy(mapped.get("start")), _xy(mapped.get("end"))]}
    return {"type": "point", "point": _xy(mapped.get("position"))}


def _xy(value: Any) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return [float(value[0]), float(value[1])]
    return [0.0, 0.0]
