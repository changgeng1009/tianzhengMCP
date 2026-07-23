"""显式恢复单一 S5 Job-owned AutoCAD PID。

此入口只服务于 S5 开发环境的启动失败收束。它从不按进程名批量结束，
不读取或打开 DWG，且必须通过 ``--execute`` 才会触及 ROT/窗口/进程。
默认只构造校验后的 RecoveryEvidenceDev，不执行任何 AutoCAD 操作。
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping

# 直接执行 ``python scripts\recover_s5_owned_autocad.py`` 时，Python 会把
# scripts/ 作为首个 import 根。仅补入本项目真实根，避免依赖当前 cwd/T:。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_nextgen.backends.autocad_launcher import WindowsHwndPidResolver, WindowsProcessIdentityInspector
from mcp_nextgen.backends.s5_autocad_recovery import (
    DEVELOPMENT_RECOVERY_ENV,
    RecoveryEvidenceDev,
    RecoveryPolicy,
    RecoveryResult,
    S5AutoCadRecovery,
    WindowsExactPidTopLevelWindowResolver,
)


S5_ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "s5_real_autocad_backend"
FIXED_AUTOCAD_EXECUTABLE = r"E:\AutoCAD 2026\acad.exe"
RECOVERY_RESULT_NAME = "recovery_result.json"
WM_CLOSE = 0x0010


def _under_s5_artifacts(path: Path) -> Path:
    canonical = path.resolve(strict=False)
    try:
        canonical.relative_to(S5_ARTIFACT_ROOT.resolve(strict=False))
    except ValueError as exc:
        raise ValueError("artifact 目录必须位于 S5 artifacts 根目录") from exc
    return canonical


def build_recovery(
    *,
    evidence: RecoveryEvidenceDev,
    allow_force: bool,
    rot_connector: Callable[[str], Any],
    hwnd_pid_resolver: Callable[[int], int],
    pid_exists: Callable[[int], bool],
    normal_window_closer: Callable[[int], bool],
    process_identity_inspector: Callable[[Any], Any],
    cim_creation_time_provider: Callable[[int], int | None] | None,
    exact_pid_window_resolver: Callable[[int], int | None] | None,
    process_image_name_provider: Callable[[int], str | None] | None,
    force_terminator: Callable[[int], bool] | None,
) -> S5AutoCadRecovery:
    """纯装配函数：测试可注入全部外部依赖，不产生副作用。"""
    return S5AutoCadRecovery(
        rot_connector=rot_connector,
        hwnd_pid_resolver=hwnd_pid_resolver,
        pid_exists=pid_exists,
        normal_window_closer=normal_window_closer,
        process_identity_inspector=process_identity_inspector,
        cim_creation_time_provider=cim_creation_time_provider,
        exact_pid_window_resolver=exact_pid_window_resolver,
        process_image_name_provider=process_image_name_provider,
        force_terminator=force_terminator,
        policy=RecoveryPolicy(allow_force_termination=allow_force),
    )


def write_recovery_result(*, artifact_dir: str | Path, result: RecoveryResult) -> Path:
    """仅写一个不可覆盖 JSON；结果不含 document token 或环境敏感值。"""
    directory = _under_s5_artifacts(Path(artifact_dir))
    if not directory.is_dir():
        raise ValueError("指定 artifact 目录不存在")
    output = directory / RECOVERY_RESULT_NAME
    if output.exists():
        raise FileExistsError("recovery_result.json 已存在，拒绝覆盖")
    output.write_text(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return output


def _rot_connector(progid: str) -> Any:
    """仅在 --execute 后由 S5AutoCadRecovery 调用；不得用于业务执行。"""
    client = importlib.import_module("win32com.client")
    getter = getattr(client, "GetActiveObject")
    return getter(progid)


def _pid_exists(pid: int) -> bool:
    try:
        WindowsProcessIdentityInspector._query_windows(int(pid))
        return True
    except Exception:
        # 某些遗留 AutoCAD 对 PROCESS_QUERY_LIMITED_INFORMATION 返回拒绝访问；
        # 仅将已存在的 CIM 单 PID 记录作为“仍存活”信号，真正的 COM-only
        # 路径仍需 HWND/PID、Path、Version 与 run-window 多数匹配。
        return _cim_creation_filetime(int(pid)) is not None


def _normal_window_close(hwnd: int) -> bool:
    """发送单一 WM_CLOSE；不模拟键盘、不枚举窗口、不按名称关闭。"""
    try:
        from ctypes import WinDLL
        from ctypes.wintypes import BOOL, DWORD, HWND, LPARAM, UINT, WPARAM

        user32 = WinDLL("user32", use_last_error=True)
        user32.PostMessageW.argtypes = (HWND, UINT, WPARAM, LPARAM)
        user32.PostMessageW.restype = BOOL
        return bool(user32.PostMessageW(int(hwnd), WM_CLOSE, 0, 0))
    except Exception:
        return False


def _cim_creation_filetime(pid: int) -> int | None:
    """仅查询单一 PID 的 CIM 创建时间，不枚举/终止任何进程。"""
    command = (
        "$p=Get-CimInstance Win32_Process -Filter 'ProcessId = " + str(int(pid)) + "';"
        "if($p){[Console]::Write($p.CreationDate.ToUniversalTime().ToFileTimeUtc())}"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        value = completed.stdout.strip()
        return int(value) if completed.returncode == 0 and value.isdigit() else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _exact_pid_process_image_name(pid: int) -> str | None:
    """只查询一个 PID 的 tasklist CSV 行；不按名称筛选/终止进程。"""
    try:
        completed = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh", "/fi", f"PID eq {int(pid)}"],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode != 0:
            return None
        rows = list(csv.reader(line for line in completed.stdout.splitlines() if line.strip()))
        if len(rows) != 1 or len(rows[0]) < 2 or rows[0][1].replace(",", "") != str(int(pid)):
            return None
        return rows[0][0]
    except (OSError, subprocess.SubprocessError, ValueError, csv.Error):
        return None


def _terminate_exact_pid_win32(pid: int) -> bool:
    """单 PID Win32 TerminateProcess；仅由受控 force callback 调用。"""
    try:
        from ctypes import WinDLL
        from ctypes.wintypes import BOOL, DWORD, HANDLE

        kernel32 = WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (DWORD, BOOL, DWORD)
        kernel32.OpenProcess.restype = HANDLE
        kernel32.TerminateProcess.argtypes = (HANDLE, DWORD)
        kernel32.TerminateProcess.restype = BOOL
        kernel32.CloseHandle.argtypes = (HANDLE,)
        kernel32.CloseHandle.restype = BOOL
        process = kernel32.OpenProcess(0x0001, False, int(pid))  # PROCESS_TERMINATE，仅此 PID
        if not process:
            return False
        try:
            return bool(kernel32.TerminateProcess(HANDLE(process), 1))
        finally:
            kernel32.CloseHandle(HANDLE(process))
    except Exception:
        return False


def _force_exact_pid_via_cim(pid: int, *, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> bool:
    """Win32 exact force 失败后的最后单 PID CIM fallback。

    命令只嵌入经过 ``int`` 解析的 PID，使用 ``shell=False`` 和精确 WMI
    Filter；既不按名称终止，也不使用 taskkill/Stop-Process。
    """
    exact_pid = int(pid)
    command = (
        "$p=Get-CimInstance -ClassName Win32_Process -Filter 'ProcessId = " + str(exact_pid) + "';"
        "if($null -eq $p){exit 3};"
        "$r=Invoke-CimMethod -InputObject $p -MethodName Terminate -Arguments @{Reason=1};"
        "[Console]::Write($r.ReturnValue)"
    )
    try:
        completed = runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return completed.returncode == 0 and completed.stdout.strip() == "0"
    except (OSError, subprocess.SubprocessError):
        return False


def _force_exact_pid(pid: int) -> bool:
    """最后兜底：先 Win32，失败时才使用精确 PID CIM 终止。"""
    return _terminate_exact_pid_win32(pid) or _force_exact_pid_via_cim(pid)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="恢复精确 S5 Job-owned AutoCAD PID（开发环境）")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--run-window-start-filetime", required=True, type=int)
    parser.add_argument("--run-window-end-filetime", required=True, type=int)
    parser.add_argument("--evidence-process-id", required=True, type=int)
    parser.add_argument("--baseline-pid", action="append", default=[], type=int)
    parser.add_argument("--hwnd", type=int)
    parser.add_argument("--user-no-manual-documents", action="store_true")
    parser.add_argument("--user-confirmed-exact-pid-force", action="store_true")
    parser.add_argument("--allow-force", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    if not args.execute:
        raise SystemExit("必须显式传入 --execute；脚本默认不执行恢复")
    evidence = RecoveryEvidenceDev(
        run_id=args.run_id,
        job_id=args.job_id,
        process_id=args.pid,
        expected_executable_path=FIXED_AUTOCAD_EXECUTABLE,
        run_window_start_filetime=args.run_window_start_filetime,
        run_window_end_filetime=args.run_window_end_filetime,
        evidence_process_id=args.evidence_process_id,
        user_no_manual_docs=bool(args.user_no_manual_documents),
        user_confirmed_exact_pid_force=bool(args.user_confirmed_exact_pid_force),
        baseline_process_ids=tuple(args.baseline_pid),
        hwnd=args.hwnd,
    )
    environment: Mapping[str, str] = dict(os.environ)
    # 入口本身是用户显式 --execute；仍将同一开发门传给 recovery 合同。
    environment = {**environment, DEVELOPMENT_RECOVERY_ENV: "1"}
    recovery = build_recovery(
        evidence=evidence,
        allow_force=bool(args.allow_force),
        rot_connector=_rot_connector,
        hwnd_pid_resolver=WindowsHwndPidResolver(),
        pid_exists=_pid_exists,
        normal_window_closer=_normal_window_close,
        process_identity_inspector=WindowsProcessIdentityInspector(),
        cim_creation_time_provider=_cim_creation_filetime,
        exact_pid_window_resolver=WindowsExactPidTopLevelWindowResolver(),
        process_image_name_provider=_exact_pid_process_image_name,
        force_terminator=_force_exact_pid if args.allow_force else None,
    )
    result = recovery.recover(evidence=evidence, environment=environment)
    write_recovery_result(artifact_dir=args.artifact_dir, result=result)
    return 0 if result.status.startswith("RECOVERED_") else 1


if __name__ == "__main__":  # pragma: no cover - 显式、危险、人工触发入口
    raise SystemExit(main())
