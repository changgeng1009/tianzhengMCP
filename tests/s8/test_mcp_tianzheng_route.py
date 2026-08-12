"""S8.6 MCP integration contract.

AutoCAD launch = 0, Tianzheng launch = 0, COM = 0. Everything here runs against the real
dispatcher with a fake route service injected, so the wiring itself is exercised without CAD.
"""
from __future__ import annotations

import json
import uuid

import pytest

from mcp_nextgen.control_server.dispatcher import (
    ControlPlaneError,
    configure_tianzheng_route_service,
    dispatch_tool,
)
from mcp_nextgen.protocol.enums import BackendKind
from mcp_nextgen.protocol.version import PROTOCOL_VERSION
from mcp_nextgen.s8.tianzheng_route import (
    AVAILABLE_SANDBOX_MVP,
    NOT_AVAILABLE,
    NOT_IMPLEMENTED,
    TIANZHENG_BACKEND,
    TIANZHENG_CAPABILITY_REGISTRY,
    S8TianzhengRouteService,
    TianzhengRouteError,
    TianzhengRouteResult,
    map_error_code,
)
from mcp_nextgen.schemas.tools import (
    ALL_DISPATCHABLE_TOOLS,
    NEXTGEN_TOOLS,
    S8_TIANZHENG_TOOLS,
    self_check_registry,
)

TIANZHENG_TOOL_NAMES = {
    "cad.tianzheng.capabilities",
    "cad.tianzheng.create_pipe",
    "cad.tianzheng.query_pipe",
    "cad.tianzheng.validate_pipe_identity",
}


def base(**extra):
    payload = {
        "schema_version": PROTOCOL_VERSION,
        "request_id": f"req-{uuid.uuid4().hex[:8]}",
        "idempotency_key": f"idem-{uuid.uuid4().hex[:8]}",
    }
    payload.update(extra)
    return payload


def pipe_payload(**extra):
    return base(job_id="job-1", document_token="tok-1",
                start=[0.0, 0.0, 0.0], end=[3000.0, 0.0, 0.0], **extra)


class FakeRoute:
    """Stands in for S8TianzhengRouteService without any transport."""

    def __init__(self, *, error=None, loaded=True):
        self.error = error
        self.loaded = loaded
        self.calls = []

    def capability_snapshot(self):
        capabilities = dict(TIANZHENG_CAPABILITY_REGISTRY)
        if not self.loaded:
            capabilities = {k: (NOT_AVAILABLE if v == AVAILABLE_SANDBOX_MVP else v)
                            for k, v in capabilities.items()}
        return {"tianzheng_loaded": self.loaded, "capabilities": capabilities,
                "arbitrary_command_available": False}

    def _run(self, name, payload):
        self.calls.append((name, payload))
        if self.error:
            raise self.error
        return TianzhengRouteResult(
            status="OK", data={"echo": name}, actual_backend_used=TIANZHENG_BACKEND)

    def create_pipe(self, payload):
        return self._run("create_pipe", payload)

    def query_pipe(self, payload):
        return self._run("query_pipe", payload)

    def validate_pipe_identity(self, payload):
        return self._run("validate_pipe_identity", payload)


@pytest.fixture(autouse=True)
def _clear_service():
    configure_tianzheng_route_service(None)
    yield
    configure_tianzheng_route_service(None)


# ------------------------------------------------------------------ MCP schema

def test_tianzheng_tools_are_registered_for_dispatch():
    assert TIANZHENG_TOOL_NAMES <= set(ALL_DISPATCHABLE_TOOLS)
    assert set(S8_TIANZHENG_TOOLS) == TIANZHENG_TOOL_NAMES


def test_mock_only_registry_is_untouched_by_s8():
    # The S4 Mock registry contract must not absorb real-backend tools.
    self_check_registry()
    assert TIANZHENG_TOOL_NAMES.isdisjoint(NEXTGEN_TOOLS)


def test_tianzheng_tools_declare_real_plugin_provenance():
    for name in TIANZHENG_TOOL_NAMES:
        assert ALL_DISPATCHABLE_TOOLS[name]["backend_kind"] == BackendKind.REAL_PLUGIN.value


def test_no_tianzheng_tool_schema_accepts_a_command_field():
    for name in TIANZHENG_TOOL_NAMES:
        schema = json.dumps(ALL_DISPATCHABLE_TOOLS[name]["inputSchema"]).lower()
        for forbidden in ("command", "lisp", "sendcommand", "script", "keystroke", "hzgx"):
            assert forbidden not in schema, f"{name} exposes {forbidden}"


def test_arbitrary_command_field_is_rejected_by_strict_schema():
    configure_tianzheng_route_service(FakeRoute())
    payload = pipe_payload(command="HZGX")

    with pytest.raises(ControlPlaneError) as excinfo:
        dispatch_tool("cad.tianzheng.create_pipe", payload)

    assert excinfo.value.code == "INVALID_PARAMS"


# ------------------------------------------------------- routing and selection

def test_create_is_routed_to_the_tianzheng_backend():
    route = FakeRoute()
    configure_tianzheng_route_service(route)

    result = dispatch_tool("cad.tianzheng.create_pipe", pipe_payload())

    assert result["status"] == "OK"
    assert result["data"]["actual_backend_used"] == TIANZHENG_BACKEND
    assert result["backend_kind"] == BackendKind.REAL_PLUGIN.value
    assert route.calls[0][0] == "create_pipe"


@pytest.mark.parametrize("tool,expected", [
    ("cad.tianzheng.query_pipe", "query_pipe"),
    ("cad.tianzheng.validate_pipe_identity", "validate_pipe_identity"),
])
def test_query_and_validate_route_to_their_handlers(tool, expected):
    route = FakeRoute()
    configure_tianzheng_route_service(route)

    result = dispatch_tool(tool, base(job_id="job-1", document_token="tok-1", handle="211"))

    assert result["status"] == "OK"
    assert route.calls[0][0] == expected


