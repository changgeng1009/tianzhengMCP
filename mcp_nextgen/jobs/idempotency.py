"""基于完整规范请求哈希的持久化幂等记录。"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import threading
import uuid
from typing import Any, Mapping

from mcp_nextgen.safety.canonical import canonical_json, canonical_request_hash
from mcp_nextgen.safety.paths import contained_path, validate_persistence_id

from .models import SCHEMA_VERSION, utc_now


class IdempotencyConflict(RuntimeError):
    """同一幂等键绑定到了不同的完整请求。"""


@dataclass
class IdempotencyRecord:
    idempotency_key: str
    request_hash: str
    job_id: str
    status: str = "IN_PROGRESS"
    schema_version: str = SCHEMA_VERSION
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    result: dict[str, Any] | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "job_id": self.job_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error_code": self.error_code,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IdempotencyRecord":
        return cls(
            schema_version=str(value.get("schema_version", SCHEMA_VERSION)),
            idempotency_key=str(value["idempotency_key"]),
            request_hash=str(value["request_hash"]),
            job_id=str(value["job_id"]),
            status=str(value.get("status", "IN_PROGRESS")),
            created_at=str(value.get("created_at", utc_now())),
            updated_at=str(value.get("updated_at", utc_now())),
            result=dict(value["result"]) if value.get("result") is not None else None,
            error_code=value.get("error_code"),
        )


class FileIdempotencyStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def path_for(self, idempotency_key: str) -> Path:
        validate_persistence_id(idempotency_key, "idempotency_key")
        return contained_path(self.root, f"{idempotency_key}.json")

    def _save(self, record: IdempotencyRecord) -> None:
        path = self.path_for(record.idempotency_key)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical_json(record.to_dict()) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()

    def load(self, idempotency_key: str) -> IdempotencyRecord | None:
        path = self.path_for(idempotency_key)
        if not path.exists():
            return None
        return IdempotencyRecord.from_mapping(json.loads(path.read_text(encoding="utf-8")))

    def begin(
        self,
        idempotency_key: str,
        complete_request: Any,
        job_id: str,
    ) -> tuple[IdempotencyRecord, bool]:
        validate_persistence_id(job_id, "job_id")
        request_hash = canonical_request_hash(complete_request)
        with self._lock:
            current = self.load(idempotency_key)
            if current is not None:
                if current.request_hash != request_hash or current.job_id != job_id:
                    raise IdempotencyConflict("同一 idempotency_key 的完整请求哈希或 job_id 不一致")
                return current, False
            record = IdempotencyRecord(idempotency_key, request_hash, job_id)
            self._save(record)
            return record, True

    def finish(
        self,
        idempotency_key: str,
        *,
        status: str,
        result: Mapping[str, Any] | None = None,
        error_code: str | None = None,
    ) -> IdempotencyRecord:
        with self._lock:
            record = self.load(idempotency_key)
            if record is None:
                raise KeyError("幂等记录不存在")
            record.status = str(status)
            record.result = dict(result) if result is not None else None
            record.error_code = error_code
            record.updated_at = utc_now()
            self._save(record)
            return record
