"""The S9 MVP synthetic scenario, plus text normalization and the MCP-backed gateway.

The scenario is deliberately deterministic and small: a rectangular working area, one
forbidden rectangle, a source anchor A and a target anchor B, and a straight route from A to B
that does not pass through the obstacle.

The straight route is not a dodge. The S8 creation adapter creates one straight native pipe per
call, so S9 designs a scenario that route constraints genuinely participate in without
pretending multi-segment Tianzheng pipe networks exist. Multi-segment routing is future work.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from mcp_nextgen.s9.contracts import (
    DISCIPLINE_WATER_SUPPLY,
    TASK_TYPE_ROUTE_NATIVE_PIPE,
    AnchorPoint,
    CapabilityConstraint,
    ContextEntity,
    DrawingContextSnapshot,
    EngineeringSemanticModel,
    EngineeringTaskSpec,
    ExecutionConstraint,
    GeometricConstraint,
    RawUserIntent,
    ReservedIntent,
    RouteIntent,
    SafetyConstraint,
    TaskConstraints,
    VerificationConstraint,
    VerificationRule,
    Zone,
)

#: The MVP working area and obstacle, in drawing units (mm).
ALLOWED_REGION = ((-500.0, -500.0, 0.0), (3500.0, 2000.0, 0.0))
FORBIDDEN_REGION = ((1000.0, 400.0, 0.0), (2000.0, 1500.0, 0.0))
ANCHOR_A = (0.0, 0.0, 0.0)
ANCHOR_B = (3000.0, 0.0, 0.0)

REQUIRED_CAPABILITIES = (
    "tianzheng_native_pipe_create",
    "tianzheng_native_pipe_query",
    "tianzheng_native_pipe_identity_validation",
    "tianzheng_native_pipe_persistence",
    "tianzheng_native_pipe_idempotency",
)


def build_task(task_id: str = "s9-mvp-task-1",
               *, raw_text: str | None = None,
               require_valve: bool = False) -> EngineeringTaskSpec:
    """The MVP task: route one native water-supply pipe from A to B.

    ``require_valve`` produces the S10 boundary case: a task that additionally wants a
    Tianzheng valve, which must be rejected rather than faked.
    """
    required = list(REQUIRED_CAPABILITIES)
    if require_valve:
        required.append("tianzheng_valve")

    return EngineeringTaskSpec(
        task_id=task_id,
        task_type=TASK_TYPE_ROUTE_NATIVE_PIPE,
        discipline=DISCIPLINE_WATER_SUPPLY,
        intent="connect the water-supply inlet at A to the target point B with a native pipe",
        source_context={"anchor": "A", "position": list(ANCHOR_A)},
        target_context={"anchor": "B", "position": list(ANCHOR_B)},
        constraints=TaskConstraints(
            geometric=GeometricConstraint(
                start_point=ANCHOR_A,
                end_point=ANCHOR_B,
                allowed_region=ALLOWED_REGION,
                forbidden_regions=(FORBIDDEN_REGION,),
                max_deviation=1.0,
            ),
            capability=CapabilityConstraint(
                required_capabilities=tuple(required),
                required_native_object="TDbPipe",
                required_backend="tianzheng_native_backend",
                allow_ordinary_cad_fallback=False,
            ),
            safety=SafetyConstraint(sandbox_only=True),
            execution=ExecutionConstraint(require_dry_run=True, require_approval=True),
            verification=VerificationConstraint(
                require_native_identity=True,
                expected_native_class="TDbPipe",
                expected_primary_count=1,
                expected_related_count=2,
                max_duplicate_count=0,
                require_persistence=True,
                require_idempotency=True,
                geometry_tolerance=1e-6,
            ),
        ),
        required_capabilities=tuple(required),
        expected_outputs=({"kind": "native_object", "runtime_class": "TDbPipe", "count": 1},
                          {"kind": "native_object", "runtime_class": "TDbPipeFitting", "count": 2}),
        verification_requirements=("native_identity", "geometry_match", "route_constraints",
                                   "persistence", "idempotency"),
        approval_level="L3_SANDBOX_WRITE",
        raw_intent=RawUserIntent(raw_text) if raw_text else None,
        metadata={"scenario": "s9_mvp_water_supply_route"},
    )


def build_context(source_type: str = "structured") -> DrawingContextSnapshot:
    """The synthetic drawing the task is set in."""
    return DrawingContextSnapshot(
        source_type=source_type,
        coordinate_system="WCS",
        drawing_units="mm",
        model_space_bounds=ALLOWED_REGION,
        layers=("0", "S9-REFERENCE"),
        relevant_entities=(
            ContextEntity("obstacle-1", "boundary_rectangle", layer="S9-REFERENCE",
                          points=(FORBIDDEN_REGION[0], FORBIDDEN_REGION[1]),
                          metadata={"role": "forbidden_zone"}),
            ContextEntity("anchor-a", "point", points=(ANCHOR_A,), metadata={"role": "source"}),
            ContextEntity("anchor-b", "point", points=(ANCHOR_B,), metadata={"role": "target"}),
        ),
        anchors={"A": ANCHOR_A, "B": ANCHOR_B},
        obstacles=(FORBIDDEN_REGION,),
        confidence=1.0,
    )


def build_semantic_model(context: DrawingContextSnapshot,
                         *, include_valve_intent: bool = False,
                         start: Sequence[float] | None = None,
                         end: Sequence[float] | None = None) -> EngineeringSemanticModel:
    """Lift the drawing context into engineering meaning.

    ``start``/``end`` override the scenario anchors so the model describes the route that was
    actually asked for. Without that the validator would compare a caller's endpoints against
    the fixture's, and report the wrong conflict.
    """
    source = tuple(float(v) for v in start) if start is not None else context.anchors["A"]
    target = tuple(float(v) for v in end) if end is not None else context.anchors["B"]
    reserved: list[ReservedIntent] = []
    if include_valve_intent:
        # An S10 extension point: it carries meaning but no backend exists for it yet.
        reserved.append(ReservedIntent(
            intent_id="valve-1", kind="ValveIntent", position=(1500.0, 0.0, 0.0),
            required_capability="tianzheng_valve"))

    return EngineeringSemanticModel(
        model_id="s9-mvp-model-1",
        anchors=(AnchorPoint("A", source, role="source"),
                 AnchorPoint("B", target, role="target")),
        zones=(Zone("working-area", "allowed", *ALLOWED_REGION),
               Zone("obstacle-1", "forbidden", *FORBIDDEN_REGION)),
        route_intents=(RouteIntent("route-1", source, target,
                                   system="water_supply", native_object_required=True),),
        reserved_intents=tuple(reserved),
        verification_rules=(
            VerificationRule("vr-native-identity", "native_identity", {"expected_class": "TDbPipe"}),
            VerificationRule("vr-geometry", "geometry_match",
                             {"start": list(ANCHOR_A), "end": list(ANCHOR_B)}),
        ),
    )


# ------------------------------------------------------------------- text normalization

_NUMBER = r"[-+]?\d+(?:\.\d+)?"
_POINT = re.compile(rf"\(\s*({_NUMBER})\s*,\s*({_NUMBER})\s*(?:,\s*({_NUMBER})\s*)?\)")


def normalize_text_intent(text: str, *, task_id: str = "s9-text-task") -> EngineeringTaskSpec:
    """Turn free text into a structured task, or refuse.

    This is Layer A -> Layer B and nothing more. It never produces operations, so no phrasing
    can reach a backend: an unparseable request raises instead of guessing coordinates.
    """
    points = _POINT.findall(text)
    if len(points) < 2:
        raise ValueError(
            "the request must name a start and an end point, e.g. '(0,0)' and '(3000,0)'")

    def to_point(match: Sequence[str]) -> tuple[float, float, float]:
        x, y, z = match[0], match[1], match[2] or "0"
        return (float(x), float(y), float(z))

    start, end = to_point(points[0]), to_point(points[1])
    task = build_task(task_id, raw_text=text)
    geometric = GeometricConstraint(
        start_point=start, end_point=end,
        allowed_region=task.constraints.geometric.allowed_region,
        forbidden_regions=task.constraints.geometric.forbidden_regions,
        max_deviation=task.constraints.geometric.max_deviation)
    constraints = TaskConstraints(
        geometric=geometric,
        capability=task.constraints.capability,
        safety=task.constraints.safety,
        execution=task.constraints.execution,
        verification=task.constraints.verification)
    return EngineeringTaskSpec(
        task_id=task.task_id, task_type=task.task_type, discipline=task.discipline,
        intent=text.strip(), source_context={"position": list(start)},
        target_context={"position": list(end)}, constraints=constraints,
        required_capabilities=task.required_capabilities,
        expected_outputs=task.expected_outputs,
        verification_requirements=task.verification_requirements,
        approval_level=task.approval_level, raw_intent=RawUserIntent(text),
        metadata={"normalized_from": "text"})


# --------------------------------------------------------------------- MCP-backed gateway


class McpEngineeringGateway:
    """Executes plan capabilities through the real MCP tools.

    The Tianzheng capability goes through ``dispatch_tool``. Document lifecycle
    (save/close/reopen) is an S7 plugin-transport concern with no MCP tool, so it is called
    through the transport and reported as such rather than being dressed up as MCP.
    """

    def __init__(self, dispatch, plugin_call, *, job_id: str, schema_version: str,
                 sandbox_file: str, backend) -> None:
        self._dispatch = dispatch
        self._plugin = plugin_call
        self._job_id = job_id
        self._schema_version = schema_version
        self._sandbox_file = sandbox_file
        self._backend = backend
        self._request_seq = 0

    def _payload(self, **fields: Any) -> dict[str, Any]:
        self._request_seq += 1
        return {"schema_version": self._schema_version,
                "request_id": f"s9-{self._job_id}-{self._request_seq}", **fields}

    def _mcp(self, tool: str, *, idempotency_key: str, **fields: Any) -> dict[str, Any]:
        response = self._dispatch(tool, self._payload(idempotency_key=idempotency_key, **fields))
        if response.get("status") not in ("OK",):
            raise RuntimeError(f"{tool} -> {response.get('status')} "
                               f"{response.get('error_code')}")
        return response.get("data") or {}

    def create_pipe(self, document_token: str, start: Sequence[float], end: Sequence[float],
                    *, idempotency_key: str) -> dict[str, Any]:
        return self._mcp("cad.tianzheng.create_pipe", idempotency_key=idempotency_key,
                         job_id=self._job_id, document_token=document_token,
                         start=list(start), end=list(end))

    def query_pipe(self, document_token: str, handle: str,
                   related_handles: Sequence[str] = ()) -> dict[str, Any]:
        data = self._mcp("cad.tianzheng.query_pipe", idempotency_key=f"q-{handle}",
                         job_id=self._job_id, document_token=document_token,
                         handle=handle, related_handles=list(related_handles))
        return data.get("snapshot") or {}

    def validate_identity(self, document_token: str, handle: str) -> dict[str, Any]:
        return self._mcp("cad.tianzheng.validate_pipe_identity", idempotency_key=f"v-{handle}",
                         job_id=self._job_id, document_token=document_token, handle=handle)

    # --- S10 native objects ---------------------------------------------------------------
    # Each goes through its own MCP tool. The Tianzheng command behind it never appears here,
    # and the annotation call carries a target handle and nothing else - no pick point.

    def create_pump(self, document_token: str, position: Sequence[float],
                    *, idempotency_key: str) -> dict[str, Any]:
        return self._mcp("cad.tianzheng.create_pump", idempotency_key=idempotency_key,
                         job_id=self._job_id, document_token=document_token,
                         position=list(position))

    def query_equipment(self, document_token: str, handle: str) -> dict[str, Any]:
        data = self._mcp("cad.tianzheng.query_pump", idempotency_key=f"qe-{handle}",
                         job_id=self._job_id, document_token=document_token, handle=handle)
        return data.get("snapshot") or {}

    def annotate_pipe_diameter(self, document_token: str, target_pipe_handle: str,
                               *, idempotency_key: str) -> dict[str, Any]:
        return self._mcp("cad.tianzheng.annotate_pipe_diameter",
                         idempotency_key=idempotency_key, job_id=self._job_id,
                         document_token=document_token,
                         target_pipe_handle=target_pipe_handle)

    def inventory(self, document_token: str) -> dict[str, Any]:
        return dict(self._backend.inventory(document_token))

    def persist(self, document_token: str, handle: str) -> dict[str, Any]:
        """save -> close -> reopen, then report whether the object came back native."""
        from mcp_nextgen.s8.persistence import compare_roundtrip

        before = self._backend.query_pipe(document_token, handle)
        saved = self._plugin("save", mutating=True,
                             parameters={"file_name": self._sandbox_file},
                             document_context={"document_token": document_token})
        self._plugin("close", mutating=True, parameters={},
                     document_context={"document_token": document_token})
        reopened = self._plugin("reopen", mutating=True, parameters={},
                                document_context={"document_token": document_token})
        new_token = reopened.get("document_token") or document_token
        after = self._backend.query_pipe(new_token, handle)
        comparison = compare_roundtrip(before, after)
        comparison.update({"document_token": new_token,
                           "sandbox_identity": saved.get("sandbox_identity"),
                           "snapshot_after_reopen": after})
        return comparison


def scenario_capability_snapshot(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """The capability snapshot the MVP scenario expects, with optional overrides."""
    snapshot = {name: "AVAILABLE_SANDBOX_MVP" for name in REQUIRED_CAPABILITIES}
    snapshot.update({
        "tianzheng_pipe_diameter_read": "NOT_AVAILABLE",
        "tianzheng_pipe_system_read": "NOT_AVAILABLE",
        "tianzheng_valve": "NOT_IMPLEMENTED",
        "tianzheng_equipment": "NOT_IMPLEMENTED",
        "tianzheng_annotation": "NOT_IMPLEMENTED",
    })
    snapshot.update(overrides or {})
    return snapshot
