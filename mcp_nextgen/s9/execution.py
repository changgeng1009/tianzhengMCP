"""S9 execution and result verification.

The executor owns orchestration only. It never opens a document, never touches COM and never
speaks a wire protocol: it walks the plan and calls an :class:`EngineeringGateway`, which is
backed by the existing MCP tools.

The verifier is the point of S9. "The backend returned success" is not a passing task. A task
passes only when the drawing, re-queried afterwards, actually satisfies what was asked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from mcp_nextgen.s10 import capabilities as s10_caps
from mcp_nextgen.s9.contracts import (
    ENGINEERING_TASK_BLOCKED,
    ENGINEERING_TASK_FAILED,
    ENGINEERING_TASK_PARTIAL,
    ENGINEERING_TASK_PASS,
    ENGINEERING_TASK_PASS_WITH_WARNINGS,
    EngineeringOperationPlan,
    EngineeringSemanticModel,
    EngineeringTaskSpec,
    Point,
)
from mcp_nextgen.s9.geometry import distance, polyline_intersects_box, polyline_within_box

CAP_CREATE = "tianzheng_native_pipe_create"
CAP_QUERY = "tianzheng_native_pipe_query"
CAP_IDENTITY = "tianzheng_native_pipe_identity_validation"
CAP_PERSISTENCE = "tianzheng_native_pipe_persistence"
CAP_IDEMPOTENCY = "tianzheng_native_pipe_idempotency"

CAP_PUMP_CREATE = s10_caps.CAP_PUMP_CREATE
CAP_EQUIPMENT_QUERY = s10_caps.CAP_EQUIPMENT_QUERY
CAP_DIAMETER_ANNOTATION = s10_caps.CAP_DIAMETER_ANNOTATION


class EngineeringGateway(Protocol):
    """The capability surface the executor is allowed to use.

    Every method is backed by an existing, already-accepted MCP tool or plugin operation.
    There is no ``run_command`` here, and there is no way to add one from a plan.
    """

    def create_pipe(self, document_token: str, start: Sequence[float], end: Sequence[float],
                    *, idempotency_key: str) -> dict[str, Any]: ...

    def query_pipe(self, document_token: str, handle: str,
                   related_handles: Sequence[str] = ()) -> dict[str, Any]: ...

    def validate_identity(self, document_token: str, handle: str) -> dict[str, Any]: ...

    def inventory(self, document_token: str) -> dict[str, Any]: ...

    def persist(self, document_token: str, handle: str) -> dict[str, Any]: ...

    # --- S10.5 -----------------------------------------------------------------------------
    # Structured parameters only. The caller never supplies a command, and never supplies the
    # pick point for an annotation: the adapter derives that from the target pipe's own
    # geometry, because only the adapter knows what the underlying hit test needs.

    def create_pump(self, document_token: str, position: Sequence[float],
                    *, idempotency_key: str) -> dict[str, Any]: ...

    def query_equipment(self, document_token: str, handle: str) -> dict[str, Any]: ...

    def annotate_pipe_diameter(self, document_token: str, target_pipe_handle: str,
                               *, idempotency_key: str) -> dict[str, Any]: ...


@dataclass
class OperationOutcome:
    operation_id: str
    backend_capability: str
    status: str                        # OK | FAILED | SKIPPED
    result: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "backend_capability": self.backend_capability,
            "status": self.status,
            "result": self.result,
            "error_code": self.error_code,
            "message": self.message,
        }


@dataclass
class ExecutionResult:
    plan_id: str
    task_id: str
    plan_hash: str
    document_token: str
    outcomes: list[OperationOutcome] = field(default_factory=list)
    primary_handle: str | None = None
    related_handles: list[str] = field(default_factory=list)
    backend_used: str | None = None
    failed: bool = False
    #: S10.5 - handles produced by non-pipe operations, kept separate so a pump handle is
    #: never mistaken for the pipe the geometry checks read.
    equipment_handles: list[str] = field(default_factory=list)
    annotated_handles: list[str] = field(default_factory=list)

    @property
    def succeeded_operations(self) -> list[OperationOutcome]:
        return [o for o in self.outcomes if o.status == "OK"]

    def outcome(self, operation_id: str) -> OperationOutcome | None:
        return next((o for o in self.outcomes if o.operation_id == operation_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "plan_hash": self.plan_hash,
            "document_token": self.document_token,
            "backend_used": self.backend_used,
            "failed": self.failed,
            "operation_count": len(self.outcomes),
            "succeeded_count": len(self.succeeded_operations),
            "primary_handle": self.primary_handle,
            "related_handles": self.related_handles,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }


class EngineeringTaskExecutor:
    """Walks an approved plan. Aggregates results. Decides nothing about correctness."""

    def __init__(self, gateway: EngineeringGateway) -> None:
        self._gateway = gateway

    def execute(
        self,
        task: EngineeringTaskSpec,
        plan: EngineeringOperationPlan,
        document_token: str,
    ) -> ExecutionResult:
        result = ExecutionResult(plan_id=plan.plan_id, task_id=plan.task_id,
                                 plan_hash=plan.plan_hash(), document_token=document_token)
        if plan.is_blocked:
            result.failed = True
            result.outcomes.append(OperationOutcome(
                "plan", "none", "SKIPPED", error_code=plan.blocked_reason,
                message="the plan is blocked and was never executed"))
            return result

        stop_on_failure = task.constraints.execution.stop_on_first_failure
        completed: set[str] = set()
        token = document_token

        for operation in plan.operations:
            unmet = [d for d in operation.depends_on if d not in completed]
            if unmet:
                # A dependency failed, so this must not quietly proceed.
                result.outcomes.append(OperationOutcome(
                    operation.operation_id, operation.backend_capability, "SKIPPED",
                    error_code="DEPENDENCY_NOT_SATISFIED",
                    message=f"depends on {unmet} which did not succeed"))
                continue

            try:
                payload = self._run(operation, result, token)
            except Exception as exc:  # noqa: BLE001 - surfaced as a structured outcome
                result.failed = True
                result.outcomes.append(OperationOutcome(
                    operation.operation_id, operation.backend_capability, "FAILED",
                    error_code=getattr(exc, "error_code", type(exc).__name__),
                    message=str(exc)))
                if stop_on_failure:
                    break
                continue

            token = payload.pop("_document_token", token)
            result.document_token = token
            result.outcomes.append(OperationOutcome(
                operation.operation_id, operation.backend_capability, "OK", result=payload))
            completed.add(operation.operation_id)

        return result

    def _run(self, operation, result: ExecutionResult, token: str) -> dict[str, Any]:
        capability = operation.backend_capability

        if capability == CAP_CREATE:
            payload = self._gateway.create_pipe(
                token, operation.parameters["start"], operation.parameters["end"],
                idempotency_key=operation.idempotency_key)
            result.primary_handle = payload.get("primary_handle") or result.primary_handle
            result.related_handles = list(payload.get("related_handles")
                                          or result.related_handles)
            result.backend_used = payload.get("actual_backend_used") or result.backend_used
            return dict(payload)

        if capability == CAP_IDENTITY:
            return dict(self._gateway.validate_identity(token, result.primary_handle or ""))

        if capability == CAP_QUERY:
            return dict(self._gateway.query_pipe(
                token, result.primary_handle or "", result.related_handles))

        if capability == CAP_PERSISTENCE:
            payload = dict(self._gateway.persist(token, result.primary_handle or ''))
            new_token = payload.get("document_token")
            if new_token:
                payload["_document_token"] = new_token
            return payload

        if capability == CAP_IDEMPOTENCY:
            before = self._gateway.inventory(token)
            replay = self._gateway.create_pipe(
                token, operation.parameters.get("start") or [],
                operation.parameters.get("end") or [],
                idempotency_key=operation.idempotency_key)
            after = self._gateway.inventory(token)
            return {"inventory_before": dict(before), "inventory_after": dict(after),
                    "replay": dict(replay)}

        if capability == CAP_PUMP_CREATE:
            payload = dict(self._gateway.create_pump(
                token, operation.parameters.get("position") or [],
                idempotency_key=operation.idempotency_key))
            handle = payload.get("primary_handle")
            if handle and handle not in result.equipment_handles:
                result.equipment_handles.append(str(handle))
            return payload

        if capability == CAP_EQUIPMENT_QUERY:
            handle = result.equipment_handles[-1] if result.equipment_handles else ""
            return dict(self._gateway.query_equipment(token, handle))

        if capability == CAP_DIAMETER_ANNOTATION:
            # The target is the pipe this plan created unless the intent named a handle. No
            # pick point crosses this boundary in either case.
            target = operation.parameters.get("target_handle") or result.primary_handle or ""
            payload = dict(self._gateway.annotate_pipe_diameter(
                token, str(target), idempotency_key=operation.idempotency_key))
            if target and target not in result.annotated_handles:
                result.annotated_handles.append(str(target))
            return payload

        raise ValueError(f"executor cannot serve capability {capability!r}")


# --------------------------------------------------------------------------- verification


@dataclass
class CheckResult:
    check_id: str
    passed: bool
    detail: str
    observed: Any = None
    expected: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {"check_id": self.check_id, "passed": self.passed, "detail": self.detail,
                "observed": self.observed, "expected": self.expected}


@dataclass
class EngineeringVerificationResult:
    task_id: str
    plan_id: str
    status: str = ENGINEERING_TASK_FAILED
    checks: list[CheckResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "status": self.status,
            "check_count": len(self.checks),
            "failed_count": len(self.failed_checks),
            "checks": [c.to_dict() for c in self.checks],
            "warnings": self.warnings,
        }


def _points(snapshot: Mapping[str, Any], key: str) -> tuple[float, ...] | None:
    value = snapshot.get(key)
    if not value:
        return None
    return tuple(float(v) for v in value)


class PumpNativeIdentityRule:
    """A pump is only a pump if the drawing says ``TDbPump``.

    A backend can return success having inserted an ordinary block. The engineering task must
    fail in that case, so this rule reads the re-queried object and never the operation result.
    """

    rule_type = "pump_native_identity"
    EXPECTED_CLASS = "TDbPump"
    EXPECTED_DXF = "TCH_PUMP"

    def check(self, plan: EngineeringOperationPlan, execution: ExecutionResult,
              snapshots: Mapping[str, Mapping[str, Any]]) -> list[CheckResult]:
        rules = [r for r in plan.verification_plan if r.rule_type == self.rule_type]
        if not rules:
            return []

        checks: list[CheckResult] = []
        for rule in rules:
            handles = list(snapshots)
            if not handles:
                checks.append(CheckResult(
                    f"{rule.rule_id}_snapshot", False,
                    "no equipment snapshot was taken, so native identity cannot be confirmed"))
                continue

            snapshot = snapshots[handles[-1]]
            runtime_class = str(snapshot.get("runtime_class") or "")
            dxf_name = str(snapshot.get("dxf_name") or "")
            confirmed = bool(snapshot.get("native_identity_confirmed"))
            expected_class = str(rule.parameters.get("expected_class") or self.EXPECTED_CLASS)
            expected_dxf = str(rule.parameters.get("expected_dxf") or self.EXPECTED_DXF)

            checks.append(CheckResult(
                f"{rule.rule_id}_class",
                runtime_class == expected_class and dxf_name == expected_dxf and confirmed,
                "the equipment re-read from the drawing is a native pump",
                observed={"runtime_class": runtime_class, "dxf_name": dxf_name,
                          "native_identity_confirmed": confirmed},
                expected={"runtime_class": expected_class, "dxf_name": expected_dxf,
                          "native_identity_confirmed": True}))

            expected_position = rule.parameters.get("position")
            observed_position = _points(snapshot, "position")
            if expected_position is not None:
                tolerance = float(rule.parameters.get("tolerance") or 1.0)
                if observed_position is None:
                    checks.append(CheckResult(
                        f"{rule.rule_id}_position", False,
                        "no position could be read from the equipment"))
                else:
                    deviation = distance(
                        tuple(observed_position),                    # type: ignore[arg-type]
                        tuple(float(v) for v in expected_position),  # type: ignore[arg-type]
                    )
                    checks.append(CheckResult(
                        f"{rule.rule_id}_position", deviation <= tolerance,
                        "the pump sits where the task asked, within tolerance",
                        observed={"position": list(observed_position), "deviation": deviation},
                        expected={"position": list(expected_position), "tolerance": tolerance}))
        return checks


class PipeAnnotationStateRule:
    """Diameter annotation is pipe-owned state, so this rule inspects the PIPE.

    It deliberately does not look for an annotation DBObject: S10.4 settled that DGGJ creates
    none, so a rule that hunted for one would fail on a correct drawing. Equally, an ordinary
    Text or MText sitting near the pipe is not the annotation and must not satisfy this rule -
    what counts is the native XData the pipe actually carries.
    """

    rule_type = "pipe_annotation_state"
    EXPECTED_CLASS = "TDbPipe"
    XDATA_APPLICATION = s10_caps.PIPE_LABEL_XDATA_APPLICATION
    STORAGE_MODEL = s10_caps.MODEL_B_PIPE_OWNED_STATE

    #: Ordinary AutoCAD text classes. Present in a drawing they prove nothing about annotation.
    ORDINARY_TEXT_CLASSES = frozenset({"AcDbText", "AcDbMText", "AcDbAttributeDefinition"})

    def check(self, plan: EngineeringOperationPlan, execution: ExecutionResult,
              snapshots: Mapping[str, Mapping[str, Any]]) -> list[CheckResult]:
        rules = [r for r in plan.verification_plan if r.rule_type == self.rule_type]
        if not rules:
            return []

        checks: list[CheckResult] = []
        for rule in rules:
            handles = list(snapshots)
            if not handles:
                checks.append(CheckResult(
                    f"{rule.rule_id}_snapshot", False,
                    "the annotated pipe was never re-queried, so the annotation state is "
                    "unverified; an execution result reporting success is not evidence"))
                continue

            snapshot = snapshots[handles[-1]]
            runtime_class = str(snapshot.get("runtime_class") or "")
            expected_class = str(rule.parameters.get("expected_class") or self.EXPECTED_CLASS)

            checks.append(CheckResult(
                f"{rule.rule_id}_carrier_class", runtime_class == expected_class,
                "the annotation state is carried by the native pipe itself",
                observed=runtime_class, expected=expected_class))

            if runtime_class in self.ORDINARY_TEXT_CLASSES:
                checks.append(CheckResult(
                    f"{rule.rule_id}_not_ordinary_text", False,
                    "an ordinary CAD text object is not a Tianzheng diameter annotation",
                    observed=runtime_class))
                continue

            applications = [str(a) for a in (snapshot.get("xdata_applications") or [])]
            checks.append(CheckResult(
                f"{rule.rule_id}_xdata", self.XDATA_APPLICATION in applications,
                "the pipe carries the native diameter-annotation state",
                observed=applications, expected=self.XDATA_APPLICATION))

            storage_model = snapshot.get("storage_model")
            if storage_model is not None:
                checks.append(CheckResult(
                    f"{rule.rule_id}_storage_model", storage_model == self.STORAGE_MODEL,
                    "the annotation is stored as pipe-owned state, as measured in S10.4",
                    observed=storage_model, expected=self.STORAGE_MODEL))
        return checks


class EngineeringResultVerifier:
    """Decides whether the drawing actually satisfies the task.

    Everything it inspects comes from ``post_snapshot`` — a fresh query of the database after
    execution. Values echoed back by the execution result are never sufficient on their own.
    """

    def verify(
        self,
        task: EngineeringTaskSpec,
        plan: EngineeringOperationPlan,
        execution: ExecutionResult,
        post_snapshot: Mapping[str, Any],
        model: EngineeringSemanticModel | None = None,
        equipment_snapshots: Mapping[str, Mapping[str, Any]] | None = None,
        annotation_snapshots: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> EngineeringVerificationResult:
        outcome = EngineeringVerificationResult(task_id=task.task_id, plan_id=plan.plan_id)
        verification = task.constraints.verification

        if plan.is_blocked:
            outcome.status = ENGINEERING_TASK_BLOCKED
            outcome.checks.append(CheckResult(
                "plan_blocked", False, f"plan blocked: {plan.blocked_reason}",
                observed=list(plan.missing_capabilities)))
            return outcome

        # --- structural -------------------------------------------------------------------
        expected_ops = len(plan.operations)
        actual_ok = len(execution.succeeded_operations)
        outcome.checks.append(CheckResult(
            "operation_count", actual_ok == expected_ops,
            "every planned operation succeeded", observed=actual_ok, expected=expected_ops))

        outcome.checks.append(CheckResult(
            "no_unexpected_failure", not execution.failed,
            "no operation failed", observed=execution.failed, expected=False))

        required_backend = task.constraints.capability.required_backend
        if required_backend:
            outcome.checks.append(CheckResult(
                "backend_used", execution.backend_used == required_backend,
                "the required backend performed the work",
                observed=execution.backend_used, expected=required_backend))

        # --- native identity, read from the post-execution snapshot -----------------------
        runtime_class = str(post_snapshot.get("runtime_class") or "")
        if verification.require_native_identity:
            expected_class = verification.expected_native_class or "TDbPipe"
            confirmed = bool(post_snapshot.get("native_identity_confirmed"))
            outcome.checks.append(CheckResult(
                "native_identity", runtime_class == expected_class and confirmed,
                "the object re-read from the drawing is the required native class",
                observed={"runtime_class": runtime_class, "confirmed": confirmed},
                expected=expected_class))

        # --- geometry, read from the object ----------------------------------------------
        geometric = task.constraints.geometric
        start = _points(post_snapshot, "start")
        end = _points(post_snapshot, "end")
        tolerance = max(verification.geometry_tolerance, geometric.max_deviation)

        if geometric.start_point and start is not None:
            deviation = distance(tuple(start), geometric.start_point)  # type: ignore[arg-type]
            outcome.checks.append(CheckResult(
                "geometry_start", deviation <= tolerance,
                "start point matches the task within tolerance",
                observed={"point": list(start), "deviation": deviation},
                expected={"point": list(geometric.start_point), "tolerance": tolerance}))
        elif geometric.start_point:
            outcome.checks.append(CheckResult(
                "geometry_start", False, "no start point could be read from the object"))

        if geometric.end_point and end is not None:
            deviation = distance(tuple(end), geometric.end_point)  # type: ignore[arg-type]
            outcome.checks.append(CheckResult(
                "geometry_end", deviation <= tolerance,
                "end point matches the task within tolerance",
                observed={"point": list(end), "deviation": deviation},
                expected={"point": list(geometric.end_point), "tolerance": tolerance}))
        elif geometric.end_point:
            outcome.checks.append(CheckResult(
                "geometry_end", False, "no end point could be read from the object"))

        # --- task constraints, re-checked against the ACTUAL geometry ---------------------
        if start is not None and end is not None:
            actual: list[Point] = [tuple(start), tuple(end)]  # type: ignore[list-item]
            forbidden = [(f"constraint-{i}", box)
                         for i, box in enumerate(geometric.forbidden_regions)]
            if model:
                forbidden += [(z.zone_id, (z.minimum, z.maximum)) for z in model.forbidden_zones]
            for zone_id, box in forbidden:
                outcome.checks.append(CheckResult(
                    f"forbidden_zone_{zone_id}", not polyline_intersects_box(actual, box),
                    f"the built route avoids forbidden zone {zone_id}"))
            if geometric.allowed_region:
                outcome.checks.append(CheckResult(
                    "allowed_region", polyline_within_box(actual, geometric.allowed_region),
                    "the built route stays inside the allowed region"))
            if model:
                for zone in model.allowed_zones:
                    outcome.checks.append(CheckResult(
                        f"allowed_zone_{zone.zone_id}",
                        polyline_within_box(actual, (zone.minimum, zone.maximum)),
                        f"the built route stays inside allowed zone {zone.zone_id}"))

        # --- counts ------------------------------------------------------------------------
        primary_count = int(post_snapshot.get("pipe_count", verification.expected_primary_count))
        outcome.checks.append(CheckResult(
            "primary_count", primary_count == verification.expected_primary_count,
            "exactly the expected number of primary native objects exist",
            observed=primary_count, expected=verification.expected_primary_count))

        if verification.expected_related_count is not None:
            related = post_snapshot.get("related_runtime_classes")
            related_count = (int(post_snapshot["fitting_count"])
                             if "fitting_count" in post_snapshot
                             else len(related or []))
            outcome.checks.append(CheckResult(
                "related_count", related_count == verification.expected_related_count,
                "the expected related native objects exist",
                observed=related_count, expected=verification.expected_related_count))

        # --- persistence -------------------------------------------------------------------
        if verification.require_persistence:
            persist = execution.outcome("op-4-persist")
            preserved = bool(persist and persist.result.get("native_identity_preserved"))
            outcome.checks.append(CheckResult(
                "persistence", preserved,
                "the object survived save, close and reopen as a native object",
                observed=persist.result.get("native_identity_preserved") if persist else None,
                expected=True))

        # --- idempotency -------------------------------------------------------------------
        if verification.require_idempotency:
            replay = execution.outcome("op-5-replay")
            if replay is None:
                outcome.checks.append(CheckResult(
                    "idempotency", False, "the plan never replayed the task"))
            else:
                before = replay.result.get("inventory_before") or {}
                after = replay.result.get("inventory_after") or {}
                pipes_before = int(before.get("pipe_count", 0))
                pipes_after = int(after.get("pipe_count", 0))
                fittings_before = int(before.get("fitting_count", 0))
                fittings_after = int(after.get("fitting_count", 0))
                duplicates = ((pipes_after - pipes_before) + (fittings_after - fittings_before))
                outcome.checks.append(CheckResult(
                    "idempotency", duplicates <= verification.max_duplicate_count,
                    "replaying the task created no duplicate objects",
                    observed={"pipes": [pipes_before, pipes_after],
                              "fittings": [fittings_before, fittings_after]},
                    expected={"max_duplicate_count": verification.max_duplicate_count}))

        # --- S10.5 equipment and annotation ------------------------------------------------
        for check in PumpNativeIdentityRule().check(plan, execution, equipment_snapshots or {}):
            outcome.checks.append(check)
        for check in PipeAnnotationStateRule().check(plan, execution, annotation_snapshots or {}):
            outcome.checks.append(check)

        if outcome.failed_checks:
            outcome.status = (ENGINEERING_TASK_PARTIAL
                              if len(outcome.failed_checks) < len(outcome.checks)
                              else ENGINEERING_TASK_FAILED)
        elif outcome.warnings:
            outcome.status = ENGINEERING_TASK_PASS_WITH_WARNINGS
        else:
            outcome.status = ENGINEERING_TASK_PASS
        return outcome
