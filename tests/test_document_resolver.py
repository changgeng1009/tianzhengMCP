from __future__ import annotations

import json


class FakeSpace:
    pass


class FakeSelectionSets:
    pass


class FakeUtility:
    pass


class FakeDocument:
    def __init__(self, name: str = "pump-room.dwg", valid: bool = True) -> None:
        self.Name = name
        self.FullName = f"D:/cad/{name}"
        if valid:
            self.ModelSpace = FakeSpace()
            self.SelectionSets = FakeSelectionSets()
            self.Utility = FakeUtility()


class FakeDocuments:
    def __init__(self, documents: list[FakeDocument], one_based: bool = False) -> None:
        self._documents = documents
        self.Count = len(documents)
        self.one_based = one_based

    def Item(self, index: int):
        if self.one_based:
            if index < 1:
                raise RuntimeError("one-based collection")
            return self._documents[index - 1]
        return self._documents[index]


class FakeApp:
    Caption = "AutoCAD 2026"
    Version = "25.1"

    def __init__(self, active_document=None, documents: FakeDocuments | None = None) -> None:
        self.ActiveDocument = active_document
        self.Documents = documents or FakeDocuments([])


def test_active_document_valid_returns_document():
    from cad.document_resolver import resolve_active_document

    document = FakeDocument("active.dwg")
    result = resolve_active_document(FakeApp(active_document=document))

    assert result["success"] is True
    assert result["document"] is document
    assert result["document_name"] == "active.dwg"
    assert result["document_validation"]["success"] is True


def test_active_document_none_falls_back_to_documents():
    from cad.document_resolver import resolve_active_document

    fallback = FakeDocument("fallback.dwg")
    app = FakeApp(active_document=None, documents=FakeDocuments([fallback]))

    result = resolve_active_document(app)

    assert result["success"] is True
    assert result["document"] is fallback
    assert result["document_name"] == "fallback.dwg"
    assert result["documents_count"] == 1


def test_documents_collection_supports_one_based_item_index():
    from cad.document_resolver import resolve_active_document

    fallback = FakeDocument("one-based.dwg")
    app = FakeApp(active_document=None, documents=FakeDocuments([fallback], one_based=True))

    result = resolve_active_document(app)

    assert result["success"] is True
    assert result["document_name"] == "one-based.dwg"


def test_application_is_not_autocad_document():
    from cad.document_resolver import is_autocad_document, validate_autocad_document

    app = FakeApp(active_document=FakeDocument())

    assert is_autocad_document(app) is False
    result = validate_autocad_document(app)
    assert result["success"] is False
    assert any("SelectionSets" in error for error in result["errors"])


def test_object_without_selection_sets_is_rejected():
    from cad.document_resolver import validate_autocad_document

    result = validate_autocad_document(FakeDocument(valid=False))

    assert result["success"] is False
    assert any("SelectionSets" in error for error in result["errors"])


def test_resolver_failure_lists_documents():
    from cad.document_resolver import resolve_active_document

    app = FakeApp(active_document=FakeDocument("bad-active.dwg", valid=False), documents=FakeDocuments([FakeDocument("bad-list.dwg", valid=False)]))

    result = resolve_active_document(app)

    assert result["success"] is False
    assert result["document"] is None
    assert result["documents"][0]["name"] == "bad-list.dwg"
    json.dumps({key: value for key, value in result.items() if key != "document"}, ensure_ascii=False)


def test_prompt_for_document_choice_can_select_document_by_number():
    from cad.document_resolver import prompt_for_document_choice, resolve_active_document

    first = FakeDocument("first.dwg")
    second = FakeDocument("second.dwg")
    app = FakeApp(
        active_document=FakeDocument("bad-active.dwg", valid=False),
        documents=FakeDocuments([first, second]),
    )
    resolved = resolve_active_document(app)

    result = prompt_for_document_choice(
        app,
        resolved,
        input_func=lambda _prompt: "2",
        print_func=lambda _message: None,
    )

    assert result["success"] is True
    assert result["document"] is second
    assert result["document_name"] == "second.dwg"


def test_prompt_for_document_choice_invalid_number_returns_clear_error():
    from cad.document_resolver import prompt_for_document_choice, resolve_active_document

    app = FakeApp(
        active_document=FakeDocument("bad-active.dwg", valid=False),
        documents=FakeDocuments([FakeDocument("first.dwg"), FakeDocument("second.dwg")]),
    )
    resolved = resolve_active_document(app)

    result = prompt_for_document_choice(
        app,
        resolved,
        input_func=lambda _prompt: "9",
        print_func=lambda _message: None,
    )

    assert result["success"] is False
    assert result["reason"] == "Document number out of range: 9"
