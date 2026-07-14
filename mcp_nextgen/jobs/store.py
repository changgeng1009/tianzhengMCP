"""JobRecord 原子快照存储；journal 仍是恢复事实来源。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from mcp_nextgen.safety.canonical import canonical_json
from mcp_nextgen.safety.paths import contained_path, validate_persistence_id

from .models import JobRecord


class FileJobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, job_id: str) -> Path:
        validate_persistence_id(job_id, "job_id")
        return contained_path(self.root, f"{job_id}.json")

    def save(self, job: JobRecord) -> Path:
        path = self.path_for(job.job_id)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical_json(job.to_dict()) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
            return path
        finally:
            if temp.exists():
                temp.unlink()

    def load(self, job_id: str) -> JobRecord | None:
        path = self.path_for(job_id)
        if not path.exists():
            return None
        return JobRecord.from_mapping(json.loads(path.read_text(encoding="utf-8")))
