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

_ERROR_OUTPUT = strict_object(
    {
        "code": {"type": "string", "minLength": 1},
        "message": {"type": "string", "minLength": 1},
        "details": {"type": "object"},
    },
    ["code", "message", "details"],
)


def _tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
    *,
    read_only: bool,
    allowed_levels: list[ApprovalLevel],
    status: str = "NOT_IMPLEMENTED",
) -> dict[str, Any]:
    if status not in {"IMPLEMENTED_BASELINE", "PARTIALLY_IMPLEMENTED", "NOT_IMPLEMENTED"}:
        raise ValueError(f"非法工具状态: {status}")
    return {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": deepcopy(_RESULT_OUTPUT),
        "errorSchema": deepcopy(_ERROR_OUTPUT),
        "version": PROTOCOL_VERSION,
        "read_only": read_only,
        "backend_kind": BackendKind.MOCK.value,
        "real_backend_available": False,
        "production_d1_allowed": False,
        "allowed_execution_runtimes": ["offline", "mock"],
        "status": status,
        "available": status == "IMPLEMENTED_BASELINE",
        "allowed_approval_levels": [level.value for level in allowed_levels],
    }


_DOCUMENT_INPUT = {"document": deepcopy(DOCUMENT_IDENTITY_SCHEMA)}
_APPROVAL_INPUT = {"approval_context": deepcopy(APPROVAL_CONTEXT_SCHEMA)}
_CONTROL_APPROVAL_SCHEMA = strict_object(
    {
        "job_id": id_property(),
        "plan_hash": sha_property(),
        "operation": {"type": "string", "minLength": 1, "maxLength": 128},
        "product": {
            "type": "string",
            "enum": ["generic_autocad", "tianzheng_water", "tianzheng_hvac", "offline_analysis"],
        },
        "runtime": {"type": "string", "enum": ["offline", "mock"]},
        "allowed_operations": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 128},
            "minItems": 1,
            "uniqueItems": True,
        },
        "expires_at": {"type": "string", "format": "date-time"},
        "single_use": {"type": "boolean", "const": True},
        "production_allowed": {"type": "boolean", "const": False},
        "production_d1_allowed": {"type": "boolean", "const": False},
    },
    [
        "job_id", "plan_hash", "operation", "product", "runtime", "allowed_operations",
        "expires_at", "single_use", "production_allowed", "production_d1_allowed",
    ],
)

NEXTGEN_TOOLS: dict[str, dict[str, Any]] = {
    "cad.capabilities": _tool(
        "cad.capabilities",
        "查询 NextGen Mock-only 能力与协议版本，不连接真实 CAD。",
        _input(),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
    ),
    "cad.documents.list": _tool(
        "cad.documents.list",
        "列出已注入的 Mock 文档；当前基线默认返回空列表。",
        _input(),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
    ),
    "cad.document.inspect": _tool(
        "cad.document.inspect",
        "校验并回显指定 Mock 文档身份，不访问文件系统。",
        _input(_DOCUMENT_INPUT, ["document"]),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
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
        "生成并保存 Mock-only dry-run 作业计划；不执行 CAD 操作。",
        _input(
            {
                "job_id": id_property(),
                **_DOCUMENT_INPUT,
                "operation": {"type": "string", "enum": ["clone", "transform"]},
                "product": {
                    "type": "string",
                    "enum": ["generic_autocad", "tianzheng_water", "tianzheng_hvac", "offline_analysis"],
                },
                "execution_runtime": {"type": "string", "enum": ["offline", "mock"]},
                "backend": {"type": "string", "enum": ["offline", "nextgen_mock"]},
                "task_ids": {"type": "array", "items": id_property(), "minItems": 1, "uniqueItems": True},
                "dry_run": {"type": "boolean", "const": True},
                "production_allowed": {"type": "boolean", "const": False},
                **_APPROVAL_INPUT,
            },
            [
                "job_id", "document", "operation", "product", "execution_runtime", "backend",
                "task_ids", "dry_run", "production_allowed",
            ],
        ),
        read_only=False,
        allowed_levels=[ApprovalLevel.L1_DRY_RUN, ApprovalLevel.L2_SANDBOX_PREP],
        status="IMPLEMENTED_BASELINE",
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
        "查询由 Mock-only 控制面保存的作业状态与进度。",
        _input({"job_id": id_property()}, ["job_id"]),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
    ),
    "cad.job.approve": _tool(
        "cad.job.approve",
        "将单次、过期受限的 Mock-only 审批绑定到 PLANNED 作业；不执行任务。",
        _input({"job_id": id_property(), "approval": deepcopy(_CONTROL_APPROVAL_SCHEMA)}, ["job_id", "approval"]),
        read_only=False,
        allowed_levels=[ApprovalLevel.L1_DRY_RUN, ApprovalLevel.L2_SANDBOX_PREP],
        status="IMPLEMENTED_BASELINE",
    ),
    "cad.job.run_mock": _tool(
        "cad.job.run_mock",
        "在已审批作业上运行确定性的 Mock 模拟；禁止 CAD、COM 和真实 backend。",
        _input(
            {"job_id": id_property(), "dry_run": {"type": "boolean", "const": True}},
            ["job_id", "dry_run"],
        ),
        read_only=False,
        allowed_levels=[ApprovalLevel.L1_DRY_RUN, ApprovalLevel.L2_SANDBOX_PREP],
        status="IMPLEMENTED_BASELINE",
    ),
    "cad.job.cancel": _tool(
        "cad.job.cancel",
        "取消未终态的 Mock-only 作业；不触发 CAD 回滚或任何文件写图。",
        _input(
            {"job_id": id_property(), "reason": {"type": "string", "minLength": 1, "maxLength": 256}},
            ["job_id"],
        ),
        read_only=False,
        allowed_levels=[ApprovalLevel.L1_DRY_RUN, ApprovalLevel.L2_SANDBOX_PREP],
        status="IMPLEMENTED_BASELINE",
    ),
    "cad.job.events": _tool(
        "cad.job.events",
        "读取 Mock-only 作业的有序进度事件；不订阅外部监听器。",
        _input({"job_id": id_property()}, ["job_id"]),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
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
        "cad.batch.clone", "cad.batch.transform", "cad.job.status", "cad.job.approve",
        "cad.job.run_mock", "cad.job.cancel", "cad.job.events",
    }
    if set(NEXTGEN_TOOLS) != expected:
        raise ValueError("NextGen registry 必须且只能包含 S4 批准工具")
    for name, tool in NEXTGEN_TOOLS.items():
        for required in ("name", "description", "inputSchema", "outputSchema", "errorSchema", "version", "status", "available"):
            if required not in tool:
                raise ValueError(f"{name} 缺少 registry 字段 {required}")
        if tool["name"] != name or tool["version"] != PROTOCOL_VERSION:
            raise ValueError(f"{name} registry identity/version 不一致")
        if tool["backend_kind"] != BackendKind.MOCK.value:
            raise ValueError(f"{name} 不得声明 Real backend")
        if tool["production_d1_allowed"] is not False:
            raise ValueError(f"{name} 不得放行 Production D1")
        if tool["status"] == "NOT_IMPLEMENTED" and tool["available"] is True:
            raise ValueError(f"{name} 未实现时不得标记 AVAILABLE")
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
