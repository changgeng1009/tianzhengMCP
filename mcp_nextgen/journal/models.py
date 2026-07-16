"""Hash-chained journal 与 checkpoint 数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from mcp_nextgen.safety.canonical import sha256_hex


# 不能从 mcp_nextgen.jobs 导入：journal 是 jobs 的底层依赖，反向导入会在
# 控制面直接使用 checkpoint 时造成初始化循环。
SCHEMA_VERSION = "1.0.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


GENESIS_HASH = "0" * 64


@dataclass
class JournalEntry:
    sequence: int
    job_id: str
    event_type: str
    payload: dict[str, Any]
    previous_hash: str
    timestamp: str = field(default_factory=utc_now)
    batch_id: str | None = None
    task_id: str | None = None
    schema_version: str = SCHEMA_VERSION
    entry_hash: str = ""

    def hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "job_id": self.job_id,
            "batch_id": self.batch_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
        }

    def compute_hash(self) -> str:
        return sha256_hex(self.hash_payload())

    def seal(self) -> None:
        self.entry_hash = self.compute_hash()

    def to_dict(self) -> dict[str, Any]:
        return {**self.hash_payload(), "entry_hash": self.entry_hash}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "JournalEntry":
        return cls(
            schema_version=str(value.get("schema_version", SCHEMA_VERSION)),
            sequence=int(value["sequence"]),
            job_id=str(value["job_id"]),
            batch_id=value.get("batch_id"),
            task_id=value.get("task_id"),
            timestamp=str(value["timestamp"]),
            event_type=str(value["event_type"]),
            payload=dict(value.get("payload", {})),
            previous_hash=str(value["previous_hash"]),
            entry_hash=str(value["entry_hash"]),
        )


@dataclass
class CheckpointRecord:
    job_id: str
    state: str
    plan_hash: str
    document_identity_digest: str
    journal_sequence: int
    journal_head_hash: str
    last_completed_batch_id: str | None
    completed_batch_ids: list[str]
    completed_task_ids: list[str]
    pending_task_ids: list[str]
    auto_dependency_task_ids: list[str]
    manual_save_required: bool = False
    schema_version: str = SCHEMA_VERSION
    updated_at: str = field(default_factory=utc_now)

    @property
    def completed_batch_count(self) -> int:
        return len(set(self.completed_batch_ids))

    @property
    def completed_task_count(self) -> int:
        return len(set(self.completed_task_ids))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "state": self.state,
            "plan_hash": self.plan_hash,
            "document_identity_digest": self.document_identity_digest,
            "journal_sequence": self.journal_sequence,
            "journal_head_hash": self.journal_head_hash,
            "last_completed_batch_id": self.last_completed_batch_id,
            "completed_batch_ids": list(dict.fromkeys(self.completed_batch_ids)),
            "completed_batch_count": self.completed_batch_count,
            "completed_task_ids": list(dict.fromkeys(self.completed_task_ids)),
            "completed_task_count": self.completed_task_count,
            "pending_task_ids": list(dict.fromkeys(self.pending_task_ids)),
            "auto_dependency_task_ids": list(dict.fromkeys(self.auto_dependency_task_ids)),
            "manual_save_required": self.manual_save_required,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CheckpointRecord":
        record = cls(
            schema_version=str(value.get("schema_version", SCHEMA_VERSION)),
            job_id=str(value["job_id"]),
            state=str(value["state"]),
            plan_hash=str(value["plan_hash"]),
            document_identity_digest=str(value["document_identity_digest"]),
            journal_sequence=int(value["journal_sequence"]),
            journal_head_hash=str(value["journal_head_hash"]),
            last_completed_batch_id=value.get("last_completed_batch_id"),
            completed_batch_ids=[str(item) for item in value.get("completed_batch_ids", [])],
            completed_task_ids=[str(item) for item in value.get("completed_task_ids", [])],
            pending_task_ids=[str(item) for item in value.get("pending_task_ids", [])],
            auto_dependency_task_ids=[str(item) for item in value.get("auto_dependency_task_ids", [])],
            manual_save_required=bool(value.get("manual_save_required", False)),
            updated_at=str(value.get("updated_at", utc_now())),
        )
        if int(value.get("completed_batch_count", record.completed_batch_count)) != record.completed_batch_count:
            raise ValueError("checkpoint completed_batch_count 不一致")
        if int(value.get("completed_task_count", record.completed_task_count)) != record.completed_task_count:
            raise ValueError("checkpoint completed_task_count 不一致")
        return record
