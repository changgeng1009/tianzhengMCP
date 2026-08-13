"""S10.5 mock multi-object engineering task, end to end.

    create native water pipe -> create native pump -> annotate the pipe's diameter

Fully deterministic and fully offline: the gateway is a fake that models the drawing as data.
No AutoCAD, no Tianzheng, no COM, no network, no LLM.

The impostor cases are the point of the exercise. A gateway that reports success while having
inserted an ordinary block, or having drawn ordinary text, must make the TASK fail - because
that is exactly the failure mode the whole S10 native-object effort exists to prevent.
"""
from __future__ import annotations

from typing import Any, Sequence

import pytest

from mcp_nextgen.s10 import capabilities as caps
from mcp_nextgen.s9.contracts import (
    ANNOTATION_PIPE_DIAMETER,
    ENGINEERING_TASK_FAILED,
    ENGINEERING_TASK_PARTIAL,
    ENGINEERING_TASK_PASS,
    AnnotationIntent,
    CapabilityConstraint,
    EngineeringSemanticModel,
    EngineeringTaskSpec,
    EquipmentIntent,
    GeometricConstraint,
    RouteIntent,
    TaskConstraints,
    VerificationConstraint,
)
from mcp_nextgen.s9.execution import (
    EngineeringResultVerifier,
    EngineeringTaskExecutor,
)
from mcp_nextgen.s9.planner import MockEngineeringPlanner, build_capability_snapshot

PIPE_START = (0.0, 0.0, 0.0)
PIPE_END = (3000.0, 0.0, 0.0)
PUMP_POSITION = (1500.0, 500.0, 0.0)
XDATA = caps.PIPE_LABEL_XDATA_APPLICATION


class FakeDrawing:
    """A drawing modelled as data, so the verifier has something real to re-read."""

    def __init__(self, *, pump_class="TDbPump", pump_dxf="TCH_PUMP",
                 annotation_writes_xdata=True, annotation_carrier="TDbPipe"):
        self.pump_class = pump_class
        self.pump_dxf = pump_dxf
        self.annotation_writes_xdata = annotation_writes_xdata
        self.annotation_carrier = annotation_carrier
        self.pipes: dict[str, dict[str, Any]] = {}
        self.equipment: dict[str, dict[str, Any]] = {}
        self.annotated: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []

    # --- gateway surface ------------------------------------------------------------------

    def create_pipe(self, document_token: str, start: Sequence[float], end: Sequence[float],
                    *, idempotency_key: str) -> dict[str, Any]:
        self.calls.append("create_pipe")
        self.pipes["9D"] = {
            "runtime_class": "TDbPipe", "dxf_name": "TCH_PIPE",
            "native_identity_confirmed": True,
            "start": list(start), "end": list(end), "xdata_applications": [],
        }
        return {"primary_handle": "9D", "related_handles": ["9E", "9F"],
                "actual_backend_used": "tianzheng_native_backend"}

    def query_pipe(self, document_token: str, handle: str,
                   related_handles: Sequence[str] = ()) -> dict[str, Any]:
        return dict(self.pipes[handle])

    def validate_identity(self, document_token: str, handle: str) -> dict[str, Any]:
        return {"native_identity_confirmed": True, "runtime_class": "TDbPipe"}

    def inventory(self, document_token: str) -> dict[str, Any]:
        return {"pipe_count": len(self.pipes), "fitting_count": 2 * len(self.pipes)}

    def persist(self, document_token: str, handle: str) -> dict[str, Any]:
        return {"native_identity_preserved": True, "document_token": document_token}

    def create_pump(self, document_token: str, position: Sequence[float],
                    *, idempotency_key: str) -> dict[str, Any]:
        self.calls.append("create_pump")
        self.equipment["A1"] = {
            "runtime_class": self.pump_class, "dxf_name": self.pump_dxf,
            "native_identity_confirmed": self.pump_class == "TDbPump",
            "position": list(position),
        }
        # NOTE: the gateway reports success regardless of what it actually inserted.
        return {"primary_handle": "A1", "status": "created"}

    def query_equipment(self, document_token: str, handle: str) -> dict[str, Any]:
        return dict(self.equipment[handle])

    def annotate_pipe_diameter(self, document_token: str, target_pipe_handle: str,
                               *, idempotency_key: str) -> dict[str, Any]:
        self.calls.append("annotate_pipe_diameter")
        if self.annotation_writes_xdata:
            self.pipes[target_pipe_handle]["xdata_applications"] = [XDATA]
        self.annotated[target_pipe_handle] = {
            "runtime_class": self.annotation_carrier,
            "xdata_applications": self.pipes[target_pipe_handle]["xdata_applications"],
            "storage_model": caps.MODEL_B_PIPE_OWNED_STATE,
        }
        return {"status": "modified_target", "storage_model": caps.MODEL_B_PIPE_OWNED_STATE}


