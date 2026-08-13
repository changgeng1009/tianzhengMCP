"""S10.4 pipe diameter annotation: default tests.

The tricky property here is that a CORRECT annotation creates no object. A verifier written
the obvious way - "find the annotation entity" - fails on a correct drawing, and one written
lazily - "some text appeared near the pipe" - passes on a faked one. Both mistakes are
tested for explicitly.

Nothing here launches AutoCAD, Tianzheng, COM or a network client.
"""
from __future__ import annotations

from typing import Any

import pytest

from mcp_nextgen.s10 import capabilities as caps
from mcp_nextgen.s8.tianzheng_backend import TianzhengBackend, TianzhengBackendError
from mcp_nextgen.s9.contracts import (
    EngineeringOperationPlan,
    PlannedOperation,
    VerificationRule,
)
from mcp_nextgen.s9.execution import ExecutionResult, PipeAnnotationStateRule
from mcp_nextgen.schemas.tools import ALL_DISPATCHABLE_TOOLS

TOOL = "cad.tianzheng.annotate_pipe_diameter"
XDATA = "TG_PIPELABEL_THICK_SHOW"


class RecordingClient:
    def __init__(self, result: dict[str, Any] | None = None):
        self.calls: list[dict[str, Any]] = []
        self._result = result or {
            "status": "modified_target",
            "storage_model": "MODEL_B_PIPE_OWNED_STATE",
            "target_pipe_handle": "9D",
            "new_objects": [],
            "target_differences": [f"xdata_apps [] -> [{XDATA}]", "xdata_item_count 0 -> 2"],
        }

    def call(self, operation_type: str, *, mutating: bool, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"operation_type": operation_type, "mutating": mutating, **kwargs})
        if operation_type == "tianzheng_annotate_pipe":
            return {"success": True, "result": {"started": True}}
        if operation_type == "tianzheng_annotation_result":
            return {"success": True,
                    "result": {"available": True, "running": False, "result": self._result}}
        return {"success": True, "result": {}}


def _plan_with_annotation_rule():
    return EngineeringOperationPlan(
        plan_id="plan-1", task_id="task-1",
        operations=(PlannedOperation(
            operation_id="op-an1-annotate-pipe-diameter",
            semantic_intent="an-1",
            backend_capability=caps.CAP_DIAMETER_ANNOTATION,
            parameters={"annotation_type": "pipe_diameter"},
            idempotency_key="k-1"),),
        verification_plan=(VerificationRule(
            "vr-annotation-1-state", "pipe_annotation_state",
            {"expected_class": "TDbPipe", "annotation_kind": "pipe_diameter"}),))


def _check(snapshots):
    return PipeAnnotationStateRule().check(
        _plan_with_annotation_rule(), ExecutionResult("plan-1", "task-1", "h", "tok"), snapshots)


# --------------------------------------------------------------------------- naming / schema


class TestAnnotationIsNotCalledEntityCreation:
    def test_the_tool_is_not_named_as_a_create(self):
        assert TOOL in ALL_DISPATCHABLE_TOOLS
        assert "create_annotation" not in TOOL
        for name in ALL_DISPATCHABLE_TOOLS:
            assert "create_annotation_entity" not in name

    def test_the_entity_create_capability_is_not_applicable(self):
        assert caps.capability_status(caps.CAP_ANNOTATION_CREATE) == caps.NOT_APPLICABLE

    def test_the_control_capability_is_what_is_published(self):
        assert caps.is_usable(caps.CAP_ANNOTATION_CONTROL)
        assert caps.is_usable(caps.CAP_DIAMETER_ANNOTATION)


class TestAnnotationSchema:
    def test_strict_and_requires_only_the_target(self):
        tool = ALL_DISPATCHABLE_TOOLS[TOOL]
        assert tool["inputSchema"]["additionalProperties"] is False
        assert "target_pipe_handle" in tool["inputSchema"]["required"]

    def test_the_caller_never_supplies_a_pick_point(self):
        # The adapter derives the point from the pipe's own geometry, because only it knows
        # what the underlying hit test needs. A caller-supplied point would also be a
        # coordinate crossing a boundary that is meant to carry a handle and nothing else.
        properties = ALL_DISPATCHABLE_TOOLS[TOOL]["inputSchema"]["properties"]
        for name in ("pick_point", "point", "position", "placement", "location", "direction"):
            assert name not in properties

    @pytest.mark.parametrize("forbidden", [
        "command", "command_text", "script", "lisp", "python", "csharp", "keystroke",
        "raw", "exec", "eval", "sendstringtoexecute", "selection", "object_id", "file_path",
    ])
    def test_no_escape_hatch_field_exists(self, forbidden):
        assert forbidden not in ALL_DISPATCHABLE_TOOLS[TOOL]["inputSchema"]["properties"]


