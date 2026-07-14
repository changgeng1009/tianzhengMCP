from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class T30Capability:
    capability_id: str
    object_type: str
    method_name: str
    available: bool
    confidence: float
    signature: dict[str, Any] | None = None
    probe_status: str = "unconfirmed"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "object_type": self.object_type,
            "method_name": self.method_name,
            "available": bool(self.available),
            "confidence": float(self.confidence),
            "signature": dict(self.signature or {}),
            "probe_status": self.probe_status,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


@dataclass
class T30ParameterSchema:
    object_type: str
    method_name: str
    parameters: dict[str, Any]
    required_fields: list[str]
    optional_fields: list[str]
    defaults: dict[str, Any]
    confidence: float
    source: str = "unknown"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "method_name": self.method_name,
            "parameters": dict(self.parameters),
            "required_fields": list(self.required_fields),
            "optional_fields": list(self.optional_fields),
            "defaults": dict(self.defaults),
            "confidence": float(self.confidence),
            "source": self.source,
            "warnings": list(self.warnings),
        }


@dataclass
class T30WritebackAction:
    action_id: str
    source_repair_action_id: str
    object_type: str
    method_name: str
    parameters: dict[str, Any]
    geometry: dict[str, Any]
    system: str | None
    dn: str | None
    layer: str | None
    confidence: float
    capability_status: str
    ready_to_execute: bool
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "source_repair_action_id": self.source_repair_action_id,
            "object_type": self.object_type,
            "method_name": self.method_name,
            "parameters": dict(self.parameters),
            "geometry": dict(self.geometry),
            "system": self.system,
            "dn": self.dn,
            "layer": self.layer,
            "confidence": float(self.confidence),
            "capability_status": self.capability_status,
            "ready_to_execute": bool(self.ready_to_execute),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class T30Transaction:
    transaction_id: str
    session_id: str
    sandbox_dwg_path: str
    original_dwg_path: str
    backup_path: str
    actions: list[T30WritebackAction]
    status: str = "planned"
    transaction_log: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "session_id": self.session_id,
            "sandbox_dwg_path": self.sandbox_dwg_path,
            "original_dwg_path": self.original_dwg_path,
            "backup_path": self.backup_path,
            "actions": [action.to_dict() for action in self.actions],
            "status": self.status,
            "transaction_log": list(self.transaction_log),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class T30WritebackResult:
    transaction_id: str
    status: str
    executed_actions: list[dict[str, Any]]
    failed_actions: list[dict[str, Any]]
    skipped_actions: list[dict[str, Any]]
    created_entities: list[dict[str, Any]]
    verification: dict[str, Any]
    rollback_available: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "executed_actions": list(self.executed_actions),
            "failed_actions": list(self.failed_actions),
            "skipped_actions": list(self.skipped_actions),
            "created_entities": list(self.created_entities),
            "verification": dict(self.verification),
            "rollback_available": bool(self.rollback_available),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }

