"""S10.5 planner integration: multi-object tasks, and the tasks that must be refused.

The negative cases matter more than the positive one. A planner that quietly substitutes a
supported object for an unsupported one produces a drawing that looks finished and is wrong,
and the S9 contract is that it must block instead.

Nothing here launches AutoCAD, Tianzheng, COM or a network client.
"""
from __future__ import annotations

import pytest

from mcp_nextgen.s10 import capabilities as caps
from mcp_nextgen.s9.contracts import (
    ANNOTATION_PIPE_DIAMETER,
    BLOCKED_BY_MISSING_CAPABILITY,
    AnnotationIntent,
    CapabilityConstraint,
    EngineeringSemanticModel,
    EngineeringTaskSpec,
    EquipmentIntent,
    GeometricConstraint,
    ReservedIntent,
    RouteIntent,
    TaskConstraints,
    VerificationConstraint,
)
from mcp_nextgen.s9.planner import (
    BLOCKED_BY_UNSUPPORTED_ANNOTATION_TYPE,
    BLOCKED_BY_UNSUPPORTED_EQUIPMENT_TYPE,
    MockEngineeringPlanner,
    build_capability_snapshot,
)

PIPE_START = (0.0, 0.0, 0.0)
PIPE_END = (3000.0, 0.0, 0.0)


def _task(**constraint_kwargs) -> EngineeringTaskSpec:
    return EngineeringTaskSpec(
        task_id="task-s10-5",
        task_type="route_native_pipe",
        discipline="water_supply",
        intent="create a native water pipe, a native pump and a diameter annotation",
        constraints=TaskConstraints(
            geometric=GeometricConstraint(start_point=PIPE_START, end_point=PIPE_END),
            capability=CapabilityConstraint(required_native_object="TDbPipe",
                                            **constraint_kwargs),
            verification=VerificationConstraint(expected_native_class="TDbPipe"),
        ),
    )


def _model(*, equipment=(), annotations=(), reserved=()) -> EngineeringSemanticModel:
    return EngineeringSemanticModel(
        model_id="model-1",
        route_intents=(RouteIntent("intent-pipe", PIPE_START, PIPE_END),),
        equipment_intents=tuple(equipment),
        annotation_intents=tuple(annotations),
        reserved_intents=tuple(reserved),
    )


def _capabilities():
    return build_capability_snapshot(caps.native_capability_registry())


def _plan(model, task=None):
    return MockEngineeringPlanner().plan(
        task or _task(), context=None, model=model, capabilities=_capabilities())


# --------------------------------------------------------------------------- positive


class TestMultiObjectPlan:
    """Pipe + pump + diameter annotation - the S10.5 mock engineering task."""

    def _full_model(self):
        return _model(
            equipment=(EquipmentIntent("intent-pump", "pump", (1500.0, 500.0, 0.0)),),
            annotations=(AnnotationIntent("intent-annotation", ANNOTATION_PIPE_DIAMETER,
                                          target_intent_id="intent-pipe"),))

    def test_the_plan_is_not_blocked(self):
        plan = _plan(self._full_model())
        assert not plan.is_blocked, plan.missing_capabilities

    def test_it_covers_pipe_pump_and_annotation(self):
        used = {op.backend_capability for op in _plan(self._full_model()).operations}
        assert caps.CAP_PIPE_CREATE in used
        assert caps.CAP_PUMP_CREATE in used
        assert caps.CAP_DIAMETER_ANNOTATION in used

    def test_each_created_object_is_identity_validated(self):
        plan = _plan(self._full_model())
        rule_types = {r.rule_type for r in plan.verification_plan}
        assert "native_identity" in rule_types          # the pipe
        assert "pump_native_identity" in rule_types     # the pump
        assert "pipe_annotation_state" in rule_types    # the annotation

    def test_the_annotation_waits_for_the_pipe_that_it_annotates(self):
        plan = _plan(self._full_model())
        annotation = next(o for o in plan.operations
                          if o.backend_capability == caps.CAP_DIAMETER_ANNOTATION)
        assert "op-1-create-native-pipe" in annotation.depends_on

    def test_every_creating_operation_carries_a_distinct_idempotency_key(self):
        plan = _plan(self._full_model())
        keys = [o.idempotency_key for o in plan.operations
                if o.backend_capability in (caps.CAP_PIPE_CREATE, caps.CAP_PUMP_CREATE,
                                            caps.CAP_DIAMETER_ANNOTATION)]
        assert all(keys)
        assert len(set(keys)) == len(keys)

    def test_the_plan_never_names_a_tianzheng_command(self):
        # The planner speaks capabilities. HZGX/HZSB/DGGJ are adapter business.
        serialised = repr(_plan(self._full_model()).to_dict())
        for command in ("HZGX", "HZSB", "DGGJ", "GJBZ", "FMFJ", "SendStringToExecute"):
            assert command not in serialised

    def test_the_plan_carries_no_forbidden_operation_field(self):
        for operation in _plan(self._full_model()).operations:
            for forbidden in ("command", "script", "lisp", "code", "keystroke", "raw"):
                assert forbidden not in operation.parameters

    def test_the_storage_model_does_not_leak_into_the_plan(self):
        # The planner asks for the pipe to be annotated; how that is stored is invisible here.
        serialised = repr(_plan(self._full_model()).to_dict())
        assert "MODEL_B" not in serialised
        assert "XDATA" not in serialised.upper()


