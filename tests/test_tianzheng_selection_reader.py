from __future__ import annotations

import json


class FakeEntity:
    def __init__(self, object_name: str, handle: str, layer: str = "0") -> None:
        self.ObjectName = object_name
        self.EntityName = object_name
        self.Handle = handle
        self.Layer = layer


class FakeSelectionSet:
    def __init__(
        self,
        name: str,
        entities: list[FakeEntity] | None = None,
        *,
        delete_fails: bool = False,
    ) -> None:
        self.Name = name
        self._entities = entities or []
        self.Count = len(self._entities)
        self.select_on_screen_called = False
        self.deleted = False
        self.delete_fails = delete_fails

    def SelectOnScreen(self):
        self.select_on_screen_called = True

    def Item(self, index: int):
        return self._entities[index]

    def Delete(self):
        if self.delete_fails:
            raise AttributeError("Add.Delete")
        self.deleted = True


class FakeSelectionSets:
    def __init__(
        self,
        entities_to_select: list[FakeEntity],
        existing: list[FakeSelectionSet] | None = None,
        *,
        added_delete_fails: bool = False,
        item_by_name: bool = False,
    ) -> None:
        self._items = existing or []
        self.entities_to_select = entities_to_select
        self.added: FakeSelectionSet | None = None
        self.added_delete_fails = added_delete_fails
        self.item_by_name = item_by_name

    @property
    def Count(self) -> int:
        return len(self._items)

    def Item(self, index: int):
        if isinstance(index, str):
            if not self.item_by_name:
                raise AttributeError(index)
            for item in self._items:
                if item.Name == index:
                    return item
            raise AttributeError(index)
        return self._items[index]

    def Add(self, name: str):
        self.added = FakeSelectionSet(
            name,
            self.entities_to_select,
            delete_fails=self.added_delete_fails,
        )
        self._items.append(self.added)
        return self.added


class FakeDocument:
    Name = "pump-room.dwg"

    def __init__(self, selection_sets: FakeSelectionSets) -> None:
        self.SelectionSets = selection_sets


def fake_inspector(entity: FakeEntity) -> dict:
    object_name = entity.ObjectName
    is_proxy = "Proxy" in object_name
    is_tianzheng_like = is_proxy or "TWT" in object_name or "TCH" in object_name
    return {
        "handle": entity.Handle,
        "object_name": object_name,
        "entity_name": entity.EntityName,
        "layer": entity.Layer,
        "color": 256,
        "linetype": "ByLayer",
        "bounding_box": [0.0, 0.0, 0.0, 100.0, 100.0, 0.0],
        "diagnostic": {
            "is_proxy": is_proxy,
            "is_tianzheng_like": is_tianzheng_like,
            "errors": [],
        },
    }


def test_existing_temp_selection_set_is_deleted_before_reading():
    from tianzheng.selection_reader import read_selected_entities

    existing = FakeSelectionSet("__TianzhengSelectionReaderTemp__")
    selected = [FakeEntity("AcDbLine", "L1")]
    selection_sets = FakeSelectionSets(selected, existing=[existing])

    result = read_selected_entities(FakeDocument(selection_sets), inspector=fake_inspector)

    assert result["selection_count"] == 1
    assert existing.deleted is True
    assert selection_sets.added is not None
    assert selection_sets.added.select_on_screen_called is True


def test_select_on_screen_reads_all_selected_objects():
    from tianzheng.selection_reader import read_selected_entities

    selected = [
        FakeEntity("AcDbLine", "L1"),
        FakeEntity("AcDbText", "T1"),
        FakeEntity("AcDbProxyEntity", "P1"),
    ]
    result = read_selected_entities(FakeDocument(FakeSelectionSets(selected)), inspector=fake_inspector)

    assert result["selection_count"] == 3
    assert [entity["handle"] for entity in result["entities"]] == ["L1", "T1", "P1"]


def test_empty_selection_returns_clear_error_and_deletes_temp_set():
    from tianzheng.selection_reader import read_selected_entities
    from tianzheng.selection_utils import NoSelectionError

    selection_sets = FakeSelectionSets([])

    try:
        read_selected_entities(FakeDocument(selection_sets), inspector=fake_inspector)
    except NoSelectionError as exc:
        assert exc.error_code == "NO_SELECTION"
        assert str(exc) == "No entity selected."
    else:  # pragma: no cover
        raise AssertionError("expected NoSelectionError")

    assert selection_sets.added is not None
    assert selection_sets.added.deleted is True


