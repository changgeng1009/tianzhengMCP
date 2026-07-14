from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from mcp.backends.com_backend import ComCadBackend
from mcp.backends import com_backend
from mcp.backends.errors import BackendError
from mcp.backends.models import BackendConfig


def test_attach_only_never_dispatches_new_autocad_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"dispatch": 0}
    pythoncom = ModuleType("pythoncom")
    pythoncom.__cad_test_mock__ = True  # type: ignore[attr-defined]
    pythoncom.CoInitialize = lambda: None  # type: ignore[attr-defined]
    client = ModuleType("win32com.client")
    client.__cad_test_mock__ = True  # type: ignore[attr-defined]

    def unavailable(_prog_id: str) -> None:
        raise RuntimeError("not in ROT")

    def dispatch(_prog_id: str) -> object:
        calls["dispatch"] += 1
        return object()

    client.GetActiveObject = unavailable  # type: ignore[attr-defined]
    client.Dispatch = dispatch  # type: ignore[attr-defined]
    package = ModuleType("win32com")
    package.__cad_test_mock__ = True  # type: ignore[attr-defined]
    package.client = client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", package)
    monkeypatch.setitem(sys.modules, "win32com.client", client)

    backend = ComCadBackend()
    config = BackendConfig(
        backend_id="com", enabled=True, execution_allowed=True,
        settings={"prog_id": "AutoCAD.Application.25.1", "attach_only": True},
    )
    with pytest.raises(BackendError):
        backend.connect(config)
    assert calls["dispatch"] == 0


def test_retry_com_recovers_from_temporary_callee_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}
    monkeypatch.setattr(com_backend.time, "sleep", lambda _delay: None)
    pythoncom = ModuleType("pythoncom")
    pythoncom.__cad_test_mock__ = True  # type: ignore[attr-defined]
    pythoncom.PumpWaitingMessages = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)

    def operation() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("-2147418111 call was rejected by callee")
        return "ready"

    assert com_backend._retry_com(operation, label="read") == "ready"
    assert calls["count"] == 3


def test_create_entity_does_not_retry_non_idempotent_addline() -> None:
    text = Path(com_backend.__file__).read_text(encoding="utf-8")
    assert "_retry_com(lambda: document.ModelSpace.AddLine" not in text
