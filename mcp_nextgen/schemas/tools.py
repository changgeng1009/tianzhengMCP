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
        # MOCK for every control-plane tool. REAL_PLUGIN only for the S7 cad.plugin.* tools,
        # so a result can never claim Mock provenance for work the AutoCAD plugin performed.
        "backend_kind": {"type": "string", "enum": [BackendKind.MOCK.value, BackendKind.REAL_PLUGIN.value]},
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
    backend_kind: str = BackendKind.MOCK.value,
    real_backend_available: bool = False,
    allowed_execution_runtimes: list[str] | None = None,
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
        "backend_kind": backend_kind,
        "real_backend_available": real_backend_available,
        "production_d1_allowed": False,
        "allowed_execution_runtimes": allowed_execution_runtimes or ["offline", "mock"],
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



#: S7 plugin tools live in their OWN registry, deliberately NOT in NEXTGEN_TOOLS.
#:
#: NEXTGEN_TOOLS is the S4 Mock-only baseline whose exact membership is contractual —
#: existing S4 tests assert that every registered tool is Mock-backed. Adding a real
#: backend there would silently break that guarantee. Keeping them separate preserves the
#: S4 invariant while `dispatch_tool` still serves both from the one MCP entry point.
S7_PLUGIN_TOOLS: dict[str, dict[str, Any]] = {
    # These are the only registered tools whose backend_kind is not MOCK. They accept a
    # STRUCTURED request only: there is no raw-protocol, command-string or passthrough
    # field, so the plugin wire protocol stays an implementation detail of the backend.
    "cad.plugin.capabilities": _tool(
        "cad.plugin.capabilities",
        "读取 AutoCAD 插件后端的运行期能力；插件未接入时安全返回 unavailable。",
        _input(),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
        backend_kind=BackendKind.REAL_PLUGIN.value,
        real_backend_available=True,
        allowed_execution_runtimes=["offline", "mock", "real_plugin"],
    ),
    "cad.plugin.execute": _tool(
        "cad.plugin.execute",
        "在 job-owned synthetic 文档中执行结构化 S6 计划；经 Capability Router 选择后端。",
        _input(
            {
                "job_id": id_property(),
                "layer": {"type": "string", "minLength": 1, "maxLength": 64},
                "entities": {
                    "type": "array", "minItems": 1, "maxItems": 256,
                    "items": {"type": "object"},
                },
                "session_id": {"type": "string", "minLength": 1},
                "dry_run": {"type": "boolean"},
                "require_atomic_batch": {"type": "boolean"},
                "preferred_backend": {"type": ["string", "null"]},
            },
            ["job_id", "layer", "entities", "session_id"],
        ),
        read_only=False,
        allowed_levels=[ApprovalLevel.L1_DRY_RUN, ApprovalLevel.L3_SANDBOX_WRITE],
        status="IMPLEMENTED_BASELINE",
        backend_kind=BackendKind.REAL_PLUGIN.value,
        real_backend_available=True,
        allowed_execution_runtimes=["offline", "mock", "real_plugin"],
    ),
}


