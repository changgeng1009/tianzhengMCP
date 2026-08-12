"""MCP route for the Tianzheng native backend.

    MCP -> Control Plane -> Capability Router -> TianzhengBackend
        -> S7 plugin transport -> Tianzheng pipe adapter

There is no second MCP server and no second protocol. MCP callers never reach a socket, a
command name, LISP or SendCommand: they submit structured pipe parameters and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from mcp_nextgen.s8.persistence import (
    IDEMPOTENCY_CONFLICT,
    NATIVE_IDENTITY_MISMATCH,
    PERSISTENCE_FAILED,
    PIPE_NOT_FOUND,
    PROPERTY_UNAVAILABLE,
)
from mcp_nextgen.s8.tianzheng_backend import (
    TianzhengBackend,
    TianzhengBackendError,
    TianzhengPipeSpec,
)

#: Capability status vocabulary already used by the project.
AVAILABLE_SANDBOX_MVP = "AVAILABLE_SANDBOX_MVP"
NOT_AVAILABLE = "NOT_AVAILABLE"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"

#: Precise capability statement. "TianzhengBackend is available" must never be read as
#: "Tianzheng water-supply-and-drainage is available" — hence the per-feature breakdown,
#: including the things that are explicitly NOT there.
TIANZHENG_CAPABILITY_REGISTRY: dict[str, str] = {
    "tianzheng_backend": AVAILABLE_SANDBOX_MVP,
    "tianzheng_native_pipe_create": AVAILABLE_SANDBOX_MVP,
    "tianzheng_native_pipe_query": AVAILABLE_SANDBOX_MVP,
    "tianzheng_native_pipe_identity_validation": AVAILABLE_SANDBOX_MVP,
    "tianzheng_native_pipe_persistence": AVAILABLE_SANDBOX_MVP,
    "tianzheng_native_pipe_idempotency": AVAILABLE_SANDBOX_MVP,
    "tianzheng_pipe_geometry_read": AVAILABLE_SANDBOX_MVP,
    # The native getters have no managed wrapper; nothing reliable can be claimed.
    "tianzheng_pipe_diameter_read": NOT_AVAILABLE,
    "tianzheng_pipe_system_read": NOT_AVAILABLE,
    # HZGX takes these from Tianzheng's own palette defaults. The API does not control them,
    # so it must not advertise that it does.
    "tianzheng_pipe_diameter_control": NOT_AVAILABLE,
    "tianzheng_pipe_system_control": NOT_AVAILABLE,
    "tianzheng_valve": NOT_IMPLEMENTED,
    "tianzheng_fitting_creation": NOT_IMPLEMENTED,
    "tianzheng_equipment": NOT_IMPLEMENTED,
    "tianzheng_annotation": NOT_IMPLEMENTED,
    "user_dwg_tianzheng_edit": NOT_AVAILABLE,
    "production_tianzheng_write": NOT_AVAILABLE,
}

#: Plugin/backend error code -> MCP error code. Nothing collapses into INTERNAL_ERROR.
TIANZHENG_ERROR_MAP: dict[str, str] = {
    "TIANZHENG_NOT_LOADED": "TIANZHENG_NOT_LOADED",
    "TIANZHENG_NATIVE_CLASS_NOT_FOUND": "TIANZHENG_NATIVE_CLASS_NOT_FOUND",
    "TIANZHENG_PIPE_CREATE_FAILED": "TIANZHENG_PIPE_CREATE_FAILED",
    PIPE_NOT_FOUND: PIPE_NOT_FOUND,
    NATIVE_IDENTITY_MISMATCH: NATIVE_IDENTITY_MISMATCH,
    PROPERTY_UNAVAILABLE: PROPERTY_UNAVAILABLE,
    PERSISTENCE_FAILED: PERSISTENCE_FAILED,
    IDEMPOTENCY_CONFLICT: IDEMPOTENCY_CONFLICT,
    "TIANZHENG_PIPE_SAVE_FAILED": "TIANZHENG_PIPE_SAVE_FAILED",
    "TIANZHENG_PIPE_REOPEN_FAILED": "TIANZHENG_PIPE_REOPEN_FAILED",
}

#: Backend name used by the capability router.
TIANZHENG_BACKEND = "tianzheng_native_backend"


def map_error_code(code: str) -> str:
    """Preserve the structured code. Unknown codes stay visible instead of being flattened."""
    return TIANZHENG_ERROR_MAP.get(code, code or "TIANZHENG_PIPE_CREATE_FAILED")


@dataclass(frozen=True)
class TianzhengRouteResult:
    status: str
    data: dict[str, Any]
    error_code: str | None = None
    actual_backend_used: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "data": self.data,
            "error_code": self.error_code,
            "actual_backend_used": self.actual_backend_used,
        }


class TianzhengRouteError(RuntimeError):
    def __init__(self, error_code: str, message: str, *, details: Mapping[str, Any] | None = None):
        super().__init__(f"{error_code}: {message}")
        self.error_code = map_error_code(error_code)
        self.details = dict(details or {})


class S8TianzhengRouteService:
    """MCP-facing service. Owns capability reporting and delegates work to TianzhengBackend."""

    def __init__(self, backend: TianzhengBackend | None, *, handshake: Mapping[str, Any] | None = None):
        self._backend = backend
        self._handshake = dict(handshake or {})

    # ----------------------------------------------------------------- capability

    def capability_snapshot(self) -> dict[str, Any]:
        """Report capability honestly, including when nothing is wired in."""
        if self._backend is None:
            return {
                "tianzheng_backend_configured": False,
                "tianzheng_loaded": False,
                "capabilities": dict(TIANZHENG_CAPABILITY_REGISTRY,
                                     tianzheng_backend=NOT_AVAILABLE),
                "supported_operations": [],
                "arbitrary_command_available": False,
            }

        handshake = self._handshake
        loaded = bool(handshake.get("tianzheng_loaded"))
        capabilities = dict(TIANZHENG_CAPABILITY_REGISTRY)
        if not loaded:
            # Without a live Tianzheng runtime nothing native is available, whatever the
            # backend object claims about itself.
            for name in list(capabilities):
                if capabilities[name] == AVAILABLE_SANDBOX_MVP:
                    capabilities[name] = NOT_AVAILABLE

        return {
            "tianzheng_backend_configured": True,
            "tianzheng_loaded": loaded,
            "tianzheng_product": handshake.get("tianzheng_product", ""),
            "tianzheng_version": handshake.get("tianzheng_version", ""),
            "tianzheng_runtime_available": bool(handshake.get("tianzheng_runtime_available")),
            "tdbpipe_rxclass_available": bool(handshake.get("tdbpipe_rxclass_available")),
            "supported_tianzheng_operations": list(
                handshake.get("supported_tianzheng_operations") or []),
            "capabilities": capabilities,
            "backend_capabilities": list(self._backend.capabilities),
            # Stated explicitly so nobody has to infer it from an absence.
            "arbitrary_command_available": False,
            "diameter_control": NOT_AVAILABLE,
            "system_control": NOT_AVAILABLE,
        }

    def set_handshake(self, handshake: Mapping[str, Any]) -> None:
        self._handshake = dict(handshake)

    # ----------------------------------------------------------------- operations

    def _require_backend(self) -> TianzhengBackend:
        if self._backend is None:
            raise TianzhengRouteError(
                "TIANZHENG_NOT_LOADED", "no Tianzheng backend is configured in this process")
        if self._handshake and not self._handshake.get("tianzheng_loaded", True):
            raise TianzhengRouteError(
                "TIANZHENG_NOT_LOADED",
                "this AutoCAD session has no Tianzheng runtime; refusing to create anything")
        return self._backend

    def create_pipe(self, payload: Mapping[str, Any]) -> TianzhengRouteResult:
        backend = self._require_backend()
        spec = TianzhengPipeSpec(
            start=tuple(float(v) for v in payload["start"]),      # type: ignore[arg-type]
            end=tuple(float(v) for v in payload["end"]),          # type: ignore[arg-type]
        )
        try:
            creation = backend.create_pipe(
                str(payload["document_token"]), spec,
                idempotency_key=str(payload["idempotency_key"]),
                operation_id=payload.get("operation_id"))
        except TianzhengBackendError as exc:
            raise TianzhengRouteError(exc.error_code, str(exc), details=exc.details) from exc

        data = creation.to_dict()
        # Never let the request's own values masquerade as controlled properties.
        data["diameter_control"] = NOT_AVAILABLE
        data["system_control"] = NOT_AVAILABLE
        return TianzhengRouteResult(
            status="OK", data=data, actual_backend_used=TIANZHENG_BACKEND)

    def query_pipe(self, payload: Mapping[str, Any]) -> TianzhengRouteResult:
        backend = self._require_backend()
        try:
            snapshot = backend.query_pipe(
                str(payload["document_token"]), str(payload["handle"]),
                payload.get("related_handles") or ())
        except TianzhengBackendError as exc:
            raise TianzhengRouteError(exc.error_code, str(exc), details=exc.details) from exc
        return TianzhengRouteResult(
            status="OK", data={"snapshot": snapshot}, actual_backend_used=TIANZHENG_BACKEND)

    def validate_pipe_identity(self, payload: Mapping[str, Any]) -> TianzhengRouteResult:
        backend = self._require_backend()
        try:
            snapshot = backend.validate_identity(
                str(payload["document_token"]), str(payload["handle"]))
        except TianzhengBackendError as exc:
            raise TianzhengRouteError(exc.error_code, str(exc), details=exc.details) from exc
        return TianzhengRouteResult(
            status="OK",
            data={"native_identity_confirmed": True, "snapshot": snapshot},
            actual_backend_used=TIANZHENG_BACKEND)


def build_tianzheng_route_service(
    backend: TianzhengBackend | None = None,
    *,
    handshake: Mapping[str, Any] | None = None,
) -> S8TianzhengRouteService:
    return S8TianzhengRouteService(backend, handshake=handshake)
