from __future__ import annotations

from typing import Any

import pytest


class FakeCOMError(Exception):
    pass


class FakeLayer:
    Name = "0"


class FakeLine:
    EntityName = "AcDbLine"
    ObjectName = "AcDbLine"
    Handle = "2A3"

    def __init__(self) -> None:
        self.updated = False

    def Update(self) -> None:
        self.updated = True


class FakeModelSpace:
    def __init__(self) -> None:
        self.Count = 3
        self.lines: list[tuple[object, object]] = []
        self.created_lines: list[FakeLine] = []

    def AddLine(self, start: object, end: object) -> FakeLine:
        line = FakeLine()
        self.lines.append((start, end))
        self.created_lines.append(line)
        return line


class FakeDocument:
    def __init__(self, name: str = "test.dwg", full_name: str = "D:/tmp/test.dwg") -> None:
        self.Name = name
        self.FullName = full_name
        self.ActiveLayer = FakeLayer()
        self.ActiveSpace = 1
        self.ModelSpace = FakeModelSpace()
        self.commands: list[str] = []
        self.regen_modes: list[int] = []

    def SendCommand(self, command: str) -> None:
        self.commands.append(command)

    def Regen(self, mode: int) -> None:
        self.regen_modes.append(mode)


class FakeDocuments:
    def __init__(self, documents: list[FakeDocument]) -> None:
        self._documents = documents
        self.Count = len(documents)

    def __iter__(self):
        return iter(self._documents)


class FakeAutoCAD:
    def __init__(self) -> None:
        self.Version = "AutoCAD 2026"
        self.Visible = True
        self.ActiveDocument = FakeDocument()
        self.Documents = FakeDocuments([self.ActiveDocument])


def test_connect_prefers_autocad_2026_point_one_progid_and_reads_active_document() -> None:
    from cad.connection import AutoCADConnectionManager

    app = FakeAutoCAD()
    attempts: list[str] = []

    def fake_get_object(prog_id: str) -> Any:
        attempts.append(prog_id)
        if prog_id == "AutoCAD.Application.25.1":
            return app
        raise FakeCOMError(prog_id)

    manager = AutoCADConnectionManager(com_get_object=fake_get_object)

    result = manager.connect()

    assert result["connected"] is True
    assert result["successful_progid"] == "AutoCAD.Application.25.1"
    assert result["version"] == "AutoCAD 2026"
    assert result["active_document"] == "test.dwg"
    assert result["attempts"] == [
        {"progid": "AutoCAD.Application.25.1", "success": True}
    ]
    assert attempts == ["AutoCAD.Application.25.1"]


def test_connect_falls_back_to_generic_progid_without_starting_autocad() -> None:
    from cad.connection import AutoCADConnectionManager

    app = FakeAutoCAD()
    attempts: list[str] = []

    def fake_get_object(prog_id: str) -> Any:
        attempts.append(prog_id)
        if prog_id == "AutoCAD.Application":
            return app
        raise FakeCOMError(prog_id)

    manager = AutoCADConnectionManager(com_get_object=fake_get_object)

    result = manager.connect()

    assert result["connected"] is True
    assert result["successful_progid"] == "AutoCAD.Application"
    assert attempts == [
        "AutoCAD.Application.25.1",
        "AutoCAD.Application.25",
        "AutoCAD.Application",
    ]
    assert [attempt["progid"] for attempt in result["attempts"]] == attempts
    assert [attempt["success"] for attempt in result["attempts"]] == [False, False, True]


def test_connect_returns_clear_error_when_autocad_is_not_running() -> None:
    from cad.connection import AutoCADConnectionManager

    def fake_get_object(prog_id: str) -> Any:
        raise FakeCOMError(f"{prog_id} not running")

    manager = AutoCADConnectionManager(com_get_object=fake_get_object)

    result = manager.connect()

    assert result["connected"] is False
    assert result["message"] == "AutoCAD is not running or COM object is not available."
    assert [attempt["progid"] for attempt in result["attempts"]] == [
        "AutoCAD.Application.25.1",
        "AutoCAD.Application.25",
        "AutoCAD.Application",
    ]
    assert all(attempt["success"] is False for attempt in result["attempts"])
    assert all("not running" in attempt["error"] for attempt in result["attempts"])


def test_status_reports_connected_autocad_state() -> None:
    from cad.connection import AutoCADConnectionManager

    manager = AutoCADConnectionManager(com_get_object=lambda _prog_id: FakeAutoCAD())
    manager.connect()

    result = manager.status()

    assert result == {
        "connected": True,
        "autocad_visible": True,
        "version": "AutoCAD 2026",
        "active_document": "test.dwg",
        "documents_count": 1,
        "successful_progid": "AutoCAD.Application.25.1",
    }


def test_disconnect_clears_cached_connection_without_closing_autocad() -> None:
    from cad.connection import AutoCADConnectionManager

    manager = AutoCADConnectionManager(com_get_object=lambda _prog_id: FakeAutoCAD())
    manager.connect()

    result = manager.disconnect()

    assert result["success"] is True
    assert manager.status()["connected"] is False
