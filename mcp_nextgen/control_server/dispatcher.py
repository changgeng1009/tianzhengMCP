"""9-tool Mock-only 控制面 dispatcher。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..protocol.enums import BackendKind
from ..protocol.version import PROTOCOL_VERSION
from ..schemas.tools import NEXTGEN_TOOLS
from ..schemas.validator import SchemaValidationError, validate_instance


class ControlPlaneError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _result(
    payload: dict[str, Any],
    *,
    status: str,
    data: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PROTOCOL_VERSION,
        "request_id": payload["request_id"],
        "job_id": payload.get("job_id"),
        "idempotency_key": payload["idempotency_key"],
        "status": status,
        "backend_kind": BackendKind.MOCK.value,
        "production_allowed": False,
        "production_d1_allowed": False,
        "dry_run": bool(payload.get("dry_run", True)),
        "error_code": error_code,
        "data": data or {},
        "evidence_paths": [],
    }


def _validate_approval(tool_name: str, payload: dict[str, Any]) -> None:
    approval = payload.get("approval_context")
    if approval is None:
        return
    tool = NEXTGEN_TOOLS[tool_name]
    if approval["approval_level"] not in tool["allowed_approval_levels"]:
        raise ControlPlaneError("APPROVAL_LEVEL_REJECTED", "审批等级不允许调用该工具")
    if approval["request_id"] != payload["request_id"]:
        raise ControlPlaneError("APPROVAL_REQUEST_MISMATCH", "审批 request_id 不匹配")
    if approval["job_id"] != payload.get("job_id"):
        raise ControlPlaneError("APPROVAL_JOB_MISMATCH", "审批 job_id 不匹配")
    if approval["document"] != payload.get("document"):
        raise ControlPlaneError("APPROVAL_DOCUMENT_MISMATCH", "审批文档身份不匹配")
    if payload.get("plan_hash") and approval["plan_hash"] != payload["plan_hash"]:
        raise ControlPlaneError("APPROVAL_PLAN_MISMATCH", "审批 plan_hash 不匹配")
    if payload.get("operation") not in approval["allowed_operations"]:
        raise ControlPlaneError("APPROVAL_OPERATION_REJECTED", "审批未允许该 operation")
    if approval["single_use"] is not True or approval.get("used_at") is not None:
        raise ControlPlaneError("APPROVAL_ALREADY_USED", "审批必须是尚未使用的 single-use 授权")
    if approval["production_allowed"] or approval["production_d1_allowed"]:
        raise ControlPlaneError("PRODUCTION_D1_BLOCKED", "当前基线禁止生产授权")
    expires_at = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) >= expires_at:
        raise ControlPlaneError("APPROVAL_EXPIRED", "审批已过期")


def dispatch_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """严格验证并分派；当前不会调用 job/backend/文件系统。"""

    tool = NEXTGEN_TOOLS.get(tool_name)
    if tool is None:
        raise ControlPlaneError("UNKNOWN_METHOD", f"未知 NextGen 工具: {tool_name!r}")
    try:
        validate_instance(payload, tool["inputSchema"])
    except SchemaValidationError as exc:
        raise ControlPlaneError("INVALID_PARAMS", str(exc), details={"errors": exc.errors}) from exc
    _validate_approval(tool_name, payload)

    if tool_name == "cad.capabilities":
        return _result(
            payload,
            status="OK",
            data={
                "protocol_version": PROTOCOL_VERSION,
                "backend_kind": BackendKind.MOCK.value,
                "real_backend_available": False,
                "production_d1_allowed": False,
                "tools": sorted(NEXTGEN_TOOLS),
            },
        )
    if tool_name == "cad.documents.list":
        return _result(payload, status="OK", data={"documents": [], "mock_only": True})
    if tool_name == "cad.document.inspect":
        return _result(
            payload,
            status="OK",
            data={"document": payload["document"], "file_access_performed": False},
        )

    return _result(
        payload,
        status="NOT_IMPLEMENTED",
        error_code="MOCK_BACKEND_NOT_IMPLEMENTED",
        data={
            "mock_only": True,
            "real_backend_available": False,
            "message": "本阶段仅建立协议/控制面基线，尚未实现 jobs、journal 或 backend。",
        },
    )
