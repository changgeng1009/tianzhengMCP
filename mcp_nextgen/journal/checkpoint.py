"""原子 checkpoint 及 journal anchor 互校验。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from mcp_nextgen.safety.canonical import canonical_json
from mcp_nextgen.safety.paths import contained_path, validate_persistence_id

from .models import CheckpointRecord
from .store import FileJournalStore, JournalCorrupted


class FileCheckpointStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, job_id: str) -> Path:
        validate_persistence_id(job_id, "job_id")
        directory = contained_path(self.root, job_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = (directory / "checkpoint.json").resolve(strict=False)
        if os.path.commonpath([str(self.root), str(path)]) != str(self.root):
            raise ValueError("checkpoint path 越界")
        return path

    def save(self, checkpoint: CheckpointRecord) -> Path:
        path = self.path_for(checkpoint.job_id)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical_json(checkpoint.to_dict()) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
            try:
                directory_fd = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
            return path
        finally:
            if temp.exists():
                temp.unlink()

    def load(self, job_id: str) -> CheckpointRecord | None:
        path = self.path_for(job_id)
        if not path.exists():
            return None
        return CheckpointRecord.from_mapping(json.loads(path.read_text(encoding="utf-8")))

    def validate_against_journal(self, checkpoint: CheckpointRecord, journal: FileJournalStore) -> None:
        entries = journal.validate(checkpoint.job_id)
        if checkpoint.journal_sequence < 1 or checkpoint.journal_sequence > len(entries):
            raise JournalCorrupted("checkpoint journal_sequence 不存在")
        anchor = entries[checkpoint.journal_sequence - 1]
        if anchor.entry_hash != checkpoint.journal_head_hash:
            raise JournalCorrupted("checkpoint journal_head_hash 不匹配")