S8_TIANZHENG_TOOLS: dict[str, dict[str, Any]] = {
    # Structured pipe parameters only. There is deliberately no command, command_text, lisp
    # or passthrough field anywhere in these schemas, and the schemas are strict, so an
    # attempt to smuggle one is rejected before dispatch.
    "cad.tianzheng.capabilities": _tool(
        "cad.tianzheng.capabilities",
        "读取天正原生后端的运行期能力；天正未加载时如实返回 NOT_AVAILABLE。",
        _input(),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
        backend_kind=BackendKind.REAL_PLUGIN.value,
        real_backend_available=True,
        allowed_execution_runtimes=["offline", "mock", "real_plugin"],
    ),
    "cad.tianzheng.create_pipe": _tool(
        "cad.tianzheng.create_pipe",
        "在 job-owned synthetic 文档中创建一根天正原生 TDbPipe；仅接受结构化几何参数。",
        _input(
            {
                "job_id": id_property(),
                "document_token": {"type": "string", "minLength": 1},
                "start": {"type": "array", "minItems": 2, "maxItems": 3,
                          "items": {"type": "number"}},
                "end": {"type": "array", "minItems": 2, "maxItems": 3,
                        "items": {"type": "number"}},
                "operation_id": {"type": ["string", "null"]},
            },
            ["job_id", "document_token", "start", "end"],
        ),
        read_only=False,
        allowed_levels=[ApprovalLevel.L1_DRY_RUN, ApprovalLevel.L3_SANDBOX_WRITE],
        status="IMPLEMENTED_BASELINE",
        backend_kind=BackendKind.REAL_PLUGIN.value,
        real_backend_available=True,
        allowed_execution_runtimes=["offline", "mock", "real_plugin"],
    ),
    "cad.tianzheng.query_pipe": _tool(
        "cad.tianzheng.query_pipe",
        "按 handle 查询天正原生管道快照；不返回 DBObject 或 native 指针。",
        _input(
            {
                "job_id": id_property(),
                "document_token": {"type": "string", "minLength": 1},
                "handle": {"type": "string", "minLength": 1, "maxLength": 32},
                "related_handles": {"type": "array", "maxItems": 64,
                                    "items": {"type": "string", "maxLength": 32}},
            },
            ["job_id", "document_token", "handle"],
        ),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
        backend_kind=BackendKind.REAL_PLUGIN.value,
        real_backend_available=True,
        allowed_execution_runtimes=["offline", "mock", "real_plugin"],
    ),
    "cad.tianzheng.validate_pipe_identity": _tool(
        "cad.tianzheng.validate_pipe_identity",
        "重新读取对象并确认其仍为活的原生 TDbPipe；Proxy 一律判定为不通过。",
        _input(
            {
                "job_id": id_property(),
                "document_token": {"type": "string", "minLength": 1},
                "handle": {"type": "string", "minLength": 1, "maxLength": 32},
            },
            ["job_id", "document_token", "handle"],
        ),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
        backend_kind=BackendKind.REAL_PLUGIN.value,
        real_backend_available=True,
        allowed_execution_runtimes=["offline", "mock", "real_plugin"],
    ),
}


_ENGINEERING_TASK_INPUT = {
    "task_id": id_property(),
    "intent": {"type": "string", "maxLength": 512},
    "start": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "number"}},
    "end": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "number"}},
    "include_valve_intent": {"type": "boolean"},
}

S9_ENGINEERING_TOOLS: dict[str, dict[str, Any]] = {
    # Planning and validation are pure: they touch no CAD. Execution is deliberately NOT a
    # tool - the executor is a client of cad.tianzheng.*, so exposing it here would make the
    # dispatcher re-enter itself. A caller supplies a task descriptor, never an operation
    # list, so the planner's capability gate cannot be bypassed.
    "cad.engineering.plan": _tool(
        "cad.engineering.plan",
        "把结构化工程任务转换为 EngineeringOperationPlan 并附带 Dry Run；不接触 CAD。",
        _input(_ENGINEERING_TASK_INPUT),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
    ),
    "cad.engineering.validate_plan": _tool(
        "cad.engineering.validate_plan",
        "对工程任务计划执行确定性校验：能力、几何、安全、依赖与幂等；不接触 CAD。",
        _input(_ENGINEERING_TASK_INPUT),
        read_only=True,
        allowed_levels=[ApprovalLevel.L0_READ_ONLY],
        status="IMPLEMENTED_BASELINE",
    ),
}


#: Everything dispatch_tool can serve: the S4 Mock baseline, the S7 plugin tools, the
#: S8 Tianzheng tools and the S9 engineering task tools. NEXTGEN_TOOLS itself stays
#: Mock-only, which its self-check enforces.
ALL_DISPATCHABLE_TOOLS: dict[str, dict[str, Any]] = {
    **NEXTGEN_TOOLS, **S7_PLUGIN_TOOLS, **S8_TIANZHENG_TOOLS, **S9_ENGINEERING_TOOLS}

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
