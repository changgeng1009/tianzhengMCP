"""9-tool Mock-only 控制面 dispatcher。"""

from __future__ import annotations

from datetime import datetime, timezone
import tempfile
from typing import Any

from ..protocol.enums import BackendKind
from ..protocol.version import PROTOCOL_VERSION
from ..schemas.tools import NEXTGEN_TOOLS, list_tools
from ..schemas.validator import SchemaValidationError, validate_instance
from ..safety.canonical import sha256_hex
from .service import ControlPlaneJobError, ControlPlaneService


_CONTROL_PLANE_SERVICE: ControlPlaneService | None = None
_CONTROL_PLANE_TEMPORARY_ROOT: tempfile.TemporaryDirectory[str] | None = None


class ControlPlaneError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def configure_control_plane_service(service: ControlPlaneService | None) -> None:
    """注入测试或宿主提供的 Mock-only 作业服务；不接受真实 backend。"""

    global _CONTROL_PLANE_SERVICE, _CONTROL_PLANE_TEMPORARY_ROOT
    _CONTROL_PLANE_SERVICE = service
    if service is not None:
        _CONTROL_PLANE_TEMPORARY_ROOT = None


def _control_plane_service() -> ControlPlaneService:
    """延迟创建仅用于当前进程的临时 Mock 作业存储。"""

    global _CONTROL_PLANE_SERVICE, _CONTROL_PLANE_TEMPORARY_ROOT
    if _CONTROL_PLANE_SERVICE is None:
        _CONTROL_PLANE_TEMPORARY_ROOT = tempfile.TemporaryDirectory(prefix="tianzheng-nextgen-s4-")
        _CONTROL_PLANE_SERVICE = ControlPlaneService(_CONTROL_PLANE_TEMPORARY_ROOT.name)
    return _CONTROL_PLANE_SERVICE


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
    """严格验证并分派；只调用 Mock-only 控制面，绝不调用真实 CAD backend。"""

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
                "control_plane_status": "IMPLEMENTED_BASELINE",
                "nextgen_mock_backend_status": "IMPLEMENTED_BASELINE",
                "real_backend_status": "NOT_IMPLEMENTED",
                "real_backend_available": False,
                "production_d1_allowed": False,
                "tool_count": len(NEXTGEN_TOOLS),
                "tools": list_tools(),
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
    if tool_name == "cad.batch.plan":
        plan_material = {
            "schema_version": PROTOCOL_VERSION,
            "job_id": payload["job_id"],
            "document": payload["document"],
            "operation": payload["operation"],
            "product": payload["product"],
            "execution_runtime": payload["execution_runtime"],
            "backend": payload["backend"],
            "task_ids": payload["task_ids"],
            "dry_run": payload["dry_run"],
        }
        tasks = [
            {
                "task_id": task_id,
                "batch_id": f"batch-{payload['job_id']}",
                "operation": payload["operation"],
            }
            for task_id in payload["task_ids"]
        ]
        try:
            job = _control_plane_service().create_job(
                job_id=payload["job_id"],
                request_id=payload["request_id"],
                idempotency_key=payload["idempotency_key"],
                plan_hash=sha256_hex(plan_material),
                operation=payload["operation"],
                product=payload["product"],
                execution_runtime=payload["execution_runtime"],
                backend=payload["backend"],
                document_identity=payload["document"],
                tasks=tasks,
                production_allowed=False,
                production_d1_allowed=False,
            )
        except ControlPlaneJobError as exc:
            raise ControlPlaneError(exc.code, str(exc)) from exc
        return _result(
            payload,
            status=job.status.value,
            data={"job": job.to_dict(), "mock_only": True, "file_access_performed": False},
        )
    if tool_name == "cad.job.status":
        try:
            status = _control_plane_service().status(payload["job_id"])
        except ControlPlaneJobError as exc:
            raise ControlPlaneError(exc.code, str(exc)) from exc
        return _result(
            payload,
            status="OK",
            data={"job": status, "mock_only": True, "file_access_performed": False},
        )
    if tool_name == "cad.job.approve":
        approval = payload["approval"]
        if approval["job_id"] != payload["job_id"]:
            raise ControlPlaneError("APPROVAL_JOB_MISMATCH", "审批 job_id 与请求不一致")
        try:
            job = _control_plane_service().approve(payload["job_id"], approval)
        except ControlPlaneJobError as exc:
            raise ControlPlaneError(exc.code, str(exc)) from exc
        return _result(
            payload,
            status=job.status.value,
            data={"job": job.to_dict(), "mock_only": True, "file_access_performed": False},
        )
    if tool_name == "cad.job.run_mock":
        try:
            job = _control_plane_service().run(payload["job_id"])
        except ControlPlaneJobError as exc:
            raise ControlPlaneError(exc.code, str(exc)) from exc
        return _result(
            payload,
            status=job.status.value,
            data={"job": job.to_dict(), "mock_only": True, "file_access_performed": False},
        )
    if tool_name == "cad.job.cancel":
        try:
            job = _control_plane_service().cancel(payload["job_id"], reason=payload.get("reason", "CANCELLED_BY_REQUEST"))
        except ControlPlaneJobError as exc:
            raise ControlPlaneError(exc.code, str(exc)) from exc
        return _result(
            payload,
            status=job.status.value,
            data={"job": job.to_dict(), "mock_only": True, "file_access_performed": False},
        )
    if tool_name == "cad.job.events":
        try:
            events = [item.to_dict() for item in _control_plane_service().progress_events(payload["job_id"])]
        except ControlPlaneJobError as exc:
            raise ControlPlaneError(exc.code, str(exc)) from exc
        return _result(
            payload,
            status="OK",
            data={"events": events, "mock_only": True, "file_access_performed": False},
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