def test_unconfigured_backend_reports_tianzheng_not_loaded():
    result = dispatch_tool("cad.tianzheng.create_pipe", pipe_payload())

    assert result["status"] == "UNAVAILABLE"
    assert result["error_code"] == "TIANZHENG_NOT_LOADED"
    assert result["data"]["real_backend_available"] is False


def test_unsupported_tianzheng_operation_is_unknown_method():
    configure_tianzheng_route_service(FakeRoute())

    with pytest.raises(ControlPlaneError) as excinfo:
        dispatch_tool("cad.tianzheng.create_valve", base(job_id="j"))

    assert excinfo.value.code == "UNKNOWN_METHOD"


# ------------------------------------------------------------------ capability

def test_capability_snapshot_is_reported_per_feature():
    configure_tianzheng_route_service(FakeRoute())

    result = dispatch_tool("cad.tianzheng.capabilities", base())
    capabilities = result["data"]["capabilities"]["capabilities"]

    assert capabilities["tianzheng_native_pipe_create"] == AVAILABLE_SANDBOX_MVP
    assert capabilities["tianzheng_native_pipe_persistence"] == AVAILABLE_SANDBOX_MVP
    assert capabilities["tianzheng_pipe_diameter_read"] == NOT_AVAILABLE
    assert capabilities["tianzheng_pipe_system_read"] == NOT_AVAILABLE
    assert capabilities["tianzheng_valve"] == NOT_IMPLEMENTED
    assert capabilities["user_dwg_tianzheng_edit"] == NOT_AVAILABLE
    assert capabilities["production_tianzheng_write"] == NOT_AVAILABLE


def test_diameter_and_system_are_never_advertised_as_controllable():
    # HZGX takes them from Tianzheng's palette defaults; the API does not control them.
    assert TIANZHENG_CAPABILITY_REGISTRY["tianzheng_pipe_diameter_control"] == NOT_AVAILABLE
    assert TIANZHENG_CAPABILITY_REGISTRY["tianzheng_pipe_system_control"] == NOT_AVAILABLE


def test_capabilities_collapse_when_tianzheng_is_not_loaded():
    configure_tianzheng_route_service(FakeRoute(loaded=False))

    result = dispatch_tool("cad.tianzheng.capabilities", base())
    capabilities = result["data"]["capabilities"]["capabilities"]

    assert capabilities["tianzheng_native_pipe_create"] == NOT_AVAILABLE
    assert AVAILABLE_SANDBOX_MVP not in capabilities.values()


def test_service_without_backend_reports_unconfigured_honestly():
    snapshot = S8TianzhengRouteService(None).capability_snapshot()

    assert snapshot["tianzheng_backend_configured"] is False
    assert snapshot["tianzheng_loaded"] is False
    assert snapshot["capabilities"]["tianzheng_backend"] == NOT_AVAILABLE


def test_service_refuses_to_create_when_handshake_says_not_loaded():
    service = S8TianzhengRouteService(object(), handshake={"tianzheng_loaded": False})

    with pytest.raises(TianzhengRouteError) as excinfo:
        service.create_pipe({"document_token": "t", "idempotency_key": "k",
                             "start": [0, 0, 0], "end": [1, 0, 0]})

    assert excinfo.value.error_code == "TIANZHENG_NOT_LOADED"


# ------------------------------------------------------------- error mapping

@pytest.mark.parametrize("code", [
    "TIANZHENG_NOT_LOADED",
    "TIANZHENG_NATIVE_CLASS_NOT_FOUND",
    "TIANZHENG_PIPE_CREATE_FAILED",
    "TIANZHENG_PIPE_NOT_FOUND",
    "TIANZHENG_PIPE_NATIVE_IDENTITY_MISMATCH",
    "TIANZHENG_PIPE_PROPERTY_UNAVAILABLE",
    "TIANZHENG_PIPE_PERSISTENCE_FAILED",
    "TIANZHENG_PIPE_IDEMPOTENCY_CONFLICT",
])
def test_structured_error_survives_to_the_mcp_caller(code):
    configure_tianzheng_route_service(FakeRoute(error=TianzhengRouteError(code, "boom")))

    result = dispatch_tool("cad.tianzheng.create_pipe", pipe_payload())

    assert result["status"] == "FAILED"
    assert result["error_code"] == code
    assert result["error_code"] != "INTERNAL_ERROR"


def test_error_codes_are_not_collapsed_by_the_mapper():
    for code in ("TIANZHENG_NOT_LOADED", "TIANZHENG_PIPE_NOT_FOUND"):
        assert map_error_code(code) == code
    # An unknown code stays visible rather than becoming INTERNAL_ERROR.
    assert map_error_code("TIANZHENG_SOMETHING_NEW") == "TIANZHENG_SOMETHING_NEW"


# ------------------------------------------------- no ordinary-CAD fallback

def test_results_never_claim_mock_provenance_for_tianzheng_work():
    configure_tianzheng_route_service(FakeRoute())

    result = dispatch_tool("cad.tianzheng.create_pipe", pipe_payload())

    assert result["backend_kind"] != BackendKind.MOCK.value


def test_production_flags_stay_false_on_every_tianzheng_result():
    configure_tianzheng_route_service(FakeRoute())

    for tool, payload in (
        ("cad.tianzheng.capabilities", base()),
        ("cad.tianzheng.create_pipe", pipe_payload()),
    ):
        result = dispatch_tool(tool, payload)
        assert result["production_allowed"] is False
        assert result["production_d1_allowed"] is False