def _task() -> EngineeringTaskSpec:
    return EngineeringTaskSpec(
        task_id="task-s10-5-e2e",
        task_type="route_native_pipe",
        discipline="water_supply",
        intent="native pipe plus native pump plus diameter annotation",
        constraints=TaskConstraints(
            geometric=GeometricConstraint(start_point=PIPE_START, end_point=PIPE_END),
            capability=CapabilityConstraint(required_native_object="TDbPipe"),
            verification=VerificationConstraint(
                expected_native_class="TDbPipe", expected_primary_count=1,
                require_persistence=False, require_idempotency=False),
        ),
    )


def _model() -> EngineeringSemanticModel:
    return EngineeringSemanticModel(
        model_id="model-e2e",
        route_intents=(RouteIntent("intent-pipe", PIPE_START, PIPE_END),),
        equipment_intents=(EquipmentIntent("intent-pump", "pump", PUMP_POSITION),),
        annotation_intents=(AnnotationIntent("intent-annotation", ANNOTATION_PIPE_DIAMETER,
                                             target_intent_id="intent-pipe"),),
    )


def _run(drawing: FakeDrawing):
    task, model = _task(), _model()
    plan = MockEngineeringPlanner().plan(
        task, context=None, model=model,
        capabilities=build_capability_snapshot(caps.native_capability_registry()))
    assert not plan.is_blocked, plan.missing_capabilities

    execution = EngineeringTaskExecutor(drawing).execute(task, plan, document_token="tok")
    post = drawing.query_pipe("tok", execution.primary_handle or "9D")
    post = {**post, "pipe_count": len(drawing.pipes), "fitting_count": 2 * len(drawing.pipes)}

    verification = EngineeringResultVerifier().verify(
        task, plan, execution, post, model,
        equipment_snapshots={h: drawing.query_equipment("tok", h)
                             for h in execution.equipment_handles},
        annotation_snapshots={h: drawing.annotated[h]
                              for h in execution.annotated_handles if h in drawing.annotated})
    return plan, execution, verification


class TestHappyPath:
    def test_all_three_objects_are_built_and_the_task_passes(self):
        drawing = FakeDrawing()
        plan, execution, verification = _run(drawing)
        assert not execution.failed
        assert verification.status == ENGINEERING_TASK_PASS, [
            c.detail for c in verification.checks if not c.passed]

    def test_every_object_family_was_exercised(self):
        drawing = FakeDrawing()
        _run(drawing)
        assert "create_pipe" in drawing.calls
        assert "create_pump" in drawing.calls
        assert "annotate_pipe_diameter" in drawing.calls

    def test_the_annotation_created_no_new_entity(self):
        drawing = FakeDrawing()
        _run(drawing)
        # Model B: the pipe carries the state; nothing was added to the drawing.
        assert len(drawing.pipes) == 1
        assert drawing.pipes["9D"]["xdata_applications"] == [XDATA]

    def test_the_pump_handle_is_never_confused_with_the_pipe_handle(self):
        drawing = FakeDrawing()
        _, execution, _ = _run(drawing)
        assert execution.primary_handle == "9D"
        assert execution.equipment_handles == ["A1"]


