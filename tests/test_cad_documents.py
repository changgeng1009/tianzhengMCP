from tests.test_cad_connection import FakeAutoCAD


def test_list_documents_marks_active_document() -> None:
    from cad.connection import AutoCADConnectionManager
    from cad.document import DocumentService

    manager = AutoCADConnectionManager(com_get_object=lambda _prog_id: FakeAutoCAD())
    manager.connect()

    result = DocumentService(manager).list_documents()

    assert result == {
        "connected": True,
        "documents": [
            {
                "name": "test.dwg",
                "full_name": "D:/tmp/test.dwg",
                "is_active": True,
            }
        ],
    }


def test_get_active_document_returns_document_details() -> None:
    from cad.connection import AutoCADConnectionManager
    from cad.document import DocumentService

    manager = AutoCADConnectionManager(com_get_object=lambda _prog_id: FakeAutoCAD())
    manager.connect()

    result = DocumentService(manager).get_active_document()

    assert result == {
        "connected": True,
        "name": "test.dwg",
        "full_name": "D:/tmp/test.dwg",
        "active_layer": "0",
        "active_space": "model",
        "model_space_count": 3,
    }
