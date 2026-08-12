"""S9 engineering task closed loop.

AutoCAD launch = 0, Tianzheng launch = 0, COM = 0, network = 0. The planner used here is the
deterministic MockEngineeringPlanner; no LLM is called.
"""
from __future__ import annotations

import json

import pytest

from mcp_nextgen.s9.contracts import (
    BLOCKED_BY_MISSING_CAPABILITY,
    ENGINEERING_TASK_FAILED,
    ENGINEERING_TASK_PARTIAL,
    ENGINEERING_TASK_PASS,
    REQUIRED_NATIVE_CAPABILITY_UNAVAILABLE,
    VALIDATION_BLOCKED,
    VALIDATION_INVALID,
    VALIDATION_PASS,
    EngineeringContractError,
    EngineeringTaskSpec,
    PlannedOperation,
    RawUserIntent,
    SafetyConstraint,
    TaskConstraints,
)
from mcp_nextgen.s9.execution import (
    EngineeringResultVerifier,
    EngineeringTaskExecutor,
)
from mcp_nextgen.s9.geometry import (
    polyline_intersects_box,
    polyline_within_box,
    segment_intersects_box,
)
from mcp_nextgen.s9.planner import MockEngineeringPlanner
from mcp_nextgen.s9.scenario import (
    ANCHOR_A,
    ANCHOR_B,
    FORBIDDEN_REGION,
    build_context,
    build_semantic_model,
    build_task,
    normalize_text_intent,
    scenario_capability_snapshot,
)
from mcp_nextgen.s9.validation import EngineeringPlanValidator, dry_run

PLANNER = MockEngineeringPlanner()
VALIDATOR = EngineeringPlanValidator()


def scenario(*, valve=False, caps=None):
    task = build_task(require_valve=valve)
    context = build_context()
    model = build_semantic_model(context, include_valve_intent=valve)
    return task, context, model, caps or scenario_capability_snapshot()


def make_plan(*, valve=False, caps=None):
    task, context, model, capabilities = scenario(valve=valve, caps=caps)
    return task, context, model, capabilities, PLANNER.plan(task, context, model, capabilities)


# ------------------------------------------------------------------ task / context model

def test_task_spec_carries_the_full_contract():
    task = build_task()

    assert task.task_type == "route_native_pipe"
    assert task.discipline == "water_supply"
    assert task.constraints.capability.required_native_object == "TDbPipe"
    assert task.constraints.verification.expected_related_count == 2
    assert json.loads(json.dumps(task.to_dict()))["schema_version"] == task.schema_version


def test_task_cannot_request_production_or_user_dwg_write():
    for unsafe in (SafetyConstraint(allow_production_write=True),
                   SafetyConstraint(allow_user_dwg_write=True)):
        with pytest.raises(EngineeringContractError):
            EngineeringTaskSpec(task_id="t", task_type="x", discipline="d", intent="i",
                                constraints=TaskConstraints(safety=unsafe))


def test_raw_text_is_layer_a_only_and_must_be_normalized():
    task = normalize_text_intent("从 (0,0) 接一根给水管到 (3000,0)")

    assert isinstance(task.raw_intent, RawUserIntent)
    assert task.constraints.geometric.start_point == (0.0, 0.0, 0.0)
    assert task.constraints.geometric.end_point == (3000.0, 0.0, 0.0)


def test_unparseable_text_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        normalize_text_intent("随便帮我画个管子")


def test_drawing_context_exposes_no_cad_handles():
    context = build_context()
    serialized = json.dumps(context.to_dict()).lower()

    for banned in ("dbobject", "objectid", "com", "unmanaged", "pointer"):
        assert banned not in serialized


def test_semantic_model_separates_intent_from_cad_entities():
    model = build_semantic_model(build_context())
    route = model.route_intents[0].to_dict()

    assert route["kind"] == "PipeRouteIntent"
    assert route["kind"] not in ("Polyline", "TDbPipe")
    assert model.forbidden_zones[0].zone_id == "obstacle-1"


# ------------------------------------------------------------------------- geometry

def test_route_from_a_to_b_avoids_the_obstacle():
    assert not polyline_intersects_box([ANCHOR_A, ANCHOR_B], FORBIDDEN_REGION)


def test_a_route_through_the_obstacle_is_detected():
    through = [(1500.0, -1000.0, 0.0), (1500.0, 1000.0, 0.0)]
    assert polyline_intersects_box(through, FORBIDDEN_REGION)


def test_touching_a_forbidden_edge_counts_as_intersecting():
    grazing = ((1000.0, 400.0, 0.0), (900.0, 400.0, 0.0))
    assert segment_intersects_box(grazing, FORBIDDEN_REGION)


def test_route_stays_within_the_allowed_region():
    from mcp_nextgen.s9.scenario import ALLOWED_REGION
    assert polyline_within_box([ANCHOR_A, ANCHOR_B], ALLOWED_REGION)


