"""S10.3 pump: the default tests that were owed before S10.5 could publish the capability.

Nothing here launches AutoCAD, Tianzheng, COM or a network client. The backend is driven
through a recording fake, which is what lets the boundary itself be asserted: what the caller
may send, what it may never send, and what the verifier refuses to accept as a pump.
"""
from __future__ import annotations

import math
from typing import Any

import pytest

from mcp_nextgen.s10 import capabilities as caps
from mcp_nextgen.s8.tianzheng_backend import TianzhengBackend, TianzhengBackendError
from mcp_nextgen.s9.contracts import (
    EngineeringOperationPlan,
    PlannedOperation,
    VerificationRule,
)
from mcp_nextgen.s9.execution import ExecutionResult, PumpNativeIdentityRule
from mcp_nextgen.schemas.tools import ALL_DISPATCHABLE_TOOLS

PUMP_TOOL = "cad.tianzheng.create_pump"


class RecordingClient:
    """Stands in for the plugin transport and records every call it is given."""

    def __init__(self, result: dict[str, Any] | None = None):
        self.calls: list[dict[str, Any]] = []
        self._result = result or {
            "status": "created", "primary_handle": "A1",
            "primary_runtime_class": "TDbPump", "dxf_name": "TCH_PUMP",
        }

    def call(self, operation_type: str, *, mutating: bool, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"operation_type": operation_type, "mutating": mutating, **kwargs})
        if operation_type == "tianzheng_create_pump":
            return {"success": True, "result": {"started": True}}
        if operation_type == "tianzheng_pump_result":
            return {"success": True,
                    "result": {"available": True, "running": False, "result": self._result}}
        if operation_type == "tianzheng_query_equipment":
            return {"success": True, "result": self._result}
        return {"success": True, "result": {}}


def _backend(result: dict[str, Any] | None = None) -> tuple[TianzhengBackend, RecordingClient]:
    client = RecordingClient(result)
    return TianzhengBackend(client, poll_interval=0.0), client


def _plan_with_pump_rule(position: list[float], tolerance: float = 1.0):
    return EngineeringOperationPlan(
        plan_id="plan-1", task_id="task-1",
        operations=(PlannedOperation(
            operation_id="op-eq1-create-native-equipment",
            semantic_intent="eq-1",
            backend_capability=caps.CAP_PUMP_CREATE,
            parameters={"position": position},
            idempotency_key="k-1"),),
        verification_plan=(VerificationRule(
            "vr-equipment-1-identity", "pump_native_identity",
            {"expected_class": "TDbPump", "expected_dxf": "TCH_PUMP",
             "position": position, "tolerance": tolerance}),))


# --------------------------------------------------------------------------- DTO / schema


class TestCreatePumpSchema:
    def test_the_tool_is_registered_and_strict(self):
        tool = ALL_DISPATCHABLE_TOOLS[PUMP_TOOL]
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["outputSchema"]["additionalProperties"] is False

    def test_required_fields(self):
        required = ALL_DISPATCHABLE_TOOLS[PUMP_TOOL]["inputSchema"]["required"]
        for name in ("job_id", "document_token", "position",
                     "request_id", "idempotency_key", "schema_version"):
            assert name in required

    def test_position_is_a_bounded_numeric_point(self):
        position = ALL_DISPATCHABLE_TOOLS[PUMP_TOOL]["inputSchema"]["properties"]["position"]
        assert position["type"] == "array"
        assert position["minItems"] == 2 and position["maxItems"] == 3
        assert position["items"] == {"type": "number"}

    @pytest.mark.parametrize("forbidden", [
        "command", "command_text", "script", "lisp", "python", "csharp", "keystroke",
        "keystrokes", "raw", "exec", "eval", "sendstringtoexecute", "selection",
        "object_id", "objectid", "file_path", "path",
    ])
    def test_no_escape_hatch_field_exists(self, forbidden):
        properties = ALL_DISPATCHABLE_TOOLS[PUMP_TOOL]["inputSchema"]["properties"]
        assert forbidden not in properties

    def test_unimplemented_pump_fields_are_not_exposed(self):
        # rotation, pump type, base size, inlet/outlet elevation and pump height are NOT
        # implemented. Accepting them would make the API promise control it does not have.
        properties = ALL_DISPATCHABLE_TOOLS[PUMP_TOOL]["inputSchema"]["properties"]
        for name in ("rotation", "pump_type", "base_size", "inlet_elevation",
                     "outlet_elevation", "pump_height"):
            assert name not in properties


