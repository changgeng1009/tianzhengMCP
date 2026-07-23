"""S5 synthetic runner 的显式集成门纯单元测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mcp_nextgen.backends.real_autocad_com import RealAutoCadComBackend, RealAutoCadComBackendError
import mcp_nextgen.backends.s5_synthetic_runner as runner_module
from mcp_nextgen.backends.s5_synthetic_runner import run_s5_synthetic_mvp


def test_runner_is_disabled_by_default_before_importing_or_activating_com(tmp_path: Path) -> None:
    def forbidden_importer():
        raise AssertionError("disabled gate 不得导入或激活 COM")

    with pytest.raises(RealAutoCadComBackendError) as error:
        run_s5_synthetic_mvp(
            artifact_root=tmp_path, run_id="s5-run", job_id="s5-job", plan_hash="a" * 64,
            integration_enabled=False, client_importer=forbidden_importer,
        )
    assert error.value.code == "S5_EXTERNAL_INTEGRATION_DISABLED"


def test_s4_capability_gate_is_closed_until_external_synthetic_evidence_exists() -> None:
    closed = RealAutoCadComBackend.s4_capability_gate(external_integration_verified=False)
    open_after_evidence = RealAutoCadComBackend.s4_capability_gate(external_integration_verified=True)
    assert closed["available"] is False
    assert closed["support_level"] == "NOT_IMPLEMENTED_UNVALIDATED"
    assert open_after_evidence["available"] is True
    assert open_after_evidence["support_level"] == "AVAILABLE_SANDBOX_MVP"
    for value in (closed, open_after_evidence):
        assert value["production_allowed"] is False
        assert value["user_dwg_access"] == "FORBIDDEN"


class _NoopActivationHost:
    def __init__(self, **_kwargs) -> None:
        pass

    def activation_context(self):
        class _Context:
            def __enter__(self):
                return None

            def __exit__(self, *_args):
                return False

        return _Context()


class _DefaultDocument:
    def __init__(self, documents) -> None:
        self._documents = documents
        self.closed = 0

    def Close(self, _save_changes):  # noqa: N802 - COM 形状
        self.closed += 1
        self._documents.default_document = None


class _Documents:
    def __init__(self) -> None:
        self.default_document: _DefaultDocument | None = _DefaultDocument(self)

    @property
    def Count(self):  # noqa: N802 - COM 形状
        return int(self.default_document is not None)

    def __iter__(self):
        return iter(()) if self.default_document is None else iter((self.default_document,))


class _Application:
    Version = "25.1"
    HWND = 4242

    def __init__(self) -> None:
        self.Documents = _Documents()
        self.quit_calls = 0

    def Quit(self):  # noqa: N802 - COM 形状
        self.quit_calls += 1


class _Activator:
    application: _Application

    def __init__(self, **_kwargs) -> None:
        pass

    def activate(self, _progid):
        return self.application


class _FailureGateway:
    instance = None

    def __init__(self, *, application, array_adapter=None) -> None:
        self.application = application
        self.array_adapter = array_adapter
        self.identity = None
        self.discard_calls = 0
        self.quit_calls = 0
        type(self).instance = self

    def create_synthetic(self, identity):
        self.identity = identity
        return {"synthetic": True, "user_document": False, "canonical_path": identity.canonical_path}

    def document_snapshot(self, identity):
        return {"synthetic": True, "user_document": False, "canonical_path": identity.canonical_path}

    def list_entities(self, _identity):
        return []

    def ensure_layer(self, _identity, _layer):
        return None

    def create_line(self, _identity, _spec):
        raise RuntimeError("forced synthetic failure")

    def has_registered_synthetic_document(self, identity):
        return self.identity == identity

    def discard_registered_synthetic_document(self, identity):
        assert self.identity == identity
        self.discard_calls += 1
        self.identity = None

    def quit_if_job_owned(self):
        self.quit_calls += 1


def _patch_verified_runner(monkeypatch: pytest.MonkeyPatch, application: _Application) -> None:
    _Activator.application = application
    monkeypatch.setattr(runner_module, "ComActivationSessionHost", _NoopActivationHost)
    monkeypatch.setattr(runner_module, "IsolatedComActivator", _Activator)
    monkeypatch.setattr(runner_module, "Pywin32AutoCadSandboxGateway", _FailureGateway)
    monkeypatch.setattr(
        runner_module,
        "AutoCadJobOwnedSessionGuard",
        lambda **_kwargs: SimpleNamespace(verify=lambda *_args: SimpleNamespace(has_only_new_default_blank_documents=True)),
    )


def test_verified_synthetic_failure_discards_only_registered_document_then_quits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    application = _Application()
    _patch_verified_runner(monkeypatch, application)
    process_calls = iter(((), (SimpleNamespace(pid=700, executable_path=r"E:\AutoCAD 2026\acad.exe"),)))
    with pytest.raises(RuntimeError, match="forced synthetic failure"):
        run_s5_synthetic_mvp(
            artifact_root=tmp_path, run_id="run", job_id="job", plan_hash="a" * 64,
            integration_enabled=True, client_importer=lambda: (_ for _ in ()).throw(AssertionError("not used")),
            process_inspector=lambda: next(process_calls), hwnd_pid_resolver=lambda _hwnd: 700,
            process_identity_inspector=lambda identity: identity,
        )
    gateway = _FailureGateway.instance
    assert gateway is not None
    assert gateway.discard_calls == 1
    assert gateway.quit_calls == 1
    assert application.Documents.Count == 0


def test_unverified_session_failure_never_closes_or_quits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    application = _Application()
    _Activator.application = application
    monkeypatch.setattr(runner_module, "ComActivationSessionHost", _NoopActivationHost)
    monkeypatch.setattr(runner_module, "IsolatedComActivator", _Activator)

    with pytest.raises(RealAutoCadComBackendError) as error:
        run_s5_synthetic_mvp(
            artifact_root=tmp_path, run_id="run", job_id="job", plan_hash="a" * 64,
            integration_enabled=True, client_importer=lambda: (_ for _ in ()).throw(AssertionError("not used")),
            process_inspector=lambda: (), hwnd_pid_resolver=lambda _hwnd: 700,
            process_identity_inspector=lambda identity: identity,
        )
    assert error.value.code == "AUTOCAD_SESSION_UNSAFE"
    assert application.Documents.Count == 1
    assert application.Documents.default_document is not None
    assert application.Documents.default_document.closed == 0
    assert application.quit_calls == 0
