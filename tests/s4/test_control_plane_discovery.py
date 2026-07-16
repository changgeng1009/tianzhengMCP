"""S4 NextGen MCP discovery 合同：仅验证静态 Mock-only 数据。"""

from __future__ import annotations

import pytest

from mcp_nextgen.control_server.discovery import (
    list_prompts,
    list_resources,
    prompt_message,
    resource_payload,
    self_check_discovery,
)
from mcp_nextgen.protocol.version import PROTOCOL_VERSION
from mcp_nextgen.schemas.tools import NEXTGEN_TOOLS


def test_s4_discovery_schema_is_versioned_and_mock_only() -> None:
    result = self_check_discovery()

    assert result == {
        "schema_version": PROTOCOL_VERSION,
        "tool_count": 13,
        "resource_count": 3,
        "prompt_count": 2,
        "backend_kind": "MOCK",
        "real_backend_available": False,
    }

    for tool in NEXTGEN_TOOLS.values():
        for key in ("name", "description", "inputSchema", "outputSchema", "errorSchema", "status", "available"):
            assert key in tool
        assert tool["version"] == PROTOCOL_VERSION
        assert tool["backend_kind"] == "MOCK"
        assert tool["real_backend_available"] is False
        assert tool["production_d1_allowed"] is False
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["outputSchema"]["additionalProperties"] is False
        assert tool["errorSchema"]["additionalProperties"] is False
        if tool["status"] == "NOT_IMPLEMENTED":
            assert tool["available"] is False


def test_s4_resources_and_prompts_are_static_and_fail_closed() -> None:
    resources = list_resources()
    prompts = list_prompts()

    assert [item["uri"] for item in resources] == [
        "cad://nextgen/capabilities",
        "cad://nextgen/safety-boundaries",
        "cad://nextgen/tool-registry",
    ]
    assert [item["name"] for item in prompts] == [
        "cad.plan_mock_job",
        "cad.review_safety_boundary",
    ]
    for item in [*resources, *prompts]:
        assert item["version"] == PROTOCOL_VERSION
        assert item["backend_kind"] == "MOCK"
        assert item["real_backend_available"] is False
        assert item["production_allowed"] is False
        assert item["production_d1_allowed"] is False
        assert item["errorSchema"]["additionalProperties"] is False

    capabilities = resource_payload("cad://nextgen/capabilities")
    safety = resource_payload("cad://nextgen/safety-boundaries")
    assert capabilities["control_plane_status"] == "IMPLEMENTED_BASELINE"
    assert capabilities["nextgen_mock_backend_status"] == "IMPLEMENTED_BASELINE"
    assert capabilities["real_backend_status"] == "NOT_IMPLEMENTED"
    assert capabilities["real_backend_available"] is False
    assert safety["allowed_backends"] == ["offline", "nextgen_mock"]
    assert safety["real_cad_access"] is False
    assert "不得连接 CAD" in prompt_message("cad.plan_mock_job")


@pytest.mark.parametrize(
    ("callback", "unknown"),
    [
        (resource_payload, "cad://nextgen/unknown"),
        (prompt_message, "cad.unknown_prompt"),
    ],
)
def test_s4_discovery_rejects_unknown_entries(callback, unknown: str) -> None:
    with pytest.raises(KeyError):
        callback(unknown)