class TestCreatePumpBoundary:
    def test_only_position_and_idempotency_key_reach_the_plugin(self):
        backend, client = _backend()
        backend.create_pump("tok", [1.0, 2.0, 0.0], idempotency_key="k-1")
        create = next(c for c in client.calls if c["operation_type"] == "tianzheng_create_pump")
        assert set(create["parameters"]) == {"position", "idempotency_key"}

    def test_position_is_normalised_to_floats(self):
        backend, client = _backend()
        backend.create_pump("tok", [1, 2, 3], idempotency_key="k-1")
        create = next(c for c in client.calls if c["operation_type"] == "tianzheng_create_pump")
        assert create["parameters"]["position"] == [1.0, 2.0, 3.0]
        assert all(isinstance(v, float) for v in create["parameters"]["position"])

    @pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
    def test_a_non_finite_position_is_rejected_before_anything_is_queued(self, bad):
        backend, client = _backend()
        with pytest.raises((ValueError, TianzhengBackendError)):
            backend.create_pump("tok", [bad, 0.0, 0.0], idempotency_key="k-1")
        # the guard must run BEFORE anything is queued, so no command was ever sent
        assert not any(c["operation_type"] == "tianzheng_create_pump" for c in client.calls)

    def test_creation_is_mutating_and_the_query_is_not(self):
        backend, client = _backend()
        backend.create_pump("tok", [0.0, 0.0, 0.0], idempotency_key="k-1")
        backend.query_equipment("tok", "A1")
        by_op = {c["operation_type"]: c["mutating"] for c in client.calls}
        assert by_op["tianzheng_create_pump"] is True
        assert by_op["tianzheng_query_equipment"] is False

    def test_a_failed_queue_is_reported_rather_than_polled_forever(self):
        class RefusingClient(RecordingClient):
            def call(self, operation_type, *, mutating, **kwargs):
                if operation_type == "tianzheng_create_pump":
                    return {"success": True, "result": {"started": False}}
                return super().call(operation_type, mutating=mutating, **kwargs)

        backend = TianzhengBackend(RefusingClient(), poll_interval=0.0)
        with pytest.raises(TianzhengBackendError):
            backend.create_pump("tok", [0.0, 0.0, 0.0], idempotency_key="k-1")


# --------------------------------------------------------------------------- identity


class TestPumpNativeIdentityRule:
    def test_a_real_tdbpump_is_accepted(self):
        plan = _plan_with_pump_rule([10.0, 20.0, 0.0])
        checks = PumpNativeIdentityRule().check(
            plan, ExecutionResult("plan-1", "task-1", "h", "tok"),
            {"A1": {"runtime_class": "TDbPump", "dxf_name": "TCH_PUMP",
                    "native_identity_confirmed": True, "position": [10.0, 20.0, 0.0]}})
        assert checks and all(c.passed for c in checks)

    def test_a_block_reference_is_rejected_even_though_the_backend_said_success(self):
        plan = _plan_with_pump_rule([10.0, 20.0, 0.0])
        checks = PumpNativeIdentityRule().check(
            plan, ExecutionResult("plan-1", "task-1", "h", "tok"),
            {"A1": {"runtime_class": "AcDbBlockReference", "dxf_name": "INSERT",
                    "native_identity_confirmed": False, "position": [10.0, 20.0, 0.0]}})
        assert any(not c.passed for c in checks)

    @pytest.mark.parametrize("wrong_class", [
        "AcDbBlockReference", "AcDbCircle", "TDbPipe", "TDbPipeValve", "TDbEquipment", ""])
    def test_any_class_other_than_tdbpump_fails(self, wrong_class):
        plan = _plan_with_pump_rule([0.0, 0.0, 0.0])
        checks = PumpNativeIdentityRule().check(
            plan, ExecutionResult("plan-1", "task-1", "h", "tok"),
            {"A1": {"runtime_class": wrong_class, "dxf_name": "TCH_PUMP",
                    "native_identity_confirmed": True, "position": [0.0, 0.0, 0.0]}})
        assert any(not c.passed for c in checks)

    def test_a_confirmed_flag_alone_does_not_make_it_a_pump(self):
        plan = _plan_with_pump_rule([0.0, 0.0, 0.0])
        checks = PumpNativeIdentityRule().check(
            plan, ExecutionResult("plan-1", "task-1", "h", "tok"),
            {"A1": {"runtime_class": "AcDbBlockReference", "dxf_name": "INSERT",
                    "native_identity_confirmed": True, "position": [0.0, 0.0, 0.0]}})
        assert any(not c.passed for c in checks)

    def test_a_missing_snapshot_fails_rather_than_passing_by_default(self):
        plan = _plan_with_pump_rule([0.0, 0.0, 0.0])
        checks = PumpNativeIdentityRule().check(
            plan, ExecutionResult("plan-1", "task-1", "h", "tok"), {})
        assert checks and not checks[0].passed

    def test_position_outside_tolerance_fails(self):
        plan = _plan_with_pump_rule([0.0, 0.0, 0.0], tolerance=1.0)
        checks = PumpNativeIdentityRule().check(
            plan, ExecutionResult("plan-1", "task-1", "h", "tok"),
            {"A1": {"runtime_class": "TDbPump", "dxf_name": "TCH_PUMP",
                    "native_identity_confirmed": True, "position": [50.0, 0.0, 0.0]}})
        assert any(c.check_id.endswith("_position") and not c.passed for c in checks)

    def test_position_within_tolerance_passes(self):
        plan = _plan_with_pump_rule([0.0, 0.0, 0.0], tolerance=1.0)
        checks = PumpNativeIdentityRule().check(
            plan, ExecutionResult("plan-1", "task-1", "h", "tok"),
            {"A1": {"runtime_class": "TDbPump", "dxf_name": "TCH_PUMP",
                    "native_identity_confirmed": True, "position": [0.5, 0.0, 0.0]}})
        assert all(c.passed for c in checks)

    def test_the_rule_is_inert_when_no_pump_was_planned(self):
        plan = EngineeringOperationPlan(plan_id="p", task_id="t")
        assert PumpNativeIdentityRule().check(
            plan, ExecutionResult("p", "t", "h", "tok"), {}) == []
