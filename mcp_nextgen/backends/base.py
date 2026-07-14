"""NextGen CAD backend 抽象合同。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from mcp_nextgen.protocol.models import DocumentIdentity, ExecutionPlan, ExecutionResult

from .models import BackendCapability, BackendSession


class BackendError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        recoverable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.recoverable = recoverable
        self.details = details or {}


class BackendUnavailableError(BackendError):
    def __init__(self, message: str = "backend 不可用") -> None:
        super().__init__("BACKEND_UNAVAILABLE", message, recoverable=False)


ProgressCallback = Callable[[str, str, int, int], None]
BoundaryCheck = Callable[[], None]


class ICadBackend(ABC):
    """所有 Mock/Legacy/未来 Real backend 必须遵循的最小生命周期。"""

    @abstractmethod
    def get_capabilities(self) -> list[BackendCapability]: ...

    @abstractmethod
    def list_documents(self) -> list[DocumentIdentity]: ...

    @abstractmethod
    def open_document(self, expected_identity: DocumentIdentity) -> BackendSession: ...

    @abstractmethod
    def inspect_document(self, session_id: str) -> DocumentIdentity: ...

    @abstractmethod
    def close_document(self, session_id: str, *, save: bool = False) -> ExecutionResult: ...

    @abstractmethod
    def list_entities(self, session_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def execute_batch(
        self,
        session_id: str,
        plan: ExecutionPlan,
        batch_id: str,
        *,
        progress_callback: ProgressCallback | None = None,
        boundary_check: BoundaryCheck | None = None,
    ) -> ExecutionResult: ...

    @abstractmethod
    def save_document(self, session_id: str) -> ExecutionResult: ...

    @abstractmethod
    def reopen_document(self, expected_identity: DocumentIdentity) -> BackendSession: ...
