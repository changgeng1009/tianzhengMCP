"""S5 显式外部集成入口：默认拒绝，且只写一个受控 evidence run 目录。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping
from uuid import uuid4
from dataclasses import dataclass

# 直接执行 ``python scripts\\run_s5_synthetic_integration.py`` 时，Python 会把
# scripts/ 作为首个 import 根。仅补入本项目真实根，避免依赖当前 cwd/T:。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_nextgen.backends.real_autocad_com import RealAutoCadComBackendError
from mcp_nextgen.backends.s5_synthetic_runner import run_s5_synthetic_mvp


EVIDENCE_FILES = (
    "s5_execution_summary.json", "com_identity.json", "synthetic_document_identity.json",
    "entity_creation_evidence.json", "save_close_reopen_evidence.json", "persistence_verification.json",
    "idempotency_verification.json", "s5_test_results.json", "s5_final_report.md",
)


@dataclass(frozen=True)
class S5EvidenceRunRoot:
    """仅由本入口创建的单次 run 根目录能力对象。"""

    path: Path


def create_s5_evidence_run_root(path: str | Path) -> S5EvidenceRunRoot:
    root = Path(path).resolve(strict=False)
    if root.exists():
        raise RealAutoCadComBackendError("S5_EVIDENCE_DIRECTORY_EXISTS", "evidence run 目录必须在运行前不存在")
    root.mkdir(parents=True)
    # runner 唯一允许的 DWG 目标目录；它属于刚创建且当前入口持有的 run 根。
    (root / "sandbox").mkdir()
    return S5EvidenceRunRoot(path=root)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    # 不接受 approval 对象/secret；防止后续调用者意外把 token 写进 evidence。
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    if "ownership_token" in encoded or "document_token" in encoded:
        raise RealAutoCadComBackendError("S5_EVIDENCE_SECRET_FORBIDDEN", "evidence 不得序列化审批或 ownership token")
    path.write_text(encoded + "\n", encoding="utf-8")


def write_s5_evidence_bundle(*, evidence_dir: str | Path, status: str, result: Mapping[str, Any] | None,
                             error: Exception | None = None, test_results: Mapping[str, Any] | None = None,
                             run_root: S5EvidenceRunRoot | None = None) -> Path:
    """为一次运行写固定九个文件；目录必须是新的单一 run 目录。"""
    root = Path(evidence_dir).resolve(strict=False)
    if run_root is None:
        if root.exists():
            raise RealAutoCadComBackendError("S5_EVIDENCE_DIRECTORY_EXISTS", "evidence run 目录必须在运行前不存在")
        root.mkdir(parents=True)
    elif run_root.path != root or not root.is_dir() or not (root / "sandbox").is_dir():
        raise RealAutoCadComBackendError("S5_EVIDENCE_DIRECTORY_UNREGISTERED", "evidence 根目录不是本次入口创建的 run 根")
    if any((root / name).exists() for name in EVIDENCE_FILES):
        raise RealAutoCadComBackendError("S5_EVIDENCE_OVERWRITE_FORBIDDEN", "不得覆盖已有 evidence 文件")
    payload = dict(result or {})
    summary = {"status": status, "created_at": datetime.now(timezone.utc).isoformat(),
               "synthetic": bool(payload.get("synthetic", False)),
               "error_code": getattr(error, "code", getattr(error, "error_code", None)),
               "error_stage": getattr(error, "stage", None),
               "exception_type": None if error is None else type(error).__name__,
               # COM 异常 message 可能含路径、参数或其他敏感运行时信息；evidence
               # 只保留可审计的安全分类，绝不序列化原始异常文本。
               "error_present": error is not None}
    document = dict(payload.get("document_identity", {}))
    creation = {"entities_created": payload.get("entities_created", 0), "synthetic": bool(payload.get("synthetic", False))}
    persistence = {"persistence_verified": bool(payload.get("persistence_verified", False))}
    reopen = {"close_and_reopen_completed": bool(payload.get("persistence_verified", False)), "synthetic": bool(payload.get("synthetic", False))}
    _write_json(root / "s5_execution_summary.json", summary)
    _write_json(root / "com_identity.json", dict(payload.get("com_identity", {})))
    _write_json(root / "synthetic_document_identity.json", document)
    _write_json(root / "entity_creation_evidence.json", creation)
    _write_json(root / "save_close_reopen_evidence.json", reopen)
    _write_json(root / "persistence_verification.json", persistence)
    _write_json(root / "idempotency_verification.json", {"results": list(payload.get("idempotency_results", []))})
    _write_json(root / "s5_test_results.json", dict(test_results or {"external_integration": "NOT_RUN_BY_ENTRY"}))
    (root / "s5_final_report.md").write_text(
        f"# S5 Synthetic Integration\n\n状态：`{status}`\n\n"
        f"- synthetic：`{summary['synthetic']}`\n- 审批 token：未写入\n- 用户 DWG：未访问\n"
        f"- 错误：`{summary['error_code'] or 'none'}` / 阶段：`{summary['error_stage'] or 'none'}`\n", encoding="utf-8",
    )
    return root


def main(argv: list[str] | None = None, *, runner: Callable[..., Mapping[str, Any]] = run_s5_synthetic_mvp) -> int:
    parser = argparse.ArgumentParser(description="显式执行 S5 synthetic AutoCAD COM 集成")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--job-id", default="s5-" + uuid4().hex)
    parser.add_argument("--plan-hash", required=True)
    args = parser.parse_args(argv)
    artifact_parent = Path(args.artifact_root).resolve(strict=False)
    requested_root = Path(args.evidence_dir).resolve(strict=False)
    if requested_root.parent != artifact_parent:
        raise RealAutoCadComBackendError("S5_EVIDENCE_DIRECTORY_UNSAFE", "run evidence 根必须是指定 artifact_root 的直接子目录")
    run_root = create_s5_evidence_run_root(args.evidence_dir)
    if os.environ.get("CAD_S5_AUTOCAD_INTEGRATION") != "1":
        error = RealAutoCadComBackendError("S5_EXTERNAL_INTEGRATION_DISABLED", "需要 CAD_S5_AUTOCAD_INTEGRATION=1")
        write_s5_evidence_bundle(evidence_dir=run_root.path, run_root=run_root, status="BLOCKED", result=None, error=error)
        return 2
    try:
        result = runner(artifact_root=run_root.path, run_id=run_root.path.name, job_id=args.job_id,
                        plan_hash=args.plan_hash, integration_enabled=True,
                        client_importer=lambda: importlib.import_module("win32com.client"))
    except Exception as error:
        write_s5_evidence_bundle(evidence_dir=run_root.path, run_root=run_root, status="FAILED", result=None, error=error)
        return 1
    write_s5_evidence_bundle(evidence_dir=run_root.path, run_root=run_root, status="COMPLETED", result=result)
    return 0


if __name__ == "__main__":  # pragma: no cover - 显式外部入口
    raise SystemExit(main())
