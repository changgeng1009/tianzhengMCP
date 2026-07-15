from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

_PATH_KEY = re.compile(r"(?:^path$|_path$|_root$|_output$)")
_NON_SEMANTIC_KEYS = {"created_at", "generated_at", "temporary_run_directory"}


def _normalize_path_text(value: str) -> str:
    normalized = value.replace("\\", "/")
    while "//" in normalized and not normalized.startswith("//"):
        normalized = normalized.replace("//", "/")
    return normalized.rstrip("/") or "."


def canonicalize(
    value: Any,
    *,
    parent_key: str | None = None,
    exclude_non_semantic: bool = False,
) -> Any:
    """返回可重复序列化的纯 JSON 值，不访问文件系统。"""
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(str(item) for item in value.keys()):
            if exclude_non_semantic and key in _NON_SEMANTIC_KEYS:
                continue
            result[key] = canonicalize(
                value[key], parent_key=key, exclude_non_semantic=exclude_non_semantic
            )
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            canonicalize(item, parent_key=parent_key, exclude_non_semantic=exclude_non_semantic)
            for item in value
        ]
    if isinstance(value, str) and parent_key and _PATH_KEY.search(parent_key):
        return _normalize_path_text(value)
    return value


def canonical_dumps(value: Any, *, exclude_non_semantic: bool = False) -> str:
    return json.dumps(
        canonicalize(value, exclude_non_semantic=exclude_non_semantic),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_hash(value: Any, *, exclude_non_semantic: bool = False) -> str:
    payload = canonical_dumps(value, exclude_non_semantic=exclude_non_semantic)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
