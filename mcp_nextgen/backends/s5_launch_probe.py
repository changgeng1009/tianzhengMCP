"""显式 S5 最小 AutoCAD 启动探针。

该模块用于外部集成测试，默认拒绝执行。它只验证 Job-owned 新会话、默认
空白文档和正常关闭边界：不新建文档，不打开/保存 DWG，也不
创建任何实体。调用者必须传入本阶段 artifacts 下的 evidence JSON 路径。
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Sequence
from uuid import uuid4

from .autocad_com_activation import ComActivationSessionHost, RealComLaunchPolicy
from .autocad_launcher import (
    AutoCadExecutableResolver,
    AutoCadJobOwnedSessionGuard,
    AutoCadLauncherError,
    AutoCadProcessIdentity,
    AutoCadProcessOwnershipRegistry,
    AutoCadSessionIdentity,
    LazyAutoCadComTransport,
    WindowsAcadProcessInspector,
    WindowsHwndPidResolver,
    WindowsProcessIdentityInspector,
)


def _write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_launch_probe(
    *,
    job_id: str,
    evidence_path: Path,
    com_progid: str = "AutoCAD.Application.25.1",
    process_inspector: Callable[[], Sequence[Any]] | None = None,
    transport: LazyAutoCadComTransport | None = None,
    activation_host: ComActivationSessionHost | None = None,
    hwnd_pid_resolver: Callable[[int], int] | None = None,
    process_identity_inspector: Callable[[AutoCadProcessIdentity], AutoCadProcessIdentity] | None = None,
    executable_resolver: AutoCadExecutableResolver | None = None,
) -> dict[str, Any]:
    """只在显式环境变量确认后启动并验证、再关闭 Job-owned 空会话。"""
    evidence: dict[str, Any] = {
        "schema_version": "1.0.0",
        "job_id": job_id,
        "integration_gate": os.environ.get("CAD_S5_AUTOCAD_INTEGRATION"),
        "synthetic_dwg_created": False,
        "save_calls": 0,
        "user_dwg_reads": 0,
        "user_dwg_writes": 0,
        "user_documents_modified": 0,
        "tianzheng_connections": 0,
        "entities_created": 0,
        "pre_acad_process_count": None,
        "post_acad_process_count": None,
        "launch_command_arguments": [],
        "launch_shell": False,
        "os_process_identity": None,
        "com_session": None,
        "default_document_inspection": {"performed": False, "documents": []},
        "shutdown": {"attempted": False, "close_without_save_calls": 0, "post_document_count": None, "quit_called": False},
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if os.environ.get("CAD_S5_AUTOCAD_INTEGRATION") != "1":
        evidence.update({"status": "BLOCKED", "error_code": "CAD_S5_AUTOCAD_INTEGRATION_REQUIRED"})
        _write_evidence(evidence_path, evidence)
        return evidence
    resolved_process_inspector: Callable[[], Sequence[Any]] | None = None
    ownership = AutoCadProcessOwnershipRegistry()
    try:
        transport = transport or LazyAutoCadComTransport()
        resolved_process_inspector = process_inspector or WindowsAcadProcessInspector()
        activation_host = activation_host or ComActivationSessionHost(policy=RealComLaunchPolicy(mode="com_activation"))
        hwnd_pid_resolver = hwnd_pid_resolver or WindowsHwndPidResolver()
        process_identity_inspector = process_identity_inspector or WindowsProcessIdentityInspector()
        executable_resolver = executable_resolver or AutoCadExecutableResolver()
        pre_processes = tuple(resolved_process_inspector())
        evidence["pre_acad_process_count"] = len(pre_processes)
        evidence["pre_acad_process_ids"] = [item.pid for item in pre_processes]
        if pre_processes:
            raise AutoCadLauncherError("EXISTING_PROCESS_UNKNOWN_OWNER", "COM activation 前发现既有 acad.exe")
        with activation_host.activation_context():
            application = transport.activate_isolated(com_progid)
        application_version = str(application.Version)
        if not application_version.startswith("25"):
            raise AutoCadLauncherError("AUTOCAD_VERSION_MISMATCH", f"COM Application.Version 不属于 AutoCAD 2026: {application_version}")
        process_id = hwnd_pid_resolver(int(application.HWND))
        activation_processes = tuple(resolved_process_inspector())
        pre_process_ids = {item.pid for item in pre_processes}
        added_process_ids = sorted({item.pid for item in activation_processes} - pre_process_ids)
        evidence["post_activation_acad_process_count"] = len(activation_processes)
        evidence["post_activation_acad_process_ids"] = [item.pid for item in activation_processes]
        evidence["com_activation_added_process_ids"] = added_process_ids
        if added_process_ids != [process_id]:
            raise AutoCadLauncherError(
                "AUTOCAD_SESSION_UNSAFE",
                "DispatchEx 后 HWND PID 不是唯一新增 acad.exe 进程",
                details={"hwnd_pid": process_id, "added_process_ids": added_process_ids},
            )
        executable = executable_resolver.resolve(os.environ.get("AUTOCAD_EXE_PATH") or None)
        process = process_identity_inspector(AutoCadProcessIdentity(
            job_id=job_id,
            process_id=process_id,
            executable_path=str(executable),
            process_start_time=monotonic(),
            launched_by_job=True,
            ownership_token=uuid4().hex,
            command_arguments=(),
            shell=False,
        ))
        ownership.register(process)
        session = AutoCadSessionIdentity(
            job_id=job_id,
            process=process,
            com_progid=com_progid,
            autocad_version=application_version,
            document_count=int(application.Documents.Count),
            connected_at=monotonic(),
        )
        evidence["activation_mode"] = "com_activation"
        evidence["launch_command_arguments"] = []
        evidence["launch_shell"] = False
        evidence["os_process_identity"] = {
            "process_id": process.process_id,
            "executable_path": process.os_verified_executable_path,
            "creation_filetime": process.os_process_creation_filetime,
            "verified_after_com_activation_before_document_access": True,
        }
        guard = AutoCadJobOwnedSessionGuard(
            ownership=ownership,
            hwnd_pid_resolver=hwnd_pid_resolver,
        )
        verification = guard.verify(session, application)
        evidence["com_session"] = {
            "progid": session.com_progid,
            "application_version": session.autocad_version,
            "application_hwnd": verification.application_hwnd,
            "hwnd_process_id": verification.hwnd_process_id,
        }
        evidence["default_document_inspection"] = {
            "performed": True,
            "all_default_blank": verification.has_only_new_default_blank_documents,
            "documents": [asdict(item) for item in verification.documents],
        }
        plan = guard.plan_safe_shutdown(verification)
        # 使用刚刚由 Guard 只读验证过的 Documents；不使用全局当前文档回退。
        current_documents = list(application.Documents)
        if tuple(str(item.Name) for item in current_documents) != plan.close_without_save_names:
            raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "关闭前默认文档集合发生变化")
        evidence["shutdown"]["attempted"] = True
        for document in current_documents:
            document.Close(False)
            evidence["shutdown"]["close_without_save_calls"] += 1
        remaining = int(application.Documents.Count)
        evidence["shutdown"]["post_document_count"] = remaining
        if remaining != 0 or not ownership.may_quit(session, document_count=remaining):
            raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "默认文档关闭后不满足 Job-owned Quit 条件")
        application.Quit()
        evidence["shutdown"]["quit_called"] = True
        evidence.update({
            "status": "PASS",
            "process": process.to_dict(),
            "session": session.to_dict(),
            "default_documents_closed_without_save": list(plan.close_without_save_names),
            "job_owned_instance_quit": True,
        })
    except AutoCadLauncherError as exc:
        evidence.update({"status": "FAILED", "error_code": exc.error_code, "error": str(exc), "details": exc.details})
    except Exception as exc:
        evidence.update({"status": "FAILED", "error_code": "AUTOCAD_LAUNCH_PROBE_UNEXPECTED", "error": type(exc).__name__})
    finally:
        if os.environ.get("CAD_S5_AUTOCAD_INTEGRATION") == "1":
            try:
                if resolved_process_inspector is None:
                    raise AutoCadLauncherError("AUTOCAD_PROCESS_INSPECTION_FAILED", "进程检查器未初始化")
                post_processes = tuple(resolved_process_inspector())
                evidence["post_acad_process_count"] = len(post_processes)
                evidence["post_acad_process_ids"] = [item.pid for item in post_processes]
            except AutoCadLauncherError as exc:
                evidence["post_acad_process_inspection_error"] = exc.error_code
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_evidence(evidence_path, evidence)
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S5 显式 AutoCAD Job-owned 空会话启动探针")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--com-progid", default="AutoCAD.Application.25.1")
    args = parser.parse_args(argv)
    result = run_launch_probe(job_id=args.job_id, evidence_path=Path(args.evidence), com_progid=args.com_progid)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
