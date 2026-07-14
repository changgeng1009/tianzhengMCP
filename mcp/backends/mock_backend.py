from __future__ import annotations

from typing import Any

from .capabilities import capability_map
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


class MockCadBackend:
    backend_id = "mock"

    def __init__(self, *, entities: list[dict[str, Any]] | None = None) -> None:
        self.entities = list(entities or [])

    def probe(self) -> BackendProbeResult:
        return BackendProbeResult(self.backend_id, True, "stage2-mock-v1", ["in-memory mock only"], real_cad_connection_attempted=False)

    def get_capabilities(self) -> BackendCapabilities:
        supported = capability_map(
            open_working_copy=True,
            scan_acdb_entities=True,
            create_acdb_line=True,
            create_acdb_text=True,
            create_acdb_polyline=True,
            save_working_copy=True,
            close_reopen=True,
            persistence_qa=True,
        )
        verified = [name for name, value in supported.items() if value]
        return BackendCapabilities(
            self.backend_id,
            "stage2-mock-v1",
            True,
            supported,
            {name: "mock-only static capability" for name in verified},
            verified,
            {"water_supply_and_drainage": "test_only", "hvac": "deferred"},
        )

    def connect(self, config: BackendConfig) -> BackendSession:
        return BackendSession(self.backend_id, True, metadata={"real_cad_execution": False})

    def disconnect(self, session: BackendSession) -> None:
        session.connected = False

    def open_working_copy(self, session: BackendSession, path: str, read_only: bool = False) -> DocumentResult:
        session.document_path = path
        session.read_only = read_only
        return DocumentResult(self.backend_id, True, path, read_only)

    def scan_entities(self, session: BackendSession, request: ScanRequest) -> ScanResult:
        return ScanResult(self.backend_id, True, list(self.entities), ["mock_scan"])

    def create_entity(self, session: BackendSession, task: RepairTask) -> ExecutionResult:
        self.entities.append({"task_id": task.task_id, "object_type": task.object_type, "geometry": task.geometry})
        return ExecutionResult(
            self.backend_id,
            True,
            task.task_id,
            created_object_ids=[f"mock:{task.task_id}"],
            created_handles=[],
            draw_delta=1,
            capability_evidence=["mock-only"],
            real_cad_execution=False,
            real_dwg_modified=False,
        )

    def save_working_copy(self, session: BackendSession) -> SaveResult:
        return SaveResult(self.backend_id, True, False, session.document_path, False)

    def close_document(self, session: BackendSession, save: bool = False) -> CloseResult:
        session.document_path = None
        return CloseResult(self.backend_id, True, True, False)

    def reopen_working_copy(self, session: BackendSession, path: str) -> DocumentResult:
        return self.open_working_copy(session, path)

    def get_command_state(self, session: BackendSession) -> CommandStateResult:
        return CommandStateResult(self.backend_id, supported=False)
