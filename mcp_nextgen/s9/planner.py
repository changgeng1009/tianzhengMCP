"""S9 engineering planner.

Turns a normalized task plus drawing context and a semantic model into an
:class:`EngineeringOperationPlan`. It never touches CAD, and it is capability-aware: if the
task needs something the backend genuinely cannot do, it produces a BLOCKED plan naming the
missing capability rather than inventing an operation or quietly substituting a lesser one.

Provider neutrality: the planner is an interface. ``MockEngineeringPlanner`` is deterministic
and is what the default tests use; an LLM-backed planner would implement the same protocol and
produce the same plan shape, and its output would still go through the same validator.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Protocol

from mcp_nextgen.s10 import capabilities as s10_caps
from mcp_nextgen.s9.contracts import (
    ANNOTATION_PIPE_DIAMETER,
    BLOCKED_BY_MISSING_CAPABILITY,
    REASON_ESTABLISHES_NATIVE_IDENTITY,
    REASON_PERSISTS_RESULT,
    REASON_SATISFIES_ROUTE_REQUIREMENT,
    REASON_VERIFIES_GEOMETRY,
    REASON_VERIFIES_IDEMPOTENCY,
    REASON_VERIFIES_PERSISTENCE,
    REQUIRED_NATIVE_CAPABILITY_UNAVAILABLE,
    DrawingContextSnapshot,
    EngineeringOperationPlan,
    EngineeringSemanticModel,
    EngineeringTaskSpec,
    PlannedOperation,
    VerificationRule,
)

#: Capability statuses that mean "you may actually use this".
USABLE_STATUSES = frozenset({"AVAILABLE_SANDBOX_MVP", "IMPLEMENTED_BASELINE", "AVAILABLE"})

#: Backend capability names this planner knows how to emit operations for.
CAP_PIPE_CREATE = "tianzheng_native_pipe_create"
CAP_PIPE_QUERY = "tianzheng_native_pipe_query"
CAP_PIPE_IDENTITY = "tianzheng_native_pipe_identity_validation"
CAP_PIPE_PERSISTENCE = "tianzheng_native_pipe_persistence"
CAP_PIPE_IDEMPOTENCY = "tianzheng_native_pipe_idempotency"

# S10.5 equipment and annotation. The names come from the registry so the two cannot drift.
CAP_PUMP_CREATE = s10_caps.CAP_PUMP_CREATE
CAP_EQUIPMENT_CREATE = s10_caps.CAP_EQUIPMENT_CREATE
CAP_EQUIPMENT_QUERY = s10_caps.CAP_EQUIPMENT_QUERY
CAP_DIAMETER_ANNOTATION = s10_caps.CAP_DIAMETER_ANNOTATION
CAP_ANNOTATION_CONTROL = s10_caps.CAP_ANNOTATION_CONTROL

#: Blocker for when a capability covers the FAMILY but not the requested member of it.
BLOCKED_BY_UNSUPPORTED_EQUIPMENT_TYPE = "PLAN_BLOCKED_BY_UNSUPPORTED_EQUIPMENT_TYPE"

#: Blocker for an annotation kind that has no adapter.
BLOCKED_BY_UNSUPPORTED_ANNOTATION_TYPE = "PLAN_BLOCKED_BY_UNSUPPORTED_ANNOTATION_TYPE"

TIANZHENG_BACKEND = "tianzheng_native_backend"


class PlannerError(RuntimeError):
    pass


class EngineeringPlanner(Protocol):
    """Provider-neutral planner interface."""

    def plan(
        self,
        task: EngineeringTaskSpec,
        context: DrawingContextSnapshot,
        model: EngineeringSemanticModel,
        capabilities: Mapping[str, str],
    ) -> EngineeringOperationPlan: ...


def capability_available(capabilities: Mapping[str, str], name: str) -> bool:
    return capabilities.get(name, "NOT_IMPLEMENTED") in USABLE_STATUSES


def missing_capabilities(capabilities: Mapping[str, str], required: tuple[str, ...]) -> list[str]:
    return [name for name in required if not capability_available(capabilities, name)]


def _key(task_id: str, suffix: str) -> str:
    """Deterministic idempotency key: same task, same key, every time."""
    digest = hashlib.sha256(f"{task_id}|{suffix}".encode("utf-8")).hexdigest()[:24]
    return f"s9-{suffix}-{digest}"


class MockEngineeringPlanner:
    """Deterministic planner for the S9 MVP.

    Given the same task, context, model and capability snapshot it returns the same plan.
    That is what makes it usable in default tests: no network, no LLM, no drift.
    """

    def plan(
        self,
        task: EngineeringTaskSpec,
        context: DrawingContextSnapshot,
        model: EngineeringSemanticModel,
        capabilities: Mapping[str, str],
    ) -> EngineeringOperationPlan:
        plan_id = f"plan-{task.task_id}"
        warnings: list[str] = []

        # --- capability gate BEFORE any operation is emitted -----------------------------
        required = tuple(dict.fromkeys(
            (*task.required_capabilities, *task.constraints.capability.required_capabilities)))
        absent = missing_capabilities(capabilities, required)

        # Reserved S10 intents carry their own capability requirement.
        for reserved in model.reserved_intents:
            if reserved.required_capability and not capability_available(
                    capabilities, reserved.required_capability):
                if reserved.required_capability not in absent:
                    absent.append(reserved.required_capability)

        # Equipment and annotation intents imply capabilities of their own.
        for equipment in model.equipment_intents:
            for name in (CAP_EQUIPMENT_CREATE, CAP_PUMP_CREATE):
                if not capability_available(capabilities, name) and name not in absent:
                    absent.append(name)
        for annotation in model.annotation_intents:
            if not capability_available(capabilities, CAP_DIAMETER_ANNOTATION):
                if CAP_DIAMETER_ANNOTATION not in absent:
                    absent.append(CAP_DIAMETER_ANNOTATION)

        if absent:
            # No partial plan, no substitution, no silent omission.
            return EngineeringOperationPlan(
                plan_id=plan_id,
                task_id=task.task_id,
                operations=(),
                required_capabilities=required,
                blocked_reason=BLOCKED_BY_MISSING_CAPABILITY,
                missing_capabilities=tuple(absent),
                approval_requirement=task.approval_level,
                confidence=1.0,
                warnings=("plan blocked before any operation was emitted",),
            )

        # --- a family capability does not cover every member of the family ---------------
        #
        # tianzheng_native_equipment_create being AVAILABLE says only that SOME equipment can
        # be created. Only pumps have an adapter, so a water tank must block here rather than
        # be quietly routed to the pump one - which would put the wrong object in the drawing
        # and report success.
        for equipment in model.equipment_intents:
            if not s10_caps.equipment_type_supported(equipment.equipment_type):
                return EngineeringOperationPlan(
                    plan_id=plan_id, task_id=task.task_id, operations=(),
                    required_capabilities=required,
                    blocked_reason=BLOCKED_BY_UNSUPPORTED_EQUIPMENT_TYPE,
                    missing_capabilities=(
                        f"{CAP_EQUIPMENT_CREATE}[{equipment.equipment_type}]",),
                    approval_requirement=task.approval_level,
                    confidence=1.0,
                    warnings=(
                        f"equipment_type {equipment.equipment_type!r} is not in "
                        f"supported_equipment_types "
                        f"{list(s10_caps.SUPPORTED_EQUIPMENT_TYPES)}; it is NOT substituted "
                        f"with a supported type",))

        for annotation in model.annotation_intents:
            if annotation.annotation_type != ANNOTATION_PIPE_DIAMETER:
                return EngineeringOperationPlan(
                    plan_id=plan_id, task_id=task.task_id, operations=(),
                    required_capabilities=required,
                    blocked_reason=BLOCKED_BY_UNSUPPORTED_ANNOTATION_TYPE,
                    missing_capabilities=(
                        f"{CAP_ANNOTATION_CONTROL}[{annotation.annotation_type}]",),
                    approval_requirement=task.approval_level,
                    confidence=1.0,
                    warnings=(f"annotation_type {annotation.annotation_type!r} has no adapter",))

        # --- native requirement must not be silently downgraded --------------------------
        native_required = any(r.native_object_required for r in model.route_intents) or bool(
            task.constraints.capability.required_native_object)
        if native_required and not capability_available(capabilities, CAP_PIPE_CREATE):
            if not task.constraints.capability.allow_ordinary_cad_fallback:
                return EngineeringOperationPlan(
                    plan_id=plan_id, task_id=task.task_id, operations=(),
                    required_capabilities=required,
                    blocked_reason=REQUIRED_NATIVE_CAPABILITY_UNAVAILABLE,
                    missing_capabilities=(CAP_PIPE_CREATE,),
                    approval_requirement=task.approval_level,
                    warnings=("native object required but the native capability is unavailable; "
                              "ordinary CAD fallback is not permitted by this task",))
            warnings.append("task permits ordinary CAD fallback, but S9 emits no fallback plan")

        if not model.route_intents:
            raise PlannerError("the semantic model carries no route intent to plan for")
        route = model.route_intents[0]
        if len(model.route_intents) > 1:
            warnings.append(
                f"{len(model.route_intents)} route intents present; the S9 MVP plans the first only")

        verification = task.constraints.verification
        expected_class = verification.expected_native_class or "TDbPipe"

        create = PlannedOperation(
            operation_id="op-1-create-native-pipe",
            semantic_intent=route.intent_id,
            backend_capability=CAP_PIPE_CREATE,
            parameters={"start": list(route.start), "end": list(route.end)},
            idempotency_key=_key(task.task_id, "create"),
            expected_result={"native_class": expected_class,
                             "primary_count": verification.expected_primary_count,
                             "related_count": verification.expected_related_count},
            verification_rule="vr-native-identity",
            why_this_operation=REASON_SATISFIES_ROUTE_REQUIREMENT,
            what_requirement_it_satisfies=f"route {route.start} -> {route.end} as a native object",
            what_constraint_it_obeys="GeometricConstraint.start_point/end_point; "
                                     "CapabilityConstraint.required_native_object",
            what_result_is_expected=f"one {expected_class} plus its related native objects",
        )

        identity = PlannedOperation(
            operation_id="op-2-validate-identity",
            semantic_intent=route.intent_id,
            backend_capability=CAP_PIPE_IDENTITY,
            parameters={},
            depends_on=("op-1-create-native-pipe",),
            expected_result={"native_identity_confirmed": True, "runtime_class": expected_class},
            verification_rule="vr-native-identity",
            why_this_operation=REASON_ESTABLISHES_NATIVE_IDENTITY,
            what_requirement_it_satisfies="the created object must really be native",
            what_constraint_it_obeys="VerificationConstraint.require_native_identity",
            what_result_is_expected=f"runtime class {expected_class}, not a proxy or ordinary entity",
        )

        geometry = PlannedOperation(
            operation_id="op-3-query-geometry",
            semantic_intent=route.intent_id,
            backend_capability=CAP_PIPE_QUERY,
            parameters={},
            depends_on=("op-1-create-native-pipe",),
            expected_result={"start": list(route.start), "end": list(route.end)},
            verification_rule="vr-geometry",
            why_this_operation=REASON_VERIFIES_GEOMETRY,
            what_requirement_it_satisfies="the object must sit where the task asked",
            what_constraint_it_obeys=f"GeometricConstraint.max_deviation "
                                     f"<= {task.constraints.geometric.max_deviation}",
            what_result_is_expected="start/end read back from the object within tolerance",
        )

        operations = [create, identity, geometry]
        verification_rules = [
            VerificationRule("vr-native-identity", "native_identity",
                             {"expected_class": expected_class}),
            VerificationRule("vr-geometry", "geometry_match",
                             {"start": list(route.start), "end": list(route.end),
                              "tolerance": verification.geometry_tolerance}),
            VerificationRule("vr-constraints", "route_constraints",
                             {"forbidden_zones": [z.to_dict() for z in model.forbidden_zones],
                              "allowed_zones": [z.to_dict() for z in model.allowed_zones]}),
        ]

        # --- S10.5: equipment -------------------------------------------------------------
        #
        # The planner names a CAPABILITY, never a Tianzheng command. HZSB, DGGJ and HZGX do not
        # appear anywhere in a plan: which command an adapter uses is its own business.
        for index, equipment in enumerate(model.equipment_intents, start=1):
            create_id = f"op-eq{index}-create-native-equipment"
            operations.append(PlannedOperation(
                operation_id=create_id,
                semantic_intent=equipment.intent_id,
                backend_capability=CAP_PUMP_CREATE,
                parameters={"equipment_type": equipment.equipment_type,
                            "position": list(equipment.position)},
                idempotency_key=_key(task.task_id, f"equipment-{index}"),
                expected_result={"native_class": "TDbPump", "primary_count": 1},
                verification_rule=f"vr-equipment-{index}-identity",
                why_this_operation=REASON_SATISFIES_ROUTE_REQUIREMENT,
                what_requirement_it_satisfies=(
                    f"a native {equipment.equipment_type} at {equipment.position}"),
                what_constraint_it_obeys="CapabilityConstraint.required_native_object; "
                                         "supported_equipment_types",
                what_result_is_expected="one TDbPump, not a block reference",
            ))
            operations.append(PlannedOperation(
                operation_id=f"op-eq{index}-validate-identity",
                semantic_intent=equipment.intent_id,
                backend_capability=CAP_EQUIPMENT_QUERY,
                parameters={},
                depends_on=(create_id,),
                expected_result={"native_identity_confirmed": True, "runtime_class": "TDbPump"},
                verification_rule=f"vr-equipment-{index}-identity",
                why_this_operation=REASON_ESTABLISHES_NATIVE_IDENTITY,
                what_requirement_it_satisfies="the equipment must really be native",
                what_constraint_it_obeys="VerificationConstraint.require_native_identity",
                what_result_is_expected="runtime class TDbPump, DXF TCH_PUMP",
            ))
            verification_rules.append(VerificationRule(
                f"vr-equipment-{index}-identity", "pump_native_identity",
                {"expected_class": "TDbPump", "expected_dxf": "TCH_PUMP",
                 "position": list(equipment.position),
                 "tolerance": verification.geometry_tolerance}))

        # --- S10.5: annotation ------------------------------------------------------------
        #
        # The plan asks for the pipe to BE annotated. It does not say whether that produces an
        # object or changes the pipe: the storage model is deliberately invisible here.
        for index, annotation in enumerate(model.annotation_intents, start=1):
            annotate_id = f"op-an{index}-annotate-pipe-diameter"
            operations.append(PlannedOperation(
                operation_id=annotate_id,
                semantic_intent=annotation.intent_id,
                backend_capability=CAP_DIAMETER_ANNOTATION,
                parameters={"annotation_type": annotation.annotation_type,
                            "target_intent_id": annotation.target_intent_id,
                            "target_handle": annotation.target_handle},
                idempotency_key=_key(task.task_id, f"annotation-{index}"),
                depends_on=("op-1-create-native-pipe",),
                expected_result={"annotation_applied": True},
                verification_rule=f"vr-annotation-{index}-state",
                why_this_operation=REASON_SATISFIES_ROUTE_REQUIREMENT,
                what_requirement_it_satisfies="the pipe must carry its diameter annotation",
                what_constraint_it_obeys="CapabilityConstraint.required_capabilities",
                what_result_is_expected="the annotation is present on the target pipe",
            ))
            verification_rules.append(VerificationRule(
                f"vr-annotation-{index}-state", "pipe_annotation_state",
                {"expected_class": "TDbPipe",
                 "annotation_kind": annotation.annotation_type}))

        if verification.require_persistence:
            operations.append(PlannedOperation(
                operation_id="op-4-persist",
                semantic_intent=route.intent_id,
                backend_capability=CAP_PIPE_PERSISTENCE,
                parameters={},
                depends_on=("op-2-validate-identity",),
                expected_result={"persisted": True},
                verification_rule="vr-persistence",
                why_this_operation=REASON_PERSISTS_RESULT,
                what_requirement_it_satisfies="the result must outlive the session",
                what_constraint_it_obeys="SafetyConstraint.sandbox_only",
                what_result_is_expected="save, close and reopen with the object still native",
            ))
            verification_rules.append(VerificationRule(
                "vr-persistence", "persistence", {"expected_class": expected_class}))

        if verification.require_idempotency:
            operations.append(PlannedOperation(
                operation_id="op-5-replay",
                semantic_intent=route.intent_id,
                backend_capability=CAP_PIPE_IDEMPOTENCY,
                # The replay must resubmit the SAME request, not an empty one: identical
                # geometry plus the identical key is what makes it a true replay.
                parameters={"start": list(route.start), "end": list(route.end)},
                depends_on=("op-4-persist",) if verification.require_persistence
                else ("op-1-create-native-pipe",),
                idempotency_key=_key(task.task_id, "create"),   # deliberately the SAME key
                expected_result={"duplicate_created": False},
                verification_rule="vr-idempotency",
                why_this_operation=REASON_VERIFIES_IDEMPOTENCY,
                what_requirement_it_satisfies="resubmitting the task must not duplicate work",
                what_constraint_it_obeys=f"VerificationConstraint.max_duplicate_count "
                                         f"= {verification.max_duplicate_count}",
                what_result_is_expected="already_applied with unchanged object counts",
            ))
            verification_rules.append(VerificationRule(
                "vr-idempotency", "idempotency",
                {"max_duplicate_count": verification.max_duplicate_count}))

        return EngineeringOperationPlan(
            plan_id=plan_id,
            task_id=task.task_id,
            operations=tuple(operations),
            assumptions=(
                "the drawing is a job-owned synthetic document",
                "the route is a single straight run: the S8 creation adapter creates one "
                "straight pipe per call",
            ),
            required_capabilities=required,
            preconditions=(
                "tianzheng runtime loaded",
                "synthetic document created and owned by this job",
            ),
            verification_plan=tuple(verification_rules),
            approval_requirement=task.approval_level,
            warnings=tuple(warnings),
            confidence=1.0,
        )


def build_capability_snapshot(raw: Mapping[str, Any] | None) -> dict[str, str]:
    """Normalize a capability report into ``{name: status}``."""
    if not raw:
        return {}
    if "capabilities" in raw and isinstance(raw["capabilities"], Mapping):
        raw = raw["capabilities"]
    return {str(k): str(v) for k, v in raw.items()}
