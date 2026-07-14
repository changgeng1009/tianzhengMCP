from __future__ import annotations

import sys
import types
from pathlib import Path


class FakeDocument:
    def __init__(self, full_name: str, read_only: bool = False) -> None:
        self.FullName = full_name
        self.Name = Path(full_name).name
        self.Path = str(Path(full_name).parent)
        self.ReadOnly = read_only


class FakeDocuments:
    def __init__(self, documents: list[FakeDocument]) -> None:
        self._documents = list(documents)
        self.opened_paths: list[str] = []

    @property
    def Count(self) -> int:  # noqa: N802
        return len(self._documents)

    def Item(self, index: int) -> FakeDocument:  # noqa: N802
        return self._documents[index]

    def Open(self, path: str) -> FakeDocument:  # noqa: N802
        self.opened_paths.append(path)
        document = FakeDocument(path)
        self._documents.append(document)
        return document


class FakeAutoCADApplication:
    Name = "AutoCAD"
    Version = "25.0"
    Visible = True

    def __init__(self, documents: FakeDocuments, active_document: FakeDocument | None = None, active_error: Exception | None = None) -> None:
        self.Documents = documents
        self._active_document = active_document
        self._active_error = active_error

    @property
    def ActiveDocument(self) -> FakeDocument:  # noqa: N802
        if self._active_error is not None:
            raise self._active_error
        if self._active_document is None:
            raise RuntimeError("无法获取 Document 对象")
        return self._active_document


def test_autocad_application_unavailable_returns_structured_failure(monkeypatch) -> None:
    from mcp.t30_writeback.com_probe import T30COMProbe

    client = types.SimpleNamespace(
        __cad_test_mock__=True,
        GetActiveObject=lambda _name: (_ for _ in ()).throw(RuntimeError("AutoCAD unavailable")),
    )
    monkeypatch.setitem(
        sys.modules,
        "win32com",
        types.SimpleNamespace(__cad_test_mock__=True, client=client),
    )
    monkeypatch.setitem(sys.modules, "win32com.client", client)

    result = T30COMProbe().probe_environment()

    assert result["status"] == "failed"
    assert result["autocad"]["application_available"] is False
    assert result["document_resolution"]["strategy"] == "failed"
    assert result["document_resolution"]["errors"]


def test_active_document_unavailable_does_not_crash_and_falls_back_to_first_document(tmp_path) -> None:
    from mcp.t30_writeback.com_probe import T30COMProbe

    document = FakeDocument(str(tmp_path / "open.dwg"))
    app = FakeAutoCADApplication(FakeDocuments([document]), active_error=RuntimeError("无法获取 Document 对象"))

    result = T30COMProbe(com_environment=app).probe_environment()

    assert result["status"] == "success"
    assert result["autocad"]["active_document_available"] is False
    assert result["autocad"]["documents_count"] == 1
    assert result["document_resolution"]["strategy"] == "documents_first"
    assert result["document_resolution"]["resolved_document_path"] == str(tmp_path / "open.dwg")


def test_target_dwg_path_matching_open_document_uses_matched_target_path(tmp_path) -> None:
    from mcp.t30_writeback.com_probe import T30COMProbe

    active = FakeDocument(str(tmp_path / "active.dwg"))
    target = FakeDocument(str(tmp_path / "target.dwg"))
    app = FakeAutoCADApplication(FakeDocuments([active, target]), active_document=active)

    result = T30COMProbe(com_environment=app).probe_environment(target_dwg_path=str(tmp_path / "target.dwg"))

    assert result["document_resolution"]["strategy"] == "matched_target_path"
    assert result["document_resolution"]["resolved_document_name"] == "target.dwg"


def test_allow_open_document_false_does_not_open_target(tmp_path, synthetic_cad_factory) -> None:
    from mcp.t30_writeback.com_probe import T30COMProbe

    target = synthetic_cad_factory(tmp_path / "target.dwg")
    documents = FakeDocuments([])
    app = FakeAutoCADApplication(documents, active_error=RuntimeError("no active document"))

    result = T30COMProbe(com_environment=app).probe_environment(target_dwg_path=str(target), options={"allow_open_document": False})

    assert result["document_resolution"]["strategy"] == "failed"
    assert documents.opened_paths == []


def test_allow_open_document_true_opens_target_in_fake_com(tmp_path, synthetic_cad_factory) -> None:
    from mcp.t30_writeback.com_probe import T30COMProbe

    target = synthetic_cad_factory(tmp_path / "target.dwg")
    documents = FakeDocuments([])
    app = FakeAutoCADApplication(documents, active_error=RuntimeError("no active document"))

    result = T30COMProbe(com_environment=app).probe_environment(target_dwg_path=str(target), options={"allow_open_document": True})

    assert result["document_resolution"]["strategy"] == "opened_target_path"
    assert documents.opened_paths == [str(target)]
    assert result["document_resolution"]["resolved_document_path"] == str(target)
