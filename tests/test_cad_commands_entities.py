from tests.test_cad_connection import FakeAutoCAD


def test_send_command_uses_active_document_send_command() -> None:
    from cad.commands import CommandService
    from cad.connection import AutoCADConnectionManager

    app = FakeAutoCAD()
    manager = AutoCADConnectionManager(com_get_object=lambda _prog_id: app)
    manager.connect()

    command = "LINE\n0,0\n5000,0\n\n"
    result = CommandService(manager).send_command(command)

    assert result == {
        "success": True,
        "command_sent": True,
        "active_document": "test.dwg",
    }
    assert app.ActiveDocument.commands == [command]


def test_draw_line_uses_model_space_add_line_and_regen(monkeypatch) -> None:
    from cad.connection import AutoCADConnectionManager
    import cad.entities

    app = FakeAutoCAD()
    manager = AutoCADConnectionManager(com_get_object=lambda _prog_id: app)
    manager.connect()

    def fake_make_point_variant(x: float, y: float, z: float = 0.0) -> tuple[str, float, float, float]:
        return ("variant", float(x), float(y), float(z))

    monkeypatch.setattr(cad.entities, "make_point_variant", fake_make_point_variant)

    result = cad.entities.EntityService(manager).draw_line(0, 0, 5000, 0)

    assert result == {
        "success": True,
        "entity_type": "Line",
        "object_name": "AcDbLine",
        "handle": "2A3",
        "active_document": "test.dwg",
        "start": [0.0, 0.0, 0.0],
        "end": [5000.0, 0.0, 0.0],
        "point_variant": "VARIANT(VT_ARRAY | VT_R8)",
    }
    assert app.ActiveDocument.ModelSpace.lines == [
        (("variant", 0.0, 0.0, 0.0), ("variant", 5000.0, 0.0, 0.0))
    ]
    assert app.ActiveDocument.ModelSpace.created_lines[0].updated is True
    assert app.ActiveDocument.regen_modes == [1]


def test_make_point_variant_returns_double_array_variant(cad_test_mock_com_modules) -> None:
    from cad.entities import make_point_variant

    point = make_point_variant(1, 2, 3)

    assert list(point.value) == [1.0, 2.0, 3.0]
