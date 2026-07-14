from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    BackendCapabilities,
    BackendConfig,
    BackendProbeResult,
    BackendSession,
    CloseResult,
    CommandStateResult,
    DocumentResult,
    ExecutionResult,
    RepairTask,
    SaveResult,
    ScanRequest,
    ScanResult,
)


@runtime_checkable
class CadBackend(Protocol):
    backend_id: str

    def probe(self) -> BackendProbeResult: ...

    def get_capabilities(self) -> BackendCapabilities: ...

    def connect(self, config: BackendConfig) -> BackendSession: ...

    def disconnect(self, session: BackendSession) -> None: ...

    def open_working_copy(self, session: BackendSession, path: str, read_only: bool = False) -> DocumentResult: ...

    def scan_entities(self, session: BackendSession, request: ScanRequest) -> ScanResult: ...

    def create_entity(self, session: BackendSession, task: RepairTask) -> ExecutionResult: ...

    def save_working_copy(self, session: BackendSession) -> SaveResult: ...

    def close_document(self, session: BackendSession, save: bool = False) -> CloseResult: ...

    def reopen_working_copy(self, session: BackendSession, path: str) -> DocumentResult: ...

    def get_command_state(self, session: BackendSession) -> CommandStateResult: ...
