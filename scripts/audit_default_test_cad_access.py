"""静态审计默认测试相关源码中的 CAD 文件访问迹象。

本工具只读取固定白名单内的 UTF-8 文本源码。它不会打开、解析、哈希
DWG/DXF，也不会跟随源码、配置或历史报告中出现的任何文件路径。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_ROOTS = ("tests", "mcp_nextgen", "mcp", "scripts", "skills/autocad-tianzheng-automation")
TEXT_SUFFIXES = {
    ".py", ".pyi", ".json", ".md", ".txt", ".toml", ".ini", ".cfg",
    ".yaml", ".yml", ".ps1", ".psm1", ".bat", ".cmd", ".csv",
}
CAD_SUFFIXES = {".dwg", ".dxf"}
EXCLUDED_DIR_NAMES = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".venv", "venv", "node_modules", "cache", "caches",
    "output", "outputs", "图纸", "tmp", "temp",
}
SEARCH_TERMS = (
    ".dwg", ".dxf", "图纸", "output", "prewrite", "candidate", "Path.read_bytes",
    "read_bytes(", "open(", "os.open", "hashlib", "sha256", "file_sha256",
    "preflight", "fixture", "artifact", "glob", "rglob", "subprocess",
)
ACCESS_TERMS = (
    "open(", ".open(", "read_bytes(", "read_text(", "os.open", "copy(", "copy2(",
    "copyfile(", "sha256", "file_sha256", "compute_sha256", "subprocess", "preflight",
)
PATH_TERMS = (".dwg", ".dxf", "图纸", "candidate", "prewrite", "output", "artifact")
EXTERNAL_TERMS = (
    "real_dwg", "external_integration", "autocad_required", "tianzheng_required",
    "com_required", "production_only",
)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def iter_text_files(project_root: Path, roots: Iterable[str]) -> Iterable[Path]:
    """遍历显式源码范围；不跟随链接，不读取 CAD 或非白名单文件。"""
    for root_name in roots:
        root = (project_root / root_name).resolve(strict=False)
        if not _is_relative_to(root, project_root):
            raise ValueError(f"审计根目录越界: {root_name}")
        if not root.is_dir():
            continue
        for current, dirs, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            dirs[:] = [
                name for name in dirs
                if name.casefold() not in EXCLUDED_DIR_NAMES
                and not (current_path / name).is_symlink()
            ]
            for name in files:
                path = current_path / name
                suffix = path.suffix.casefold()
                if path.is_symlink() or suffix in CAD_SUFFIXES or suffix not in TEXT_SUFFIXES:
                    continue
                yield path


def classify_hit(relative_path: str, line: str) -> str:
    lowered = line.casefold()
    in_tests = relative_path.casefold().startswith("tests/") or "/tests/" in relative_path.casefold()
    has_access = any(term.casefold() in lowered for term in ACCESS_TERMS)
    has_cad_context = any(term.casefold() in lowered for term in PATH_TERMS)
    if any(term in lowered for term in EXTERNAL_TERMS):
        return "EXTERNAL_INTEGRATION_ONLY"
    if "synthetic" in lowered or "tmp_path" in lowered or "fake_" in lowered:
        return "SAFE_SYNTHETIC_FIXTURE"
    if in_tests and has_access and has_cad_context:
        if ".dwg" in lowered or ".dxf" in lowered:
            return "REAL_DWG_DIRECT_ACCESS"
        if "preflight" in lowered or "artifact" in lowered or "config" in lowered:
            return "REAL_DWG_INDIRECT_ACCESS"
        return "REQUIRES_REFACTOR"
    if not in_tests and has_access and has_cad_context:
        return "RUNTIME_PRODUCTION_CODE"
    if has_cad_context and not has_access:
        return "SAFE_STATIC_STRING"
    if has_access:
        return "FALSE_POSITIVE"
    return "FALSE_POSITIVE"


def audit(project_root: Path, roots: Iterable[str]) -> dict:
    project_root = project_root.resolve(strict=True)
    hits: list[dict] = []
    files_scanned = 0
    for path in iter_text_files(project_root, roots):
        files_scanned += 1
        relative = path.relative_to(project_root).as_posix()
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for line_number, line in enumerate(handle, 1):
                matched = [term for term in SEARCH_TERMS if re.search(re.escape(term), line, re.IGNORECASE)]
                if not matched:
                    continue
                hits.append(
                    {
                        "path": relative,
                        "line": line_number,
                        "matched_terms": matched,
                        "classification": classify_hit(relative, line),
                        "excerpt": line.strip()[:500],
                    }
                )
    counts = Counter(item["classification"] for item in hits)
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "roots": list(roots),
        "safety": {
            "text_suffix_allowlist": sorted(TEXT_SUFFIXES),
            "cad_suffixes_never_opened": sorted(CAD_SUFFIXES),
            "follow_symlinks": False,
            "follow_paths_found_in_content": False,
        },
        "files_scanned": files_scanned,
        "hit_count": len(hits),
        "classification_counts": dict(sorted(counts.items())),
        "classification_taxonomy": [
            "SAFE_STATIC_STRING", "SAFE_SYNTHETIC_FIXTURE", "REAL_DWG_DIRECT_ACCESS",
            "REAL_DWG_INDIRECT_ACCESS", "EXTERNAL_INTEGRATION_ONLY",
            "RUNTIME_PRODUCTION_CODE", "FALSE_POSITIVE", "REQUIRES_REFACTOR",
        ],
        "hits": hits,
    }


def render_markdown(result: dict) -> str:
    lines = [
        "# 默认测试 CAD 静态访问清单",
        "",
        f"- 生成时间：`{result['generated_at']}`",
        f"- 扫描文本文件：`{result['files_scanned']}`",
        f"- 命中：`{result['hit_count']}`",
        "- DWG/DXF 内容读取：`0`（工具按扩展名硬排除）",
        "- 跟随文本中的路径：`否`",
        "",
        "## 分类统计",
        "",
    ]
    for name, count in result["classification_counts"].items():
        lines.append(f"- `{name}`：{count}")
    lines.extend(["", "## 命中明细", ""])
    for hit in result["hits"]:
        excerpt = hit["excerpt"].replace("`", "'")
        lines.append(
            f"- `{hit['classification']}` `{hit['path']}:{hit['line']}` "
            f"（{', '.join(hit['matched_terms'])}）：`{excerpt}`"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--root", action="append", dest="roots")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = audit(args.project_root, args.roots or DEFAULT_ROOTS)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.output_dir / "real_dwg_static_access_inventory.json"
        md_path = args.output_dir / "real_dwg_static_access_inventory.md"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "files_scanned": result["files_scanned"],
        "hit_count": result["hit_count"],
        "classification_counts": result["classification_counts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
