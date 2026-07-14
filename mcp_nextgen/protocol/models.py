"""NextGen 核心数据结构。

这些 dataclass 只定义协议合同，不实现 job 执行、journal 存储、CAD backend
或任何真实写图能力。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any

from .enums import ApprovalLevel, BackendKind, DocumentRole, JobStatus
from .version import PROTOCOL_VERSION

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 不能为空")


def _require_sha256(value: str, field_name: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} 必须是 64 位小写十六进制 SHA-256")


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


class ProtocolModel:
    schema_version: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))

    def _validate_version(self) -> None:
        if self.schema_version != PROTOCOL_VERSION:
            raise ValueError(
                f"schema_version 必须为 {PROTOCOL_VERSION!r}，实际为 {self.schema_version!r}"
            )


@dataclass
class DocumentIdentity(ProtocolModel):
    document_full_path: str
    document_sha256: str
    document_role: DocumentRole
    document_id: str
    schema_version: str = PROTOCOL_VERSION
    backend_kind: BackendKind = BackendKind.MOCK
    read_only: bool = True
    created_at: str = field(default_factory=utc_now)
    evidence_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_version()
        _require(self.document_full_path, "document_full_path")
        _require_sha256(self.document_sha256, "document_sha256")
        _require(self.document_id, "document_id")
        if self.backend_kind is BackendKind.MOCK and self.document_role is not DocumentRole.MOCK_DOCUMENT:
            raise ValueError("Mock backend 的文档角色必须是 MOCK_DOCUMENT")


@dataclass
class OperationIntent(ProtocolModel):
    request_id: str
    job_id: str
    idempotency_key: str
    operation: str
    document: DocumentIdentity
    schema_version: str = PROTOCOL_VERSION
    dry_run: bool = True
    production_allowed: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    evidence_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_version()
        for name in ("request_id", "job_id", "idempotency_key", "operation"):
            _require(getattr(self, name), name)
        if self.production_allowed:
            raise ValueError("当前基线禁止 OperationIntent.production_allowed=true")


@dataclass
class ExecutionTask(ProtocolModel):
    request_id: str
    job_id: str
    batch_id: str
    task_id: str
    operation: str
    idempotency_key: str
    schema_version: str = PROTOCOL_VERSION
    status: str = "PENDING"
    automatic_dependency: bool = False
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    evidence_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_version()
        for name in (
            "request_id", "job_id", "batch_id", "task_id", "operation", "idempotency_key", "status"
        ):
            _require(getattr(self, name), name)


@dataclass
class ExecutionPlan(ProtocolModel):
    request_id: str
    job_id: str
    idempotency_key: str
    document: DocumentIdentity
    operation: str
    plan_hash: str
    tasks: list[ExecutionTask]
    schema_version: str = PROTOCOL_VERSION
    dry_run: bool = True
    production_allowed: bool = False
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    evidence_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_version()
        for name in ("request_id", "job_id", "idempotency_key", "operation"):
            _require(getattr(self, name), name)
        _require_sha256(self.plan_hash, "plan_hash")
        if self.production_allowed:
            raise ValueError("当前基线禁止 ExecutionPlan.production_allowed=true")
        if any(task.job_id != self.job_id for task in self.tasks):
            raise ValueError("ExecutionTask.job_id 必须与 ExecutionPlan.job_id 一致")


@dataclass
class ApprovalContext(ProtocolModel):
    request_id: str
    job_id: str
    idempotency_key: str
    document: DocumentIdentity
    plan_hash: str
    approval_level: ApprovalLevel
    allowed_operations: list[str]
    expires_at: str
    schema_version: str = PROTOCOL_VERSION
    single_use: bool = True
    production_allowed: bool = False
    production_d1_allowed: bool = False
    dry_run: bool = True
    used_at: str | None = None
    created_at: str = field(default_factory=utc_now)
    evidence_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_version()
        for name in ("request_id", "job_id", "idempotency_key", "expires_at"):
            _require(getattr(self, name), name)
        _require_sha256(self.plan_hash, "plan_hash")
        if not self.allowed_operations:
            raise ValueError("allowed_operations 不能为空")
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        if expires.tzinfo is None:
            raise ValueError("expires_at 必须包含时区")
        if self.production_allowed or self.production_d1_allowed:
            if self.approval_level is not ApprovalLevel.L4_CONTROLLED_PRODUCTION:
                raise ValueError("生产授权必须使用 L4_CONTROLLED_PRODUCTION")
        if self.production_d1_allowed and not self.production_allowed:
            raise ValueError("production_d1_allowed=true 时 production_allowed 也必须为 true")
        if self.approval_level is ApprovalLevel.L0_READ_ONLY and not self.dry_run:
            raise ValueError("L0_READ_ONLY 必须 dry_run=true")

    def is_expired(self, now: datetime | None = None) -> bool:
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        return current >= expires

    def permits(self, *, job_id: str, document: DocumentIdentity, plan_hash: str, operation: str) -> bool:
        if self.is_expired() or (self.single_use and self.used_at is not None):
            return False
        return (
            self.job_id == job_id
            and self.document.document_id == document.document_id
            and self.document.document_full_path == document.document_full_path
            and self.document.document_sha256 == document.document_sha256
            and self.plan_hash == plan_hash
            and operation in self.allowed_operations
        )


@dataclass
class JobRecord(ProtocolModel):
    request_id: str
    job_id: str
    idempotency_key: str
    document: DocumentIdentity
    operation: str
    plan_hash: str
    status: JobStatus
    approval_level: ApprovalLevel
    schema_version: str = PROTOCOL_VERSION
    production_allowed: bool = False
    dry_run: bool = True
    last_completed_batch_id: str | None = None
    completed_batch_count: int = 0
    completed_task_count: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    error_code: str | None = None
    evidence_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_version()
        for name in ("request_id", "job_id", "idempotency_key", "operation"):
            _require(getattr(self, name), name)
        _require_sha256(self.plan_hash, "plan_hash")
        if min(self.completed_batch_count, self.completed_task_count) < 0:
            raise ValueError("completed count 不能为负数")
        if self.production_allowed:
            raise ValueError("当前基线禁止 JobRecord.production_allowed=true")


@dataclass
class Checkpoint(ProtocolModel):
    job_id: str
    plan_hash: str
    status: JobStatus
    last_completed_batch_id: str | None
    completed_batch_count: int
    completed_task_count: int
    completed_task_ids: list[str]
    journal_sequence: int
    journal_head_hash: str
    schema_version: str = PROTOCOL_VERSION
    updated_at: str = field(default_factory=utc_now)
    evidence_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_version()
        _require(self.job_id, "job_id")
        _require_sha256(self.plan_hash, "plan_hash")
        _require_sha256(self.journal_head_hash, "journal_head_hash")
        if min(self.completed_batch_count, self.completed_task_count, self.journal_sequence) < 0:
            raise ValueError("checkpoint count/sequence 不能为负数")


@dataclass
class JournalEntry(ProtocolModel):
    job_id: str
    batch_id: str
    task_id: str
    sequence: int
    status: str
    previous_hash: str
    entry_hash: str
    schema_version: str = PROTOCOL_VERSION
    timestamp: str = field(default_factory=utc_now)
    automatic_dependency: bool = False
    payload: dict[str, Any] = field(default_factory=dict)
    evidence_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_version()
        for name in ("job_id", "batch_id", "task_id", "status"):
            _require(getattr(self, name), name)
        if self.sequence < 1:
            raise ValueError("JournalEntry.sequence 必须从 1 开始")
        _require_sha256(self.previous_hash, "previous_hash")
        _require_sha256(self.entry_hash, "entry_hash")


@dataclass
class CapabilityRecord(ProtocolModel):
    capability_id: str
    operation: str
    backend_kind: BackendKind = BackendKind.MOCK
    schema_version: str = PROTOCOL_VERSION
    available: bool = False
    production_allowed: bool = False
    dry_run: bool = True
    evidence_paths: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self._validate_version()
        _require(self.capability_id, "capability_id")
        _require(self.operation, "operation")
        if self.backend_kind is not BackendKind.MOCK:
            raise ValueError("当前基线只允许 BackendKind.MOCK")
        if self.production_allowed:
            raise ValueError("Mock capability 不得标记 production_allowed=true")


@dataclass
class ErrorRecord(ProtocolModel):
    request_id: str
    error_code: str
    message: str
    schema_version: str = PROTOCOL_VERSION
    job_id: str | None = None
    status: str = "ERROR"
    recoverable: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    evidence_paths: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self._validate_version()
        for name in ("request_id", "error_code", "message", "status"):
            _require(getattr(self, name), name)


@dataclass
class ExecutionResult(ProtocolModel):
    request_id: str
    job_id: str
    idempotency_key: str
    status: str
    schema_version: str = PROTOCOL_VERSION
    batch_id: str | None = None
    task_id: str | None = None
    production_allowed: bool = False
    dry_run: bool = True
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    evidence_paths: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self._validate_version()
        for name in ("request_id", "job_id", "idempotency_key", "status"):
            _require(getattr(self, name), name)
        if self.production_allowed:
            raise ValueError("当前基线禁止 ExecutionResult.production_allowed=true")


@dataclass
class ProgressEvent(ProtocolModel):
    request_id: str
    job_id: str
    sequence: int
    status: str
    completed_batch_count: int
    completed_task_count: int
    total_task_count: int
    schema_version: str = PROTOCOL_VERSION
    batch_id: str | None = None
    task_id: str | None = None
    error_code: str | None = None
    timestamp: str = field(default_factory=utc_now)
    evidence_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_version()
        for name in ("request_id", "job_id", "status"):
            _require(getattr(self, name), name)
        if self.sequence < 1:
            raise ValueError("ProgressEvent.sequence 必须从 1 开始")
        if min(self.completed_batch_count, self.completed_task_count, self.total_task_count) < 0:
            raise ValueError("progress count 不能为负数")
        if self.completed_task_count > self.total_task_count:
            raise ValueError("completed_task_count 不得超过 total_task_count")
