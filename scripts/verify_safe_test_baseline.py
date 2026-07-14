"""独立复核 SEC-FINAL-019 安全测试冻结基线。

只读取基线 JSON、校验清单及清单中经过 fail-closed 校验的文本源码。
绝不读取 DWG/DXF，绝不跟随报告或配置中的 CAD 路径。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


CAD_SUFFIXES = {".dwg", ".dxf"}
TEXT_SUFFIXES = {
    ".py", ".pyi", ".json", ".md", ".txt", ".toml", ".ini", ".cfg",
    ".yaml", ".yml", ".ps1", ".psm1", ".bat", ".cmd", ".csv", ".sha256",
    ".lsp", ".dcl", ".scr",
}
EXCLUDED_PARTS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".venv", "venv", "node_modules", "cache", "caches", "output",
    "outputs", "图纸", "tmp", "temp",
}
REQUIRED_BASELINE_JSON = (
    "safe_test_baseline_manifest.json",
    "test_command_manifest.json",
    "pytest_marker_policy.json",
    "file_access_guard_policy.json",
    "synthetic_fixture_manifest.json",
    "test_inventory.json",
    "test_result_summary.json",
    "default_test_file_access_summary.json",
    "source_tree_hash_manifest.json",
    "known_excluded_tests.json",
    "sec_final_019_closure.json",
)
REQUIRED_CONDITIONS = tuple(f"condition_{index:02d}" for index in range(1, 17))
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class VerificationError(RuntimeError):
    pass


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _read_utf8(path: Path) -> str:
    if path.suffix.casefold() not in TEXT_SUFFIXES:
        raise VerificationError(f"拒绝读取非文本文件: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _read_json(path: Path) -> dict:
    value = json.loads(_read_utf8(path))
    if not isinstance(value, dict):
        raise VerificationError(f"JSON 顶层必须为对象: {path}")
    return value


def _text_sha256(path: Path) -> str:
    return hashlib.sha256(_read_utf8(path).encode("utf-8")).hexdigest()


def _source_sha256(path: Path) -> str:
    # 仅在 _validate_source_path 完成根目录、禁区、链接和文本后缀校验后调用。
    with path.open("rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _validate_source_path(project_root: Path, relative: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise VerificationError(f"源码清单路径不安全: {relative}")
    if any(part.casefold() in EXCLUDED_PARTS for part in raw.parts):
        raise VerificationError(f"源码清单命中排除目录: {relative}")
    if "artifacts" in {part.casefold() for part in raw.parts}:
        raise VerificationError(f"源码清单不得包含 artifacts: {relative}")
    suffix = raw.suffix.casefold()
    if suffix in CAD_SUFFIXES or suffix not in TEXT_SUFFIXES:
        raise VerificationError(f"源码清单包含 CAD 或非文本文件: {relative}")
    candidate = project_root / raw
    if candidate.is_symlink():
        raise VerificationError(f"源码清单不得包含符号链接: {relative}")
    resolved = candidate.resolve(strict=True)
    if not _is_relative_to(resolved, project_root):
        raise VerificationError(f"源码清单解析后越界: {relative}")
    return resolved


def verify_source_manifest(project_root: Path, manifest: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return False, ["source_tree_hash_manifest.files 必须为数组"]
    if not entries:
        return False, ["source_tree_hash_manifest.files 不能为空"]
    for index, entry in enumerate(entries):
        try:
            if not isinstance(entry, dict):
                raise VerificationError("条目必须为对象")
            relative = entry.get("path")
            expected = entry.get("sha256")
            if not isinstance(relative, str) or not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
                raise VerificationError("path/sha256 无效")
            path = _validate_source_path(project_root, relative)
            actual = _source_sha256(path)
            if actual != expected:
                raise VerificationError(f"哈希不一致: {relative}")
        except (OSError, VerificationError) as exc:
            errors.append(f"files[{index}]: {exc}")
    return not errors, errors


def verify_checksum_file(baseline: Path) -> tuple[bool, list[str]]:
    checksum_path = baseline / "safe_test_baseline.sha256"
    if not checksum_path.is_file():
        return False, ["缺少 safe_test_baseline.sha256"]
    errors: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(_read_utf8(checksum_path).splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not SHA256_RE.fullmatch(parts[0]):
            errors.append(f"sha256:{line_number}: 格式错误")
            continue
        name = parts[1].lstrip("*")
        if Path(name).name != name or name not in REQUIRED_BASELINE_JSON:
            errors.append(f"sha256:{line_number}: 文件名不允许: {name}")
            continue
        if name in seen:
            errors.append(f"sha256:{line_number}: 文件重复: {name}")
            continue
        seen.add(name)
        path = baseline / name
        if not path.is_file() or path.is_symlink():
            errors.append(f"sha256:{line_number}: 文件缺失或为链接: {name}")
            continue
        if _text_sha256(path) != parts[0]:
            errors.append(f"sha256:{line_number}: 哈希不一致: {name}")
    missing = sorted(set(REQUIRED_BASELINE_JSON) - seen)
    if missing:
        errors.append(f"sha256 清单缺少文件: {', '.join(missing)}")
    return not errors, errors


def verify_closure(
    closure: dict,
    access: dict,
    results: dict,
    baseline_manifest: dict,
    test_inventory: dict,
    source_manifest_digest: str,
    candidate_precheck: bool = False,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    expected_status = "CANDIDATE_CLOSED_PENDING_INDEPENDENT_VERIFY" if candidate_precheck else "CLOSED"
    if closure.get("sec_final_019") != expected_status:
        errors.append(f"sec_final_019 不是 {expected_status}")
    conditions = closure.get("closure_conditions")
    if not isinstance(conditions, dict):
        errors.append("closure_conditions 必须为对象")
    else:
        expected_conditions = REQUIRED_CONDITIONS[:-1] if candidate_precheck else REQUIRED_CONDITIONS
        for key in expected_conditions:
            item = conditions.get(key)
            if not isinstance(item, dict) or item.get("passed") is not True:
                errors.append(f"关闭条件未通过: {key}")
        if candidate_precheck:
            independent = conditions.get("condition_16")
            if not isinstance(independent, dict) or independent.get("passed") is not False:
                errors.append("候选预检阶段 condition_16 必须保持 false")
    expected_zero = (
        "real_dwg_successful_reads", "real_dwg_successful_writes", "cad_processes_started",
        "autocad_com_connections", "tianzheng_connections",
    )
    for key in expected_zero:
        if access.get(key) != 0:
            errors.append(f"访问摘要必须为 0: {key}")
    if access.get("blocked_real_dwg_attempts") != 0:
        errors.append("默认回归意外 blocked_real_dwg_attempts 必须为 0")
    if results.get("failed_count") != 0:
        errors.append("默认安全回归 failed_count 必须为 0")
    if results.get("passed") is not True:
        errors.append("默认安全回归 passed 必须为 true")
    if test_inventory.get("unmarked_real_dwg_tests") != 0:
        errors.append("unmarked_real_dwg_tests 必须为 0")
    expected_baseline_status = "CANDIDATE_CLOSED_PENDING_INDEPENDENT_VERIFY" if candidate_precheck else "FROZEN"
    if baseline_manifest.get("status") != expected_baseline_status:
        errors.append(f"基线状态必须为 {expected_baseline_status}")
    if baseline_manifest.get("guard_enabled") is not True:
        errors.append("guard_enabled 必须为 true")
    if baseline_manifest.get("source_tree_manifest_sha256") != source_manifest_digest:
        errors.append("source_tree_manifest_sha256 不匹配")
    return not errors, errors


def verify(baseline: Path, project_root: Path, candidate_precheck: bool = False) -> dict:
    baseline = baseline.resolve(strict=True)
    project_root = project_root.resolve(strict=True)
    errors: list[str] = []
    documents: dict[str, dict] = {}
    for name in REQUIRED_BASELINE_JSON:
        path = baseline / name
        try:
            if not path.is_file() or path.is_symlink():
                raise VerificationError("文件缺失或为符号链接")
            documents[name] = _read_json(path)
        except (OSError, ValueError, VerificationError) as exc:
            errors.append(f"{name}: {exc}")
    if errors:
        return {"status": "FAIL", "errors": errors}
    source_ok, source_errors = verify_source_manifest(
        project_root, documents["source_tree_hash_manifest.json"]
    )
    checksum_ok, checksum_errors = verify_checksum_file(baseline)
    closure_ok, closure_errors = verify_closure(
        documents["sec_final_019_closure.json"],
        documents["default_test_file_access_summary.json"],
        documents["test_result_summary.json"],
        documents["safe_test_baseline_manifest.json"],
        documents["test_inventory.json"],
        _text_sha256(baseline / "source_tree_hash_manifest.json"),
        candidate_precheck,
    )
    errors.extend(source_errors + checksum_errors + closure_errors)
    return {
        "status": "PASS" if source_ok and checksum_ok and closure_ok else "FAIL",
        "baseline_id": documents["safe_test_baseline_manifest.json"].get("baseline_id"),
        "source_manifest_verified": source_ok,
        "baseline_checksums_verified": checksum_ok,
        "closure_conditions_verified": closure_ok,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate-precheck", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(args.baseline, args.project_root, args.candidate_precheck)
    except (OSError, ValueError, VerificationError) as exc:
        result = {"status": "FAIL", "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
