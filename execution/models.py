from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OperationType(str, Enum):
    ADD_LINE = "add_line"
    ADD_POLYLINE = "add_polyline"
    ADD_TEXT = "add_text"
    MOVE_ENTITY = "move_entity"
    MODIFY_ENTITY = "modify_entity"
    DELETE_SUGGESTION = "delete_suggestion"


class OperationStatus(str, Enum):
    PENDING = "pending"
    PREVIEWED = "previewed"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


EXECUTABLE_ACTIONS = {
    OperationType.ADD_LINE,
    OperationType.ADD_POLYLINE,
    OperationType.ADD_TEXT,
}


def _coerce_operation_type(value: OperationType | str) -> OperationType:
    return value if isinstance(value, OperationType) else OperationType(value)


def _coerce_status(value: OperationStatus | str) -> OperationStatus:
    return value if isinstance(value, OperationStatus) else OperationStatus(value)


def _coerce_risk(value: RiskLevel | str) -> RiskLevel:
    return value if isinstance(value, RiskLevel) else RiskLevel(value)


@dataclass
class Operation:
    id: str
    action: OperationType | str
    entity_type: str
    geometry: dict[str, Any]
    layer: str
    reason: str
    source_diff_id: str
    risk_level: RiskLevel | str
    requires_confirmation: bool
    mapping_confidence: float | None = None
    calibration_id: str | None = None
    transform_type: str | None = None
    status: OperationStatus | str = OperationStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.action = _coerce_operation_type(self.action)
        self.status = _coerce_status(self.status)
        self.risk_level = _coerce_risk(self.risk_level)
        if self.action == OperationType.DELETE_SUGGESTION:
            self.requires_confirmation = True
            self.risk_level = RiskLevel.HIGH

    @property
    def executable(self) -> bool:
        return self.action in EXECUTABLE_ACTIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action.value,
            "entity_type": self.entity_type,
            "geometry": self.geometry,
            "layer": self.layer,
            "reason": self.reason,
            "source_diff_id": self.source_diff_id,
            "risk_level": self.risk_level.value,
            "requires_confirmation": self.requires_confirmation,
            "mapping_confidence": self.mapping_confidence,
            "calibration_id": self.calibration_id,
            "transform_type": self.transform_type,
            "status": self.status.value,
            "executable": self.executable,
            "result": self.result,
        }


@dataclass
class ExecutionPlan:
    id: str
    operations: list[Operation]
    confirmed: bool = False
    previewed: bool = False
    active_document: str | None = None
    risk_level: RiskLevel | str = RiskLevel.LOW

    def __post_init__(self) -> None:
        self.risk_level = self._compute_risk()
        if len(self.operations) > 10:
            for operation in self.operations:
                operation.risk_level = RiskLevel.HIGH

    def _compute_risk(self) -> RiskLevel:
        if len(self.operations) > 10:
            return RiskLevel.HIGH
        if any(_coerce_risk(operation.risk_level) == RiskLevel.HIGH for operation in self.operations):
            return RiskLevel.HIGH
        if any(_coerce_risk(operation.risk_level) == RiskLevel.MEDIUM for operation in self.operations):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "confirmed": self.confirmed,
            "previewed": self.previewed,
            "active_document": self.active_document,
            "risk_level": self.risk_level.value,
            "operation_count": len(self.operations),
            "operations": [operation.to_dict() for operation in self.operations],
        }


@dataclass
class ExecutionResult:
    plan_id: str
    success: bool
    results: list[dict[str, Any]]
    active_document: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "success": self.success,
            "active_document": self.active_document,
            "results": self.results,
        }


@dataclass(frozen=True)
class OperationQueueSnapshot:
    plan_id: str
    operations: list[dict[str, Any]]
    summary: dict[str, Any]
