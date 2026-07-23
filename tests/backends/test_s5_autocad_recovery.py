"""S5 开发期 AutoCAD 恢复的纯 Mock 合同。

本文件不导入 pywin32、不连接 ROT、不启动或终止真实进程。所有外部行为均由
Fake 注入，以确保恢复逻辑只能针对 evidence 中的精确 Job-owned PID。
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp_nextgen.backends.autocad_com_activation import RPC_E_CALL_REJECTED
from mcp_nextgen.backends.autocad_launcher import AutoCadProcessIdentity
from mcp_nextgen.backends.s5_autocad_recovery import (
    RecoveryEvidence,
    RecoveryEvidenceDev,
    RecoveryPolicy,
    S5AutoCadRecovery,
    WindowsExactPidTopLevelWindowResolver,
)


class FakeComBusyError(Exception):
    def __init__(self, hresult: int) -> None:
        super().__init__("fake COM busy")
        self.hresult = hresult


@dataclass
class _ProcessState:
    alive: bool = True
    creation_filetime: int = 123456


class _SyntheticDocument:
    def __init__(self, owner: "_Application", path: str, *, busy_attempts: int = 0) -> None:
        self._owner = owner
        self.FullName = path
        self.Name = Path(path).name
        self._busy_attempts = busy_attempts
        self.close_calls = 0

    def Close(self, save_changes: bool) -> None:  # noqa: N802 - COM 形状
        assert save_changes is False
        self.close_calls += 1
        if self.close_calls <= self._busy_attempts:
            raise FakeComBusyError(RPC_E_CALL_REJECTED)
        self._owner.Documents._items.clear()


class _NonRetryableCloseDocument(_SyntheticDocument):
    def Close(self, save_changes: bool) -> None:  # noqa: N802 - COM 形状
        assert save_changes is False
        self.close_calls += 1
        raise RuntimeError("synthetic close failure")


class _Documents:
    def __init__(self, document: _SyntheticDocument | None = None) -> None:
        self._items: list[_SyntheticDocument] = [] if document is None else [document]

    @property
    def Count(self) -> int:  # noqa: N802 - COM 形状
        return len(self._items)

    def __iter__(self):
        return iter(tuple(self._items))


class _Application:
    HWND = 7722

    def __init__(self, state: _ProcessState, document_path: str, *, close_busy_attempts: int = 0,
                 quit_busy_attempts: int = 0) -> None:
        self._state = state
        self.Documents = _Documents()
        self.Documents._items.append(_SyntheticDocument(self, document_path, busy_attempts=close_busy_attempts))
        self._quit_busy_attempts = quit_busy_attempts
        self.quit_calls = 0

    def Quit(self) -> None:  # noqa: N802 - COM 形状
        self.quit_calls += 1
        if self.quit_calls <= self._quit_busy_attempts:
            raise FakeComBusyError(RPC_E_CALL_REJECTED)
        self._state.alive = False


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _evidence(tmp_path: Path, *, pid: int = 7001) -> RecoveryEvidence:
    synthetic = tmp_path / "sandbox" / "s5_real_autocad_backend_mvp.dwg"
    return RecoveryEvidence(
        run_id="run-1", job_id="job-1", process_id=pid, ownership_token="must-not-be-emitted",
        expected_executable_path=r"E:\AutoCAD 2026\acad.exe", process_creation_filetime=123456,
        synthetic_document_path=str(synthetic), artifact_root=str(tmp_path), hwnd=7722,
    )


def _identity(evidence: RecoveryEvidence, *, pid: int | None = None, executable_path: str | None = None,
              creation_filetime: int | None = None) -> AutoCadProcessIdentity:
    return AutoCadProcessIdentity(
        job_id=evidence.job_id,
        process_id=evidence.process_id if pid is None else pid,
        executable_path=evidence.expected_executable_path,
        process_start_time=0.0,
        launched_by_job=True,
        ownership_token=evidence.ownership_token,
        os_verified_executable_path=evidence.expected_executable_path if executable_path is None else executable_path,
        os_process_creation_filetime=evidence.process_creation_filetime if creation_filetime is None else creation_filetime,
    )


def _recovery(evidence: RecoveryEvidence, state: _ProcessState, application: _Application, *,
              identity: Any | None = None, hwnd_pid: int | None = None, normal_window_closer=None,
              force_terminator=None, policy: RecoveryPolicy | None = None, sleeper=None) -> S5AutoCadRecovery:
    clock = _Clock()
    return S5AutoCadRecovery(
        process_identity_inspector=(lambda _value: _identity(evidence) if identity is None else identity),
        pid_exists=lambda pid: pid == evidence.process_id and state.alive,
        rot_connector=lambda _progid: application,
        hwnd_pid_resolver=lambda _hwnd: evidence.process_id if hwnd_pid is None else hwnd_pid,
        normal_window_closer=normal_window_closer or (lambda _hwnd: None),
        force_terminator=force_terminator or (lambda _pid: None),
        policy=policy or RecoveryPolicy(),
        clock=clock,
        sleeper=sleeper or clock.sleep,
    )


def test_recovery_is_disabled_without_explicit_development_gate(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, evidence.synthetic_document_path)
    recovery = _recovery(evidence, state, application)

    result = recovery.recover(evidence=evidence, environment={})

    assert result.status == "BLOCKED"
    assert result.error_code == "S5_DEVELOPMENT_RECOVERY_DISABLED"
    assert result.operations == ()
    assert result.process_ids == (evidence.process_id,)
    assert application.quit_calls == 0


def test_recovery_requires_exact_pid_path_and_creation_identity_before_any_close(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, evidence.synthetic_document_path)
    bad_identity = _identity(evidence, executable_path=r"E:\Other\acad.exe")
    recovery = _recovery(evidence, state, application, identity=bad_identity)

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "BLOCKED"
    assert result.error_code == "S5_RECOVERY_EVIDENCE_MISMATCH"
    assert result.operations == ("evidence_validated",)
    assert application.Documents.Count == 1
    assert application.quit_calls == 0


def test_recovery_requires_rot_hwnd_to_exact_job_owned_pid(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, evidence.synthetic_document_path)
    recovery = _recovery(evidence, state, application, hwnd_pid=evidence.process_id + 1)

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "BLOCKED"
    assert result.error_code == "AUTOCAD_COM_INSTANCE_IDENTITY_MISMATCH"
    assert "rot_connected" in result.operations
    assert application.Documents.Count == 1
    assert application.quit_calls == 0


def test_recovery_retries_two_rpc_busy_calls_then_closes_exact_synthetic_document(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, evidence.synthetic_document_path, close_busy_attempts=2)
    sleeps: list[float] = []
    recovery = _recovery(evidence, state, application, sleeper=sleeps.append)

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "RECOVERED_COM_ROT"
    assert result.error_code is None
    assert application.Documents.Count == 0
    assert application.quit_calls == 1
    assert sleeps == [0.5, 0.5]
    assert result.process_ids == (evidence.process_id,)


def test_normal_window_close_is_fallback_and_force_is_never_a_batch_operation(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, evidence.synthetic_document_path)
    window_closes: list[int] = []
    forced: list[int] = []

    def connector():
        raise RuntimeError("ROT unavailable")

    recovery = S5AutoCadRecovery(
        process_identity_inspector=lambda _value: _identity(evidence),
        pid_exists=lambda pid: pid == evidence.process_id and state.alive,
        rot_connector=connector,
        hwnd_pid_resolver=lambda _hwnd: evidence.process_id,
        normal_window_closer=lambda hwnd: (window_closes.append(hwnd), setattr(state, "alive", False)),
        force_terminator=lambda pid: forced.append(pid),
        policy=RecoveryPolicy(), clock=lambda: 0.0, sleeper=lambda _seconds: None,
    )

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "RECOVERED_WINDOW_CLOSE"
    assert window_closes == [evidence.hwnd]
    assert forced == []
    assert result.process_ids == (evidence.process_id,)
    assert "normal_window_close" in result.operations


def test_force_recovery_requires_all_three_gates_and_normal_close_attempt(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, evidence.synthetic_document_path)
    force_calls: list[int] = []
    normal_calls: list[int] = []

    clock = _Clock()
    recovery = S5AutoCadRecovery(
        process_identity_inspector=lambda _value: _identity(evidence),
        pid_exists=lambda pid: pid == evidence.process_id and state.alive,
        rot_connector=lambda _progid: (_ for _ in ()).throw(RuntimeError("ROT unavailable")),
        hwnd_pid_resolver=lambda _hwnd: evidence.process_id,
        normal_window_closer=lambda hwnd: normal_calls.append(hwnd) or True,
        force_terminator=lambda pid: force_calls.append(pid) or setattr(state, "alive", False) or True,
        policy=RecoveryPolicy(allow_force_termination=True), clock=clock, sleeper=clock.sleep,
    )
    result = recovery.recover(
        evidence=evidence,
        environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"},
    )

    assert result.status == "RECOVERED_FORCE_EXACT_PID"
    assert normal_calls == [evidence.hwnd]
    assert force_calls == [evidence.process_id]
    assert result.process_ids == (evidence.process_id,)
    assert result.operations[-1] == "force_exact_pid"
    assert result.warnings == ("AUTOCAD_JOB_OWNED_PROCESS_FORCE_RECOVERED",)


def test_force_recovery_is_not_authorized_without_explicit_force_policy(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, evidence.synthetic_document_path)
    force_calls: list[int] = []
    clock = _Clock()
    recovery = S5AutoCadRecovery(
        process_identity_inspector=lambda _value: _identity(evidence),
        pid_exists=lambda pid: pid == evidence.process_id and state.alive,
        rot_connector=lambda _progid: (_ for _ in ()).throw(RuntimeError("ROT unavailable")),
        hwnd_pid_resolver=lambda _hwnd: evidence.process_id,
        normal_window_closer=lambda _hwnd: True,
        force_terminator=lambda pid: force_calls.append(pid) or True,
        policy=RecoveryPolicy(allow_force_termination=False), clock=clock, sleeper=clock.sleep,
    )

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "FAILED"
    assert result.error_code == "AUTOCAD_RECOVERY_FORCE_NOT_AUTHORIZED"
    assert force_calls == []


def test_recovery_result_evidence_is_structured_and_never_serializes_ownership_token(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, evidence.synthetic_document_path)
    recovery = _recovery(evidence, state, application)
    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    payload = result.to_dict()
    assert set(("status", "error_code", "error_stage", "operations", "process_ids")) <= set(payload)
    assert payload["process_ids"] == [evidence.process_id]
    assert "must-not-be-emitted" not in repr(payload)


def _dev_evidence(tmp_path: Path, *, no_manual_docs: bool = True) -> RecoveryEvidenceDev:
    return RecoveryEvidenceDev(
        run_id="startup-failure-run", job_id="startup-failure-job", process_id=8118,
        expected_executable_path=r"E:\AutoCAD 2026\acad.exe",
        run_window_start_filetime=123450, run_window_end_filetime=123460,
        evidence_process_id=8118, user_no_manual_docs=no_manual_docs,
        baseline_process_ids=(), hwnd=7722,
    )


def _dev_identity(evidence: RecoveryEvidenceDev, *, executable_path: str | None = None,
                  creation_filetime: int = 123456) -> AutoCadProcessIdentity:
    return AutoCadProcessIdentity(
        job_id=evidence.job_id, process_id=evidence.process_id,
        executable_path=evidence.expected_executable_path, process_start_time=0.0,
        launched_by_job=True, ownership_token="not-a-real-token",
        os_verified_executable_path=evidence.expected_executable_path if executable_path is None else executable_path,
        os_process_creation_filetime=creation_filetime,
    )


def _dev_recovery(evidence: RecoveryEvidenceDev, state: _ProcessState, application: _Application, *,
                  identity: AutoCadProcessIdentity | None = None, rot_connector=None,
                  normal_window_closer=None, force_terminator=None,
                  policy: RecoveryPolicy | None = None, process_identity_inspector=None,
                  cim_creation_time_provider=None, exact_pid_window_resolver=None,
                  process_image_name_provider=None) -> S5AutoCadRecovery:
    clock = _Clock()
    return S5AutoCadRecovery(
        process_identity_inspector=process_identity_inspector or (lambda _value: identity or _dev_identity(evidence)),
        cim_creation_time_provider=cim_creation_time_provider,
        exact_pid_window_resolver=exact_pid_window_resolver,
        process_image_name_provider=process_image_name_provider,
        pid_exists=lambda pid: pid == evidence.process_id and state.alive,
        rot_connector=rot_connector or (lambda _progid: application),
        hwnd_pid_resolver=lambda _hwnd: evidence.process_id,
        normal_window_closer=normal_window_closer or (lambda _hwnd: False),
        force_terminator=force_terminator or (lambda _pid: False),
        policy=policy or RecoveryPolicy(), clock=clock, sleeper=clock.sleep,
    )


def test_dev_startup_recovery_closes_only_declared_job_owned_documents_after_majority_match(tmp_path: Path) -> None:
    evidence = _dev_evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, r"C:\\temporary-default.dwg", close_busy_attempts=2)
    document = application.Documents._items[0]
    recovery = _dev_recovery(evidence, state, application)

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "RECOVERED_COM_ROT"
    assert result.error_code is None
    assert result.process_ids == (evidence.process_id,)
    assert result.operations == (
        "dev_evidence_validated", "os_identity_verified", "rot_connected", "rot_pid_verified",
        "declared_dev_documents_closed", "application_quit",
    )
    assert application.Documents.Count == 0
    assert application.quit_calls == 1
    assert document.close_calls == 3  # 两次 RPC busy 后第三次 Close(False) 成功。


def test_dev_recovery_uses_current_rot_hwnd_for_normal_close_after_post_identity_failure(tmp_path: Path) -> None:
    """ROT 已完成 HWND→PID 验证后，Close 失败不得丢弃该 HWND。"""
    evidence = _dev_evidence(tmp_path)
    evidence = RecoveryEvidenceDev(**{**evidence.__dict__, "hwnd": None})
    state = _ProcessState()
    application = _Application(state, r"C:\\temporary-default.dwg")
    application.Documents._items[:] = [_NonRetryableCloseDocument(application, r"C:\\temporary-default.dwg")]
    normal_calls: list[int] = []
    recovery = _dev_recovery(
        evidence,
        state,
        application,
        normal_window_closer=lambda hwnd: normal_calls.append(hwnd) or setattr(state, "alive", False) or True,
    )

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "RECOVERED_WINDOW_CLOSE"
    assert normal_calls == [application.HWND]
    assert "rot_pid_verified" in result.operations
    assert "normal_window_close" in result.operations


def test_dev_startup_recovery_rejects_wrong_executable_path_before_rot_or_document_close(tmp_path: Path) -> None:
    evidence = _dev_evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, r"C:\\temporary-default.dwg")
    recovery = _dev_recovery(evidence, state, application, identity=_dev_identity(evidence, executable_path=r"E:\\Other\\acad.exe"))

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "BLOCKED"
    assert result.error_code == "S5_RECOVERY_EVIDENCE_MISMATCH"
    assert result.error_stage == "OS_PROCESS_IDENTITY"
    assert result.operations == ("dev_evidence_validated",)
    assert application.Documents.Count == 1
    assert application.quit_calls == 0


def test_dev_startup_recovery_rejects_creation_time_outside_recorded_window(tmp_path: Path) -> None:
    evidence = _dev_evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, r"C:\\temporary-default.dwg")
    recovery = _dev_recovery(evidence, state, application, identity=_dev_identity(evidence, creation_filetime=123999))

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "BLOCKED"
    assert result.error_code == "S5_RECOVERY_EVIDENCE_MISMATCH"
    assert application.Documents.Count == 1


def test_dev_startup_recovery_requires_explicit_user_no_manual_documents_declaration(tmp_path: Path) -> None:
    evidence = _dev_evidence(tmp_path, no_manual_docs=False)
    state = _ProcessState()
    application = _Application(state, r"C:\\temporary-default.dwg")
    recovery = _dev_recovery(evidence, state, application)

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "BLOCKED"
    assert result.error_code == "S5_RECOVERY_EVIDENCE_MISMATCH"
    assert result.operations == ()
    assert application.Documents.Count == 1


def test_dev_startup_force_is_exact_pid_only_after_normal_close_and_two_explicit_gates(tmp_path: Path) -> None:
    evidence = _dev_evidence(tmp_path)
    state = _ProcessState()
    application = _Application(state, r"C:\\temporary-default.dwg")
    normal_calls: list[int] = []
    force_calls: list[int] = []

    recovery = _dev_recovery(
        evidence, state, application,
        rot_connector=lambda _progid: (_ for _ in ()).throw(RuntimeError("ROT unavailable")),
        normal_window_closer=lambda hwnd: normal_calls.append(hwnd) or True,
        force_terminator=lambda pid: force_calls.append(pid) or setattr(state, "alive", False) or True,
        policy=RecoveryPolicy(allow_force_termination=True),
    )
    result = recovery.recover(
        evidence=evidence,
        environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"},
    )

    assert result.status == "RECOVERED_FORCE_EXACT_PID"
    assert normal_calls == [evidence.hwnd]
    assert force_calls == [evidence.process_id]
    assert result.process_ids == (evidence.process_id,)
    assert result.operations[-1] == "force_exact_pid"


def test_exact_pid_top_level_window_resolver_requires_exactly_one_visible_unowned_candidate() -> None:
    resolver = WindowsExactPidTopLevelWindowResolver(
        enumerate_windows=lambda callback: [callback(hwnd) for hwnd in (101, 102)] and True,
        is_visible=lambda hwnd: hwnd in {101, 102},
        owner_of=lambda _hwnd: 0,
        pid_of=lambda hwnd: 8118 if hwnd == 101 else 9999,
    )
    assert resolver(8118) == 101
    ambiguous = WindowsExactPidTopLevelWindowResolver(
        enumerate_windows=lambda callback: [callback(hwnd) for hwnd in (101, 102)] and True,
        is_visible=lambda _hwnd: True, owner_of=lambda _hwnd: 0, pid_of=lambda _hwnd: 8118,
    )
    assert ambiguous(8118) is None


def test_dev_cim_com_recovery_uses_exact_resolved_window_when_rot_is_unavailable(tmp_path: Path) -> None:
    evidence = _dev_evidence(tmp_path)
    evidence = RecoveryEvidenceDev(**{**evidence.__dict__, "hwnd": None})
    state = _ProcessState()
    application = _Application(state, r"C:\\temporary-default.dwg")
    window_closes: list[int] = []
    recovery = _dev_recovery(
        evidence,
        state,
        application,
        process_identity_inspector=lambda _value: (_ for _ in ()).throw(OSError(5, "access denied")),
        cim_creation_time_provider=lambda pid: 123456 if pid == evidence.process_id else None,
        exact_pid_window_resolver=lambda pid: 7722 if pid == evidence.process_id else None,
        rot_connector=lambda _progid: (_ for _ in ()).throw(RuntimeError("ROT unavailable")),
        normal_window_closer=lambda hwnd: window_closes.append(hwnd) or setattr(state, "alive", False) or True,
    )

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "RECOVERED_WINDOW_CLOSE"
    assert window_closes == [7722]
    assert "cim_creation_window_verified" in result.operations
    assert "exact_pid_top_level_hwnd_resolved" in result.operations
    assert "force_exact_pid" not in result.operations


def test_user_confirmed_dev_force_requires_exact_pid_cim_image_and_unavailable_normal_paths(tmp_path: Path) -> None:
    evidence = _dev_evidence(tmp_path)
    evidence = RecoveryEvidenceDev(**{**evidence.__dict__, "hwnd": None, "user_confirmed_exact_pid_force": True})
    state = _ProcessState()
    application = _Application(state, r"C:\\temporary-default.dwg")
    force_calls: list[int] = []
    recovery = _dev_recovery(
        evidence,
        state,
        application,
        process_identity_inspector=lambda _value: (_ for _ in ()).throw(OSError(5, "access denied")),
        cim_creation_time_provider=lambda pid: 123456 if pid == evidence.process_id else None,
        exact_pid_window_resolver=lambda _pid: None,
        process_image_name_provider=lambda pid: "acad.exe" if pid == evidence.process_id else None,
        rot_connector=lambda _progid: (_ for _ in ()).throw(RuntimeError("ROT unavailable")),
        force_terminator=lambda pid: force_calls.append(pid) or setattr(state, "alive", False) or True,
        policy=RecoveryPolicy(allow_force_termination=True),
    )

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "RECOVERED_FORCE_EXACT_PID"
    assert force_calls == [evidence.process_id]
    assert "normal_window_close_unavailable" in result.operations
    assert result.warnings == ("AUTOCAD_USER_CONFIRMED_EXACT_PID_DEV_FORCE_RECOVERED",)


def test_user_confirmed_dev_force_rejects_non_acad_process_image(tmp_path: Path) -> None:
    evidence = _dev_evidence(tmp_path)
    evidence = RecoveryEvidenceDev(**{**evidence.__dict__, "hwnd": None, "user_confirmed_exact_pid_force": True})
    state = _ProcessState()
    application = _Application(state, r"C:\\temporary-default.dwg")
    recovery = _dev_recovery(
        evidence,
        state,
        application,
        process_identity_inspector=lambda _value: (_ for _ in ()).throw(OSError(5, "access denied")),
        cim_creation_time_provider=lambda _pid: 123456,
        exact_pid_window_resolver=lambda _pid: None,
        process_image_name_provider=lambda _pid: "notepad.exe",
        rot_connector=lambda _progid: (_ for _ in ()).throw(RuntimeError("ROT unavailable")),
        force_terminator=lambda _pid: (_ for _ in ()).throw(AssertionError("不得 force")),
        policy=RecoveryPolicy(allow_force_termination=True),
    )

    result = recovery.recover(evidence=evidence, environment={"CAD_S5_DEVELOPMENT_AUTORECOVERY": "1"})

    assert result.status == "BLOCKED"
    assert result.error_stage == "USER_CONFIRMED_DEV_FORCE_EVIDENCE"


def test_recovery_module_has_no_direct_or_batch_process_kill_implementation() -> None:
    source_path = Path(__file__).parents[2] / "mcp_nextgen" / "backends" / "s5_autocad_recovery.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    # ctypes 仅用于 EnumWindows/GetWindowThreadProcessId 的只读 HWND 解析；
    # 真正的 force callback 位于显式 CLI 脚本，不在 recovery 模块内。
    assert not ({"subprocess", "psutil", "os"} & imported)
    assert not ({"taskkill", "TerminateProcess", "kill", "terminate"} & called_names)
    assert not ({"TerminateProcess", "kill", "terminate"} & called_attributes)
