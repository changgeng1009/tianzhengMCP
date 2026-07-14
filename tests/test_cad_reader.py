from __future__ import annotations

from typing import Any


class FakeLayer:
    def __init__(self, name: str = "0", color: int = 7, linetype: str = "Continuous") -> None:
        self.Name = name
        self.Color = color
        self.Linetype = linetype


class FakeLayers:
    def __init__(self) -> None:
        self._layers = [FakeLayer("0"), FakeLayer("A-WALL", 1, "Continuous")]
        self.Count = len(self._layers)

    def __iter__(self):
        return iter(self._layers)


class FakeBaseEntity:
    def __init__(self, object_name: str, handle: str, layer: str = "0") -> None:
        self.ObjectName = object_name
        self.EntityName = object_name
        self.Handle = handle
        self.Layer = layer
        self.Color = 256
        self.Linetype = "ByLayer"
        self.get_bounding_box_calls = 0

    def GetBoundingBox(self):
        self.get_bounding_box_calls += 1
        return ([0.0, 0.0, 0.0], [10.0, 10.0, 0.0])

    def Delete(self):  # pragma: no cover - must never be called by reader
        raise AssertionError("reader must not delete CAD entities")

    def Move(self, *_args):  # pragma: no cover - must never be called by reader
        raise AssertionError("reader must not move CAD entities")


class FakeLineEntity(FakeBaseEntity):
    def __init__(self) -> None:
        super().__init__("AcDbLine", "L1", "A-WALL")
        self.StartPoint = [0.0, 0.0, 0.0]
        self.EndPoint = [5000.0, 0.0, 0.0]


class FakePolylineEntity(FakeBaseEntity):
    def __init__(self) -> None:
        super().__init__("AcDbPolyline", "P1")
        self.Coordinates = [0.0, 0.0, 1000.0, 0.0, 1000.0, 500.0]


class FakeTextEntity(FakeBaseEntity):
    def __init__(self) -> None:
        super().__init__("AcDbText", "T1")
        self.TextString = "测试文字"
        self.InsertionPoint = [100.0, 200.0, 0.0]
        self.Height = 250.0


class FakeBlockReferenceEntity(FakeBaseEntity):
    def __init__(self) -> None:
        super().__init__("AcDbBlockReference", "B1")
        self.Name = "VALVE_BLOCK"
        self.EffectiveName = "VALVE_BLOCK"
        self.InsertionPoint = [300.0, 400.0, 0.0]
        self.Rotation = 0.0


class FakeUnknownEntity(FakeBaseEntity):
    def __init__(self) -> None:
        super().__init__("AcDbTianzhengCustomObject", "U1")

    def GetBoundingBox(self):
        self.get_bounding_box_calls += 1
        raise RuntimeError("bounding box unavailable")


class FakeModelSpace:
    def __init__(self, entities: list[Any]) -> None:
        self._entities = entities
        self.Count = len(entities)
        self.add_line_called = False

    def __iter__(self):
        return iter(self._entities)

    def AddLine(self, *_args):  # pragma: no cover - must never be called by reader
        self.add_line_called = True
        raise AssertionError("reader must be read-only")


class FakeDocument:
    def __init__(self, entities: list[Any], selected: list[Any] | None = None) -> None:
        self.Name = "reader-test.dwg"
        self.FullName = "D:/tmp/reader-test.dwg"
        self.ModelSpace = FakeModelSpace(entities)
        self.PaperSpace = FakeModelSpace([])
        self.Layers = FakeLayers()
        self.ActiveSelectionSet = FakeModelSpace(selected or [])


class FakeManager:
    def __init__(self, document: FakeDocument) -> None:
        self.document = document

    def require_active_document(self) -> FakeDocument:
        return self.document


def test_read_current_drawing_extracts_supported_entities():
    from cad.reader import CADReader
    from vision.models import CurrentCADModel

    document = FakeDocument(
        [
            FakeLineEntity(),
            FakePolylineEntity(),
            FakeTextEntity(),
            FakeBlockReferenceEntity(),
        ]
    )

    result = CADReader(FakeManager(document)).read_current_drawing()

    assert result["success"] is True
    assert result["model"]["source"]["kind"] == "current_autocad"
    assert [entity["type"] for entity in result["model"]["entities"]] == [
        "line",
        "polyline",
        "text",
        "block_reference",
    ]
    assert result["model"]["entities"][0]["handle"] == "L1"
    assert result["model"]["entities"][0]["geometry"]["coordinate_system"] == "cad_world"
    assert result["model"]["entities"][0]["geometry"]["points"][0] == {
        "x": 0.0,
        "y": 0.0,
        "coordinate_system": "cad_world",
    }
    assert result["model"]["entities"][2]["properties"]["text"] == "测试文字"
    assert result["model"]["entities"][3]["properties"]["block_name"] == "VALVE_BLOCK"
    assert CurrentCADModel.from_dict(result["model"]).source["kind"] == "current_autocad"


def test_unknown_entity_does_not_crash_and_keeps_identity():
    from cad.reader import CADReader

    result = CADReader(FakeManager(FakeDocument([FakeUnknownEntity()]))).read_current_drawing()
    entity = result["model"]["entities"][0]

    assert entity["type"] == "unknown_cad_entity"
    assert entity["handle"] == "U1"
    assert entity["object_name"] == "AcDbTianzhengCustomObject"
    assert entity["bounding_box"] is None
    assert entity["confidence"] < 1.0
    assert entity["reason"] == "Unsupported CAD object type."


def test_summarize_current_drawing_counts_entity_types():
    from cad.reader import CADReader

    result = CADReader(
        FakeManager(
            FakeDocument(
                [
                    FakeLineEntity(),
                    FakePolylineEntity(),
                    FakeTextEntity(),
                    FakeBlockReferenceEntity(),
                    FakeUnknownEntity(),
                ]
            )
        )
    ).summarize_current_drawing()

    assert result["summary"] == {
        "lines": 1,
        "polylines": 1,
        "circles": 0,
        "arcs": 0,
        "texts": 1,
        "mtexts": 0,
        "blocks": 1,
        "dimensions": 0,
        "unknown": 1,
    }


def test_read_selected_entities_returns_empty_selection_without_error():
    from cad.reader import CADReader

    result = CADReader(FakeManager(FakeDocument([FakeLineEntity()], selected=[]))).read_selected_entities()

    assert result["success"] is True
    assert result["selection_count"] == 0
    assert result["model"]["entities"] == []


def test_reader_is_read_only_and_never_calls_add_line():
    from cad.reader import CADReader

    document = FakeDocument([FakeLineEntity()])

    CADReader(FakeManager(document)).read_current_drawing()

    assert document.ModelSpace.add_line_called is False
