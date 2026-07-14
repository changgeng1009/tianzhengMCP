"""NextGen 9 个工具的严格版本化 registry。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..protocol.enums import ApprovalLevel, BackendKind
from ..protocol.version import PROTOCOL_VERSION
from .core import (
    APPROVAL_CONTEXT_SCHEMA,
    DOCUMENT_IDENTITY_SCHEMA,
    EVIDENCE_PATHS,
    id_property,
    sha_property,
    strict_object,
    version_property,
)

_COMMON_INPUT = {
    "schema_version": version_property(),
    "request_id": id_property(),
    "idempotency_key": id_property(),
}
_COMMON_REQUIRED = ["schema_version", "request_id", "idempotency_key"]


def _input(extra: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    properties = deepcopy(_COMMON_INPUT)
    properties.update(deepcopy(extra or {}))
    return strict_object(properties, [*_COMMON_REQUIRED, *(required or [])])


_RESULT_OUTPUT = strict_object(
    {
        "schema_version": version_property(),
        "request_id": id_property(),
        "job_id": {"type": ["string", "null"]},
        "idempotency_key": id_property(),
        "status": {"type": "string", "minLength": 1},
        "backend_kind": {"type": "string", "const": BackendKind.MOCK.value},
        "production_allowed": {"type": "boolean", "const": False},
        "production_d1_allowed": {"type": "boolean", "const": False},
        "dry_run": {"type": "boolean"},
        "error_code": {"type": ["string", "null"]},
        "data": {"type": "object"},
        "evidence_paths": deepcopy(EVIDENCE_PATHS),
    },
    [
        "schema_version", "request_id", "job_id", "idempotency_key", "status",
        "backend_kind", "production_allowed", "production_d1_allowed", "dry_run",
        "error_code", "data", "evidence_paths",
    ],
)


def _tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
    *,
    read_only: bool,
    allowed_levels: list[ApprovalLevel],
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": deepcopy(_RESULT_OUTPUT),
        "version": PROTOCOL_VERSION,
        "read_only": read_only,
        "backend_kind": BackendKind.MOCK.value,
        "real_backend_available": False,
        "production_d1_allowed": False,
        "allowed_approval_levels": [level.value for level in allowed_levels],
    }


_DOCUMENT_INPUT = {"document": deepcopy(DOCUMENT_IDENTITY_SCHEMA)}
_APPROVAL_INPUT = {"approval_context": deepcopy(APPROVAL_CONTEXT_SCHEMA)}

NEXTGEN_TOOLS: dict[str, dict[str, Any]] = {
    "cad.capabilities": _tool(
        "cad.capabilities",
        "查询 NextGen Mock-only 能力与协议版本，不连接真实 CAD。",
        _input(),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
    ),
    "cad.documents.list": _tool(
        "cad.documents.list",
        "列出已注入的 Mock 文档；当前基线默认返回空列表。",
        _input(),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
    ),
    "cad.document.inspect": _tool(
        "cad.document.inspect",
        "校验并回显指定 Mock 文档身份，不访问文件系统。",
        _input(_DOCUMENT_INPUT, ["document"]),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
    ),
    "cad.entities.query": _tool(
        "cad.entities.query",
        "查询 Mock entity；未接 backend 时安全返回未实现。",
        _input(
            {
                **_DOCUMENT_INPUT,
                "filters": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            ["document", "filters", "limit"],
        ),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
    ),
    "cad.entities.inspect": _tool(
        "cad.entities.inspect",
        "读取指定 Mock entity 摘要；未接 backend 时安全返回未实现。",
        _input(
            {
                **_DOCUMENT_INPUT,
                "entity_ids": {
                    "type": "array", "items": id_property(), "minItems": 1,
                    "maxItems": 100, "uniqueItems": True,
                },
            },
            ["document", "entity_ids"],
        ),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
    ),
    "cad.batch.plan": _tool(
        "cad.batch.plan",
        "生成 Mock-only dry-run 计划合同；当前不实现 job planner。",
        _input(
            {
                "job_id": id_property(),
                **_DOCUMENT_INPUT,
                "operation": {"type": "string", "enum": ["clone", "transform"]},
                "task_ids": {"type": "array", "items": id_property(), "minItems": 1, "uniqueItems": True},
                "dry_run": {"type": "boolean", "const": True},
                "production_allowed": {"type": "boolean", "const": False},
                **_APPROVAL_INPUT,
            },
            ["job_id", "document", "operation", "task_ids", "dry_run", "production_allowed", "approval_context"],
        ),
        read_only=False,
        allowed_levels=[ApprovalLevel.L1_DRY_RUN, ApprovalLevel.L2_SANDBOX_PREP],
    ),
    "cad.batch.clone": _tool(
        "cad.batch.clone",
        "Mock-only 克隆合同占位；当前始终阻止真实执行。",
        _input(
            {
                "job_id": id_property(),
                **_DOCUMENT_INPUT,
                "operation": {"type": "string", "const": "clone"},
                "plan_hash": sha_property(),
                "task_ids": {"type": "array", "items": id_property(), "minItems": 1, "uniqueItems": True},
                "dry_run": {"type": "boolean", "const": True},
                "production_allowed": {"type": "boolean", "const": False},
                **_APPROVAL_INPUT,
            },
            [
                "job_id", "document", "operation", "plan_hash", "task_ids",
                "dry_run", "production_allowed", "approval_context",
            ],
        ),
        read_only=False,
        allowed_levels=[ApprovalLevel.L1_DRY_RUN, ApprovalLevel.L2_SANDBOX_PREP],
    ),
    "cad.batch.transform": _tool(
        "cad.batch.transform",
        "Mock-only 变换合同占位；当前始终阻止真实执行。",
        _input(
            {
                "job_id": id_property(),
                **_DOCUMENT_INPUT,
                "operation": {"type": "string", "const": "transform"},
                "plan_hash": sha_property(),
                "task_ids": {"type": "array", "items": id_property(), "minItems": 1, "uniqueItems": True},
                "transform": strict_object(
                    {
                        "type": {"type": "string", "enum": ["move", "rotate", "scale"]},
                        "parameters": {"type": "object"},
                    },
                    ["type", "parameters"],
                ),
                "dry_run": {"type": "boolean", "const": True},
                "production_allowed": {"type": "boolean", "const": False},
                **_APPROVAL_INPUT,
            },
            [
                "job_id", "document", "operation", "plan_hash", "task_ids", "transform",
                "dry_run", "production_allowed", "approval_context",
            ],
        ),
        read_only=False,
        allowed_levels=[ApprovalLevel.L1_DRY_RUN, ApprovalLevel.L2_SANDBOX_PREP],
    ),
    "cad.job.status": _tool(
        "cad.job.status",
        "查询 Mock job 状态；当前未实现 job store。",
        _input({"job_id": id_property()}, ["job_id"]),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
    ),
}


def get_tool(name: str) -> dict[str, Any] | None:
    tool = NEXTGEN_TOOLS.get(name)
    return deepcopy(tool) if tool else None


def list_tools() -> list[dict[str, Any]]:
    return [deepcopy(NEXTGEN_TOOLS[name]) for name in sorted(NEXTGEN_TOOLS)]


def self_check_registry() -> dict[str, Any]:
    expected = {
        "cad.capabilities", "cad.documents.list", "cad.document.inspect",
        "cad.entities.query", "cad.entities.inspect", "cad.batch.plan",
        "cad.batch.clone", "cad.batch.transform", "cad.job.status",
    }
    if set(NEXTGEN_TOOLS) != expected:
        raise ValueError("NextGen registry 必须且只能包含 9 个批准工具")
    for name, tool in NEXTGEN_TOOLS.items():
        for required in ("name", "description", "inputSchema", "outputSchema", "version"):
            if required not in tool:
                raise ValueError(f"{name} 缺少 registry 字段 {required}")
        if tool["name"] != name or tool["version"] != PROTOCOL_VERSION:
            raise ValueError(f"{name} registry identity/version 不一致")
        if tool["backend_kind"] != BackendKind.MOCK.value:
            raise ValueError(f"{name} 不得声明 Real backend")
        if tool["production_d1_allowed"] is not False:
            raise ValueError(f"{name} 不得放行 Production D1")
        if tool["inputSchema"].get("additionalProperties") is not False:
            raise ValueError(f"{name} inputSchema 必须拒绝额外字段")
        if tool["outputSchema"].get("additionalProperties") is not False:
            raise ValueError(f"{name} outputSchema 必须拒绝额外字段")
    return {
        "schema_version": PROTOCOL_VERSION,
        "tool_count": len(NEXTGEN_TOOLS),
        "tools": sorted(NEXTGEN_TOOLS),
        "backend_kind": BackendKind.MOCK.value,
        "production_d1_allowed": False,
    }
