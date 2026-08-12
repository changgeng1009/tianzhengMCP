"""S9 engineering task layer over MCP. AutoCAD/Tianzheng/COM/network launches = 0."""
from __future__ import annotations

import json
import uuid

import pytest

from mcp_nextgen.control_server.dispatcher import (
    ControlPlaneError,
    configure_engineering_route_service,
    dispatch_tool,
)
from mcp_nextgen.protocol.version import PROTOCOL_VERSION
from mcp_nextgen.s9.route import build_engineering_route_service
from mcp_nextgen.s9.scenario import ANCHOR_A, ANCHOR_B, scenario_capability_snapshot
from mcp_nextgen.schemas.tools import (
    ALL_DISPATCHABLE_TOOLS,
    NEXTGEN_TOOLS,
    S9_ENGINEERING_TOOLS,
    self_check_registry,
)

TOOL_NAMES = {"cad.engineering.plan", "cad.engineering.validate_plan"}


def base(**extra):
    return {"schema_version": PROTOCOL_VERSION,
            "request_id": f"req-{uuid.uuid4().hex[:8]}",
            "idempotency_key": f"idem-{uuid.uuid4().hex[:8]}", **extra}


@pytest.fixture(autouse=True)
def _service():
    configure_engineering_route_service(
        build_engineering_route_service(capabilities=scenario_capability_snapshot()))
    yield
    configure_engineering_route_service(None)


def test_engineering_tools_are_registered_without_touching_the_mock_registry():
    assert TOOL_NAMES <= set(ALL_DISPATCHABLE_TOOLS)
    assert set(S9_ENGINEERING_TOOLS) == TOOL_NAMES
    assert TOOL_NAMES.isdisjoint(NEXTGEN_TOOLS)
    self_check_registry()


def test_no_engineering_schema_accepts_free_text_or_operations():
    for name in TOOL_NAMES:
        schema = json.dumps(ALL_DISPATCHABLE_TOOLS[name]["inputSchema"]).lower()
        for forbidden in ("command", "lisp", "script", "operations", "csharp", "python"):
            assert forbidden not in schema, f"{name} exposes {forbidden}"


def test_plan_tool_returns_a_plan_and_a_dry_run():
    result = dispatch_tool("cad.engineering.plan", base(start=list(ANCHOR_A), end=list(ANCHOR_B)))

    assert result["status"] == "OK"
    data = result["data"]
    assert data["plan"]["blocked"] is False
    assert data["dry_run"]["performed_cad_work"] is False
    assert data["dry_run"]["validation"]["status"] == "PASS"
    assert len(data["plan"]["operations"]) == 5


def test_plan_tool_performs_no_cad_work():
    result = dispatch_tool("cad.engineering.plan", base())
    assert result["data"]["dry_run"]["performed_cad_work"] is False


def test_valve_task_is_blocked_through_mcp():
    result = dispatch_tool("cad.engineering.plan", base(include_valve_intent=True))

    plan = result["data"]["plan"]
    assert plan["blocked"] is True
    assert "tianzheng_valve" in plan["missing_capabilities"]
    assert plan["operations"] == []


def test_validate_tool_reports_blocked_capability():
    result = dispatch_tool("cad.engineering.validate_plan", base(include_valve_intent=True))

    assert result["data"]["validation"]["status"] == "BLOCKED"
    assert "tianzheng_valve" in result["data"]["missing_capabilities"]


def test_route_through_the_obstacle_is_rejected_by_validation():
    result = dispatch_tool("cad.engineering.plan",
                           base(start=[1500.0, -1000.0, 0.0], end=[1500.0, 1000.0, 0.0]))

    validation = result["data"]["dry_run"]["validation"]
    assert validation["status"] != "PASS"
    assert any("forbidden" in c for c in validation["geometry_conflicts"])


def test_unconfigured_planner_is_reported_honestly():
    configure_engineering_route_service(None)
    result = dispatch_tool("cad.engineering.plan", base())

    assert result["status"] == "UNAVAILABLE"
    assert result["error_code"] == "ENGINEERING_PLANNER_NOT_CONFIGURED"


def test_unknown_engineering_tool_is_rejected():
    with pytest.raises(ControlPlaneError) as excinfo:
        dispatch_tool("cad.engineering.execute_anything", base())
    assert excinfo.value.code == "UNKNOWN_METHOD"


def test_extra_command_field_is_rejected_by_the_strict_schema():
    with pytest.raises(ControlPlaneError) as excinfo:
        dispatch_tool("cad.engineering.plan", base(command="HZGX"))
    assert excinfo.value.code == "INVALID_PARAMS"


def test_production_flags_stay_false():
    result = dispatch_tool("cad.engineering.plan", base())
    assert result["production_allowed"] is False
    assert result["production_d1_allowed"] is False
