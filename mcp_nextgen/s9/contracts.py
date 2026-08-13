"""S9 engineering contracts: task, drawing context, semantic model, constraints, plan.

The layering matters more than any individual field:

    Layer A  raw user intent          free text, never executed
    Layer B  EngineeringTaskSpec      normalized, structured, still not executable
    Layer C  EngineeringOperationPlan produced only after validation

Nothing in this module touches CAD. These are the shapes that let a planner reason about a
job and let deterministic code decide whether the result actually satisfied it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "s9.1"

# --------------------------------------------------------------------------- vocabulary

DISCIPLINE_WATER_SUPPLY = "water_supply"
TASK_TYPE_ROUTE_NATIVE_PIPE = "route_native_pipe"

#: Structured reason codes. Explanations are codes plus data, never essays.
REASON_SATISFIES_ROUTE_REQUIREMENT = "SATISFIES_ROUTE_REQUIREMENT"
REASON_ESTABLISHES_NATIVE_IDENTITY = "ESTABLISHES_NATIVE_IDENTITY"
REASON_VERIFIES_GEOMETRY = "VERIFIES_GEOMETRY"
REASON_PERSISTS_RESULT = "PERSISTS_RESULT"
REASON_VERIFIES_PERSISTENCE = "VERIFIES_PERSISTENCE"
REASON_VERIFIES_IDEMPOTENCY = "VERIFIES_IDEMPOTENCY"
REASON_PREPARES_CONTEXT = "PREPARES_CONTEXT"

#: Task-level outcome vocabulary.
ENGINEERING_TASK_PASS = "ENGINEERING_TASK_PASS"
ENGINEERING_TASK_PASS_WITH_WARNINGS = "ENGINEERING_TASK_PASS_WITH_WARNINGS"
ENGINEERING_TASK_FAILED = "ENGINEERING_TASK_FAILED"
ENGINEERING_TASK_BLOCKED = "ENGINEERING_TASK_BLOCKED"
ENGINEERING_TASK_PARTIAL = "ENGINEERING_TASK_PARTIAL"

#: Plan-level validation vocabulary.
VALIDATION_PASS = "PASS"
VALIDATION_PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
VALIDATION_BLOCKED = "BLOCKED"
VALIDATION_INVALID = "INVALID"

#: Structured blockers.
BLOCKED_BY_MISSING_CAPABILITY = "PLAN_BLOCKED_BY_MISSING_CAPABILITY"
REQUIRED_NATIVE_CAPABILITY_UNAVAILABLE = "REQUIRED_NATIVE_CAPABILITY_UNAVAILABLE"

Point = tuple[float, float, float]


def _point(value: Sequence[float]) -> Point:
    parts = [float(v) for v in value]
    if len(parts) == 2:
        parts.append(0.0)
    if len(parts) != 3:
        raise ValueError("a point needs 2 or 3 coordinates")
    if any(p != p or p in (float("inf"), float("-inf")) for p in parts):
        raise ValueError("coordinates must be finite")
    return (parts[0], parts[1], parts[2])


class EngineeringContractError(ValueError):
    """A structural problem in a task, context or plan."""


# ------------------------------------------------------------------- Layer A: raw intent


@dataclass(frozen=True)
class RawUserIntent:
    """What the user actually said. Recorded, never executed.

    Kept as its own type so it is impossible to accidentally hand free text to a backend:
    the only way forward is through normalization into an EngineeringTaskSpec.
    """

    text: str
    locale: str = "zh-CN"
    source: str = "user"

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "locale": self.locale, "source": self.source}


# ------------------------------------------------------------------------- constraints


@dataclass(frozen=True)
class GeometricConstraint:
    """Where the work may and may not go."""

    start_point: Point | None = None
    end_point: Point | None = None
    allowed_region: tuple[Point, Point] | None = None       # axis-aligned min/max
    forbidden_regions: tuple[tuple[Point, Point], ...] = ()
    max_deviation: float = 1.0
    min_segment_length: float = 1e-6

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_point": list(self.start_point) if self.start_point else None,
            "end_point": list(self.end_point) if self.end_point else None,
            "allowed_region": [list(p) for p in self.allowed_region] if self.allowed_region else None,
            "forbidden_regions": [[list(p) for p in r] for r in self.forbidden_regions],
            "max_deviation": self.max_deviation,
            "min_segment_length": self.min_segment_length,
        }


@dataclass(frozen=True)
class CapabilityConstraint:
    """What the backend must genuinely be able to do."""

    required_capabilities: tuple[str, ...] = ()
    required_native_object: str | None = None
    required_backend: str | None = None
    allow_ordinary_cad_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_capabilities": list(self.required_capabilities),
            "required_native_object": self.required_native_object,
            "required_backend": self.required_backend,
            "allow_ordinary_cad_fallback": self.allow_ordinary_cad_fallback,
        }


@dataclass(frozen=True)
class SafetyConstraint:
    """Blast radius. Defaults are the safe ones."""

    sandbox_only: bool = True
    allow_user_dwg_write: bool = False
    allow_production_write: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox_only": self.sandbox_only,
            "allow_user_dwg_write": self.allow_user_dwg_write,
            "allow_production_write": self.allow_production_write,
        }


@dataclass(frozen=True)
class ExecutionConstraint:
    """How the plan may run."""

    require_dry_run: bool = True
    require_approval: bool = True
    max_operations: int = 32
    stop_on_first_failure: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_dry_run": self.require_dry_run,
            "require_approval": self.require_approval,
            "max_operations": self.max_operations,
            "stop_on_first_failure": self.stop_on_first_failure,
        }


@dataclass(frozen=True)
class VerificationConstraint:
    """What must be true afterwards for the task to count as done."""

    require_native_identity: bool = True
    expected_native_class: str | None = None
    expected_primary_count: int = 1
    expected_related_count: int | None = None
    max_duplicate_count: int = 0
    require_persistence: bool = True
    require_idempotency: bool = True
    geometry_tolerance: float = 1e-6

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_native_identity": self.require_native_identity,
            "expected_native_class": self.expected_native_class,
            "expected_primary_count": self.expected_primary_count,
            "expected_related_count": self.expected_related_count,
            "max_duplicate_count": self.max_duplicate_count,
            "require_persistence": self.require_persistence,
            "require_idempotency": self.require_idempotency,
            "geometry_tolerance": self.geometry_tolerance,
        }


@dataclass(frozen=True)
class TaskConstraints:
    geometric: GeometricConstraint = field(default_factory=GeometricConstraint)
    capability: CapabilityConstraint = field(default_factory=CapabilityConstraint)
    safety: SafetyConstraint = field(default_factory=SafetyConstraint)
    execution: ExecutionConstraint = field(default_factory=ExecutionConstraint)
    verification: VerificationConstraint = field(default_factory=VerificationConstraint)

    def to_dict(self) -> dict[str, Any]:
        return {
            "geometric": self.geometric.to_dict(),
            "capability": self.capability.to_dict(),
            "safety": self.safety.to_dict(),
            "execution": self.execution.to_dict(),
            "verification": self.verification.to_dict(),
        }


# --------------------------------------------------------------- Layer B: the task spec


@dataclass(frozen=True)
class EngineeringTaskSpec:
    """A normalized engineering task. Structured, reviewable, still not executable."""

    task_id: str
    task_type: str
    discipline: str
    intent: str
    source_context: dict[str, Any] = field(default_factory=dict)
    target_context: dict[str, Any] = field(default_factory=dict)
    constraints: TaskConstraints = field(default_factory=TaskConstraints)
    required_capabilities: tuple[str, ...] = ()
    expected_outputs: tuple[dict[str, Any], ...] = ()
    verification_requirements: tuple[str, ...] = ()
    approval_level: str = "L3_SANDBOX_WRITE"
    raw_intent: RawUserIntent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.task_id:
            raise EngineeringContractError("task_id is required")
        if not self.task_type:
            raise EngineeringContractError("task_type is required")
        if not self.discipline:
            raise EngineeringContractError("discipline is required")
        if self.constraints.safety.allow_production_write:
            raise EngineeringContractError("production write is not available in S9")
        if self.constraints.safety.allow_user_dwg_write:
            raise EngineeringContractError("user DWG write is not available in S9")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "discipline": self.discipline,
            "intent": self.intent,
            "source_context": self.source_context,
            "target_context": self.target_context,
            "constraints": self.constraints.to_dict(),
            "required_capabilities": list(self.required_capabilities),
            "expected_outputs": [dict(o) for o in self.expected_outputs],
            "verification_requirements": list(self.verification_requirements),
            "approval_level": self.approval_level,
            "raw_intent": self.raw_intent.to_dict() if self.raw_intent else None,
            "metadata": self.metadata,
        }


# ------------------------------------------------------------- drawing context snapshot


@dataclass(frozen=True)
class ContextEntity:
    """One thing already in the drawing, described in neutral terms.

    Deliberately not a COM object, a DBObject or an ObjectId: the planner reasons about
    geometry and classes, never about live CAD handles it could misuse.
    """

    entity_id: str
    entity_type: str
    layer: str = "0"
    points: tuple[Point, ...] = ()
    text: str | None = None
    runtime_class: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "layer": self.layer,
            "points": [list(p) for p in self.points],
            "text": self.text,
            "runtime_class": self.runtime_class,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DrawingContextSnapshot:
    """What the planner is allowed to know about the drawing."""

    source_type: str                    # structured | synthetic_dwg | text | pdf | image
    coordinate_system: str = "WCS"
    drawing_units: str = "mm"
    model_space_bounds: tuple[Point, Point] | None = None
    layers: tuple[str, ...] = ()
    relevant_entities: tuple[ContextEntity, ...] = ()
    blocks: tuple[str, ...] = ()
    anchors: dict[str, Point] = field(default_factory=dict)
    obstacles: tuple[tuple[Point, Point], ...] = ()
    existing_native_objects: tuple[ContextEntity, ...] = ()
    confidence: float = 1.0
    warnings: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_type": self.source_type,
            "coordinate_system": self.coordinate_system,
            "drawing_units": self.drawing_units,
            "model_space_bounds": [list(p) for p in self.model_space_bounds]
            if self.model_space_bounds else None,
            "layers": list(self.layers),
            "relevant_entities": [e.to_dict() for e in self.relevant_entities],
            "blocks": list(self.blocks),
            "anchors": {k: list(v) for k, v in self.anchors.items()},
            "obstacles": [[list(p) for p in o] for o in self.obstacles],
            "existing_native_objects": [e.to_dict() for e in self.existing_native_objects],
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }


# ------------------------------------------------------------------- semantic model


@dataclass(frozen=True)
class AnchorPoint:
    anchor_id: str
    position: Point
    role: str = "generic"

    def to_dict(self) -> dict[str, Any]:
        return {"anchor_id": self.anchor_id, "position": list(self.position), "role": self.role}


@dataclass(frozen=True)
class Zone:
    """An axis-aligned region. allowed / forbidden is carried by ``kind``."""

    zone_id: str
    kind: str                       # allowed | forbidden | restricted
    minimum: Point
    maximum: Point

    def to_dict(self) -> dict[str, Any]:
        return {"zone_id": self.zone_id, "kind": self.kind,
                "min": list(self.minimum), "max": list(self.maximum)}


@dataclass(frozen=True)
class RouteIntent:
    """The engineering wish for a run of pipe. NOT a Polyline and NOT a TDbPipe.

    Keeping the intent separate from both the ordinary CAD entity and the Tianzheng native
    object is what lets S10 add ValveIntent -> TDbValve without touching the planner.
    """

    intent_id: str
    start: Point
    end: Point
    system: str = "water_supply"
    native_object_required: bool = True
    waypoints: tuple[Point, ...] = ()

    @property
    def polyline(self) -> tuple[Point, ...]:
        return (self.start, *self.waypoints, self.end)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id, "kind": "PipeRouteIntent",
            "start": list(self.start), "end": list(self.end),
            "waypoints": [list(p) for p in self.waypoints],
            "system": self.system,
            "native_object_required": self.native_object_required,
        }


@dataclass(frozen=True)
class EquipmentIntent:
    """The engineering wish for a piece of equipment. NOT a block and NOT a TDbPump.

    ``equipment_type`` is engineering vocabulary. Whether a given type can actually be built is
    a separate capability question - a type being expressible here is not a promise that it is
    supported, which is exactly the water_tank case.
    """

    intent_id: str
    equipment_type: str
    position: Point
    system: str = "water_supply"
    native_object_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id, "kind": "EquipmentIntent",
            "equipment_type": self.equipment_type,
            "position": list(self.position),
            "system": self.system,
            "native_object_required": self.native_object_required,
        }


#: Annotation kinds the semantic layer can express.
ANNOTATION_PIPE_DIAMETER = "pipe_diameter"


@dataclass(frozen=True)
class AnnotationIntent:
    """The engineering wish to annotate something.

    Deliberately says nothing about HOW the annotation is stored. Whether the backend creates
    an entity or writes state onto the annotated object is an adapter-level fact; letting it
    leak up here would make the planner depend on a storage model it should never know about.
    """

    intent_id: str
    annotation_type: str
    target_intent_id: str | None = None
    target_handle: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id, "kind": "AnnotationIntent",
            "annotation_type": self.annotation_type,
            "target_intent_id": self.target_intent_id,
            "target_handle": self.target_handle,
        }


@dataclass(frozen=True)
class ReservedIntent:
    """S10 extension point. Carries meaning but has no backend behind it yet."""

    intent_id: str
    kind: str                        # ValveIntent | (others promoted to real intents in S10.5)
    position: Point | None = None
    required_capability: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id, "kind": self.kind,
            "position": list(self.position) if self.position else None,
            "required_capability": self.required_capability,
            "reserved_for": "S10",
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class VerificationRule:
    rule_id: str
    rule_type: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "rule_type": self.rule_type,
                "parameters": self.parameters}


@dataclass(frozen=True)
class EngineeringSemanticModel:
    """The engineering layer between the agent and any CAD backend."""

    model_id: str
    anchors: tuple[AnchorPoint, ...] = ()
    zones: tuple[Zone, ...] = ()
    route_intents: tuple[RouteIntent, ...] = ()
    equipment_intents: tuple[EquipmentIntent, ...] = ()
    annotation_intents: tuple[AnnotationIntent, ...] = ()
    reserved_intents: tuple[ReservedIntent, ...] = ()
    verification_rules: tuple[VerificationRule, ...] = ()
    warnings: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    @property
    def forbidden_zones(self) -> tuple[Zone, ...]:
        return tuple(z for z in self.zones if z.kind in ("forbidden", "restricted"))

    @property
    def allowed_zones(self) -> tuple[Zone, ...]:
        return tuple(z for z in self.zones if z.kind == "allowed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "anchors": [a.to_dict() for a in self.anchors],
            "zones": [z.to_dict() for z in self.zones],
            "route_intents": [r.to_dict() for r in self.route_intents],
            "equipment_intents": [e.to_dict() for e in self.equipment_intents],
            "annotation_intents": [a.to_dict() for a in self.annotation_intents],
            "reserved_intents": [r.to_dict() for r in self.reserved_intents],
            "verification_rules": [v.to_dict() for v in self.verification_rules],
            "warnings": list(self.warnings),
        }


# ------------------------------------------------------------ Layer C: executable plan

#: Fields a plan operation may never carry. A plan describes intent, not code.
FORBIDDEN_OPERATION_FIELDS = frozenset({
    "command", "command_text", "script", "code", "lisp", "python", "csharp",
    "sendcommand", "keystroke", "raw", "exec", "eval",
})


@dataclass(frozen=True)
class PlannedOperation:
    operation_id: str
    semantic_intent: str
    backend_capability: str
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    idempotency_key: str = ""
    expected_result: dict[str, Any] = field(default_factory=dict)
    verification_rule: str | None = None
    # Structured explanation, not prose.
    why_this_operation: str = ""
    what_requirement_it_satisfies: str = ""
    what_constraint_it_obeys: str = ""
    what_result_is_expected: str = ""

    def __post_init__(self) -> None:
        offending = FORBIDDEN_OPERATION_FIELDS & {k.lower() for k in self.parameters}
        if offending:
            raise EngineeringContractError(
                f"operation parameters may not carry executable fields: {sorted(offending)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "semantic_intent": self.semantic_intent,
            "backend_capability": self.backend_capability,
            "parameters": self.parameters,
            "depends_on": list(self.depends_on),
            "idempotency_key": self.idempotency_key,
            "expected_result": self.expected_result,
            "verification_rule": self.verification_rule,
            "explanation": {
                "why_this_operation": self.why_this_operation,
                "what_requirement_it_satisfies": self.what_requirement_it_satisfies,
                "what_constraint_it_obeys": self.what_constraint_it_obeys,
                "what_result_is_expected": self.what_result_is_expected,
            },
        }


@dataclass(frozen=True)
class EngineeringOperationPlan:
    plan_id: str
    task_id: str
    operations: tuple[PlannedOperation, ...] = ()
    assumptions: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    verification_plan: tuple[VerificationRule, ...] = ()
    rollback_strategy: str = "abort_without_partial_commit"
    warnings: tuple[str, ...] = ()
    approval_requirement: str = "L3_SANDBOX_WRITE"
    confidence: float = 1.0
    blocked_reason: str | None = None
    missing_capabilities: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    @property
    def is_blocked(self) -> bool:
        return self.blocked_reason is not None

    def operation(self, operation_id: str) -> PlannedOperation | None:
        return next((o for o in self.operations if o.operation_id == operation_id), None)

    def dependencies(self) -> dict[str, list[str]]:
        return {o.operation_id: list(o.depends_on) for o in self.operations}

    def plan_hash(self) -> str:
        """Stable hash over the executable content, used for task-level idempotency."""
        material = json.dumps(
            {"task_id": self.task_id,
             "operations": [
                 {"operation_id": o.operation_id,
                  "backend_capability": o.backend_capability,
                  "parameters": o.parameters}
                 for o in self.operations]},
            sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "plan_hash": self.plan_hash(),
            "assumptions": list(self.assumptions),
            "required_capabilities": list(self.required_capabilities),
            "preconditions": list(self.preconditions),
            "operations": [o.to_dict() for o in self.operations],
            "dependencies": self.dependencies(),
            "verification_plan": [v.to_dict() for v in self.verification_plan],
            "rollback_strategy": self.rollback_strategy,
            "warnings": list(self.warnings),
            "approval_requirement": self.approval_requirement,
            "confidence": self.confidence,
            "blocked": self.is_blocked,
            "blocked_reason": self.blocked_reason,
            "missing_capabilities": list(self.missing_capabilities),
        }


def make_point(value: Sequence[float]) -> Point:
    return _point(value)


def points_of(values: Iterable[Sequence[float]]) -> tuple[Point, ...]:
    return tuple(_point(v) for v in values)


def as_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})
