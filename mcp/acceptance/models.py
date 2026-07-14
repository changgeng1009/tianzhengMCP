from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class T30ProbeWorkflowResult:
    workflow_id: str
    probe_result_path: str
    status: str
    capabilities: list[dict[str, Any]]
    candidate_methods: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "probe_result_path": self.probe_result_path,
            "status": self.status,
            "capabilities": list(self.capabilities),
            "candidate_methods": list(self.candidate_methods),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }


@dataclass
class ManualConfirmationTemplate:
    template_id: str
    generated_from_probe: str
    object_types: list[str]
    confirmation_items: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "generated_from_probe": self.generated_from_probe,
            "object_types": list(self.object_types),
            "confirmation_items": dict(self.confirmation_items),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class ConfirmedSchemaSet:
    schema_set_id: str
    schemas: list[dict[str, Any]]
    confirmed_object_types: list[str]
    unconfirmed_object_types: list[str]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_set_id": self.schema_set_id,
            "schemas": list(self.schemas),
            "confirmed_object_types": list(self.confirmed_object_types),
            "unconfirmed_object_types": list(self.unconfirmed_object_types),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }


@dataclass
class AcceptanceRunConfig:
    run_id: str = field(default_factory=lambda: f"accept_{uuid4().hex}")
    scenario_path: str = ""
    probe_result_path: str = ""
    manual_confirmation_path: str = ""
    sandbox_dir: str = "artifacts/acceptance_sandbox"
    output_dir: str = "artifacts/acceptance_reports"
    enable_real_writeback: bool = False
    real_com_mode: bool = False
    dry_run_only: bool = True
    verification_mode: str = "manual_review"
    thresholds: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_path": self.scenario_path,
            "probe_result_path": self.probe_result_path,
            "manual_confirmation_path": self.manual_confirmation_path,
            "sandbox_dir": self.sandbox_dir,
            "output_dir": self.output_dir,
            "enable_real_writeback": bool(self.enable_real_writeback),
            "real_com_mode": bool(self.real_com_mode),
            "dry_run_only": bool(self.dry_run_only),
            "verification_mode": self.verification_mode,
            "thresholds": dict(self.thresholds),
            "metadata": dict(self.metadata),
        }


@dataclass
class AcceptanceRunResult:
    run_id: str
    status: str
    confirmed_schema_status: dict[str, Any] = field(default_factory=dict)
    e2e_result: dict[str, Any] = field(default_factory=dict)
    writeback_result: dict[str, Any] = field(default_factory=dict)
    reread_verification: dict[str, Any] = field(default_factory=dict)
    acceptance_report_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "confirmed_schema_status": dict(self.confirmed_schema_status),
            "e2e_result": dict(self.e2e_result),
            "writeback_result": dict(self.writeback_result),
            "reread_verification": dict(self.reread_verification),
            "acceptance_report_path": self.acceptance_report_path,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }

