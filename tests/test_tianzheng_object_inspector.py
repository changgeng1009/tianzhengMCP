from __future__ import annotations

import json


class FakeEntity:
    def __init__(
        self,
        object_name: str = "AcDbLine",
        handle: str = "L1",
        layer: str = "0",
        fail_attrs: set[str] | None = None,
        fail_bbox: bool = False,
        fail_xdata: bool = False,
        fail_extension_dictionary: bool = False,
    ) -> None:
        self._fail_attrs = fail_attrs or set()
        self._fail_bbox = fail_bbox
        self._fail_xdata = fail_xdata
        self._fail_extension_dictionary = fail_extension_dictionary
        self.ObjectName = object_name
        self.EntityName = object_name
        self.Handle = handle
        self.Layer = layer
        self.Color = 256
        self.Linetype = "ByLayer"
        self.StartPoint = [0.0, 0.0, 0.0]
        self.EndPoint = [1000.0, 0.0, 0.0]

    def __getattribute__(self, name: str):
        if name not in {
            "_fail_attrs",
            "_fail_bbox",
            "_fail_xdata",
            "_fail_extension_dictionary",
            "__dict__",
            "__class__",
            "__getattribute__",
            "GetBoundingBox",
            "GetXData",
            "GetExtensionDictionary",
        }:
            fail_attrs = object.__getattribute__(self, "_fail_attrs")
            if name in fail_attrs:
                raise RuntimeError(f"{name} read failed")
        return object.__getattribute__(self, name)

    def GetBoundingBox(self):
        if self._fail_bbox:
            raise RuntimeError("bounding box failed")
        return ([0.0, 0.0, 0.0], [1000.0, 500.0, 0.0])

    def GetXData(self, _app_name=""):
        if self._fail_xdata:
            raise RuntimeError("xdata failed")
        return ([1001, 1000], ["TWT", "PIPE"])

    def GetExtensionDictionary(self):
        if self._fail_extension_dictionary:
            raise RuntimeError("extension dictionary failed")
        return FakeDictionary(["TWT_META"])


class FakeDictionary:
    def __init__(self, names: list[str]) -> None:
        self._items = [FakeDictionaryItem(name) for name in names]
        self.Count = len(self._items)

    def __iter__(self):
        return iter(self._items)


class FakeDictionaryItem:
    def __init__(self, name: str) -> None:
        self.Name = name


def test_normal_line_outputs_identity_fields():
    from tianzheng.object_inspector import inspect_entity

    result = inspect_entity(FakeEntity())

    assert result["handle"] == "L1"
    assert result["object_name"] == "AcDbLine"
    assert result["layer"] == "0"


def test_proxy_entity_does_not_crash_and_marks_proxy():
    from tianzheng.object_inspector import inspect_entity

    result = inspect_entity(FakeEntity(object_name="AcDbProxyEntity", handle="P1"))

    assert result["handle"] == "P1"
    assert result["diagnostic"]["is_proxy"] is True


def test_property_read_failure_is_recorded_in_errors():
    from tianzheng.object_inspector import inspect_entity

    result = inspect_entity(FakeEntity(fail_attrs={"Layer"}))

    assert result["layer"] is None
    assert any("Layer" in error for error in result["diagnostic"]["errors"])


def test_bounding_box_success_outputs_flat_box():
    from tianzheng.object_inspector import inspect_entity

    result = inspect_entity(FakeEntity())

    assert result["bounding_box"] == [0.0, 0.0, 0.0, 1000.0, 500.0, 0.0]
    assert result["diagnostic"]["read_bounding_box_success"] is True


def test_bounding_box_failure_does_not_crash():
    from tianzheng.object_inspector import inspect_entity

    result = inspect_entity(FakeEntity(fail_bbox=True))

    assert result["bounding_box"] is None
    assert result["diagnostic"]["read_bounding_box_success"] is False
    assert any("GetBoundingBox" in error for error in result["diagnostic"]["errors"])


def test_tianzheng_name_signals_are_detected():
    from tianzheng.object_inspector import inspect_entity

    assert inspect_entity(FakeEntity(object_name="TWT_PIPE"))["diagnostic"]["is_tianzheng_like"]
    assert inspect_entity(FakeEntity(object_name="TCH_VALVE"))["diagnostic"]["is_tianzheng_like"]
    assert inspect_entity(FakeEntity(object_name="TangentPump"))["diagnostic"]["is_tianzheng_like"]


def test_acdb_proxy_entity_is_tianzheng_like_signal():
    from tianzheng.object_inspector import inspect_entity

    result = inspect_entity(FakeEntity(object_name="AcDbProxyEntity"))

    assert result["diagnostic"]["is_proxy"] is True
    assert result["diagnostic"]["is_tianzheng_like"] is True


def test_xdata_failure_does_not_crash():
    from tianzheng.object_inspector import inspect_entity

    result = inspect_entity(FakeEntity(fail_xdata=True))

    assert result["xdata_available"] is False
    assert result["xdata_error"] is not None


def test_extension_dictionary_failure_does_not_crash():
    from tianzheng.object_inspector import inspect_entity

    result = inspect_entity(FakeEntity(fail_extension_dictionary=True))

    assert result["extension_dictionary_available"] is False
    assert result["extension_dictionary_error"] is not None


def test_inspection_output_is_json_serializable():
    from tianzheng.object_inspector import inspect_entity

    result = inspect_entity(FakeEntity(object_name="TWT_PIPE", layer="TWT_给排水"))

    json.dumps(result, ensure_ascii=False)


class FakeSelectionSet:
    def __init__(self, name: str, entities: list[FakeEntity] | None = None) -> None:
        self.Name = name
        self._entities = entities or []
        self.Count = len(self._entities)
        self.select_on_screen_called = False
        self.deleted = False

    def SelectOnScreen(self):
        self.select_on_screen_called = True

    def Item(self, index: int):
        return self._entities[index]

    def Delete(self):
        self.deleted = True


class FakeSelectionSets:
    def __init__(self, entities_to_select: list[FakeEntity], existing: list[FakeSelectionSet] | None = None) -> None:
        self._items = existing or []
        self.entities_to_select = entities_to_select
        self.added: FakeSelectionSet | None = None

    @property
    def Count(self) -> int:
        return len(self._items)

    def Item(self, index: int):
        return self._items[index]

    def Add(self, name: str):
        self.added = FakeSelectionSet(name, self.entities_to_select)
        self._items.append(self.added)
        return self.added


class FakeSelectionDocument:
    def __init__(self, selection_sets: FakeSelectionSets) -> None:
        self.SelectionSets = selection_sets


def test_selection_set_picker_deletes_existing_temp_set_and_returns_first_entity():
    from scripts.manual_tianzheng_object_inspect import get_entity_by_selection_set

    existing = FakeSelectionSet("__TianzhengObjectInspectTemp__")
    first = FakeEntity(handle="L1")
    second = FakeEntity(handle="L2")
    selection_sets = FakeSelectionSets([first, second], existing=[existing])

    result = get_entity_by_selection_set(FakeSelectionDocument(selection_sets))

    assert existing.deleted is True
    assert selection_sets.added is not None
    assert selection_sets.added.select_on_screen_called is True
    assert selection_sets.added.deleted is True
    assert result is first


def test_selection_set_picker_raises_clear_error_when_nothing_selected():
    from scripts.manual_tianzheng_object_inspect import get_entity_by_selection_set

    selection_sets = FakeSelectionSets([])

    try:
        get_entity_by_selection_set(FakeSelectionDocument(selection_sets))
    except RuntimeError as exc:
        assert "未选择任何对象" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")
    assert selection_sets.added is not None
    assert selection_sets.added.deleted is True
