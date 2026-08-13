"""S10.5 MCP surface: the new tools dispatch, and they carry no escape hatch.

Nothing here launches AutoCAD, Tianzheng, COM or a network client - the route service is a
recording fake.
"""
from __future__ import annotations

from typing import Any

import pytest

from mcp_nextgen.control_server import dispatcher
from mcp_nextgen.s10 import capabilities as caps
from mcp_nextgen.s8.tianzheng_route import TianzhengRouteError, TianzhengRouteResult
from mcp_nextgen.schemas.tools import ALL_DISPATCHABLE_TOOLS, S10_NATIVE_OBJECT_TOOLS

S10_TOOLS = ["cad.tianzheng.create_pump", "cad.tianzheng.query_pump",
             "cad.tianzheng.annotate_pipe_diameter", "cad.tianzheng.native_capabilities"]


class FakeRoute:
    def __init__(self, error: TianzhengRouteError | None = None):
        self.seen: list[tuple[str, dict[str, Any]]] = []
        self._error = error

    def _record(self, name: str, payload: dict[str, Any]) -> TianzhengRouteResult:
        self.seen.append((name, dict(payload)))
        if self._error:
            raise self._error
        return TianzhengRouteResult(status="OK", data={"ok": True},
                                    actual_backend_used="tianzheng_native_backend")

    def create_pump(self, payload): return self._record("create_pump", payload)
    def query_pump(self, payload): return self._record("query_pump", payload)
    def annotate_pipe_diameter(self, payload):
        return self._record("annotate_pipe_diameter", payload)


@pytest.fixture
def route(monkeypatch):
    fake = FakeRoute()
    monkeypatch.setattr(dispatcher, "_TIANZHENG_ROUTE_SERVICE", fake, raising=False)
    return fake


def _payload(**extra: Any) -> dict[str, Any]:
    return {"schema_version": "1.0.0", "request_id": "req-1", "idempotency_key": "key-1",
            "job_id": "job-1", "document_token": "tok-1", **extra}


class TestToolsAreRegistered:
    @pytest.mark.parametrize("name", S10_TOOLS)
    def test_each_tool_exists_and_is_strict(self, name):
        tool = ALL_DISPATCHABLE_TOOLS[name]
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["outputSchema"]["additionalProperties"] is False

    def test_no_tool_name_promises_annotation_entity_creation(self):
        for name in S10_NATIVE_OBJECT_TOOLS:
            assert "create_annotation" not in name

    @pytest.mark.parametrize("name", S10_TOOLS)
    def test_production_is_never_allowed(self, name):
        assert ALL_DISPATCHABLE_TOOLS[name]["production_d1_allowed"] is False


class TestDispatch:
    def test_create_pump_reaches_the_route_service(self, route):
        dispatcher._dispatch_tianzheng_tool(
            "cad.tianzheng.create_pump", _payload(position=[1.0, 2.0, 0.0]))
        assert [name for name, _ in route.seen] == ["create_pump"]

    def test_annotate_reaches_the_route_service_with_only_the_handle(self, route):
        dispatcher._dispatch_tianzheng_tool(
            "cad.tianzheng.annotate_pipe_diameter", _payload(target_pipe_handle="9D"))
        name, payload = route.seen[0]
        assert name == "annotate_pipe_diameter"
        assert payload["target_pipe_handle"] == "9D"
        assert "pick_point" not in payload

    def test_a_structured_backend_error_survives_to_the_caller(self, monkeypatch):
        failing = FakeRoute(TianzhengRouteError("TIANZHENG_PIPE_NOT_FOUND", "no such pipe"))
        monkeypatch.setattr(dispatcher, "_TIANZHENG_ROUTE_SERVICE", failing, raising=False)
        result = dispatcher._dispatch_tianzheng_tool(
            "cad.tianzheng.annotate_pipe_diameter", _payload(target_pipe_handle="ZZ"))
        assert result["status"] == "FAILED"
        assert result["error_code"] == "TIANZHENG_PIPE_NOT_FOUND"

    def test_results_never_claim_mock_provenance(self, route):
        result = dispatcher._dispatch_tianzheng_tool(
            "cad.tianzheng.create_pump", _payload(position=[0.0, 0.0, 0.0]))
        assert result["backend_kind"] == "REAL_PLUGIN"
        assert result["production_allowed"] is False


class TestCapabilityReportIsAlwaysAnswerable:
    def test_it_answers_even_with_no_backend_configured(self, monkeypatch):
        monkeypatch.setattr(dispatcher, "_TIANZHENG_ROUTE_SERVICE", None, raising=False)
        result = dispatcher._dispatch_tianzheng_tool(
            "cad.tianzheng.native_capabilities", _payload())
        assert result["status"] == "OK"
        assert result["data"]["capabilities"]["tianzheng_native_valve_create"] == "NOT_IMPLEMENTED"

    def test_it_reports_the_three_layer_model(self, monkeypatch):
        monkeypatch.setattr(dispatcher, "_TIANZHENG_ROUTE_SERVICE", None, raising=False)
        families = dispatcher._dispatch_tianzheng_tool(
            "cad.tianzheng.native_capabilities", _payload())["data"]["object_families"]
        valve = families["valve"]
        assert valve["runtime_available"] is True
        assert valve["manual_creation_available"] is True
        assert valve["automation_available"] is False

    def test_it_reports_supported_equipment_types(self, monkeypatch):
        monkeypatch.setattr(dispatcher, "_TIANZHENG_ROUTE_SERVICE", None, raising=False)
        data = dispatcher._dispatch_tianzheng_tool(
            "cad.tianzheng.native_capabilities", _payload())["data"]
        assert data["supported_equipment_types"] == ["pump"]
        assert data["annotation_storage_model"] == caps.MODEL_B_PIPE_OWNED_STATE
