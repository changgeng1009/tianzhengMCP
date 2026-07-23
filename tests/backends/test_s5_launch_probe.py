"""S5 最小启动 Probe 的纯 Fake 回归；不启动进程、不导入真实 COM。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import inspect
from pathlib import Path

import pytest

from mcp_nextgen.backends.autocad_launcher import AutoCadExecutableResolver, ProcessSnapshot
from mcp_nextgen.backends.s5_launch_probe import run_launch_probe


class FakeDocuments(list):
    @property
    def Count(self) -> int:
        return len(self)


@dataclass
class FakeSpace:
    Count: int = 0


class FakeDocument:
    Name = "Drawing1.dwg"
    FullName = ""
    Saved = True
    ReadOnly = False
    ModelSpace = FakeSpace()
    PaperSpace: tuple[object, ...] = ()

    def __init__(self, documents: FakeDocuments) -> None:
        self._documents = documents

    def GetVariable(self, name: str) -> int | str:
        return {"DWGTITLED": 0, "DBMOD": 0, "CMDNAMES": ""}[name]

    def Close(self, save: bool) -> None:
        assert save is False
        self._documents.remove(self)


class FakeApplication:
    HWND = 4242
    Version = "25.1"

    def __init__(self) -> None:
        self.Documents = FakeDocuments()
        self.Documents.append(FakeDocument(self.Documents))
        self.quit_calls = 0

    def Quit(self) -> None:
        self.quit_calls += 1


class FakeTransport:
    def __init__(self, application: FakeApplication) -> None:
        self.application = application
        self.activation_calls = 0

    def activate_isolated(self, progid: str) -> FakeApplication:
        self.activation_calls += 1
        assert progid == "AutoCAD.Application.25.1"
        return self.application


class FakeActivationHost:
    context_calls = 0

    @contextmanager
    def activation_context(self):
        self.context_calls += 1
        yield


def _resolver() -> AutoCadExecutableResolver:
    return AutoCadExecutableResolver(
        path_exists=lambda path: path == Path(r"E:\AutoCAD 2026\acad.exe"),
        version_reader=lambda _path: "25.1",
        environment={},
    )


def test_probe_preexisting_acad_blocks_before_com_activation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CAD_S5_AUTOCAD_INTEGRATION", "1")
    monkeypatch.delenv("AUTOCAD_EXE_PATH", raising=False)
    transport = FakeTransport(FakeApplication())
    result = run_launch_probe(
        job_id="s5-mock-preexisting",
        evidence_path=tmp_path / "preexisting.json",
        process_inspector=lambda: (ProcessSnapshot(777, r"E:\AutoCAD 2026\acad.exe"),),
        transport=transport,  # type: ignore[arg-type]
        activation_host=FakeActivationHost(),  # type: ignore[arg-type]
        hwnd_pid_resolver=lambda _hwnd: 4321,
        process_identity_inspector=lambda identity: identity,
        executable_resolver=_resolver(),
    )
    assert result["status"] == "FAILED"
    assert result["error_code"] == "EXISTING_PROCESS_UNKNOWN_OWNER"
    assert transport.activation_calls == 0


def test_probe_requires_hwnd_pid_to_be_unique_new_process_after_activation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CAD_S5_AUTOCAD_INTEGRATION", "1")
    monkeypatch.delenv("AUTOCAD_EXE_PATH", raising=False)
    transport = FakeTransport(FakeApplication())
    snapshots = iter(
        (
            (),
            (ProcessSnapshot(999, r"E:\AutoCAD 2026\acad.exe"),),
            (),
        )
    )
    result = run_launch_probe(
        job_id="s5-mock-wrong-pid",
        evidence_path=tmp_path / "wrong-pid.json",
        process_inspector=lambda: next(snapshots),
        transport=transport,  # type: ignore[arg-type]
        activation_host=FakeActivationHost(),  # type: ignore[arg-type]
        hwnd_pid_resolver=lambda _hwnd: 4321,
        process_identity_inspector=lambda identity: identity,
        executable_resolver=_resolver(),
    )
    assert result["status"] == "FAILED"
    assert result["error_code"] == "AUTOCAD_SESSION_UNSAFE"
    assert result["com_activation_added_process_ids"] == [999]
    assert transport.activation_calls == 1


def test_probe_com_activation_has_one_unique_pid_and_no_process_launch_injection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CAD_S5_AUTOCAD_INTEGRATION", "1")
    monkeypatch.delenv("AUTOCAD_EXE_PATH", raising=False)
    application = FakeApplication()
    transport = FakeTransport(application)
    host = FakeActivationHost()
    process = ProcessSnapshot(4321, r"E:\AutoCAD 2026\acad.exe")
    snapshots = iter(((), (process,), ()))
    result = run_launch_probe(
        job_id="s5-mock-success",
        evidence_path=tmp_path / "success.json",
        process_inspector=lambda: next(snapshots),
        transport=transport,  # type: ignore[arg-type]
        activation_host=host,  # type: ignore[arg-type]
        hwnd_pid_resolver=lambda _hwnd: 4321,
        process_identity_inspector=lambda identity: identity,
        executable_resolver=_resolver(),
    )
    assert result["status"] == "PASS"
    assert result["activation_mode"] == "com_activation"
    assert result["com_activation_added_process_ids"] == [4321]
    assert transport.activation_calls == host.context_calls == 1
    assert application.quit_calls == 1
    assert "popen" not in inspect.signature(run_launch_probe).parameters


def test_probe_without_explicit_gate_never_constructs_com_dependencies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CAD_S5_AUTOCAD_INTEGRATION", raising=False)
    result = run_launch_probe(
        job_id="s5-mock-gated",
        evidence_path=tmp_path / "gated.json",
    )
    assert result["status"] == "BLOCKED"
    assert result["error_code"] == "CAD_S5_AUTOCAD_INTEGRATION_REQUIRED"
