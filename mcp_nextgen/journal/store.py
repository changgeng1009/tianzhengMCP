"""Append-only、全 SHA-256 previous_hash 链 journal。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from typing import Any

from mcp_nextgen.safety.canonical import canonical_json
from mcp_nextgen.safety.paths import contained_path, validate_persistence_id

from .models import GENESIS_HASH, JournalEntry


class JournalCorrupted(RuntimeError):
    pass


class FileJournalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def path_for(self, job_id: str) -> Path:
        validate_persistence_id(job_id, "job_id")
        return contained_path(self.root, f"{job_id}.jsonl")

    def read(self, job_id: str) -> list[JournalEntry]:
        path = self.path_for(job_id)
        if not path.exists():
            return []
        entries: list[JournalEntry] = []
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    entries.append(JournalEntry.from_mapping(json.loads(line)))
                except Exception as exc:
                    raise JournalCorrupted(f"journal 第 {line_number} 行损坏") from exc
        self.validate_entries(job_id, entries)
        return entries

    @staticmethod
    def validate_entries(job_id: str, entries: list[JournalEntry]) -> None:
        previous = GENESIS_HASH
        for expected_sequence, entry in enumerate(entries, 1):
            if entry.job_id != job_id:
                raise JournalCorrupted("journal job_id 不一致")
            if entry.sequence != expected_sequence:
                raise JournalCorrupted("journal sequence 不连续")
            if entry.previous_hash != previous:
                raise JournalCorrupted("journal previous_hash 链断裂")
            if entry.compute_hash() != entry.entry_hash:
                raise JournalCorrupted("journal entry_hash 不匹配")
            previous = entry.entry_hash

    def append(
        self,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        batch_id: str | None = None,
        task_id: str | None = None,
    ) -> JournalEntry:
        validate_persistence_id(job_id, "job_id")
        if batch_id is not None:
            validate_persistence_id(batch_id, "batch_id")
        if task_id is not None:
            validate_persistence_id(task_id, "task_id")
        with self._lock:
            entries = self.read(job_id)
            entry = JournalEntry(
                sequence=len(entries) + 1,
                job_id=job_id,
                batch_id=batch_id,
                task_id=task_id,
                event_type=str(event_type),
                payload=dict(payload),
                previous_hash=entries[-1].entry_hash if entries else GENESIS_HASH,
            )
            entry.seal()
            path = self.path_for(job_id)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical_json(entry.to_dict()) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return entry

    def validate(self, job_id: str) -> list[JournalEntry]:
        return self.read(job_id)