class TestAnnotationBoundary:
    def test_only_the_handle_and_key_reach_the_plugin(self):
        backend = TianzhengBackend(RecordingClient(), poll_interval=0.0)
        client = backend._client                                    # noqa: SLF001 - boundary test
        backend.annotate_pipe_diameter("tok", "9D", idempotency_key="k-1")
        queued = next(c for c in client.calls
                      if c["operation_type"] == "tianzheng_annotate_pipe")
        assert set(queued["parameters"]) == {"target_pipe_handle", "idempotency_key"}
        assert queued["parameters"]["target_pipe_handle"] == "9D"

    def test_the_command_name_never_crosses_the_boundary(self):
        backend = TianzhengBackend(RecordingClient(), poll_interval=0.0)
        client = backend._client                                    # noqa: SLF001
        backend.annotate_pipe_diameter("tok", "9D", idempotency_key="k-1")
        serialised = repr(client.calls)
        assert "DGGJ" not in serialised
        assert "GJBZ" not in serialised

    def test_a_failed_queue_is_reported(self):
        class RefusingClient(RecordingClient):
            def call(self, operation_type, *, mutating, **kwargs):
                if operation_type == "tianzheng_annotate_pipe":
                    return {"success": True, "result": {"started": False}}
                return super().call(operation_type, mutating=mutating, **kwargs)

        backend = TianzhengBackend(RefusingClient(), poll_interval=0.0)
        with pytest.raises(TianzhengBackendError):
            backend.annotate_pipe_diameter("tok", "9D", idempotency_key="k-1")


# --------------------------------------------------------------------------- Model B verdict


class TestModelBVerdict:
    def test_a_pipe_carrying_the_xdata_passes(self):
        checks = _check({"9D": {"runtime_class": "TDbPipe",
                                "xdata_applications": [XDATA],
                                "storage_model": "MODEL_B_PIPE_OWNED_STATE"}})
        assert checks and all(c.passed for c in checks)

    def test_no_new_object_is_valid_for_model_b(self):
        # The rule must not require a new entity: a correct annotation creates none.
        checks = _check({"9D": {"runtime_class": "TDbPipe", "xdata_applications": [XDATA],
                                "new_objects": [], "entity_count": 3}})
        assert all(c.passed for c in checks)

    def test_a_pipe_without_the_xdata_fails(self):
        checks = _check({"9D": {"runtime_class": "TDbPipe", "xdata_applications": []}})
        assert any(c.check_id.endswith("_xdata") and not c.passed for c in checks)

    def test_an_unrelated_xdata_application_does_not_count(self):
        checks = _check({"9D": {"runtime_class": "TDbPipe",
                                "xdata_applications": ["ACAD", "SOME_OTHER_APP"]}})
        assert any(c.check_id.endswith("_xdata") and not c.passed for c in checks)

    def test_the_xdata_application_name_is_the_measured_one(self):
        assert PipeAnnotationStateRule.XDATA_APPLICATION == XDATA
        assert caps.PIPE_LABEL_XDATA_APPLICATION == XDATA

    def test_a_wrong_storage_model_fails(self):
        checks = _check({"9D": {"runtime_class": "TDbPipe", "xdata_applications": [XDATA],
                                "storage_model": "MODEL_A_SEPARATE_OBJECT"}})
        assert any(c.check_id.endswith("_storage_model") and not c.passed for c in checks)