# --------------------------------------------------------------------------- negative


class TestValveIsBlocked:
    def test_a_task_needing_a_valve_blocks_naming_the_capability(self):
        model = _model(reserved=(ReservedIntent(
            "intent-valve", "ValveIntent", position=(500.0, 0.0, 0.0),
            required_capability=caps.CAP_VALVE_CREATE),))
        plan = _plan(model)
        assert plan.is_blocked
        assert plan.blocked_reason == BLOCKED_BY_MISSING_CAPABILITY
        assert caps.CAP_VALVE_CREATE in plan.missing_capabilities

    def test_no_operation_is_emitted_at_all(self):
        model = _model(reserved=(ReservedIntent(
            "intent-valve", "ValveIntent", required_capability=caps.CAP_VALVE_CREATE),))
        # Not even the pipe, which IS supported: a partial plan would silently drop the valve.
        assert _plan(model).operations == ()


class TestUnsupportedEquipmentIsBlocked:
    def test_a_water_tank_blocks_even_though_equipment_create_is_available(self):
        assert caps.is_usable(caps.CAP_EQUIPMENT_CREATE), "the family capability IS available"
        model = _model(equipment=(
            EquipmentIntent("intent-tank", "water_tank", (100.0, 100.0, 0.0)),))
        plan = _plan(model)
        assert plan.is_blocked
        assert plan.blocked_reason == BLOCKED_BY_UNSUPPORTED_EQUIPMENT_TYPE

    def test_a_water_tank_is_never_rerouted_to_a_pump(self):
        model = _model(equipment=(
            EquipmentIntent("intent-tank", "water_tank", (100.0, 100.0, 0.0)),))
        plan = _plan(model)
        assert all(o.backend_capability != caps.CAP_PUMP_CREATE for o in plan.operations)
        assert "water_tank" in " ".join(plan.warnings)

    @pytest.mark.parametrize("equipment_type", ["water_tank", "boiler", "chiller", "fan"])
    def test_every_unsupported_type_blocks(self, equipment_type):
        model = _model(equipment=(
            EquipmentIntent("intent-x", equipment_type, (0.0, 0.0, 0.0)),))
        assert _plan(model).is_blocked

    def test_a_pump_is_not_blocked(self):
        model = _model(equipment=(EquipmentIntent("intent-pump", "pump", (0.0, 0.0, 0.0)),))
        assert not _plan(model).is_blocked


class TestActiveFittingIsBlocked:
    def test_a_task_demanding_a_deliberate_fitting_blocks(self):
        model = _model(reserved=(ReservedIntent(
            "intent-fitting", "FittingIntent", position=(1000.0, 0.0, 0.0),
            required_capability=caps.CAP_FITTING_CREATE),))
        plan = _plan(model)
        assert plan.is_blocked
        assert caps.CAP_FITTING_CREATE in plan.missing_capabilities

    def test_a_plain_pipe_task_does_not_require_a_fitting_capability(self):
        # HZGX produces endpoint fittings as a side effect. That must not be turned into a
        # requirement, or every ordinary pipe task would block.
        plan = _plan(_model())
        assert not plan.is_blocked
        assert caps.CAP_FITTING_CREATE not in plan.required_capabilities


class TestUnsupportedAnnotationIsBlocked:
    @pytest.mark.parametrize("annotation_type", ["pipe_elevation", "pipe_slope", "flow_arrow"])
    def test_an_annotation_kind_without_an_adapter_blocks(self, annotation_type):
        model = _model(annotations=(
            AnnotationIntent("intent-an", annotation_type, target_intent_id="intent-pipe"),))
        plan = _plan(model)
        assert plan.is_blocked
        assert plan.blocked_reason == BLOCKED_BY_UNSUPPORTED_ANNOTATION_TYPE

    def test_pipe_diameter_is_supported(self):
        model = _model(annotations=(
            AnnotationIntent("intent-an", ANNOTATION_PIPE_DIAMETER,
                             target_intent_id="intent-pipe"),))
        assert not _plan(model).is_blocked


class TestCapabilityGateRunsBeforeAnyOperation:
    def test_an_unavailable_pipe_capability_blocks_the_whole_plan(self):
        capabilities = dict(_capabilities())
        capabilities[caps.CAP_PIPE_CREATE] = "NOT_IMPLEMENTED"
        plan = MockEngineeringPlanner().plan(
            _task(), context=None, model=_model(), capabilities=capabilities)
        assert plan.is_blocked
        assert plan.operations == ()
