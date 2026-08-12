"""9-tool Mock-only 控制面 dispatcher。"""

from __future__ import annotations

from datetime import datetime, timezone
import tempfile
from typing import Any

from ..protocol.enums import BackendKind
from ..protocol.version import PROTOCOL_VERSION
from ..schemas.tools import ALL_DISPATCHABLE_TOOLS, NEXTGEN_TOOLS, list_tools
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


#: Injected S7 plugin route service. None (the default) means the AutoCAD plugin backend is
#: not wired in, so the cad.plugin.* tools answer "unavailable" rather than touching CAD.
#: This default is what keeps the standard test suite from ever starting AutoCAD.
_PLUGIN_ROUTE_SERVICE: Any = None


def configure_plugin_route_service(service: Any) -> None:
    """绑定或清除 cad.plugin.* 工具使用的 S7 路由服务；由宿主显式注入，不自行创建真实 backend。"""

    global _PLUGIN_ROUTE_SERVICE
    _PLUGIN_ROUTE_SERVICE = service


def plugin_route_service() -> Any:
    return _PLUGIN_ROUTE_SERVICE


_TIANZHENG_ROUTE_SERVICE: Any = None


def configure_tianzheng_route_service(service: Any) -> None:
    """绑定或清除 cad.tianzheng.* 工具使用的 S8 路由服务；由宿主显式注入。"""

    global _TIANZHENG_ROUTE_SERVICE
    _TIANZHENG_ROUTE_SERVICE = service


def tianzheng_route_service() -> Any:
    return _TIANZHENG_ROUTE_SERVICE


