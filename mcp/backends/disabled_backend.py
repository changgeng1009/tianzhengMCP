from __future__ import annotations

from .capabilities import capability_map
from .errors import BackendUnavailableError
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


class DisabledBackend:
    backend_id = "disabled"
    backend_version = "contract-v1"

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled

    def probe(self) -> BackendProbeResult:
        return BackendProbeResult(self.backend_id, False, self.backend_version, ["contract skeleton only"], "backend_disabled", "backend is disabled", False)

    def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            self.backend_id,
            self.backend_version,
            False,
            capability_map(),
            {},
            [],
            {"water_supply_and_drainage": "contract_only", "hvac": "deferred"},
        )

    def connect(self, config: BackendConfig) -> BackendSession:
        raise BackendUnavailableError(self.backend_id, "contract skeleton cannot connect")

    def disconnect(self, session: BackendSession) -> None:
        session.connected = False

    def open_working_copy(self, session: BackendSession, path: str, read_only: bool = False) -> DocumentResult:
        raise BackendUnavailableError(self.backend_id)

    def scan_entities(self, session: BackendSession, request: ScanRequest) -> ScanResult:
        raise BackendUnavailableError(self.backend_id)

    def create_entity(self, session: BackendSession, task: RepairTask) -> ExecutionResult:
        raise BackendUnavailableError(self.backend_id)

    def save_working_copy(self, session: BackendSession) -> SaveResult:
        raise BackendUnavailableError(self.backend_id)

    def close_document(self, session: BackendSession, save: bool = False) -> CloseResult:
        raise BackendUnavailableError(self.backend_id)

    def reopen_working_copy(self, session: BackendSession, path: str) -> DocumentResult:
        raise BackendUnavailableError(self.backend_id)

    def get_command_state(self, session: BackendSession) -> CommandStateResult:
        return CommandStateResult(self.backend_id, supported=False)
