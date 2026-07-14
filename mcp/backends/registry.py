from __future__ import annotations

from .base import CadBackend
from .errors import BackendError


class BackendRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, CadBackend] = {}

    def register(self, backend: CadBackend, *, replace: bool = False) -> None:
        if not isinstance(backend, CadBackend):
            raise TypeError("backend does not implement CadBackend protocol")
        if backend.backend_id in self._backends and not replace:
            raise BackendError("duplicate_backend", f"backend already registered: {backend.backend_id}")
        self._backends[backend.backend_id] = backend

    def get(self, backend_id: str) -> CadBackend:
        try:
            return self._backends[backend_id]
        except KeyError as exc:
            raise BackendError("backend_not_registered", f"backend is not registered: {backend_id}") from exc

    def list(self) -> list[CadBackend]:
        return [self._backends[key] for key in sorted(self._backends)]

    def ids(self) -> list[str]:
        return sorted(self._backends)


def build_default_registry() -> BackendRegistry:
    from .com_backend import ComCadBackend
    from .mock_backend import MockCadBackend
    from .net_bridge_backend import NetBridgeCadBackend
    from .tianzheng_api_backend import TianzhengOfficialApiBackend

    registry = BackendRegistry()
    registry.register(ComCadBackend())
    registry.register(MockCadBackend())
    registry.register(NetBridgeCadBackend())
    registry.register(TianzhengOfficialApiBackend())
    return registry
