from __future__ import annotations


class FakeEntity:
    def __init__(self, object_name: str, handle: str, layer: str = "0") -> None:
        self.ObjectName = object_name
        self.EntityName = object_name
        self.Handle = handle
        self.Layer = layer
        self.Color = 256
        self.Linetype = "ByLayer"
        self.StartPoint = [0.0, 0.0, 0.0]
        self.EndPoint = [1000.0, 0.0, 0.0]

    def GetBoundingBox(self):
        return ([0.0, 0.0, 0.0], [1000.0, 0.0, 0.0])

    def Delete(self):  # pragma: no cover
        raise AssertionError("diagnostics must be read-only")

    def Move(self, *_args):  # pragma: no cover
        raise AssertionError("diagnostics must be read-only")


class FakeCollection:
    def __init__(self, items: list[FakeEntity]) -> None:
        self._items = items
        self.Count = len(items)

    def __iter__(self):
        return iter(self._items)


class FakeDocument:
    Name = "pump-room.dwg"
    FullName = "D:/cad/pump-room.dwg"

    def __init__(self, entities: list[FakeEntity], selected: list[FakeEntity] | None = None) -> None:
        self.ModelSpace = FakeCollection(entities)
        self.PaperSpace = FakeCollection([])
        self.ActiveSelectionSet = FakeCollection(selected or [])


class FakeManager:
    def __init__(self, document: FakeDocument) -> None:
        self.document = document

    def require_active_document(self):
        return self.document


def test_visibility_diagnostic_counts_proxy_unknown_and_tianzheng_objects():
    from tianzheng.visibility import TianzhengVisibilityDiagnostic

    doc = FakeDocument(
        [
            FakeEntity("AcDbLine", "L1"),
            FakeEntity("AecDbProxyEntity", "P1"),
            FakeEntity("TzDrainPipe", "TZ1"),
            FakeEntity("AcDbTianzhengCustomObject", "U1"),
        ]
    )

    result = TianzhengVisibilityDiagnostic(FakeManager(doc)).diagnose_current_drawing()

    assert result["success"] is True
    assert result["summary"]["total_entities"] == 4
    assert result["summary"]["proxy_entities"] == 1
    assert result["summary"]["tianzheng_like_entities"] == 2
    assert result["summary"]["unknown_cad_entities"] == 3


def test_selected_entity_diagnostic_returns_empty_selection_without_error():
    from tianzheng.visibility import TianzhengVisibilityDiagnostic

    result = TianzhengVisibilityDiagnostic(FakeManager(FakeDocument([]))).diagnose_selected_entities()

    assert result["success"] is True
    assert result["selection_count"] == 0
    assert result["entities"] == []


def test_selected_entity_diagnostic_reads_identity_only():
    from tianzheng.visibility import TianzhengVisibilityDiagnostic

    selected = [FakeEntity("TzValve", "V1", "TWT_VALVE")]

    result = TianzhengVisibilityDiagnostic(
        FakeManager(FakeDocument([], selected=selected))
    ).diagnose_selected_entities()

    assert result["selection_count"] == 1
    assert result["entities"][0]["handle"] == "V1"
    assert result["entities"][0]["object_name"] == "TzValve"
    assert result["entities"][0]["layer"] == "TWT_VALVE"
