"""Structured MCP route: MCP tool -> S6 plan -> router -> backend -> plugin.

This is the ONLY sanctioned path from MCP to the AutoCAD plugin. It deliberately exposes
no raw-protocol surface: there is no ``plugin_send``, no ``raw_socket``, no
``send_autocad_command`` and no arbitrary-request tool. Callers submit a *validated
structured request*; the plugin wire protocol stays an implementation detail of the
backend beneath.

The MCP layer therefore cannot:
  * choose a document by path, window title or active-document state;
  * send an arbitrary CAD command or LISP string;
  * bypass the capability router;
  * observe or supply a plugin document token or session nonce.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from mcp_nextgen.backends.autocad_plugin import (
    UNSUPPORTED_OPERATION_ERROR,
    AutoCadPluginBackend,
    PluginBackendError,
    plan_supported,
)
from mcp_nextgen.backends.capability_router import (
    PLUGIN_BACKEND,
    BackendOffer,
    CapabilityRouter,
    RoutingDecision,
    RoutingRequest,
    com_offer,
    mock_offer,
    plugin_offer,
)
from mcp_nextgen.s6.contracts import (
    CadOperation,
    CadOperationPlan,
    CadOperationValidationError,
    EntitySpec,
    LayerSpec,
)


class PluginRouteError(RuntimeError):
    def __init__(self, error_code: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code
        self.details = dict(details or {})


@dataclass(frozen=True)
class PluginRouteResult:
    status: str
    routing: dict[str, Any]
    execution: dict[str, Any]
    actual_backend_used: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "routing": self.routing,
            "execution": self.execution,
            "actual_backend_used": self.actual_backend_used,
        }


def build_plan_from_structured_request(payload: Mapping[str, Any]) -> CadOperationPlan:
    """Turn a validated MCP structured request into an S6 plan.

    Only the S6 vocabulary is accepted. There is no passthrough field, so an MCP caller
    cannot express a raw plugin request or a CAD command string.
    """
    job_id = str(payload.get("job_id") or "")
    document_token = str(payload.get("document_token") or job_id or "pending")
    entities: Sequence[Mapping[str, Any]] = payload.get("entities") or ()
    layer = str(payload.get("layer") or "")

    if not job_id:
        raise PluginRouteError("MISSING_FIELD", "job_id is required")
    if not layer:
        raise PluginRouteError("MISSING_FIELD", "layer is required")
    if not entities:
        raise PluginRouteError("MISSING_FIELD", "at least one entity is required")

    operations: list[CadOperation] = []
    try:
        operations.append(CadOperation(
            operation_id=f"{job_id}.layer",
            operation="ENSURE_LAYER",
            parameters={"layer": LayerSpec(name=layer).to_dict()},
        ))
        for index, entity in enumerate(entities):
            entity_type = str(entity.get("type") or entity.get("entity_type") or "")
            geometry = dict(entity.get("geometry") or {})
            operations.append(CadOperation(
                operation_id=f"{job_id}.e{index}",
                operation=f"CREATE_{entity_type.upper()}",
                entity=EntitySpec(entity_type=entity_type, geometry=geometry, layer=layer),
            ))
    except CadOperationValidationError as exc:
        raise PluginRouteError("INVALID_STRUCTURED_REQUEST", str(exc)) from exc

    return CadOperationPlan(
        job_id=job_id,
        document_token=document_token,
        operations=tuple(operations),
        batch_policy="all_or_nothing",
        dry_run=bool(payload.get("dry_run", False)),
    )


class S7PluginRouteService:
    """MCP-facing service. Owns routing and delegates execution to the chosen backend."""

    def __init__(
        self,
        router: CapabilityRouter,
        *,
        plugin_backend: AutoCadPluginBackend | None = None,
        approval_granted: bool = False,
    ) -> None:
        self._router = router
        self._plugin_backend = plugin_backend
        self._approval_granted = approval_granted

    def plan_capability(self, plan: CadOperationPlan) -> dict[str, Any]:
        supported, blocker = plan_supported(plan)
        return {"plugin_supports_plan": supported, "unsupported_reason": blocker}

    def route(self, plan: CadOperationPlan, *, require_atomic_batch: bool = True,
              preferred_backend: str | None = None, allow_fallback: bool = False) -> RoutingDecision:
        return self._router.route(RoutingRequest(
            plan=plan,
            require_atomic_batch=require_atomic_batch,
            require_sandbox=True,
            approval_granted=self._approval_granted,
            preferred_backend=preferred_backend,
            allow_fallback=allow_fallback,
        ))

    def execute(
        self,
        plan: CadOperationPlan,
        *,
        session_id: str,
        require_atomic_batch: bool = True,
        preferred_backend: str | None = None,
        allow_fallback: bool = False,
        idempotency_key: str | None = None,
    ) -> PluginRouteResult:
        """Route, then execute on the selected backend, always reporting which one ran."""
        decision = self.route(
            plan, require_atomic_batch=require_atomic_batch,
            preferred_backend=preferred_backend, allow_fallback=allow_fallback)

        if decision.status != "selected" or decision.selected_backend is None:
            # Blocked is reported honestly; nothing is executed and nothing is faked.
            return PluginRouteResult("blocked", decision.to_dict(), {}, None)

        if decision.selected_backend != PLUGIN_BACKEND:
            # Another backend was chosen. This service does not execute on its behalf, and
            # the caller is told exactly which backend must run the plan.
            return PluginRouteResult(
                "delegated", decision.to_dict(),
                {"note": "selected backend is not the plugin backend; execute via its own adapter"},
                decision.selected_backend)

        if self._plugin_backend is None:
            raise PluginRouteError("PLUGIN_BACKEND_NOT_CONFIGURED", "no plugin backend instance is bound")

        try:
            result = self._plugin_backend.execute_cad_plan(
                session_id, plan, batch_id=plan.plan_id, idempotency_key=idempotency_key)
        except PluginBackendError as exc:
            return PluginRouteResult(
                "failed", decision.to_dict(),
                {"error_code": exc.error_code, "category": exc.category,
                 "retryable": exc.retryable, "message": str(exc)},
                PLUGIN_BACKEND)

        return PluginRouteResult("completed", decision.to_dict(), result.to_dict(), PLUGIN_BACKEND)


def build_plugin_route_service(
    *,
    plugin_backend: AutoCadPluginBackend | None = None,
    mock_available: bool = True,
    com_available: bool = False,
    approval_granted: bool = False,
) -> S7PluginRouteService:
    """Wire the standard three-backend router. Mock and COM are always preserved."""
    providers: dict[str, Any] = {
        "nextgen_mock": lambda plan: mock_offer(plan, available=mock_available),
        "real_autocad_com": lambda plan: com_offer(plan, available=com_available),
    }
    if plugin_backend is not None:
        providers[PLUGIN_BACKEND] = lambda plan: plugin_offer(plugin_backend, plan)

    return S7PluginRouteService(
        CapabilityRouter(providers),
        plugin_backend=plugin_backend,
        approval_granted=approval_granted,
    )