# -------------------------------------------------------------------------- planner

def test_planner_is_deterministic():
    task, context, model, capabilities = scenario()
    first = PLANNER.plan(task, context, model, capabilities)
    second = PLANNER.plan(task, context, model, capabilities)

    assert first.plan_hash() == second.plan_hash()
    assert [o.operation_id for o in first.operations] == [o.operation_id for o in second.operations]


def test_plan_covers_create_identity_geometry_persistence_and_replay():
    _t, _c, _m, _caps, plan = make_plan()
    capabilities = [o.backend_capability for o in plan.operations]

    assert capabilities == [
        "tianzheng_native_pipe_create",
        "tianzheng_native_pipe_identity_validation",
        "tianzheng_native_pipe_query",
        "tianzheng_native_pipe_persistence",
        "tianzheng_native_pipe_idempotency",
    ]


def test_every_operation_is_explained_with_reason_codes():
    _t, _c, _m, _caps, plan = make_plan()

    for operation in plan.operations:
        explanation = operation.to_dict()["explanation"]
        assert explanation["why_this_operation"]
        assert explanation["what_requirement_it_satisfies"]
        assert explanation["what_constraint_it_obeys"]
        assert explanation["what_result_is_expected"]


def test_replay_reuses_the_creating_operations_idempotency_key():
    _t, _c, _m, _caps, plan = make_plan()

    create = plan.operation("op-1-create-native-pipe")
    replay = plan.operation("op-5-replay")
    assert create.idempotency_key
    assert replay.idempotency_key == create.idempotency_key


def test_same_task_yields_the_same_idempotency_keys_across_runs():
    # Task-level idempotency rides on the existing operation-level mechanism.
    first = PLANNER.plan(*scenario())
    second = PLANNER.plan(*scenario())
    assert (first.operation("op-1-create-native-pipe").idempotency_key
            == second.operation("op-1-create-native-pipe").idempotency_key)


def test_plans_are_free_of_executable_fields():
    _t, _c, _m, _caps, plan = make_plan()
    serialized = json.dumps(plan.to_dict()).lower()

    for banned in ("lisp", "sendcommand", "\"script\"", "csharp", "hzgx"):
        assert banned not in serialized


def test_operation_rejects_executable_parameters_outright():
    with pytest.raises(EngineeringContractError):
        PlannedOperation(operation_id="x", semantic_intent="i",
                         backend_capability="tianzheng_native_pipe_create",
                         parameters={"command": "HZGX"})


# ------------------------------------------------- capability-aware planning (S10 gate)

def test_task_requiring_a_valve_is_blocked_not_faked():
    _t, _c, _m, _caps, plan = make_plan(valve=True)

    assert plan.is_blocked
    assert plan.blocked_reason == BLOCKED_BY_MISSING_CAPABILITY
    assert "tianzheng_valve" in plan.missing_capabilities
    assert plan.operations == ()


def test_blocked_plan_never_substitutes_an_ordinary_entity():
    _t, _c, _m, _caps, plan = make_plan(valve=True)

    # Nothing was emitted at all, so there is nothing to substitute WITH.
    assert plan.operations == ()
    emitted = {o.backend_capability for o in plan.operations}
    for substitute in ("create_circle", "create_polyline", "create_line", "create_block"):
        assert substitute not in emitted


def test_native_requirement_is_not_downgraded_when_tianzheng_is_missing():
    caps = scenario_capability_snapshot({"tianzheng_native_pipe_create": "NOT_AVAILABLE"})
    _t, _c, _m, _caps, plan = make_plan(caps=caps)

    assert plan.is_blocked
    assert plan.blocked_reason in (BLOCKED_BY_MISSING_CAPABILITY,
                                   REQUIRED_NATIVE_CAPABILITY_UNAVAILABLE)
    assert plan.operations == ()


def test_reserved_s10_intents_are_declared_but_carry_no_backend():
    model = build_semantic_model(build_context(), include_valve_intent=True)
    reserved = model.reserved_intents[0].to_dict()

    assert reserved["kind"] == "ValveIntent"
    assert reserved["reserved_for"] == "S10"


# ------------------------------------------------------------------ validation / dry run

def test_valid_plan_passes_validation():
    task, context, model, capabilities, plan = make_plan()
    report = VALIDATOR.validate(task, plan, model, capabilities, context)

    assert report.status == VALIDATION_PASS, report.errors
    assert report.ok


def test_dry_run_performs_no_cad_work():
    task, context, model, capabilities, plan = make_plan()
    result = dry_run(task, plan, model, capabilities, context)

    assert result.performed_cad_work is False
    assert result.to_dict()["dry_run"] is True
    assert result.planned_operation_count == len(plan.operations)


