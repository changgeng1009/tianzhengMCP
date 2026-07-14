"""默认禁用的 Legacy backend adapter 骨架。

本模块不导入 COM、旧 executor 或 P4 模块。即使注入 facade，本阶段仍保持
unavailable，避免把一次实验授权解释为持久真实执行能力。
"""

from __future__ import annotations

from typing import Any, Protocol

from mcp_nextgen.backends.base import BackendUnavailableError, ICadBackend
from mcp_nextgen.backends.models import BackendCapability, BackendSession
from mcp_nextgen.protocol.enums import BackendKind
from mcp_nextgen.protocol.models import DocumentIdentity, ExecutionPlan, ExecutionResult


class LegacyExecutionFacade(Protocol):
    """未来由受控 runner 显式注入的最小合同；当前绝不调用。"""

    def probe(self) -> dict[str, Any]: ...


class LegacyCadBackendAdapter(ICadBackend):
    backend_kind = BackendKind.LEGACY_ADAPTER
    enabled = False
    available = False
    production_allowed = False
    production_d1_allowed = False
    real_cad_execution = False
    real_dwg_modified = False

    def __init__(self, facade: LegacyExecutionFacade | None = None, *, enabled: bool = False) -> None:
        self._facade = facade
        self.requested_enabled = bool(enabled)

    def probe(self) -> dict[str, Any]:
        return {
            "backend_kind": self.backend_kind.value,
            "enabled": False,
            "available": False,
            "production_allowed": False,
            "production_d1_allowed": False,
            "facade_injected": self._facade is not None,
            "facade_called": False,
            "real_cad_connection_attempted": False,
            "reason": "MCP-UPGRADE-HANDOFF 阶段只提供 disabled contract skeleton",
        }

    def get_capabilities(self) -> list[BackendCapability]:
        operations = (
            "document.open", "document.inspect", "entity.create", "entity.copy",
            "entity.transform", "batch.execute", "document.save", "document.reopen",
        )
        return [
            BackendCapability(
                capability_id=f"legacy.disabled.{operation}",
                operation=operation,
                backend_kind=BackendKind.LEGACY_ADAPTER,
                available=False,
                production_allowed=False,
                dry_run=True,
                real_cad_execution=False,
                real_dwg_modified=False,
                details={
                    "implementation_kind": "LEGACY_ADAPTER",
                    "contract_only": True,
                    "facade_called": False,
                },
            )
            for operation in operations
        ]

    def list_documents(self) -> list[DocumentIdentity]:
        return []

    def open_document(self, expected_identity: DocumentIdentity) -> BackendSession:
        self._blocked()

    def inspect_document(self, session_id: str) -> DocumentIdentity:
        self._blocked()

    def close_document(self, session_id: str, *, save: bool = False) -> ExecutionResult:
        self._blocked()

    def list_entities(self, session_id: str) -> list[dict[str, Any]]:
        self._blocked()

    def execute_batch(
        self,
        session_id: str,
        plan: ExecutionPlan,
        batch_id: str,
        *,
        progress_callback=None,
        boundary_check=None,
    ) -> ExecutionResult:
        self._blocked()

    def save_document(self, session_id: str) -> ExecutionResult:
        self._blocked()

    def reopen_document(self, expected_identity: DocumentIdentity) -> BackendSession:
        self._blocked()

    @staticmethod
    def _blocked() -> None:
        raise BackendUnavailableError(
            "LegacyCadBackendAdapter 在本阶段永久 disabled；未调用 COM、旧执行器或 P4"
        )
