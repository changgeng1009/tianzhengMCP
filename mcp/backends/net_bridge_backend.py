from __future__ import annotations

from .disabled_backend import DisabledBackend
from .models import BackendCapabilities


class NetBridgeCadBackend(DisabledBackend):
    """未来 AutoCAD 进程内 .NET/ObjectARX Bridge 的禁用契约骨架。"""

    backend_id = "net_bridge"
    backend_version = "contract-v1"

    def get_capabilities(self) -> BackendCapabilities:
        result = super().get_capabilities()
        result.capability_evidence = {
            "transport": "future configurable localhost HTTP or Named Pipe",
            "contract": "request_id/run_id/hash/idempotency/safety context required",
            "execution": "not implemented and disabled",
        }
        return result
