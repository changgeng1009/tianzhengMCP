from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class E2EScenario:
    scenario_id: str
    name: str
    reference_sources: list[dict[str, Any]]
    target_dwg_path: str
    expected_missing: list[dict[str, Any]] = field(default_factory=list)
    manual_anchor_pairs: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "reference_sources": list(self.reference_sources),
            "target_dwg_path": self.target_dwg_path,
            "expected_missing": list(self.expected_missing),
            "manual_anchor_pairs": list(self.manual_anchor_pairs),
            "options": dict(self.options),
            "metadata": dict(self.metadata),
        }


@dataclass
class E2ERunConfig:
    run_id: str = field(default_factory=lambda: f"e2e_{uuid4().hex}")
    scenario_id: str = ""
    real_com_mode: bool = False
    dry_run_only: bool = True
    sandbox_dir: str | None = None
    require_confirmed_schema: bool = True
    enable_spatial_alignment: bool = True
    enable_coordinate_repair_actions: bool = True
    enable_t30_writeback: bool = False
    verification_mode: str = "fake"
    thresholds: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "real_com_mode": bool(self.real_com_mode),
            "dry_run_only": bool(self.dry_run_only),
            "sandbox_dir": self.sandbox_dir,
            "require_confirmed_schema": bool(self.require_confirmed_schema),
            "enable_spatial_alignment": bool(self.enable_spatial_alignment),
            "enable_coordinate_repair_actions": bool(self.enable_coordinate_repair_actions),
            "enable_t30_writeback": bool(self.enable_t30_writeback),
            "verification_mode": self.verification_mode,
            "thresholds": dict(self.thresholds),
            "metadata": dict(self.metadata),
        }


@dataclass
class E2EMetrics:
    detected_missing_count: int = 0
    generated_action_count: int = 0
    auto_executable_count: int = 0
    review_required_count: int = 0
    rejected_count: int = 0
    writeback_success_count: int = 0
    writeback_failed_count: int = 0
    reread_confirmed_count: int = 0
    false_positive_estimate: float = 0.0
    confidence_average: float = 0.0
    warnings_count: int = 0
    errors_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected_missing_count": int(self.detected_missing_count),
            "generated_action_count": int(self.generated_action_count),
            "auto_executable_count": int(self.auto_executable_count),
            "review_required_count": int(self.review_required_count),
            "rejected_count": int(self.rejected_count),
            "writeback_success_count": int(self.writeback_success_count),
            "writeback_failed_count": int(self.writeback_failed_count),
            "reread_confirmed_count": int(self.reread_confirmed_count),
            "false_positive_estimate": float(self.false_positive_estimate),
            "confidence_average": float(self.confidence_average),
            "warnings_count": int(self.warnings_count),
            "errors_count": int(self.errors_count),
            "metadata": dict(self.metadata),
            **dict(self.metadata.get("derived", {})),
        }


@dataclass
class E2ERunResult:
    run_id: str
    scenario_id: str
    status: str
    pipeline_result: dict[str, Any] = field(default_factory=dict)
    repair_plan_v2: dict[str, Any] = field(default_factory=dict)
    writeback_result: dict[str, Any] = field(default_factory=dict)
    reread_verification: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    report_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "status": self.status,
            "pipeline_result": dict(self.pipeline_result),
            "repair_plan_v2": dict(self.repair_plan_v2),
            "writeback_result": dict(self.writeback_result),
            "reread_verification": dict(self.reread_verification),
            "metrics": dict(self.metrics),
            "report_path": self.report_path,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }


def scenario_from_dict(data: dict[str, Any]) -> E2EScenario:
    return E2EScenario(
        scenario_id=str(data.get("scenario_id") or ""),
        name=str(data.get("name") or ""),
        reference_sources=list(data.get("reference_sources") or []),
        target_dwg_path=str(data.get("target_dwg_path") or ""),
        expected_missing=list(data.get("expected_missing") or []),
        manual_anchor_pairs=list(data.get("manual_anchor_pairs") or []),
        options=dict(data.get("options") or {}),
        metadata=dict(data.get("metadata") or {}),
    )

