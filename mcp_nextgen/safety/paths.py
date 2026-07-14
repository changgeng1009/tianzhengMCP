"""持久化 ID 白名单和 resolved-path containment。"""

from __future__ import annotations

import os
from pathlib import Path
import re


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_persistence_id(value: str, field_name: str = "id") -> str:
    text = str(value)
    if not SAFE_ID.fullmatch(text):
        raise ValueError(f"{field_name} 不符合持久化 ID 白名单")
    return text


def contained_path(base: str | Path, *parts: str) -> Path:
    root = Path(base).resolve(strict=False)
    safe_parts = [validate_persistence_id(part, "path_part") for part in parts]
    candidate = root.joinpath(*safe_parts).resolve(strict=False)
    if os.path.commonpath([str(root), str(candidate)]) != str(root):
        raise ValueError("resolved path 越出持久化根目录")
    return candidate

