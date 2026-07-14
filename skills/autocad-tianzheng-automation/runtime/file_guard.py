from __future__ import annotations

from pathlib import Path

from .errors import UnsafeOperation

FORBIDDEN_SUFFIXES = {".dwg", ".dxf"}
FORBIDDEN_PROJECT_ROOT_NAME = "天正-mcp-lab"


def assert_offline_read_allowed(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise UnsafeOperation("离线入口禁止读取 DWG/DXF 内容")
    if FORBIDDEN_PROJECT_ROOT_NAME in candidate.parts:
        raise UnsafeOperation("本阶段禁止读取或迁移天正-mcp-lab")
    return candidate

