"""安全相关 canonical JSON 与摘要。"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def to_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return to_json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"canonical JSON 不支持类型: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(to_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_request_hash(request: Any) -> str:
    """对完整 canonical request 求哈希；不静默删除任何字段。"""
    return sha256_hex(request)
