from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid


@dataclass
class SerializableModel:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BackendConfig(SerializableModel):
    backend_id: str
    enabled: bool = False
    execution_allowed: bool = False
    backend_version: str = ""
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackendProbeResult(SerializableModel):
    backend_id: str
    available: bool
    backend_version: str = ""
    evidence: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    real_cad_connection_attempted: bool = False


@dataclass
class BackendCapabilities(SerializableModel):
    backend_id: str
    backend_version: str
    available: bool
    capabilities: dict[str, bool] = field(default_factory=dict)
    capability_evidence: dict[str, str] = field(default_factory=dict)
    sandbox_verified_capabilities: list[str] = field(default_factory=list)
    professional_domains: dict[str, str] = field(default_factory=dict)

    def supports(self, required: list[str]) -> bool:
        return all(self.capabilities.get(name) is True for name in required)

    def missing(self, required: list[str]) -> list[str]:
        return [name for name in required if self.capabilities.get(name) is not True]

    def sandbox_verified(self, required: list[str]) -> bool:
        verified = set(self.sandbox_verified_capabilities)
        return all(name in verified for name in required)


@dataclass
class BackendSession(SerializableModel):
    backend_id: str
    connected: bool
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    document_path: str | None = None
    read_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    native_handle: Any = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("native_handle", None)
        return data


@dataclass
class DocumentResult(SerializableModel):
    backend_id: str
    success: bool
    document_path: str
    read_only: bool
    document_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class ScanRequest(SerializableModel):
    professional_domain: str = "water_supply_and_drainage"
    include_acdb: bool = True
    include_tianzheng_water_objects: bool = True
    spaces: list[str] = field(default_factory=lambda: ["modelspace"])


@dataclass
class ScanResult(SerializableModel):
    backend_id: str
    success: bool
    entities: list[dict[str, Any]] = field(default_factory=list)
    capability_evidence: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class RepairTask(SerializableModel):
    task_id: str
    classification: str
    object_type: str
    execution_allowed: bool
    required_capabilities: list[str]
    professional_domain: str = "water_supply_and_drainage"
    system_type: str | None = None
    domain_object_type: str | None = None
    geometry: dict[str, Any] = field(default_factory=dict)
    preferred_backend: str | None = None
    allowed_backends: list[str] = field(default_factory=list)
    fallback_policy: str = "blocked"
    selected_backend: str | None = None
    backend_selection_reason: str = ""
    backend_capability_evidence: dict[str, Any] = field(default_factory=dict)
    validation_fixture_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RepairTask":
        known = {field.name for field in cls.__dataclass_fields__.values()}
        payload = {key: item for key, item in value.items() if key in known}
        payload.setdefault("geometry", value.get("cad_geometry") or value.get("geometry") or {})
        payload.setdefault("execution_allowed", bool(value.get("execution_allowed", False)))
        payload.setdefault("required_capabilities", list(value.get("required_capabilities") or []))
        return cls(**payload)


@dataclass
class ExecutionResult(SerializableModel):
    backend_id: str
    success: bool
    task_id: str
    created_object_ids: list[str] = field(default_factory=list)
    created_handles: list[str] = field(default_factory=list)
    draw_delta: int = 0
    capability_evidence: list[str] = field(default_factory=list)
    real_cad_execution: bool = False
    real_dwg_modified: bool = False
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class SaveResult(SerializableModel):
    backend_id: str
    success: bool
    document_saved: bool
    document_path: str | None = None
    real_dwg_modified: bool = False
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class CloseResult(SerializableModel):
    backend_id: str
    success: bool
    closed: bool
    saved: bool = False
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class CommandStateResult(SerializableModel):
    backend_id: str
    supported: bool
    command_started: bool = False
    command_ended: bool = False
    command_cancelled: bool = False
    command_failed: bool = False


@dataclass
class BackendSelectionResult(SerializableModel):
    task_id: str
    requested_capabilities: list[str]
    candidate_backends: list[dict[str, Any]]
    selected_backend: str | None
    selection_status: str
    selection_reason: str
    fallback_used: bool
    backend_capability_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class PersistenceQaResult(SerializableModel):
    backend_id: str
    success: bool
    saved: bool
    reopened: bool
    persisted_delta: int
    geometry_match: bool
    layer_match: bool
