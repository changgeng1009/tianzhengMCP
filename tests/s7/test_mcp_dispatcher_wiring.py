"""The plugin backend must be reachable from the REAL MCP dispatcher.

S7 originally shipped `mcp_nextgen/s7/plugin_route.py` as a service object that nothing in
`dispatch_tool` referenced — a parallel route. These tests pin the wiring so that regression
cannot recur: the plugin is reachable only through registered tools on the existing
dispatcher, and never through a raw-protocol surface.

No AutoCAD is started: with no route service configured the tools report UNAVAILABLE.
"""
from __future__ import annotations

import uuid

import pytest

from mcp_nextgen.control_server import dispatcher as dispatcher_module
from mcp_nextgen.control_server.dispatcher import (
    ControlPlaneError,
    configure_plugin_route_service,
    dispatch_tool,
)
from mcp_nextgen.protocol.enums import BackendKind
from mcp_nextgen.protocol.version import PROTOCOL_VERSION
from mcp_nextgen.schemas.tools import ALL_DISPATCHABLE_TOOLS, NEXTGEN_TOOLS, S7_PLUGIN_TOOLS

PLUGIN_TOOLS = ("cad.plugin.capabilities", "cad.plugin.execute")
LAYER = "CADAGENT_S6_MVP"


def envelope(**extra):
    payload = {
        "schema_version": PROTOCOL_VERSION,
        "request_id": "r-" + uuid.uuid4().hex[:10],
        "idempotency_key": "k-" + uuid.uuid4().hex[:10],
    }
    payload.update(extra)
    return payload


def execute_payload(**extra):
    fields = {
        "job_id": "j-" + uuid.uuid4().hex[:8],
        "session_id": "s1",
        "layer": LAYER,
        "entities": [{"type": "line", "geometry": {"start": {"x": 0, "y": 0}, "end": {"x": 10, "y": 0}}}],
    }
    fields.update(extra)  # callers may override any field, including entities
    return envelope(**fields)


@pytest.fixture(autouse=True)
def _clear_service():
    configure_plugin_route_service(None)
    yield
    configure_plugin_route_service(None)


# ------------------------------------------------------------------ registration


@pytest.mark.parametrize("name", PLUGIN_TOOLS)
def test_plugin_tools_are_dispatchable_from_the_existing_registry(name):
    assert name in ALL_DISPATCHABLE_TOOLS, f"{name} must be servable by dispatch_tool"
    assert ALL_DISPATCHABLE_TOOLS[name]["available"] is True


@pytest.mark.parametrize("name", PLUGIN_TOOLS)
def test_plugin_tools_stay_out_of_the_s4_mock_only_registry(name):
    """NEXTGEN_TOOLS is the S4 Mock-only baseline; a real backend must not be added to it."""
    assert name not in NEXTGEN_TOOLS
    assert name in S7_PLUGIN_TOOLS


def test_s4_registry_remains_entirely_mock_backed():
    for name, tool in NEXTGEN_TOOLS.items():
        assert tool["backend_kind"] == BackendKind.MOCK.value, f"{name} broke the S4 Mock-only guarantee"
        assert tool["real_backend_available"] is False


@pytest.mark.parametrize("name", PLUGIN_TOOLS)
def test_plugin_tools_declare_real_plugin_provenance(name):
    tool = S7_PLUGIN_TOOLS[name]
    assert tool["backend_kind"] == BackendKind.REAL_PLUGIN.value
    assert tool["real_backend_available"] is True
    assert tool["production_d1_allowed"] is False


@pytest.mark.parametrize("name", PLUGIN_TOOLS)
def test_plugin_tools_are_dispatchable(name):
    """The decisive check: dispatch_tool must handle them, not fall through to unknown."""
    payload = envelope() if name.endswith("capabilities") else execute_payload()
    result = dispatch_tool(name, payload)
    assert result["status"] != "NOT_IMPLEMENTED"
    assert result["error_code"] != "MOCK_BACKEND_NOT_IMPLEMENTED"


def test_dispatcher_exposes_the_plugin_injection_point():
    assert hasattr(dispatcher_module, "configure_plugin_route_service")
    assert hasattr(dispatcher_module, "_dispatch_plugin_tool")


# ------------------------------------------------------------------ safe default


@pytest.mark.parametrize("name", PLUGIN_TOOLS)
def test_unconfigured_plugin_reports_unavailable_and_touches_no_cad(name):
    payload = envelope() if name.endswith("capabilities") else execute_payload()
    result = dispatch_tool(name, payload)

    assert result["status"] == "UNAVAILABLE"
    assert result["error_code"] == "PLUGIN_BACKEND_NOT_CONFIGURED"
    assert (result["data"] or {}).get("actual_backend_used") is None


