"""S9 dry run and plan validation.

Dry run touches nothing. It re-checks, deterministically, everything a planner could have got
wrong or lied about: schema shape, coordinates, capabilities, forbidden operations, geometry
against the task's own constraints, sandbox and approval requirements.

The division of labour matters: an agent may propose a plan, but only this module decides
whether it is allowed to run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from mcp_nextgen.s9.contracts import (
    FORBIDDEN_OPERATION_FIELDS,
    VALIDATION_BLOCKED,
    VALIDATION_INVALID,
    VALIDATION_PASS,
    VALIDATION_PASS_WITH_WARNINGS,
    DrawingContextSnapshot,
    EngineeringOperationPlan,
    EngineeringSemanticModel,
    EngineeringTaskSpec,
)
from mcp_nextgen.s9.geometry import (
    find_duplicate_segments,
    find_zero_length_segments,
    point_in_box,
    polyline_intersects_box,
    polyline_within_box,
)
from mcp_nextgen.s10 import capabilities as s10_caps
from mcp_nextgen.s9.planner import capability_available

#: Capabilities the planner is allowed to emit. Anything else never reaches a backend.
#:
#: The S10 names are DERIVED from the registry rather than retyped. When S10.5 added the pump
#: and annotation operations this list was not updated, so every plan containing them was
#: rejected as INVALID - a break the mock end-to-end test could not see, because it drove the
#: planner and executor but never the validator. Deriving the set removes that class of drift.
KNOWN_BACKEND_CAPABILITIES = frozenset({
    "tianzheng_native_pipe_create",
    "tianzheng_native_pipe_query",
    "tianzheng_native_pipe_identity_validation",
    "tianzheng_native_pipe_persistence",
    "tianzheng_native_pipe_idempotency",
    *s10_caps.native_capability_registry(),
})


@dataclass
class ValidationReport:
    status: str = VALIDATION_PASS
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    unsafe_operations: list[str] = field(default_factory=list)
    geometry_conflicts: list[str] = field(default_factory=list)
    assumption_conflicts: list[str] = field(default_factory=list)
    checks_performed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in (VALIDATION_PASS, VALIDATION_PASS_WITH_WARNINGS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "missing_capabilities": self.missing_capabilities,
            "unsafe_operations": self.unsafe_operations,
            "geometry_conflicts": self.geometry_conflicts,
            "assumption_conflicts": self.assumption_conflicts,
            "checks_performed": self.checks_performed,
        }


class EngineeringPlanValidator:
    """Deterministic gate between a proposed plan and execution."""

    def validate(
        self,
        task: EngineeringTaskSpec,
        plan: EngineeringOperationPlan,
        model: EngineeringSemanticModel,
        capabilities: Mapping[str, str],
        context: DrawingContextSnapshot | None = None,
    ) -> ValidationReport:
        report = ValidationReport()

        # --- a blocked plan is a legitimate outcome, not an error -------------------------
        if plan.is_blocked:
            report.status = VALIDATION_BLOCKED
            report.missing_capabilities = list(plan.missing_capabilities)
            report.errors.append(plan.blocked_reason or "plan is blocked")
            report.checks_performed.append("blocked_plan_short_circuit")
            return report

        self._check_schema(task, plan, report)
        self._check_capabilities(plan, capabilities, report)
        self._check_safety(task, plan, report)
        self._check_dependencies(plan, report)
        self._check_idempotency(plan, report)
        self._check_geometry(task, model, context, report)
        self._check_expected_counts(task, plan, report)

        if report.errors:
            report.status = (VALIDATION_BLOCKED if report.missing_capabilities
                             else VALIDATION_INVALID)
        elif report.warnings:
            report.status = VALIDATION_PASS_WITH_WARNINGS
        else:
            report.status = VALIDATION_PASS
        return report

    # ------------------------------------------------------------------ individual checks

    def _check_schema(self, task, plan, report: ValidationReport) -> None:
        report.checks_performed.append("schema")
        if plan.task_id != task.task_id:
            report.errors.append(
                f"plan.task_id {plan.task_id!r} does not match task {task.task_id!r}")
        if not plan.operations:
            report.errors.append("plan has no operations")
        if len(plan.operations) > task.constraints.execution.max_operations:
            report.errors.append(
                f"plan has {len(plan.operations)} operations, over the task limit "
                f"{task.constraints.execution.max_operations}")
        seen: set[str] = set()
        for operation in plan.operations:
            if operation.operation_id in seen:
                report.errors.append(f"duplicate operation_id {operation.operation_id!r}")
            seen.add(operation.operation_id)
            # Defence in depth: PlannedOperation rejects these at construction, but a plan
            # could arrive from elsewhere.
            offending = FORBIDDEN_OPERATION_FIELDS & {k.lower() for k in operation.parameters}
            if offending:
                report.unsafe_operations.append(operation.operation_id)
                report.errors.append(
                    f"{operation.operation_id} carries executable fields {sorted(offending)}")

    def _check_capabilities(self, plan, capabilities, report: ValidationReport) -> None:
        report.checks_performed.append("capabilities")
        for operation in plan.operations:
            capability = operation.backend_capability
            # An operation the system has never heard of must never reach a backend.
            if capability not in KNOWN_BACKEND_CAPABILITIES:
                report.unsafe_operations.append(operation.operation_id)
                report.errors.append(
                    f"{operation.operation_id} names unknown backend capability {capability!r}")
                continue
            if not capability_available(capabilities, capability):
                report.missing_capabilities.append(capability)
                report.errors.append(
                    f"{operation.operation_id} needs {capability!r}, which is "
                    f"{capabilities.get(capability, 'NOT_IMPLEMENTED')}")

    def _check_safety(self, task, plan, report: ValidationReport) -> None:
        report.checks_performed.append("safety")
        safety = task.constraints.safety
        if not safety.sandbox_only:
            report.errors.append("S9 requires sandbox_only execution")
        if safety.allow_user_dwg_write or safety.allow_production_write:
            report.errors.append("user DWG write and production write are not available")
        if task.constraints.execution.require_approval and not plan.approval_requirement:
            report.errors.append("task requires approval but the plan states no requirement")

    def _check_dependencies(self, plan, report: ValidationReport) -> None:
        report.checks_performed.append("dependencies")
        known = {o.operation_id for o in plan.operations}
        position = {o.operation_id: i for i, o in enumerate(plan.operations)}
        for operation in plan.operations:
            for dependency in operation.depends_on:
                if dependency not in known:
                    report.errors.append(
                        f"{operation.operation_id} depends on unknown {dependency!r}")
                elif position[dependency] > position[operation.operation_id]:
                    report.errors.append(
                        f"{operation.operation_id} depends on {dependency!r} which runs later")

    def _check_idempotency(self, plan, report: ValidationReport) -> None:
        report.checks_performed.append("idempotency_keys")
        creators = [o for o in plan.operations
                    if o.backend_capability == "tianzheng_native_pipe_create"]
        for operation in creators:
            if not operation.idempotency_key:
                report.errors.append(
                    f"{operation.operation_id} creates objects but carries no idempotency_key")
        replays = [o for o in plan.operations
                   if o.backend_capability == "tianzheng_native_pipe_idempotency"]
        for replay in replays:
            if creators and replay.idempotency_key != creators[0].idempotency_key:
                report.errors.append(
                    "the replay operation must reuse the creating operation's idempotency_key")

    def _check_geometry(self, task, model, context, report: ValidationReport) -> None:
        report.checks_performed.append("geometry")
        geometric = task.constraints.geometric
        for route in model.route_intents:
            points = route.polyline

            zero = find_zero_length_segments(points, geometric.min_segment_length)
            if zero:
                report.geometry_conflicts.append(f"zero-length segments at {zero}")
                report.errors.append("route contains a zero-length segment")

            duplicates = find_duplicate_segments(points)
            if duplicates:
                report.geometry_conflicts.append(f"duplicate segments at {duplicates}")
                report.errors.append("route repeats a segment")

            if geometric.start_point and route.start != geometric.start_point:
                report.errors.append(
                    f"route start {route.start} does not match required {geometric.start_point}")
            if geometric.end_point and route.end != geometric.end_point:
                report.errors.append(
                    f"route end {route.end} does not match required {geometric.end_point}")

            if geometric.allowed_region:
                if not polyline_within_box(points, geometric.allowed_region):
                    report.geometry_conflicts.append("route leaves the allowed region")
                    report.errors.append("route leaves the allowed region")
            for zone in model.allowed_zones:
                if not polyline_within_box(points, (zone.minimum, zone.maximum)):
                    report.geometry_conflicts.append(f"route leaves allowed zone {zone.zone_id}")
                    report.errors.append(f"route leaves allowed zone {zone.zone_id}")

            forbidden_boxes = [(z.zone_id, (z.minimum, z.maximum)) for z in model.forbidden_zones]
            forbidden_boxes += [(f"constraint-{i}", box)
                                for i, box in enumerate(geometric.forbidden_regions)]
            for zone_id, box in forbidden_boxes:
                if polyline_intersects_box(points, box):
                    report.geometry_conflicts.append(f"route intersects forbidden zone {zone_id}")
                    report.errors.append(f"route intersects forbidden zone {zone_id}")

            if context and context.model_space_bounds:
                if not polyline_within_box(points, context.model_space_bounds):
                    report.warnings.append("route extends beyond the reported drawing bounds")

            for anchor in model.anchors:
                if anchor.role == "source" and route.start != anchor.position:
                    report.warnings.append(
                        f"route start does not sit on source anchor {anchor.anchor_id}")
                if anchor.role == "target" and route.end != anchor.position:
                    report.warnings.append(
                        f"route end does not sit on target anchor {anchor.anchor_id}")
                if anchor.role in ("source", "target") and model.allowed_zones:
                    zone = model.allowed_zones[0]
                    if not point_in_box(anchor.position, (zone.minimum, zone.maximum)):
                        report.warnings.append(
                            f"anchor {anchor.anchor_id} lies outside the allowed zone")

    def _check_expected_counts(self, task, plan, report: ValidationReport) -> None:
        report.checks_performed.append("expected_counts")
        verification = task.constraints.verification
        if verification.expected_primary_count < 1:
            report.errors.append("expected_primary_count must be at least 1")
        if verification.max_duplicate_count < 0:
            report.errors.append("max_duplicate_count cannot be negative")
        if verification.require_persistence and not any(
                o.backend_capability == "tianzheng_native_pipe_persistence"
                for o in plan.operations):
            report.errors.append("task requires persistence but the plan never persists")
        if verification.require_idempotency and not any(
                o.backend_capability == "tianzheng_native_pipe_idempotency"
                for o in plan.operations):
            report.errors.append("task requires idempotency but the plan never replays")


@dataclass
class DryRunResult:
    """A dry run performs no CAD work at all."""

    performed_cad_work: bool = False
    validation: ValidationReport = field(default_factory=ValidationReport)
    planned_operation_count: int = 0
    planned_capabilities: list[str] = field(default_factory=list)
    sandbox_only: bool = True
    approval_required: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": True,
            "performed_cad_work": self.performed_cad_work,
            "planned_operation_count": self.planned_operation_count,
            "planned_capabilities": self.planned_capabilities,
            "sandbox_only": self.sandbox_only,
            "approval_required": self.approval_required,
            "validation": self.validation.to_dict(),
        }


def dry_run(
    task: EngineeringTaskSpec,
    plan: EngineeringOperationPlan,
    model: EngineeringSemanticModel,
    capabilities: Mapping[str, str],
    context: DrawingContextSnapshot | None = None,
) -> DryRunResult:
    """Validate a plan without executing anything."""
    report = EngineeringPlanValidator().validate(task, plan, model, capabilities, context)
    return DryRunResult(
        performed_cad_work=False,
        validation=report,
        planned_operation_count=len(plan.operations),
        planned_capabilities=[o.backend_capability for o in plan.operations],
        sandbox_only=task.constraints.safety.sandbox_only,
        approval_required=plan.approval_requirement,
    )
