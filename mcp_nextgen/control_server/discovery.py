"""NextGen MCP 发现合同（tools/resources/prompts）。

本模块仅返回静态、版本化的描述数据，不能启动监听器、读取 CAD 文件或连接任何
CAD 产品。它使 MCP 客户端在调用前能够识别 Mock-only 控制面的真实边界。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..protocol.enums import BackendKind
from ..protocol.version import PROTOCOL_VERSION
from ..schemas.tools import NEXTGEN_TOOLS, list_tools

_EMPTY_INPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}

_DISCOVERY_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"schema_version": {"type": "string", "const": PROTOCOL_VERSION}},
    "required": ["schema_version"],
    "additionalProperties": True,
}

_ERROR_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "code": {"type": "string", "minLength": 1},
        "message": {"type": "string", "minLength": 1},
        "details": {"type": "object"},
    },
    "required": ["code", "message", "details"],
    "additionalProperties": False,
}


def _entry(name: str, description: str, uri: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "uri": uri,
        "version": PROTOCOL_VERSION,
        "inputSchema": deepcopy(_EMPTY_INPUT_SCHEMA),
        "outputSchema": deepcopy(_DISCOVERY_OUTPUT_SCHEMA),
        "errorSchema": deepcopy(_ERROR_SCHEMA),
        "backend_kind": BackendKind.MOCK.value,
        "real_backend_available": False,
        "production_allowed": False,
        "production_d1_allowed": False,
    }


NEXTGEN_RESOURCES: dict[str, dict[str, Any]] = {
    "cad://nextgen/capabilities": _entry(
        "cad.capabilities.resource",
        "读取 NextGen Mock-only 能力边界；不调用 CAD backend。",
        "cad://nextgen/capabilities",
    ),
    "cad://nextgen/tool-registry": _entry(
        "cad.tool_registry.resource",
        "读取所有已注册工具及其真实支持等级。",
        "cad://nextgen/tool-registry",
    ),
    "cad://nextgen/safety-boundaries": _entry(
        "cad.safety_boundaries.resource",
        "读取固定安全边界：仅 offline/nextgen_mock，禁止真实 CAD。",
        "cad://nextgen/safety-boundaries",
    ),
}

NEXTGEN_PROMPTS: dict[str, dict[str, Any]] = {
    "cad.plan_mock_job": {
        "name": "cad.plan_mock_job",
        "description": "生成 Mock-only 作业规划提示，不授权执行或提升审批。",
        "version": PROTOCOL_VERSION,
        "argumentsSchema": deepcopy(_EMPTY_INPUT_SCHEMA),
        "errorSchema": deepcopy(_ERROR_SCHEMA),
        "backend_kind": BackendKind.MOCK.value,
        "real_backend_available": False,
        "production_allowed": False,
        "production_d1_allowed": False,
    },
    "cad.review_safety_boundary": {
        "name": "cad.review_safety_boundary",
        "description": "生成 Mock-only 控制面安全复核提示。",
        "version": PROTOCOL_VERSION,
        "argumentsSchema": deepcopy(_EMPTY_INPUT_SCHEMA),
        "errorSchema": deepcopy(_ERROR_SCHEMA),
        "backend_kind": BackendKind.MOCK.value,
        "real_backend_available": False,
        "production_allowed": False,
        "production_d1_allowed": False,
    },
}


def list_resources() -> list[dict[str, Any]]:
    """按 URI 返回不可变的资源描述副本。"""

    return [deepcopy(NEXTGEN_RESOURCES[uri]) for uri in sorted(NEXTGEN_RESOURCES)]


def list_prompts() -> list[dict[str, Any]]:
    """按名称返回不可变的提示描述副本。"""

    return [deepcopy(NEXTGEN_PROMPTS[name]) for name in sorted(NEXTGEN_PROMPTS)]


def resource_payload(uri: str) -> dict[str, Any]:
    """返回指定资源的纯数据载荷；未知 URI 由调用方转为协议错误。"""

    if uri == "cad://nextgen/capabilities":
        return {
            "schema_version": PROTOCOL_VERSION,
            "backend_kind": BackendKind.MOCK.value,
            "control_plane_status": "IMPLEMENTED_BASELINE",
            "nextgen_mock_backend_status": "IMPLEMENTED_BASELINE",
            "real_backend_status": "NOT_IMPLEMENTED",
            "real_backend_available": False,
            "production_allowed": False,
            "production_d1_allowed": False,
            "tools": list_tools(),
        }
    if uri == "cad://nextgen/tool-registry":
        return {"schema_version": PROTOCOL_VERSION, "tools": list_tools()}
    if uri == "cad://nextgen/safety-boundaries":
        return {
            "schema_version": PROTOCOL_VERSION,
            "allowed_backends": ["offline", "nextgen_mock"],
            "forbidden_backends": ["legacy_com", "nextgen_real", "autocad_dotnet_plugin"],
            "real_cad_access": False,
            "production_allowed": False,
            "production_d1_allowed": False,
        }
    raise KeyError(uri)


def prompt_message(name: str) -> str:
    """提供不会触发执行的固定安全提示。"""

    if name == "cad.plan_mock_job":
        return "仅生成 offline 或 nextgen_mock 计划；不得连接 CAD、读取 DWG 或提升审批。"
    if name == "cad.review_safety_boundary":
        return "确认 production_allowed=false、real_cad_access=false，且所有后端均为 Mock-only。"
    raise KeyError(name)


def self_check_discovery() -> dict[str, Any]:
    """验证发现层未把未实现能力标成可用。"""

    for tool in NEXTGEN_TOOLS.values():
        for field in ("name", "description", "inputSchema", "outputSchema", "errorSchema", "status"):
            if field not in tool:
                raise ValueError(f"工具缺少发现字段: {field}")
        if tool["status"] == "NOT_IMPLEMENTED" and tool["available"] is True:
            raise ValueError(f"未实现工具不得声明 available=true: {tool['name']}")
    return {
        "schema_version": PROTOCOL_VERSION,
        "tool_count": len(NEXTGEN_TOOLS),
        "resource_count": len(NEXTGEN_RESOURCES),
        "prompt_count": len(NEXTGEN_PROMPTS),
        "backend_kind": BackendKind.MOCK.value,
        "real_backend_available": False,
    }