def test_unknown_tool_is_still_rejected():
    with pytest.raises(ControlPlaneError):
        dispatch_tool("cad.plugin.raw_send", envelope())


# ------------------------------------------------------------------ provenance


def test_plugin_results_never_claim_mock_provenance():
    result = dispatch_tool("cad.plugin.capabilities", envelope())
    assert result["backend_kind"] == BackendKind.REAL_PLUGIN.value


def test_existing_mock_tools_keep_mock_provenance():
    """Wiring the plugin must not change any pre-existing tool's provenance."""
    result = dispatch_tool("cad.capabilities", envelope())
    assert result["backend_kind"] == BackendKind.MOCK.value


# ------------------------------------------------------------------ no raw surface


def test_no_raw_protocol_tool_is_registered():
    forbidden = ("plugin_send", "raw", "socket", "send_command", "netload", "lisp", "eval")
    for name in ALL_DISPATCHABLE_TOOLS:
        lowered = name.lower()
        for token in forbidden:
            assert token not in lowered, f"tool {name} exposes a raw-protocol surface"


def test_execute_schema_accepts_only_structured_fields():
    properties = set(S7_PLUGIN_TOOLS["cad.plugin.execute"]["inputSchema"]["properties"])
    for forbidden in ("payload", "raw", "frame", "command", "document_token", "session_nonce",
                      "auth_token", "operation_type"):
        assert forbidden not in properties, f"{forbidden} must not be caller-supplied"


def test_execute_rejects_an_unknown_field():
    with pytest.raises(ControlPlaneError):
        dispatch_tool("cad.plugin.execute", execute_payload(raw_frame="{}"))


# ------------------------------------------------------------------ routed execution


class _StubService:
    """Minimal stand-in for the route service; no socket, no AutoCAD."""

    def __init__(self, status="completed", backend="autocad_plugin_backend"):
        self._status = status
        self._backend = backend
        self.calls: list[dict] = []

    def capability_snapshot(self):
        return {"plugin_backend_configured": True, "autocad_plugin_backend": "AVAILABLE_SANDBOX_MVP"}

    def execute(self, plan, *, session_id, require_atomic_batch, preferred_backend, idempotency_key):
        from mcp_nextgen.s7.plugin_route import PluginRouteResult

        self.calls.append({
            "job_id": plan.job_id, "session_id": session_id,
            "require_atomic_batch": require_atomic_batch, "idempotency_key": idempotency_key,
            "operations": [op.operation for op in plan.operations],
        })
        return PluginRouteResult(self._status, {"selected_backend": self._backend},
                                 {"data": {"created_count": 1}}, self._backend)


def test_configured_service_is_actually_invoked_with_an_s6_plan():
    service = _StubService()
    configure_plugin_route_service(service)

    result = dispatch_tool("cad.plugin.execute", execute_payload())

    assert result["status"] == "COMPLETED"
    assert len(service.calls) == 1
    call = service.calls[0]
    # The dispatcher built a real S6 plan, not a passthrough blob.
    assert call["operations"] == ["ENSURE_LAYER", "CREATE_LINE"]
    assert call["require_atomic_batch"] is True
    assert call["idempotency_key"]


def test_capabilities_tool_reads_from_the_configured_service():
    configure_plugin_route_service(_StubService())
    result = dispatch_tool("cad.plugin.capabilities", envelope())

    assert result["status"] == "OK"
    assert result["data"]["capabilities"]["plugin_backend_configured"] is True


def test_blocked_routing_is_reported_not_faked():
    configure_plugin_route_service(_StubService(status="blocked", backend=None))
    result = dispatch_tool("cad.plugin.execute", execute_payload())

    assert result["status"] == "BLOCKED"
    assert result["data"]["actual_backend_used"] is None


def test_delegated_routing_names_the_real_backend():
    configure_plugin_route_service(_StubService(status="delegated", backend="nextgen_mock"))
    result = dispatch_tool("cad.plugin.execute", execute_payload())

    assert result["status"] == "DELEGATED"
    assert result["data"]["actual_backend_used"] == "nextgen_mock"


def test_invalid_structured_request_is_rejected_before_routing():
    service = _StubService()
    configure_plugin_route_service(service)

    with pytest.raises(ControlPlaneError):
        dispatch_tool("cad.plugin.execute", execute_payload(entities=[{"type": "text", "geometry": {}}]))
    assert service.calls == [], "nothing may be routed when the request is invalid"