def test_validator_blocks_a_blocked_plan_and_names_the_capability():
    task, context, model, capabilities, plan = make_plan(valve=True)
    report = VALIDATOR.validate(task, plan, model, capabilities, context)

    assert report.status == VALIDATION_BLOCKED
    assert "tianzheng_valve" in report.missing_capabilities


def test_validator_rejects_an_unknown_backend_capability():
    task, context, model, capabilities, plan = make_plan()
    rogue = PlannedOperation(operation_id="op-x", semantic_intent="route-1",
                             backend_capability="create_tianzheng_valve", parameters={})
    tampered = type(plan)(**{**plan.__dict__, "operations": (*plan.operations, rogue)})

    report = VALIDATOR.validate(task, tampered, model, capabilities, context)

    assert report.status in (VALIDATION_INVALID, VALIDATION_BLOCKED)
    assert "op-x" in report.unsafe_operations


def test_validator_rejects_a_route_through_the_forbidden_zone():
    from mcp_nextgen.s9.contracts import EngineeringSemanticModel, RouteIntent
    task, context, model, capabilities, plan = make_plan()
    crossing = EngineeringSemanticModel(
        model_id=model.model_id, anchors=model.anchors, zones=model.zones,
        route_intents=(RouteIntent("route-1", (1500.0, -1000.0, 0.0), (1500.0, 1000.0, 0.0)),))

    report = VALIDATOR.validate(task, plan, crossing, capabilities, context)

    assert not report.ok
    assert any("forbidden" in c for c in report.geometry_conflicts)


def test_validator_rejects_a_zero_length_route():
    from mcp_nextgen.s9.contracts import EngineeringSemanticModel, RouteIntent
    task, context, model, capabilities, plan = make_plan()
    degenerate = EngineeringSemanticModel(
        model_id=model.model_id, zones=model.zones,
        route_intents=(RouteIntent("route-1", ANCHOR_A, ANCHOR_A),))

    report = VALIDATOR.validate(task, plan, degenerate, capabilities, context)

    assert not report.ok
    assert any("zero-length" in c for c in report.geometry_conflicts)


def test_validator_requires_approval_and_sandbox():
    task, context, model, capabilities, plan = make_plan()
    report = VALIDATOR.validate(task, plan, model, capabilities, context)

    assert plan.approval_requirement == "L3_SANDBOX_WRITE"
    assert task.constraints.safety.sandbox_only is True
    assert "safety" in report.checks_performed


# ------------------------------------------------------------------------- execution

class FakeGateway:
    """Deterministic stand-in for the MCP tools. No sockets, no CAD."""

    def __init__(self, *, pipe_count_after_replay=1, fitting_count_after_replay=2,
                 runtime_class="TDbPipe", fail_on=None, preserved=True):
        self.pipe_after = pipe_count_after_replay
        self.fitting_after = fitting_count_after_replay
        self.runtime_class = runtime_class
        self.fail_on = fail_on
        self.preserved = preserved
        self.calls: list[str] = []

    def _snapshot(self):
        return {"runtime_class": self.runtime_class, "dxf_name": "TCH_PIPE",
                "primary_handle": "9D", "native_identity_confirmed": self.runtime_class == "TDbPipe",
                "start": list(ANCHOR_A), "end": list(ANCHOR_B), "length": 3000.0,
                "related_runtime_classes": ["TDbPipeFitting", "TDbPipeFitting"]}

    def create_pipe(self, document_token, start, end, *, idempotency_key):
        self.calls.append("create_pipe")
        if self.fail_on == "create":
            raise RuntimeError("create exploded")
        return {"primary_handle": "9D", "primary_runtime_class": self.runtime_class,
                "related_handles": ["9E", "9F"],
                "related_runtime_classes": ["TDbPipeFitting", "TDbPipeFitting"],
                "actual_backend_used": "tianzheng_native_backend", "status": "created"}

    def query_pipe(self, document_token, handle, related_handles=()):
        self.calls.append("query_pipe")
        return self._snapshot()

    def validate_identity(self, document_token, handle):
        self.calls.append("validate_identity")
        if self.fail_on == "identity":
            raise RuntimeError("identity exploded")
        return {"native_identity_confirmed": True, "snapshot": self._snapshot()}

    def inventory(self, document_token):
        self.calls.append("inventory")
        count = len([c for c in self.calls if c == "inventory"])
        if count == 1:
            return {"pipe_count": 1, "fitting_count": 2}
        return {"pipe_count": self.pipe_after, "fitting_count": self.fitting_after}

    def persist(self, document_token, handle):
        self.calls.append("persist")
        return {"native_identity_preserved": self.preserved, "document_token": "tok-2",
                "native_class_before": "TDbPipe", "native_class_after": self.runtime_class,
                "snapshot_after_reopen": self._snapshot()}