def test_selection_set_delete_failure_falls_back_to_item_by_name():
    from tianzheng.selection_utils import safe_delete_selection_set

    direct = FakeSelectionSet("__TianzhengSelectionReaderTemp__", delete_fails=True)
    named = FakeSelectionSet("__TianzhengSelectionReaderTemp__")

    class SelectionSetsByName(FakeSelectionSets):
        def Item(self, index: int | str):
            if isinstance(index, str):
                return named
            return super().Item(index)

    selection_sets = SelectionSetsByName([], existing=[direct])

    safe_delete_selection_set(FakeDocument(selection_sets), "__TianzhengSelectionReaderTemp__", direct)

    assert direct.deleted is False
    assert named.deleted is True


def test_existing_delete_failure_falls_back_to_iterated_selection_sets():
    from tianzheng.selection_utils import safe_delete_selection_set

    existing = FakeSelectionSet("__TianzhengSelectionReaderTemp__", delete_fails=True)
    fallback = FakeSelectionSet("__TianzhengSelectionReaderTemp__")
    selection_sets = FakeSelectionSets([], existing=[existing, fallback])

    safe_delete_selection_set(FakeDocument(selection_sets), "__TianzhengSelectionReaderTemp__", existing)

    assert fallback.deleted is True


def test_selection_retry_handles_no_selection_then_retries():
    from tianzheng.selection_utils import NoSelectionError, run_selection_with_retry

    calls = {"count": 0}
    outputs: list[str] = []

    def operation():
        calls["count"] += 1
        if calls["count"] == 1:
            raise NoSelectionError()
        return {"success": True}

    result = run_selection_with_retry(
        operation,
        input_func=lambda _prompt: "",
        print_func=outputs.append,
    )

    assert result == {"success": True}
    assert calls["count"] == 2
    assert any("No entity selected" in output for output in outputs)


def test_selection_retry_can_quit_after_no_selection():
    from tianzheng.selection_utils import NoSelectionError, run_selection_with_retry

    result = run_selection_with_retry(
        lambda: (_ for _ in ()).throw(NoSelectionError()),
        active_document="pump-room.dwg",
        input_func=lambda _prompt: "q",
        print_func=lambda _message: None,
    )

    assert result["success"] is False
    assert result["error_code"] == "NO_SELECTION"
    assert result["active_document"] == "pump-room.dwg"


def test_every_object_calls_inspector():
    from tianzheng.selection_reader import read_selected_entities

    calls: list[str] = []

    def inspector(entity: FakeEntity) -> dict:
        calls.append(entity.Handle)
        return fake_inspector(entity)

    selected = [FakeEntity("AcDbLine", "L1"), FakeEntity("AcDbCircle", "C1")]
    read_selected_entities(FakeDocument(FakeSelectionSets(selected)), inspector=inspector)

    assert calls == ["L1", "C1"]


def test_proxy_object_does_not_interrupt_reading():
    from tianzheng.selection_reader import read_selected_entities

    selected = [FakeEntity("AcDbProxyEntity", "P1"), FakeEntity("AcDbLine", "L1")]
    result = read_selected_entities(FakeDocument(FakeSelectionSets(selected)), inspector=fake_inspector)

    assert result["summary"]["proxy"] == 1
    assert result["selection_count"] == 2


def test_temp_selection_set_is_deleted_after_success():
    from tianzheng.selection_reader import read_selected_entities

    selection_sets = FakeSelectionSets([FakeEntity("AcDbLine", "L1")])

    read_selected_entities(FakeDocument(selection_sets), inspector=fake_inspector)

    assert selection_sets.added is not None
    assert selection_sets.added.deleted is True


def test_selected_model_is_json_serializable():
    from tianzheng.selection_reader import read_selected_entities

    result = read_selected_entities(
        FakeDocument(FakeSelectionSets([FakeEntity("TWT_PIPE", "TW1", "TWT_给排水")])),
        inspector=fake_inspector,
    )

    json.dumps(result, ensure_ascii=False)


def test_summary_counts_supported_entity_types():
    from tianzheng.selection_reader import read_selected_entities

    selected = [
        FakeEntity("AcDbLine", "L1"),
        FakeEntity("AcDbPolyline", "PL1"),
        FakeEntity("AcDbBlockReference", "B1"),
        FakeEntity("AcDbText", "T1"),
        FakeEntity("AcDbMText", "MT1"),
        FakeEntity("AcDbAlignedDimension", "D1"),
        FakeEntity("AcDbProxyEntity", "P1"),
        FakeEntity("UnknownObject", "U1"),
    ]
    result = read_selected_entities(FakeDocument(FakeSelectionSets(selected)), inspector=fake_inspector)

    assert result["summary"]["total"] == 8
    assert result["summary"]["line"] == 1
    assert result["summary"]["polyline"] == 1
    assert result["summary"]["block_reference"] == 1
    assert result["summary"]["text"] == 1
    assert result["summary"]["mtext"] == 1
    assert result["summary"]["dimension"] == 1
    assert result["summary"]["proxy"] == 1
    assert result["summary"]["tianzheng_like"] == 1
    assert result["summary"]["unknown"] == 1
