"""Regression: the plan validator must accept every capability the planner can emit.

S10.5 added pump and annotation operations to the planner but not to the validator's
KNOWN_BACKEND_CAPABILITIES whitelist. The mock end-to-end test drove the planner and the
executor and never the validator, so nothing caught it until the first real S10.6 run, where
a valid multi-object plan was rejected as INVALID before it could execute.

The whitelist is now derived from the registry. These tests fail if anyone re-hardcodes it.
"""
from __future__ import annotations

import pytest

from mcp_nextgen.s10 import capabilities as caps
from mcp_nextgen.s9.contracts import (
    ANNOTATION_PIPE_DIAMETER,
    AnnotationIntent,
    CapabilityConstraint,
    DrawingContextSnapshot,
    EngineeringSemanticModel,
    EngineeringTaskSpec,
    EquipmentIntent,
    GeometricConstraint,
    RouteIntent,
    TaskConstraints,
    VerificationConstraint,
)
from mcp_nextgen.s9.planner import MockEngineeringPlanner, build_capability_snapshot
from mcp_nextgen.s9.validation import KNOWN_BACKEND_CAPABILITIES, EngineeringPlanValidator

PIPE_START = (0.0, 0.0, 0.0)
PIPE_END = (3000.0, 0.0, 0.0)
PUMP_POSITION = (4500.0, 1000.0, 0.0)


def _task() -> EngineeringTaskSpec:
    return EngineeringTaskSpec(
        task_id="task-validate", task_type="route_native_pipe", discipline="water_supply",
        intent="pipe plus pump plus diameter annotation",
        constraints=TaskConstraints(
            geometric=GeometricConstraint(start_point=PIPE_START, end_point=PIPE_END),
            capability=CapabilityConstraint(required_native_object="TDbPipe"),
            verification=VerificationConstraint(expected_native_class="TDbPipe"),
        ),
    )


def _model() -> EngineeringSemanticModel:
    return EngineeringSemanticModel(
        model_id="m",
        route_intents=(RouteIntent("intent-pipe", PIPE_START, PIPE_END),),
        equipment_intents=(EquipmentIntent("intent-pump", "pump", PUMP_POSITION),),
        annotation_intents=(AnnotationIntent("intent-annotation", ANNOTATION_PIPE_DIAMETER,
                                             target_intent_id="intent-pipe"),),
    )


class TestValidatorKnowsEveryPublishedCapability:
    @pytest.mark.parametrize("capability", sorted(
        name for name, status in caps.native_capability_registry().items()
        if status in caps.USABLE_STATUSES))
    def test_every_usable_registry_capability_is_known_to_the_validator(self, capability):
        assert capability in KNOWN_BACKEND_CAPABILITIES

    def test_the_multi_object_plan_validates(self):
        task, model = _task(), _model()
        capabilities = build_capability_snapshot(caps.native_capability_registry())
        context = DrawingContextSnapshot(source_type="structured")
        plan = MockEngineeringPlanner().plan(task, context, model, capabilities)
        assert not plan.is_blocked

        report = EngineeringPlanValidator().validate(task, plan, model, capabilities, context)
        assert report.status in ("PASS", "PASS_WITH_WARNINGS"), report.errors
        assert not any("unknown backend capability" in e for e in report.errors)

    def test_every_capability_the_planner_emits_is_accepted(self):
        # The invariant that actually matters: planner output and validator input agree.
        task, model = _task(), _model()
        capabilities = build_capability_snapshot(caps.native_capability_registry())
        plan = MockEngineeringPlanner().plan(
            task, DrawingContextSnapshot(source_type="structured"), model, capabilities)
        for operation in plan.operations:
            assert operation.backend_capability in KNOWN_BACKEND_CAPABILITIES, (
                f"{operation.operation_id} emits {operation.backend_capability}, which the "
                f"validator would reject")

    def test_an_invented_capability_is_still_rejected(self):
        # The fix widened the whitelist; it must not have removed the check.
        assert "tianzheng_do_whatever_i_want" not in KNOWN_BACKEND_CAPABILITIES