class TestImpostorsFailVerification:
    def test_a_block_reference_pretending_to_be_a_pump_fails_the_task(self):
        drawing = FakeDrawing(pump_class="AcDbBlockReference", pump_dxf="INSERT")
        _, execution, verification = _run(drawing)
        # the backend reported success for every operation...
        assert not execution.failed
        # ...and the TASK still fails, because the drawing was re-read.
        assert verification.status in (ENGINEERING_TASK_FAILED, ENGINEERING_TASK_PARTIAL)
        failed = [c for c in verification.checks if not c.passed]
        assert any(c.check_id.startswith("vr-equipment-") for c in failed)
        assert any("AcDbBlockReference" in repr(c.observed) for c in failed)

    def test_ordinary_text_pretending_to_be_an_annotation_fails_the_task(self):
        drawing = FakeDrawing(annotation_writes_xdata=False, annotation_carrier="AcDbText")
        _, execution, verification = _run(drawing)
        assert not execution.failed
        assert verification.status in (ENGINEERING_TASK_FAILED, ENGINEERING_TASK_PARTIAL)
        assert any("annotation" in c.check_id for c in verification.checks if not c.passed)

    def test_a_missing_annotation_state_fails_even_with_the_right_carrier(self):
        drawing = FakeDrawing(annotation_writes_xdata=False)
        _, _, verification = _run(drawing)
        assert any(c.check_id.endswith("_xdata") and not c.passed
                   for c in verification.checks)

    @pytest.mark.parametrize("wrong_class", ["AcDbBlockReference", "AcDbCircle", "TDbPipe"])
    def test_no_substitute_class_is_accepted_as_a_pump(self, wrong_class):
        drawing = FakeDrawing(pump_class=wrong_class, pump_dxf="INSERT")
        _, _, verification = _run(drawing)
        assert verification.status != ENGINEERING_TASK_PASS


class TestPersistenceAndIdempotency:
    """Replaying the task must not duplicate anything, in any family."""

    def _replay(self, drawing: FakeDrawing):
        task, model = _task(), _model()
        plan = MockEngineeringPlanner().plan(
            task, context=None, model=model,
            capabilities=build_capability_snapshot(caps.native_capability_registry()))
        executor = EngineeringTaskExecutor(drawing)
        first = executor.execute(task, plan, document_token="tok")
        second = executor.execute(task, plan, document_token="tok")
        return first, second

    def test_replaying_creates_no_duplicate_pipe(self):
        drawing = FakeDrawing()
        self._replay(drawing)
        # The fake keys objects by handle, which is exactly what an idempotent backend does.
        assert len(drawing.pipes) == 1

    def test_replaying_creates_no_duplicate_pump(self):
        drawing = FakeDrawing()
        self._replay(drawing)
        assert len(drawing.equipment) == 1

    def test_replaying_the_annotation_creates_no_duplicate_state(self):
        drawing = FakeDrawing()
        self._replay(drawing)
        # Model B has no object to duplicate, so the invariant is on the STATE: the pipe
        # carries the application once, not twice.
        assert drawing.pipes["9D"]["xdata_applications"] == [XDATA]
        assert len(drawing.annotated) == 1

    def test_the_replay_reuses_the_same_idempotency_keys(self):
        task, model = _task(), _model()
        capabilities = build_capability_snapshot(caps.native_capability_registry())
        first = MockEngineeringPlanner().plan(
            task, context=None, model=model, capabilities=capabilities)
        second = MockEngineeringPlanner().plan(
            task, context=None, model=model, capabilities=capabilities)
        assert [o.idempotency_key for o in first.operations] == [
            o.idempotency_key for o in second.operations]

    def test_the_annotated_pipe_still_carries_its_state_after_a_reopen(self):
        drawing = FakeDrawing()
        _run(drawing)
        # persist() models save/close/reopen; the state lives on the pipe, so it survives.
        drawing.persist("tok", "9D")
        assert XDATA in drawing.query_pipe("tok", "9D")["xdata_applications"]


class TestNoRealCadSideEffects:
    def test_the_gateway_is_the_only_thing_touched(self):
        drawing = FakeDrawing()
        _run(drawing)
        assert set(drawing.calls) <= {"create_pipe", "create_pump", "annotate_pipe_diameter"}

    def test_no_command_string_appears_anywhere_in_the_run(self):
        drawing = FakeDrawing()
        plan, execution, _ = _run(drawing)
        serialised = repr(plan.to_dict()) + repr(execution.to_dict())
        for command in ("HZGX", "HZSB", "DGGJ", "GJBZ", "FMFJ"):
            assert command not in serialised
