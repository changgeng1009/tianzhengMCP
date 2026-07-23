"""S5 Launcher 的纯 Mock 测试；不得启动 AutoCAD 或连接 COM。"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import subprocess

import pytest

from mcp_nextgen.backends.autocad_launcher import (
    AutoCadExecutableResolver,
    AutoCadLaunchPolicy,
    AutoCadLauncherError,
    AutoCadProcessIdentity,
    AutoCadProcessLauncher,
    AutoCadProcessOwnershipRegistry,
    AutoCadJobOwnedSessionGuard,
    LazyAutoCadComTransport,
    ProcessSnapshot,
    SafeAutoCadPopen,
    WindowsAcadProcessInspector,
    WindowsHwndPidResolver,
    WindowsProcessIdentityInspector,
)
from mcp_nextgen.backends.s5_launch_probe import run_launch_probe


def s5_runtime_environment(*, drive: str = "C:") -> dict[str, str]:
    """十项关键环境变量的纯字符串夹具；不读取宿主环境。"""
    root = f"{drive}\\Windows"
    profile = f"{drive}\\Users\\REDACTED_USER"
    return {
        "SystemDrive": drive,
        "SystemRoot": root,
        "windir": root,
        "ProgramData": f"{drive}\\ProgramData",
        "ALLUSERSPROFILE": f"{drive}\\ProgramData",
        "USERPROFILE": profile,
        "APPDATA": f"{profile}\\AppData\\Roaming",
        "LOCALAPPDATA": f"{profile}\\AppData\\Local",
        "TEMP": f"{profile}\\AppData\\Local\\Temp",
        "TMP": f"{profile}\\AppData\\Local\\Temp",
    }

@dataclass
class FakeProcess:
    pid: int = 4321
    exit_code: int | None = None

    def poll(self) -> int | None:
        return self.exit_code


class FakeDocuments:
    Count = 0


class FakeSpace:
    def __init__(self, count: int = 0) -> None:
        self.Count = count


@dataclass
class FakePaperEntity:
    ObjectName: str


class FakeApplication:
    Version = "25.1"
    Documents = FakeDocuments()
    HWND = 4242


@dataclass
class FakeDocument:
    Name: str = "Drawing1.dwg"
    FullName: str = ""
    Saved: bool = True
    ReadOnly: bool = False
    dwg_titled: int = 0
    dbmod: int = 0
    cmdnames: str = ""
    model_space_count: int = 0
    paper_space: tuple[FakePaperEntity, ...] = ()

    @property
    def ModelSpace(self) -> FakeSpace:
        return FakeSpace(self.model_space_count)

    @property
    def PaperSpace(self) -> tuple[FakePaperEntity, ...]:
        return self.paper_space

    def GetVariable(self, name: str):
        return {
            "DWGTITLED": self.dwg_titled,
            "DBMOD": self.dbmod,
            "CMDNAMES": self.cmdnames,
        }[name]


def make_launcher(*, processes=(), connector=None, clock_values=None, process_identity_inspector=None, popen=None):
    starts: list[tuple[list[str], bool]] = []
    values = iter(clock_values or (0.0, 0.1, 0.2, 0.3))
    launcher = AutoCadProcessLauncher(
        policy=AutoCadLaunchPolicy(startup_timeout_seconds=5, poll_interval_seconds=0.01),
        process_inspector=lambda: list(processes),
        popen=popen or (lambda args, *, shell: starts.append((args, shell)) or FakeProcess()),
        com_connector=connector or (lambda _progid: FakeApplication()),
        resolver=AutoCadExecutableResolver(
            allowed_install_root=Path(r"E:\AutoCAD 2026"),
            path_exists=lambda path: path.name.lower() == "acad.exe",
            version_reader=lambda _path: "25.1",
        ),
        process_identity_inspector=process_identity_inspector,
        clock=lambda: next(values, 100.0),
        sleeper=lambda _seconds: None,
    )
    return launcher, starts


def test_launch_uses_only_verified_executable_shell_false_and_empty_arguments() -> None:
    launcher, starts = make_launcher()
    result = launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert result.status == "COM_READY"
    assert result.launched is True
    assert starts and starts[0][0][0].lower().endswith("acad.exe")
    assert starts[0][1] is False
    assert result.process.command_arguments == ()
    assert result.process.shell is False


def test_process_launch_only_never_calls_com_connector() -> None:
    calls = {"connect": 0}
    safe = SafeAutoCadPopen.for_process_launch(
        factory=lambda args, *, shell, env, cwd: FakeProcess(),
        environment=s5_runtime_environment(),
    )
    launcher, _starts = make_launcher(
        connector=lambda _progid: calls.__setitem__("connect", calls["connect"] + 1),
        popen=safe,
    )
    result = launcher.launch_process_only(job_id="s5-process-only")
    assert result.status == "PROCESS_STARTED"
    assert result.session is None
    assert calls["connect"] == 0


def test_existing_process_is_fail_closed_and_never_starts_or_attaches() -> None:
    launcher, starts = make_launcher(processes=(ProcessSnapshot(9, r"E:\AutoCAD 2026\acad.exe"),))
    with pytest.raises(AutoCadLauncherError, match="既有") as error:
        launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert error.value.error_code == "EXISTING_PROCESS_UNKNOWN_OWNER"
    assert starts == []


def test_process_launch_only_rejects_preexisting_process_before_popen_or_com() -> None:
    calls = {"com": 0}
    safe = SafeAutoCadPopen.for_process_launch(
        factory=lambda args, *, shell, env, cwd: FakeProcess(),
        environment=s5_runtime_environment(),
    )
    launcher, starts = make_launcher(
        processes=(ProcessSnapshot(91, r"E:\AutoCAD 2026\acad.exe"),),
        connector=lambda _progid: calls.__setitem__("com", calls["com"] + 1),
        popen=safe,
    )
    with pytest.raises(AutoCadLauncherError) as error:
        launcher.launch_process_only(job_id="s5-process-only")
    assert error.value.error_code == "EXISTING_PROCESS_UNKNOWN_OWNER"
    assert starts == []
    assert calls["com"] == 0


@pytest.mark.parametrize("candidate", [r"C:\Windows\acad.exe", r"E:\AutoCAD 2026\not-acad.exe"])
def test_executable_resolver_rejects_outside_or_wrong_name(candidate: str) -> None:
    resolver = AutoCadExecutableResolver(path_exists=lambda _path: True)
    with pytest.raises(AutoCadLauncherError) as error:
        resolver.resolve(candidate)
    assert error.value.error_code == "AUTOCAD_EXECUTABLE_PATH_INVALID"


def test_executable_resolver_accepts_explicit_trusted_acad_path() -> None:
    resolver = AutoCadExecutableResolver(
        path_exists=lambda path: path == Path(r"E:\AutoCAD 2026\acad.exe"),
        version_reader=lambda _path: "25.1",
    )
    assert resolver.resolve(r"E:\AutoCAD 2026\acad.exe") == Path(
        r"E:\AutoCAD 2026\acad.exe"
    )


def test_executable_resolver_reports_missing_trusted_acad_path() -> None:
    resolver = AutoCadExecutableResolver(path_exists=lambda _path: False)
    with pytest.raises(AutoCadLauncherError) as error:
        resolver.resolve(r"E:\AutoCAD 2026\acad.exe")
    assert error.value.error_code == "AUTOCAD_EXECUTABLE_NOT_FOUND"


def test_executable_resolver_expands_explicit_environment_variable_without_disk_fallback() -> None:
    resolver = AutoCadExecutableResolver(
        environment={"AUTOCAD_HOME": r"E:\AutoCAD 2026"},
        path_exists=lambda path: path == Path(r"E:\AutoCAD 2026\acad.exe"),
        version_reader=lambda _path: "25.1",
    )
    assert resolver.resolve(r"%AUTOCAD_HOME%\acad.exe") == Path(
        r"E:\AutoCAD 2026\acad.exe"
    )


@pytest.mark.parametrize(
    ("explicit_path", "environment", "error_code"),
    [
        (r"%MISSING_HOME%\acad.exe", {}, "AUTOCAD_EXECUTABLE_PATH_UNEXPANDED"),
        (r"relative\acad.exe", {}, "AUTOCAD_EXECUTABLE_PATH_NOT_ABSOLUTE"),
        (r"D:\CodexWork\天正\acad.exe", {}, "AUTOCAD_EXECUTABLE_PATH_FORBIDDEN_FALLBACK"),
        (r"T:\fallback\acad.exe", {}, "AUTOCAD_EXECUTABLE_PATH_FORBIDDEN_FALLBACK"),
    ],
)
def test_executable_resolver_rejects_unexpanded_relative_or_forbidden_fallback(
    explicit_path: str, environment: dict[str, str], error_code: str
) -> None:
    resolver = AutoCadExecutableResolver(
        environment=environment,
        path_exists=lambda _path: (_ for _ in ()).throw(
            AssertionError("不可信路径不得触发文件存在性检查")
        ),
    )
    with pytest.raises(AutoCadLauncherError) as error:
        resolver.resolve(explicit_path)
    assert error.value.error_code == error_code


def test_executable_resolver_rejects_system_drive_expansion_to_project_before_path_access() -> None:
    checks: list[Path] = []
    resolver = AutoCadExecutableResolver(
        environment={"SystemDrive": "D:"},
        path_exists=lambda path: checks.append(path) or True,
    )
    with pytest.raises(AutoCadLauncherError) as error:
        resolver.resolve(r"%SystemDrive%\CodexWork\天正\acad.exe")
    assert error.value.error_code == "AUTOCAD_EXECUTABLE_PATH_FORBIDDEN_FALLBACK"
    assert checks == []


def test_launcher_rejects_version_mismatch_before_session_is_ready() -> None:
    launcher, _starts = make_launcher(connector=lambda _progid: type("Bad", (), {"Version": "24.3", "Documents": FakeDocuments()})())
    with pytest.raises(AutoCadLauncherError) as error:
        launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert error.value.error_code == "AUTOCAD_VERSION_MISMATCH"


def test_launcher_reports_process_exit_without_com_fallback() -> None:
    calls = {"connect": 0}
    launcher, _starts = make_launcher()
    launcher._popen = lambda _args, *, shell: FakeProcess(exit_code=1)  # type: ignore[method-assign]
    launcher._com_connector = lambda _progid: calls.__setitem__("connect", calls["connect"] + 1)  # type: ignore[assignment]
    with pytest.raises(AutoCadLauncherError) as error:
        launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert error.value.error_code == "AUTOCAD_PROCESS_EXITED_DURING_STARTUP"
    assert calls["connect"] == 0


def test_launcher_reports_com_not_ready_after_bounded_timeout() -> None:
    clock_values = iter((0.0, 0.0, 0.1, 2.0))
    launcher = AutoCadProcessLauncher(
        policy=AutoCadLaunchPolicy(startup_timeout_seconds=1, poll_interval_seconds=0.01),
        process_inspector=lambda: (),
        popen=lambda _args, *, shell: FakeProcess(),
        com_connector=lambda _progid: (_ for _ in ()).throw(RuntimeError("not ready")),
        resolver=AutoCadExecutableResolver(
            path_exists=lambda _path: True, version_reader=lambda _path: "25.1"
        ),
        clock=lambda: next(clock_values),
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(AutoCadLauncherError) as error:
        launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert error.value.error_code == "AUTOCAD_COM_NOT_READY"


def test_lazy_transport_reports_pywin32_dependency_missing_without_real_import_or_dispatch() -> None:
    def missing_importer():
        raise ImportError("synthetic missing pywin32")

    with pytest.raises(AutoCadLauncherError) as error:
        LazyAutoCadComTransport(client_importer=missing_importer).connect("AutoCAD.Application.25.1")
    assert error.value.error_code == "AUTOCAD_COM_DEPENDENCY_MISSING"


def test_ownership_registry_allows_quit_only_for_registered_job_owned_empty_session() -> None:
    launcher, _starts = make_launcher()
    result = launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert result.session is not None
    assert launcher.ownership.may_quit(result.session, document_count=0)
    assert not launcher.ownership.may_quit(result.session, document_count=1)
    foreign = AutoCadProcessOwnershipRegistry()
    assert not foreign.may_quit(result.session, document_count=0)


def test_ownership_registry_rejects_same_pid_with_different_ownership_token() -> None:
    registry = AutoCadProcessOwnershipRegistry()
    first = AutoCadProcessIdentity(
        job_id="s5-job",
        process_id=4321,
        executable_path=r"E:\AutoCAD 2026\acad.exe",
        process_start_time=0.0,
        launched_by_job=True,
        ownership_token="first",
    )
    registry.register(first)
    with pytest.raises(AutoCadLauncherError) as error:
        registry.register(
            AutoCadProcessIdentity(
                job_id="s5-job",
                process_id=4321,
                executable_path=first.executable_path,
                process_start_time=0.0,
                launched_by_job=True,
                ownership_token="different",
            )
        )
    assert error.value.error_code == "AUTOCAD_SESSION_UNSAFE"


def test_os_process_identity_inspector_records_actual_path_and_creation_time_before_com() -> None:
    calls: list[int] = []
    inspector = WindowsProcessIdentityInspector(
        query=lambda pid: calls.append(pid) or (r"E:\AutoCAD 2026\acad.exe", 133700000000000000)
    )
    launcher, _starts = make_launcher(process_identity_inspector=inspector)
    result = launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert calls == [4321]
    assert result.process.os_verified_executable_path == str(Path(r"E:\AutoCAD 2026\acad.exe"))
    assert result.process.os_process_creation_filetime == 133700000000000000


def test_os_process_identity_inspector_rejects_path_mismatch_without_com_connect() -> None:
    calls = {"connect": 0}
    launcher, _starts = make_launcher(
        connector=lambda _progid: calls.__setitem__("connect", calls["connect"] + 1),
        process_identity_inspector=WindowsProcessIdentityInspector(
            query=lambda _pid: (r"C:\\untrusted\\acad.exe", 133700000000000000)
        ),
    )
    with pytest.raises(AutoCadLauncherError) as error:
        launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert error.value.error_code == "AUTOCAD_SESSION_UNSAFE"
    assert calls["connect"] == 0


def test_policy_rejects_existing_attachment_and_user_documents() -> None:
    with pytest.raises(ValueError):
        AutoCadLaunchPolicy(attach_existing=True)
    with pytest.raises(ValueError):
        AutoCadLaunchPolicy(allow_user_documents=True)


def test_windows_inspector_uses_fixed_read_only_shell_false_command() -> None:
    calls = []
    inspector = WindowsAcadProcessInspector(
        runner=lambda *args, **kwargs: calls.append((args, kwargs)) or subprocess.CompletedProcess(
            args[0], 0, '"acad.exe","800","Console","1","10,000 K"\n', ''
        )
    )
    values = inspector()
    assert [item.pid for item in values] == [800]
    assert calls[0][0][0] == ["tasklist", "/fo", "csv", "/nh", "/fi", "IMAGENAME eq acad.exe"]
    assert calls[0][1]["shell"] is False


def test_safe_popen_rejects_dwg_arguments_and_shell_true() -> None:
    invoked = []
    safe = SafeAutoCadPopen(factory=lambda args, *, shell: invoked.append((args, shell)) or FakeProcess())
    with pytest.raises(AutoCadLauncherError) as error:
        safe([r"E:\AutoCAD 2026\acad.exe", r"C:\user.dwg"], shell=False)
    assert error.value.error_code == "AUTOCAD_LAUNCH_ARGUMENTS_INVALID"
    with pytest.raises(AutoCadLauncherError):
        safe([r"E:\AutoCAD 2026\acad.exe"], shell=True)
    assert invoked == []


def test_safe_popen_process_launch_uses_explicit_external_cwd_and_sanitized_environment() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    safe = SafeAutoCadPopen.for_process_launch(
        factory=lambda args, **kwargs: calls.append((args, kwargs)) or FakeProcess(),
        environment=s5_runtime_environment(),
    )
    result = safe([r"E:\AutoCAD 2026\acad.exe"], shell=False)
    assert result.pid == 4321
    assert calls == [
        (
            [r"E:\AutoCAD 2026\acad.exe"],
            {
                "shell": False,
                "cwd": r"D:\CadAgentRuntime\s5\launch",
                "env": s5_runtime_environment(),
            },
        )
    ]


def test_safe_popen_rejects_partial_process_launch_runtime_contract() -> None:
    with pytest.raises(AutoCadLauncherError) as error:
        SafeAutoCadPopen(
            factory=lambda _args, **_kwargs: FakeProcess(),
            sanitized_environment={"SystemDrive": "D:"},
        )
    assert error.value.error_code == "AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVED"


def test_launcher_has_no_active_document_or_destructive_command_call_sites() -> None:
    source = Path(__file__).parents[2] / "mcp_nextgen" / "backends" / "autocad_launcher.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden = {"ActiveDocument", "SendCommand", "NETLOAD", "LISP", "taskkill"}
    assert not (forbidden & called_attributes)
    assert not (forbidden & called_names)


def test_hwnd_pid_and_default_blank_document_are_verified_before_shutdown() -> None:
    launcher, _starts = make_launcher()
    result = launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert result.session is not None
    app = FakeApplication()
    app.Documents = [FakeDocument(paper_space=(FakePaperEntity("AcDbViewport"),))]
    guard = AutoCadJobOwnedSessionGuard(
        ownership=launcher.ownership,
        hwnd_pid_resolver=WindowsHwndPidResolver(get_window_thread_process_id=lambda _hwnd: (7, 4321)),
    )
    verification = guard.verify(result.session, app)
    assert verification.has_only_new_default_blank_documents
    plan = guard.plan_safe_shutdown(verification)
    assert plan.close_without_save_names == ("Drawing1.dwg",)
    assert plan.quit_after_close is True


def test_hwnd_pid_mismatch_or_non_default_document_blocks_job_owned_shutdown() -> None:
    launcher, _starts = make_launcher()
    result = launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert result.session is not None
    app = FakeApplication()
    app.Documents = [FakeDocument(FullName=r"C:\\user\\drawing.dwg", Saved=True)]
    mismatch_guard = AutoCadJobOwnedSessionGuard(ownership=launcher.ownership, hwnd_pid_resolver=lambda _hwnd: 999)
    with pytest.raises(AutoCadLauncherError) as mismatch:
        mismatch_guard.verify(result.session, app)
    assert mismatch.value.error_code == "AUTOCAD_SESSION_UNSAFE"
    guard = AutoCadJobOwnedSessionGuard(ownership=launcher.ownership, hwnd_pid_resolver=lambda _hwnd: 4321)
    with pytest.raises(AutoCadLauncherError) as unsafe_doc:
        guard.plan_safe_shutdown(guard.verify(result.session, app))
    assert unsafe_doc.value.error_code == "AUTOCAD_USER_DOCUMENT_PROTECTION_TRIGGERED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dwg_titled", 1),
        ("dbmod", 1),
        ("cmdnames", "LINE"),
        ("model_space_count", 1),
        ("paper_space", (FakePaperEntity("AcDbLine"),)),
    ],
)
def test_default_blank_document_guard_rejects_non_blank_system_state(
    field: str, value: object
) -> None:
    """Saved=True 的新 Drawing 文档仍可接受；其余状态必须逐项 fail-closed。"""
    launcher, _starts = make_launcher()
    result = launcher.launch(job_id="s5-job", com_progid="AutoCAD.Application.25.1")
    assert result.session is not None
    app = FakeApplication()
    app.Documents = [FakeDocument(**{field: value})]
    guard = AutoCadJobOwnedSessionGuard(
        ownership=launcher.ownership,
        hwnd_pid_resolver=lambda _hwnd: 4321,
    )
    verification = guard.verify(result.session, app)
    assert verification.documents[0].saved is True
    assert not verification.has_only_new_default_blank_documents
    with pytest.raises(AutoCadLauncherError) as error:
        guard.plan_safe_shutdown(verification)
    assert error.value.error_code == "AUTOCAD_USER_DOCUMENT_PROTECTION_TRIGGERED"


def test_launch_probe_is_explicitly_gated_and_does_not_construct_launcher_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CAD_S5_AUTOCAD_INTEGRATION", raising=False)
    evidence = tmp_path / "launch-evidence.json"
    result = run_launch_probe(job_id="s5-test-job", evidence_path=evidence)
    assert result["status"] == "BLOCKED"
    assert result["error_code"] == "CAD_S5_AUTOCAD_INTEGRATION_REQUIRED"
    assert result["synthetic_dwg_created"] is False
    assert result["user_dwg_reads"] == result["user_dwg_writes"] == 0
    assert evidence.is_file()


def test_launch_probe_source_has_no_document_creation_open_or_save_operations() -> None:
    source = (Path(__file__).parents[2] / "mcp_nextgen" / "backends" / "s5_launch_probe.py").read_text(encoding="utf-8")
    forbidden = ("Documents.Add", ".Open(", ".Save(", ".SaveAs(", "ActiveDocument", "SendCommand", "NETLOAD")
    assert not any(value in source for value in forbidden)
    assert "document.Close(False)" in source
    assert "application.Quit()" in source
    for evidence_key in (
        "pre_acad_process_count",
        "post_acad_process_count",
        "launch_command_arguments",
        "os_process_identity",
        "application_hwnd",
        "default_document_inspection",
        "save_calls",
        "post_document_count",
    ):
        assert evidence_key in source
