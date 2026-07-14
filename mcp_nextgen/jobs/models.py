"""Nextgen 作业记录；不依赖任何 CAD/COM 实现。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


SCHEMA_VERSION = "1.0.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    PAUSED_SAFE_BOUNDARY = "PAUSED_SAFE_BOUNDARY"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    CANCELLED_SAFE_BOUNDARY = "CANCELLED_SAFE_BOUNDARY"
    MANUAL_SAVE_REQUIRED = "MANUAL_SAVE_REQUIRED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class TaskOrigin(str, Enum):
    PLANNED = "PLANNED"
    AUTO_DEPENDENCY = "AUTO_DEPENDENCY"


@dataclass
class TaskRecord:
    task_id: str
    batch_id: str
    operation: str
    origin: TaskOrigin = TaskOrigin.PLANNED
    status: TaskStatus = TaskStatus.PENDING
    dependency_task_ids: list[str] = field(default_factory=list)
    evidence_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["origin"] = self.origin.value
        value["status"] = self.status.value
        return value

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TaskRecord":
        return cls(
            task_id=str(value["task_id"]),
            batch_id=str(value["batch_id"]),
            operation=str(value["operation"]),
            origin=TaskOrigin(str(value.get("origin", TaskOrigin.PLANNED.value))),
            status=TaskStatus(str(value.get("status", TaskStatus.PENDING.value))),
            dependency_task_ids=[str(item) for item in value.get("dependency_task_ids", [])],
            evidence_paths=[str(item) for item in value.get("evidence_paths", [])],
        )


@dataclass
class JobRecord:
    request_id: str
    job_id: str
    idempotency_key: str
    document_identity: dict[str, Any]
    plan_hash: str
    approval_context: dict[str, Any]
    tasks: dict[str, TaskRecord]
    schema_version: str = SCHEMA_VERSION
    status: JobStatus = JobStatus.CREATED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    last_completed_batch_id: str | None = None
    completed_batch_ids: list[str] = field(default_factory=list)
    completed_task_ids: list[str] = field(default_factory=list)
    manual_save_required: bool = False
    cancellation_requested: bool = False
    error_code: str | None = None
    evidence_paths: list[str] = field(default_factory=list)

    @property
    def completed_batch_count(self) -> int:
        return len(set(self.completed_batch_ids))

    @property
    def completed_task_count(self) -> int:
        return len(set(self.completed_task_ids))

    def pending_task_ids(self) -> list[str]:
        completed = set(self.completed_task_ids)
        return [task_id for task_id in self.tasks if task_id not in completed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "job_id": self.job_id,
            "idempotency_key": self.idempotency_key,
            "document_identity": dict(self.document_identity),
            "plan_hash": self.plan_hash,
            "approval_context": dict(self.approval_context),
            "tasks": {key: task.to_dict() for key, task in self.tasks.items()},
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_completed_batch_id": self.last_completed_batch_id,
            "completed_batch_ids": list(dict.fromkeys(self.completed_batch_ids)),
            "completed_batch_count": self.completed_batch_count,
            "completed_task_ids": list(dict.fromkeys(self.completed_task_ids)),
            "completed_task_count": self.completed_task_count,
            "manual_save_required": self.manual_save_required,
            "cancellation_requested": self.cancellation_requested,
            "error_code": self.error_code,
            "evidence_paths": list(self.evidence_paths),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "JobRecord":
        tasks = {
            str(key): TaskRecord.from_mapping(item)
            for key, item in dict(value.get("tasks", {})).items()
        }
        record = cls(
            schema_version=str(value.get("schema_version", SCHEMA_VERSION)),
            request_id=str(value["request_id"]),
            job_id=str(value["job_id"]),
            idempotency_key=str(value["idempotency_key"]),
            document_identity=dict(value["document_identity"]),
            plan_hash=str(value["plan_hash"]),
            approval_context=dict(value["approval_context"]),
            tasks=tasks,
            status=JobStatus(str(value.get("status", JobStatus.CREATED.value))),
            created_at=str(value.get("created_at", utc_now())),
            updated_at=str(value.get("updated_at", utc_now())),
            last_completed_batch_id=value.get("last_completed_batch_id"),
            completed_batch_ids=[str(item) for item in value.get("completed_batch_ids", [])],
            completed_task_ids=[str(item) for item in value.get("completed_task_ids", [])],
            manual_save_required=bool(value.get("manual_save_required", False)),
            cancellation_requested=bool(value.get("cancellation_requested", False)),
            error_code=value.get("error_code"),
            evidence_paths=[str(item) for item in value.get("evidence_paths", [])],
        )
        expected_batches = value.get("completed_batch_count")
        expected_tasks = value.get("completed_task_count")
        if expected_batches is not None and int(expected_batches) != record.completed_batch_count:
            raise ValueError("completed_batch_count 与 completed_batch_ids 不一致")
        if expected_tasks is not None and int(expected_tasks) != record.completed_task_count:
            raise ValueError("completed_task_count 与 completed_task_ids 不一致")
        return record

