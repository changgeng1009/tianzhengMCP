"""WP2 静态 Backend Registry 的稳定运行时导入面。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from adapters.registry import (
    BackendContract,
    BackendRegistry,
    BackendSelectionResult,
    BackendSelector,
)


def select_backend(
    manifest: Mapping[str, Any],
    *,
    selector: BackendSelector | None = None,
) -> BackendSelectionResult:
    return (selector or BackendSelector()).select_from_manifest(manifest)


__all__ = [
    "BackendContract",
    "BackendRegistry",
    "BackendSelectionResult",
    "BackendSelector",
    "select_backend",
]