class TestOrdinaryTextIsNotAnAnnotation:
    @pytest.mark.parametrize("text_class", ["AcDbText", "AcDbMText", "AcDbAttributeDefinition"])
    def test_ordinary_cad_text_is_rejected(self, text_class):
        # A DN20 drawn as ordinary text looks identical on screen. It is not the annotation.
        checks = _check({"X1": {"runtime_class": text_class,
                                "xdata_applications": [XDATA]}})
        assert any(not c.passed for c in checks)

    def test_text_saying_dn20_does_not_satisfy_the_rule(self):
        checks = _check({"X1": {"runtime_class": "AcDbText", "text_string": "DN20",
                                "xdata_applications": []}})
        assert any(not c.passed for c in checks)

    def test_the_carrier_must_be_the_native_pipe(self):
        checks = _check({"X1": {"runtime_class": "TDbPipeValve", "xdata_applications": [XDATA]}})
        assert any(c.check_id.endswith("_carrier_class") and not c.passed for c in checks)


class TestVerifierNeverTrustsTheExecutionResult:
    def test_a_missing_snapshot_fails_rather_than_passing(self):
        checks = _check({})
        assert checks and not checks[0].passed
        assert "success is not evidence" in checks[0].detail

    def test_the_rule_is_inert_when_no_annotation_was_planned(self):
        plan = EngineeringOperationPlan(plan_id="p", task_id="t")
        assert PipeAnnotationStateRule().check(
            plan, ExecutionResult("p", "t", "h", "tok"), {}) == []

    def test_the_rule_does_not_look_for_an_annotation_dbobject(self):
        # Guards the specific mistake: hunting for a TDbPipeLabel that does not exist would
        # fail every correct drawing.
        source = PipeAnnotationStateRule.check.__doc__ or ""
        assert "TDbPipeLabel" not in source
        assert PipeAnnotationStateRule.STORAGE_MODEL == "MODEL_B_PIPE_OWNED_STATE"


class TestAnnotationResultContract:
    """The structured result reports what happened, in the vocabulary of Model B."""

    def _route_result(self, adapter_result: dict[str, Any] | None = None):
        from mcp_nextgen.s8.tianzheng_route import S8TianzhengRouteService

        backend = TianzhengBackend(RecordingClient(adapter_result), poll_interval=0.0)
        service = S8TianzhengRouteService(backend)
        return service.annotate_pipe_diameter(
            {"document_token": "tok", "target_pipe_handle": "9D", "idempotency_key": "k-1"}).data

    def test_it_carries_the_required_fields(self):
        data = self._route_result()
        for field in ("target_pipe_handle", "runtime_class", "storage_model", "annotation_kind",
                      "native_state_confirmed", "xdata_application", "persistence_status",
                      "idempotency_status", "warnings"):
            assert field in data, field

    def test_the_storage_model_and_carrier_are_reported_honestly(self):
        data = self._route_result()
        assert data["storage_model"] == "MODEL_B_PIPE_OWNED_STATE"
        assert data["runtime_class"] == "TDbPipe"
        assert data["annotation_kind"] == "diameter"
        assert data["xdata_application"] == XDATA

    def test_native_state_confirmed_comes_from_the_object_not_the_command(self):
        # No target_after fingerprint -> the command "succeeded" but nothing is confirmed.
        assert self._route_result()["native_state_confirmed"] is False

        confirmed = self._route_result({
            "status": "modified_target", "target_pipe_handle": "9D",
            "target_after": {"runtime_class": "TDbPipe", "x_data_applications": [XDATA]},
        })
        assert confirmed["native_state_confirmed"] is True

    def test_a_replay_is_reported_as_already_applied(self):
        data = self._route_result({
            "status": "already_applied", "target_pipe_handle": "9D",
            "replayed_from_record": True, "record_persisted": True,
        })
        assert data["idempotency_status"] == "ALREADY_APPLIED"
        assert data["persistence_status"] == "PERSISTED"


class TestDisplayTextIsNotClaimedAsReadable:
    def test_screen_confirmation_is_not_an_api_read_capability(self):
        # DN20 was confirmed on SCREEN. No native query has been shown to return it, so no
        # capability claims it can be read.
        registry = caps.native_capability_registry()
        assert not any("display_text" in name for name in registry)

    def test_the_result_reports_display_text_read_as_unavailable(self):
        from mcp_nextgen.s8.tianzheng_route import S8TianzhengRouteService

        backend = TianzhengBackend(RecordingClient(), poll_interval=0.0)
        data = S8TianzhengRouteService(backend).annotate_pipe_diameter(
            {"document_token": "tok", "target_pipe_handle": "9D",
             "idempotency_key": "k-1"}).data
        assert data["display_text_read"] == "NOT_AVAILABLE"
