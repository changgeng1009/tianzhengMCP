"""Capability router for S6 plans across Mock / Real-COM / Plugin backends.

The router answers one question: *which* backend may execute this plan, and it always
reports which one actually did. It never silently substitutes one backend for another —
``actual_backend_used`` is part of every decision, so a caller can never believe the
plugin ran work that COM performed (or vice versa).

Existing backends are preserved: registering the plugin does not deprecate or remove
``MockCadBackend`` or ``RealAutoCadComBackend``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from mcp_nextgen.s6.contracts import CadOperationPlan

MOCK_BACKEND = "nextgen_mock"
COM_BACKEND = "real_autocad_com"
PLUGIN_BACKEND = "autocad_plugin_backend"

#: Preserved registration order. Presence here is not availability.
KNOWN_BACKENDS: tuple[str, ...] = (MOCK_BACKEND, COM_BACKEND, PLUGIN_BACKEND)


@dataclass(frozen=True)
class BackendOffer:
    """What one backend can do for a given plan, as reported by the backend itself."""

    backend_id: str
    available: bool
    supports_plan: bool
    #: True only for backends with a real database transaction (COM has none).
    atomic_batch: bool = False
    sandbox_only: bool = True
    requires_approval: bool = False
    unsupported_reason: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingDecision:
    selected_backend: str | None
    status: str  # selected | blocked
    reason: str
    actual_backend_used: str | None = None
    fallback_used: bool = False
    candidates: tuple[BackendOffer, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_backend": self.selected_backend,
            "actual_backend_used": self.actual_backend_used,
            "status": self.status,
            "reason": self.reason,
            "fallback_used": self.fallback_used,
            "candidates": [
                {
                    "backend_id": offer.backend_id,
                    "available": offer.available,
                    "supports_plan": offer.supports_plan,
                    "atomic_batch": offer.atomic_batch,
                    "unsupported_reason": offer.unsupported_reason,
                }
                for offer in self.candidates
            ],
        }


@dataclass(frozen=True)
class RoutingRequest:
    plan: CadOperationPlan
    #: When true, only a backend with a genuine all-or-nothing transaction may be chosen.
    require_atomic_batch: bool = False
    require_sandbox: bool = True
    approval_granted: bool = False
    preferred_backend: str | None = None
    allow_fallback: bool = False


class CapabilityRouter:
    """Chooses a backend for an S6 plan from live capability offers."""

    def __init__(self, offer_providers: Mapping[str, Callable[[CadOperationPlan], BackendOffer]]) -> None:
        self._providers = dict(offer_providers)

    @property
    def registered_backends(self) -> tuple[str, ...]:
        return tuple(backend for backend in KNOWN_BACKENDS if backend in self._providers)

    def _offers(self, plan: CadOperationPlan) -> list[BackendOffer]:
        offers: list[BackendOffer] = []
        for backend_id in KNOWN_BACKENDS:
            provider = self._providers.get(backend_id)
            if provider is None:
                continue
            try:
                offers.append(provider(plan))
            except Exception as exc:  # a probe failure is "unavailable", never a crash
                offers.append(BackendOffer(
                    backend_id=backend_id, available=False, supports_plan=False,
                    unsupported_reason=f"capability probe failed: {type(exc).__name__}"))
        return offers

    def route(self, request: RoutingRequest) -> RoutingDecision:
        offers = self._offers(request.plan)
        by_id = {offer.backend_id: offer for offer in offers}

        # An explicit preference is honoured or refused, never silently replaced.
        if request.preferred_backend:
            offer = by_id.get(request.preferred_backend)
            if offer is None:
                return RoutingDecision(
                    None, "blocked", f"backend {request.preferred_backend} is not registered",
                    candidates=tuple(offers))
            problem = self._reject_reason(offer, request)
            if problem is None:
                return RoutingDecision(
                    offer.backend_id, "selected", "preferred backend satisfies the plan",
                    actual_backend_used=offer.backend_id, candidates=tuple(offers))
            if not request.allow_fallback:
                return RoutingDecision(
                    None, "blocked",
                    f"preferred backend {request.preferred_backend} cannot run this plan: {problem}",
                    candidates=tuple(offers))

        # Prefer the most capable real backend, then COM, then Mock.
        for backend_id in (PLUGIN_BACKEND, COM_BACKEND, MOCK_BACKEND):
            offer = by_id.get(backend_id)
            if offer is None:
                continue
            if self._reject_reason(offer, request) is None:
                fallback = bool(request.preferred_backend and backend_id != request.preferred_backend)
                return RoutingDecision(
                    backend_id, "selected",
                    "backend is available and satisfies the plan's capability requirements",
                    actual_backend_used=backend_id, fallback_used=fallback, candidates=tuple(offers))

        reasons = "; ".join(
            f"{offer.backend_id}: {self._reject_reason(offer, request)}" for offer in offers) or "no backend registered"
        return RoutingDecision(None, "blocked", f"no backend can run this plan ({reasons})", candidates=tuple(offers))

    @staticmethod
    def _reject_reason(offer: BackendOffer, request: RoutingRequest) -> str | None:
        if not offer.available:
            return "backend unavailable"
        if not offer.supports_plan:
            return offer.unsupported_reason or "plan contains unsupported operations"
        if request.require_atomic_batch and not offer.atomic_batch:
            return "backend has no atomic all_or_nothing transaction"
        if request.require_sandbox and not offer.sandbox_only:
            return "backend is not sandbox-constrained"
        if offer.requires_approval and not request.approval_granted:
            return "backend requires an explicit approval that was not granted"
        return None


# ------------------------------------------------------------------ offer builders


def plugin_offer(backend: Any, plan: CadOperationPlan) -> BackendOffer:
    """Live offer from the plugin backend: capability comes from its runtime handshake."""
    from .autocad_plugin import plan_supported

    try:
        capabilities = backend.client.connect()
    except Exception as exc:
        return BackendOffer(
            PLUGIN_BACKEND, available=False, supports_plan=False,
            unsupported_reason=f"plugin unavailable: {type(exc).__name__}")

    supported, blocker = plan_supported(plan)
    return BackendOffer(
        backend_id=PLUGIN_BACKEND,
        available=bool(capabilities.readiness and capabilities.readiness_state.startswith("AVAILABLE")),
        supports_plan=supported,
        atomic_batch=bool(capabilities.batch_support and capabilities.batch_transaction_mode == "all_or_nothing"),
        sandbox_only=True,
        unsupported_reason=None if supported else f"unsupported by plugin: {blocker}",
        details={"readiness_state": capabilities.readiness_state,
                 "capability_version": capabilities.capability_version,
                 "persistence_support": capabilities.persistence_support},
    )


def com_offer(plan: CadOperationPlan, *, available: bool = False) -> BackendOffer:
    """Real COM backend offer.

    ``atomic_batch`` is FALSE and stays false: AutoCAD COM automation has no database
    transaction, so COM is best-effort. This is a genuine capability difference and is
    never papered over to make conformance look uniform.
    """
    return BackendOffer(
        backend_id=COM_BACKEND, available=available, supports_plan=True,
        atomic_batch=False, sandbox_only=True, requires_approval=True,
        details={"batch_semantics": "best_effort", "true_atomic_transaction": False})


def mock_offer(plan: CadOperationPlan, *, available: bool = True) -> BackendOffer:
    """Mock backend offer: simulates all_or_nothing in memory; never touches CAD."""
    return BackendOffer(
        backend_id=MOCK_BACKEND, available=available, supports_plan=True,
        atomic_batch=True, sandbox_only=True,
        details={"real_cad_execution": False, "batch_semantics": "simulated_all_or_nothing"})