def _dispatch_tianzheng_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Route a ``cad.tianzheng.*`` tool to the S8 native backend.

    This is the ONLY place the Tianzheng backend is reachable from MCP. The payload carries
    structured geometry; there is no command, LISP or socket surface behind it, and a
    Tianzheng-specific failure keeps its own error code rather than becoming INTERNAL_ERROR.
    """
    service = _TIANZHENG_ROUTE_SERVICE
    if service is None:
        return _result(
            payload,
            status="UNAVAILABLE",
            error_code="TIANZHENG_NOT_LOADED",
            data={
                "actual_backend_used": None,
                "real_backend_available": False,
                "message": "Tianzheng native backend is not configured in this process.",
            },
            backend_kind=BackendKind.REAL_PLUGIN.value,
        )

    # Imported lazily so the default dispatcher import never pulls in transport code.
    from mcp_nextgen.s8.tianzheng_route import TianzhengRouteError

    if tool_name == "cad.tianzheng.capabilities":
        try:
            capabilities = service.capability_snapshot()
        except Exception as exc:
            return _result(
                payload, status="UNAVAILABLE", error_code="TIANZHENG_NOT_LOADED",
                data={"actual_backend_used": None, "reason": type(exc).__name__},
                backend_kind=BackendKind.REAL_PLUGIN.value)
        return _result(payload, status="OK",
                       data={"capabilities": capabilities, "actual_backend_used": None},
                       backend_kind=BackendKind.REAL_PLUGIN.value)

    handlers = {
        "cad.tianzheng.create_pipe": service.create_pipe,
        "cad.tianzheng.query_pipe": service.query_pipe,
        "cad.tianzheng.validate_pipe_identity": service.validate_pipe_identity,
    }
    handler = handlers.get(tool_name)
    if handler is None:
        raise ControlPlaneError("UNKNOWN_METHOD", f"未知天正工具: {tool_name!r}")

    try:
        outcome = handler(payload)
    except TianzhengRouteError as exc:
        # Structured Tianzheng failures survive to the caller.
        return _result(
            payload, status="FAILED", error_code=exc.error_code,
            data={"actual_backend_used": None, "details": exc.details},
            backend_kind=BackendKind.REAL_PLUGIN.value)

    return _result(
        payload,
        status=outcome.status,
        data={**outcome.data, "actual_backend_used": outcome.actual_backend_used},
        error_code=outcome.error_code,
        backend_kind=BackendKind.REAL_PLUGIN.value,
    )


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
    backend_kind: str = BackendKind.MOCK.value,
) -> dict[str, Any]:
    return {
        "schema_version": PROTOCOL_VERSION,
        "request_id": payload["request_id"],
        "job_id": payload.get("job_id"),
        "idempotency_key": payload["idempotency_key"],
        "status": status,
        # Honest provenance: only the S7 plugin tools may report REAL_PLUGIN.
        "backend_kind": backend_kind,
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
    tool = ALL_DISPATCHABLE_TOOLS[tool_name]
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


def _dispatch_plugin_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Route a ``cad.plugin.*`` tool through the S7 capability router and backend.

    This is the ONLY place the AutoCAD plugin is reachable from MCP. The payload is a
    validated structured request; no raw plugin frame, command string or document token is
    accepted from, or returned to, the caller.
    """
    service = _PLUGIN_ROUTE_SERVICE
    if service is None:
        # Not wired in: report unavailable honestly rather than pretending or touching CAD.
        return _result(
            payload,
            status="UNAVAILABLE",
            error_code="PLUGIN_BACKEND_NOT_CONFIGURED",
            data={
                "actual_backend_used": None,
                "real_backend_available": False,
                "message": "AutoCAD plugin backend is not configured in this process.",
            },
            backend_kind=BackendKind.REAL_PLUGIN.value,
        )

    # Imported lazily so the default dispatcher import never pulls in transport code.
    from mcp_nextgen.s7.plugin_route import PluginRouteError, build_plan_from_structured_request

    if tool_name == "cad.plugin.capabilities":
        try:
            capabilities = service.capability_snapshot()
        except Exception as exc:
            return _result(
                payload, status="UNAVAILABLE",
                error_code="PLUGIN_UNAVAILABLE",
                data={"actual_backend_used": None, "reason": type(exc).__name__},
                backend_kind=BackendKind.REAL_PLUGIN.value)
        return _result(payload, status="OK",
                       data={"capabilities": capabilities, "actual_backend_used": None},
                       backend_kind=BackendKind.REAL_PLUGIN.value)

    # cad.plugin.execute
    try:
        plan = build_plan_from_structured_request({
            "job_id": payload["job_id"],
            "layer": payload["layer"],
            "entities": payload["entities"],
            "dry_run": payload.get("dry_run", False),
        })
    except PluginRouteError as exc:
        raise ControlPlaneError(exc.error_code, str(exc), details=exc.details) from exc

    try:
        outcome = service.execute(
            plan,
            session_id=payload["session_id"],
            require_atomic_batch=bool(payload.get("require_atomic_batch", True)),
            preferred_backend=payload.get("preferred_backend"),
            idempotency_key=payload["idempotency_key"],
        )
    except Exception as exc:
        return _result(
            payload, status="FAILED",
            error_code=getattr(exc, "error_code", "PLUGIN_EXECUTION_FAILED"),
            data={"actual_backend_used": None, "reason": type(exc).__name__},
                backend_kind=BackendKind.REAL_PLUGIN.value)

    status = {"completed": "COMPLETED", "blocked": "BLOCKED",
              "delegated": "DELEGATED", "failed": "FAILED"}.get(outcome.status, "FAILED")
    return _result(
        payload,
        status=status,
        error_code=(outcome.execution or {}).get("error_code") if status == "FAILED" else None,
        data=outcome.to_dict(),
        backend_kind=BackendKind.REAL_PLUGIN.value,
    )


def dispatch_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """严格验证并分派；只调用 Mock-only 控制面，绝不调用真实 CAD backend。"""

    tool = ALL_DISPATCHABLE_TOOLS.get(tool_name)
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
    # --- S7: AutoCAD plugin backend, dispatched from this same main path ---
    if tool_name in {"cad.plugin.capabilities", "cad.plugin.execute"}:
        return _dispatch_plugin_tool(tool_name, payload)

    # --- S8: Tianzheng native backend, dispatched from this same main path ---
    if tool_name.startswith("cad.tianzheng."):
        return _dispatch_tianzheng_tool(tool_name, payload)

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