def run_scenario(gateway):
    task, context, model, capabilities, plan = make_plan()
    execution = EngineeringTaskExecutor(gateway).execute(task, plan, "tok-1")
    snapshot = dict(gateway.query_pipe(execution.document_token, execution.primary_handle or ""))
    snapshot.update({"pipe_count": 1, "fitting_count": 2})
    verdict = EngineeringResultVerifier().verify(task, plan, execution, snapshot, model)
    return execution, verdict


def test_execution_runs_every_operation_in_order():
    execution, _verdict = run_scenario(FakeGateway())

    assert execution.failed is False
    assert len(execution.succeeded_operations) == 5
    assert execution.primary_handle == "9D"
    assert execution.backend_used == "tianzheng_native_backend"


def test_dependent_operation_is_skipped_when_its_dependency_fails():
    gateway = FakeGateway(fail_on="create")
    task, context, model, capabilities, plan = make_plan()

    execution = EngineeringTaskExecutor(gateway).execute(task, plan, "tok-1")

    assert execution.failed is True
    # stop_on_first_failure means nothing after the failure ran at all.
    assert execution.outcome("op-1-create-native-pipe").status == "FAILED"
    assert execution.outcome("op-2-validate-identity") is None


def test_blocked_plan_is_never_executed():
    task, context, model, capabilities, plan = make_plan(valve=True)
    gateway = FakeGateway()

    execution = EngineeringTaskExecutor(gateway).execute(task, plan, "tok-1")

    assert gateway.calls == []
    assert execution.failed is True


# ----------------------------------------------------------------------- verification

def test_full_scenario_passes_verification():
    _execution, verdict = run_scenario(FakeGateway())

    assert verdict.status == ENGINEERING_TASK_PASS, [c.to_dict() for c in verdict.failed_checks]
    assert {c.check_id for c in verdict.checks} >= {
        "operation_count", "native_identity", "geometry_start", "geometry_end",
        "primary_count", "related_count", "persistence", "idempotency",
        "forbidden_zone_obstacle-1", "allowed_region"}


def test_backend_success_alone_does_not_pass_the_task():
    # Everything "succeeded", but the object that came back is an ordinary line.
    _execution, verdict = run_scenario(FakeGateway(runtime_class="AcDbLine"))

    assert verdict.status != ENGINEERING_TASK_PASS
    assert any(c.check_id == "native_identity" and not c.passed for c in verdict.checks)


def test_duplicate_pipe_on_replay_fails_verification():
    _execution, verdict = run_scenario(FakeGateway(pipe_count_after_replay=2))

    assert verdict.status in (ENGINEERING_TASK_PARTIAL, ENGINEERING_TASK_FAILED)
    assert any(c.check_id == "idempotency" and not c.passed for c in verdict.checks)


def test_duplicate_fittings_on_replay_fail_verification():
    _execution, verdict = run_scenario(FakeGateway(fitting_count_after_replay=4))

    assert any(c.check_id == "idempotency" and not c.passed for c in verdict.checks)


def test_lost_persistence_fails_verification():
    _execution, verdict = run_scenario(FakeGateway(preserved=False))

    assert any(c.check_id == "persistence" and not c.passed for c in verdict.checks)


def test_geometry_drift_beyond_tolerance_fails_verification():
    gateway = FakeGateway()
    task, context, model, capabilities, plan = make_plan()
    execution = EngineeringTaskExecutor(gateway).execute(task, plan, "tok-1")
    drifted = dict(gateway.query_pipe("tok", "9D"))
    drifted.update({"end": [2500.0, 0.0, 0.0], "pipe_count": 1, "fitting_count": 2})

    verdict = EngineeringResultVerifier().verify(task, plan, execution, drifted, model)

    assert any(c.check_id == "geometry_end" and not c.passed for c in verdict.checks)


def test_verification_uses_the_post_execution_snapshot_not_the_execution_echo():
    # The execution said TDbPipe; the drawing says otherwise. The drawing wins.
    gateway = FakeGateway()
    task, context, model, capabilities, plan = make_plan()
    execution = EngineeringTaskExecutor(gateway).execute(task, plan, "tok-1")
    lying = {"runtime_class": "AcDbProxyEntity", "native_identity_confirmed": False,
             "start": list(ANCHOR_A), "end": list(ANCHOR_B),
             "pipe_count": 1, "fitting_count": 2}

    verdict = EngineeringResultVerifier().verify(task, plan, execution, lying, model)

    assert verdict.status != ENGINEERING_TASK_PASS


def test_verification_result_is_json_serializable_evidence():
    _execution, verdict = run_scenario(FakeGateway())
    round_tripped = json.loads(json.dumps(verdict.to_dict()))

    assert round_tripped["status"] == ENGINEERING_TASK_PASS
    assert round_tripped["check_count"] >= 8
