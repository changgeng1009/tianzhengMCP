from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepairAction:
    action_id: str
    action_type: str
    target_space: str
    geometry: dict[str, Any]
    system: str | None
    dn: str | None
    layer: str | None
    source_element_id: str
    source_type: str
    confidence: float
    auto_execute: bool
    reason: str
    validation_status: str
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "target_space": self.target_space,
            "geometry": self.geometry,
            "system": self.system,
            "dn": self.dn,
            "layer": self.layer,
            "source_element_id": self.source_element_id,
            "source_type": self.source_type,
            "confidence": float(self.confidence),
            "auto_execute": bool(self.auto_execute),
            "reason": self.reason,
            "validation_status": self.validation_status,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class RepairPlanV2:
    plan_id: str
    source_reference_graph_id: str
    target_graph_id: str
    actions: list[RepairAction]
    review_actions: list[RepairAction]
    rejected_actions: list[RepairAction]
    confidence: float
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "source_reference_graph_id": self.source_reference_graph_id,
            "target_graph_id": self.target_graph_id,
            "actions": [action.to_dict() for action in self.actions],
            "review_actions": [action.to_dict() for action in self.review_actions],
            "rejected_actions": [action.to_dict() for action in self.rejected_actions],
            "confidence": float(self.confidence),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }


@dataclass
class GeometryMatchResult:
    matched: bool
    distance: float
    tolerance: float
    confidence: float
    reason: str
    target_element_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "distance": float(self.distance),
            "tolerance": float(self.tolerance),
            "confidence": float(self.confidence),
            "reason": self.reason,
            "target_element_id": self.target_element_id,
        }


@dataclass
class DryRunResult:
    valid: bool
    executable_actions: list[dict[str, Any]]
    review_actions: list[dict[str, Any]]
    rejected_actions: list[dict[str, Any]]
    simulated_entities: list[dict[str, Any]]
    warnings: list[str]
    errors: list[str]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "executable_actions": list(self.executable_actions),
            "review_actions": list(self.review_actions),
            "rejected_actions": list(self.rejected_actions),
            "simulated_entities": list(self.simulated_entities),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metrics": dict(self.metrics),
        }

