"""生成安全测试基线的文本源码 SHA-256 清单。

只读取明确允许目录中的 UTF-8 文本源码。DWG/DXF、artifacts、output、图纸、
缓存、临时目录、符号链接和非文本文件在任何内容读取之前均被排除。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


INCLUDE_DIRS = (
    "acceptance_pack", "autocad_lisp", "autocad_ui",
    "cad", "cad_compare", "command_registry", "config", "coordinate", "docs", "examples",
    "execution", "integrations", "mcp", "mcp_nextgen", "mcp_service", "pipe_network",
    "reference", "reports", "roi", "scripts", "semantic_diff", "skill", "skills", "tests",
    "tianzheng", "tianzheng_command_registry_pack", "tianzheng_interface", "tools", "vision",
)
TEXT_SUFFIXES = {
    ".py", ".pyi", ".json", ".md", ".txt", ".toml", ".ini", ".cfg", ".yaml",
    ".yml", ".ps1", ".psm1", ".bat", ".cmd", ".csv", ".lsp", ".dcl", ".scr",
}
CAD_SUFFIXES = {".dwg", ".dxf"}
EXCLUDED_PARTS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".venv", "venv", "node_modules", "cache", "caches", "output", "outputs", "图纸",
    "artifacts", "logs", "tmp", "temp", "temporary", "_analyze_temp",
}
ROOT_TEXT_NAMES = {
    "AGENTS.md", "CLAUDE.md", "README.md", "ROADMAP.md", "SAFETY_POLICY.md",
    "TASK_BOARD.md", "pytest.ini", "requirements.txt",
}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_text_hash(path: Path, project_root: Path) -> str:
    if path.suffix.casefold() in CAD_SUFFIXES or path.suffix.casefold() not in TEXT_SUFFIXES:
        raise ValueError(f"拒绝读取 CAD 或非文本文件: {path}")
    if path.is_symlink():
        raise ValueError(f"拒绝读取符号链接: {path}")
    resolved = path.resolve(strict=True)
    if not _is_relative_to(resolved, project_root):
        raise ValueError(f"拒绝读取越界路径: {path}")
    if any(part.casefold() in EXCLUDED_PARTS for part in resolved.relative_to(project_root).parts):
        raise ValueError(f"拒绝读取排除目录: {path}")
    # 路径、目录和扩展名已经在内容读取前完成 fail-closed 校验。
    # 原始字节哈希可覆盖既有的非 UTF-8 源码配置，但绝不用于 CAD/二进制候选图。
    with resolved.open("rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def iter_sources(project_root: Path):
    candidates: list[Path] = []
    for name in ROOT_TEXT_NAMES:
        path = project_root / name
        if path.is_file() and not path.is_symlink():
            candidates.append(path)
    for root_name in INCLUDE_DIRS:
        root = project_root / root_name
        if not root.is_dir() or root.is_symlink():
            continue
        for current, dirs, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            dirs[:] = [
                name for name in dirs
                if name.casefold() not in EXCLUDED_PARTS and not (current_path / name).is_symlink()
            ]
            for name in files:
                path = current_path / name
                if path.is_symlink() or path.suffix.casefold() not in TEXT_SUFFIXES:
                    continue
                candidates.append(path)
    for path in sorted(set(candidates), key=lambda item: item.relative_to(project_root).as_posix()):
        yield path


def build(project_root: Path) -> dict:
    project_root = project_root.resolve(strict=True)
    files = []
    for path in iter_sources(project_root):
        relative = path.relative_to(project_root).as_posix()
        files.append({"path": relative, "sha256": _safe_text_hash(path, project_root)})
    canonical = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": "1.0.0",
        "status": "CANDIDATE_CLOSED_PENDING_INDEPENDENT_VERIFY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hash_algorithm": "sha256",
        "hash_input": "exact_source_bytes_after_text_suffix_and_path_validation",
        "included_roots": list(INCLUDE_DIRS),
        "excluded": ["*.dwg", "*.dxf", "图纸", "output", "artifacts", "cache", ".git", "temporary files", "symlinks", "non-text files"],
        "cad_files_opened_or_hashed": 0,
        "files": files,
        "file_count": len(files),
        "manifest_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.project_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "file_count": result["file_count"], "manifest_sha256": result["manifest_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
