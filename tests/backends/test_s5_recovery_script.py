"""S5 精确 PID 恢复 CLI 的纯命令构造测试；绝不调用 PowerShell/AutoCAD。"""
from __future__ import annotations

import subprocess

from scripts.recover_s5_owned_autocad import _force_exact_pid_via_cim


def test_cim_force_fallback_uses_exact_numeric_pid_shell_false_and_returnvalue_zero() -> None:
    calls: list[tuple[list[str], dict]] = []

    def runner(args, **kwargs):
        calls.append((list(args), kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="0", stderr="")

    assert _force_exact_pid_via_cim(32652, runner=runner) is True
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    assert "Filter 'ProcessId = 32652'" in args[4]
    assert "Invoke-CimMethod" in args[4]
    assert "Stop-Process" not in args[4] and "taskkill" not in args[4]
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 15


def test_cim_force_fallback_rejects_nonzero_returnvalue_or_runner_error() -> None:
    failed = lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="5", stderr="")
    assert _force_exact_pid_via_cim(32652, runner=failed) is False

    def unavailable(*_args, **_kwargs):
        raise OSError("PowerShell unavailable")

    assert _force_exact_pid_via_cim(32652, runner=unavailable) is False
