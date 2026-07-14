from __future__ import annotations

from mcp.agents.agent_result_schema import default_result, validate_agent_result


def test_default_result_schema_is_parseable() -> None:
    result = default_result("AGENT-DS1", "PARTIAL", "dry_run")
    ok, errors = validate_agent_result(result)
    assert ok, errors


def test_invalid_status_is_rejected() -> None:
    result = default_result("AGENT-DS1")
    result["status"] = "UNKNOWN"
    ok, errors = validate_agent_result(result)
    assert not ok
    assert "invalid status" in errors

