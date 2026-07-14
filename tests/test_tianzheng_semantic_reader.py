from __future__ import annotations

import json


class FakeEntity:
    def __init__(
        self,
        object_name: str,
        handle: str = "H1",
        layer: str = "0",
        bounding_box: tuple[list[float], list[float]] | None = None,
        fail_attrs: set[str] | None = None,
        **attrs,
    ) -> None:
        self.ObjectName = object_name
        self.EntityName = object_name
        self.Handle = handle
        self.Layer = layer
        self.Color = 256
        self.Linetype = "ByLayer"
        self._bounding_box = bounding_box or ([0.0, 0.0, 0.0], [100.0, 0.0, 0.0])
        self._fail_attrs = fail_attrs or set()
        self.deleted = False
        self.moved = False
        for key, value in attrs.items():
            setattr(self, key, value)

    def __getattribute__(self, name: str):
        if name not in {
            "_fail_attrs",
            "_bounding_box",
            "__dict__",
            "__class__",
            "__getattribute__",
            "GetBoundingBox",
            "GetXData",
            "GetExtensionDictionary",
            "Delete",
            "Move",
        }:
            fail_attrs = object.__getattribute__(self, "_fail_attrs")
            if name in fail_attrs:
                raise RuntimeError(f"{name} failed")
        return object.__getattribute__(self, name)

    def GetBoundingBox(self):
        return self._bounding_box

    def GetXData(self, _app_name=""):
        return ([1001, 1000], ["TWT", self.ObjectName])

    def GetExtensionDictionary(self):
        return FakeDictionary(["TWT_META"])

    def Delete(self):  # pragma: no cover
        self.deleted = True
        raise AssertionError("semantic reader must be read-only")

    def Move(self, *_args):  # pragma: no cover
        self.moved = True
        raise AssertionError("semantic reader must be read-only")


class FakeDictionary:
    def __init__(self, names: list[str]) -> None:
        self._items = [FakeDictionaryItem(name) for name in names]
        self.Count = len(self._items)

    def __iter__(self):
        return iter(self._items)


class FakeDictionaryItem:
    def __init__(self, name: str) -> None:
        self.Name = name


class FakeSelectionSet:
    def __init__(self, name: str, entities: list[FakeEntity]) -> None:
        self.Name = name
        self._entities = entities
        self.Count = len(entities)
        self.deleted = False
        self.select_on_screen_called = False

    def SelectOnScreen(self):
        self.select_on_screen_called = True

    def Item(self, index: int):
        return self._entities[index]

    def Delete(self):
        self.deleted = True


class FakeSelectionSets:
    def __init__(self, entities: list[FakeEntity]) -> None:
        self.entities = entities
        self.added: FakeSelectionSet | None = None
        self._items: list[FakeSelectionSet] = []

    @property
    def Count(self) -> int:
        return len(self._items)

    def Item(self, index: int):
        return self._items[index]

    def Add(self, name: str):
        self.added = FakeSelectionSet(name, self.entities)
        self._items.append(self.added)
        return self.added


class FakeDocument:
    Name = "pump-room.dwg"

    def __init__(self, entities: list[FakeEntity]) -> None:
        self.ModelSpace = object()
        self.Utility = object()
        self.SelectionSets = FakeSelectionSets(entities)


def test_tdb_pipe_is_read_as_pipe():
    from tianzheng.semantic_reader import read_tdb_pipe

    result = read_tdb_pipe(FakeEntity("TDbPipe", layer="PIPE-消防"))

    assert result["semantic_type"] == "pipe"
    assert result["object_name"] == "TDbPipe"


def test_tdb_pipe_infers_fire_system_from_layer():
    from tianzheng.semantic_reader import read_tdb_pipe

    result = read_tdb_pipe(FakeEntity("TDbPipe", layer="PIPE-消防"))

    assert result["system_type"] == "消防"


def test_tdb_pipe_infers_sprinkler_system_from_layer():
    from tianzheng.semantic_reader import read_tdb_pipe

    result = read_tdb_pipe(FakeEntity("TDbPipe", layer="PIPE-喷淋"))

    assert result["system_type"] == "喷淋"


def test_tdb_pipe_reads_radius_as_display_radius_only():
    from tianzheng.semantic_reader import read_tdb_pipe

    result = read_tdb_pipe(FakeEntity("TDbPipe", layer="PIPE-消防", Radius=50.0))

    assert result["properties"]["display_radius"] == 50.0
    assert "diameter_guess" not in result["properties"]
    assert result["diagnostic"]["read_radius_success"] is True


def test_tdb_pipe_uses_dndiameter_for_diameter():
    from tianzheng.semantic_reader import read_tdb_pipe

    result = read_tdb_pipe(
        FakeEntity("TDbPipe", layer="PIPE-消防", Radius=1.5, DNDiameter=100)
    )

    assert result["diameter"] == {
        "raw": 100,
        "normalized": "DN100",
        "source": "TDbPipe.DNDiameter",
        "confidence": 0.95,
        "requires_confirmation": False,
    }
    assert result["properties"]["display_radius"] == 1.5


def test_tdb_pipe_dndiameter_failure_requires_confirmation():
    from tianzheng.semantic_reader import read_tdb_pipe

    result = read_tdb_pipe(
        FakeEntity("TDbPipe", layer="PIPE-消防", Radius=1.5, fail_attrs={"DNDiameter"})
    )

    assert result["diameter"] == {
        "raw": None,
        "normalized": None,
        "source": None,
        "confidence": 0.0,
        "requires_confirmation": True,
    }
    assert "DNDiameter" in result["properties"]["failed_properties"]


def test_tdb_pipe_reads_systype_and_elevation():
    from tianzheng.semantic_reader import read_tdb_pipe

    result = read_tdb_pipe(
        FakeEntity(
            "TDbPipe",
            layer="PIPE-消防",
            SysType="消防",
            SElevation=1.2,
            EElevation=1.5,
            ModelType="室内管",
        )
    )

    assert result["system_type"] == "消防"
    assert result["system_type_source"] == "layer_inference"
    assert result["system_type_raw"] == "消防"
    assert result["system_type_raw_source"] == "TDbPipe.SysType"
    assert result["elevation"] == {
        "start": 1.2,
        "end": 1.5,
        "source": "TDbPipe.SElevation / TDbPipe.EElevation",
    }
    assert result["properties"]["ModelType"] == "室内管"


def test_tdb_pipe_infers_horizontal_and_vertical_from_bounding_box():
    from tianzheng.semantic_reader import read_tdb_pipe

    horizontal = read_tdb_pipe(
        FakeEntity("TDbPipe", bounding_box=([0.0, 0.0, 0.0], [500.0, 0.0, 0.0]))
    )
    vertical = read_tdb_pipe(
        FakeEntity("TDbPipe", bounding_box=([10.0, 0.0, 0.0], [10.0, 500.0, 0.0]))
    )

    assert horizontal["inferred_geometry"]["orientation"] == "horizontal"
    assert vertical["inferred_geometry"]["orientation"] == "vertical"
    assert horizontal["inferred_geometry"]["source"] == "bounding_box_inference"


def test_tdb_pipe_valve_is_read_as_valve():
    from tianzheng.semantic_reader import read_tdb_pipe_valve

    result = read_tdb_pipe_valve(FakeEntity("TDbPipeValve", layer="VALVE_消防"))

    assert result["semantic_type"] == "valve"
    assert result["object_name"] == "TDbPipeValve"


def test_tdb_pipe_valve_infers_fire_system_from_layer():
    from tianzheng.semantic_reader import read_tdb_pipe_valve

    result = read_tdb_pipe_valve(FakeEntity("TDbPipeValve", layer="VALVE_消防"))

    assert result["system_type"] == "消防"
    assert result["valve_type_guess"] == "消防阀门"


def test_evalve_sprinkler_infers_electric_sprinkler_valve():
    from tianzheng.semantic_reader import read_tdb_pipe_valve

    result = read_tdb_pipe_valve(FakeEntity("TDbPipeValve", layer="EVALVE_喷淋"))

    assert result["system_type"] == "喷淋"
    assert result["valve_type_guess"] == "喷淋电动阀"


def test_tdb_dimension_is_read_as_dimension():
    from tianzheng.semantic_reader import read_tdb_dimension

    result = read_tdb_dimension(FakeEntity("TDbDimension2", layer="TWT_DIM", TextOverride="DN100"))

    assert result["semantic_type"] == "dimension"
    assert result["text"] == "DN100"


def test_property_read_failure_does_not_crash():
    from tianzheng.semantic_reader import read_tdb_dimension

    result = read_tdb_dimension(
        FakeEntity("TDbDimension2", layer="TWT_DIM", fail_attrs={"TextOverride", "Measurement"})
    )

    assert result["semantic_type"] == "dimension"
    assert result["diagnostic"]["read_text_success"] is False
    assert result["diagnostic"]["read_measurement_success"] is False
    assert result["diagnostic"]["warnings"]


def test_unknown_tianzheng_object_preserves_identity():
    from tianzheng.semantic_reader import read_semantic_entity

    result = read_semantic_entity(FakeEntity("TDbUnknownThing", handle="U1", layer="TWT_MISC"))

    assert result["semantic_type"] == "unknown_tianzheng"
    assert result["handle"] == "U1"
    assert result["object_name"] == "TDbUnknownThing"
    assert result["layer"] == "TWT_MISC"


def test_semantic_model_output_is_json_serializable():
    from tianzheng.semantic_reader import read_selected_tianzheng_semantic_model

    model = read_selected_tianzheng_semantic_model(
        FakeDocument(
            [
                FakeEntity("TDbPipe", handle="P1", layer="PIPE-消防", Radius=50.0),
                FakeEntity("TDbPipeValve", handle="V1", layer="VALVE_消防"),
                FakeEntity("TDbDimension2", handle="D1", layer="TWT_DIM", TextOverride="DN100"),
            ]
        )
    )

    assert model["summary"]["pipe"] == 1
    assert model["summary"]["valve"] == 1
    assert model["summary"]["dimension"] == 1
    json.dumps(model, ensure_ascii=False)


def test_semantic_reader_does_not_write_to_cad_entities():
    from tianzheng.semantic_reader import read_semantic_entity

    entity = FakeEntity("TDbPipe", handle="P1", layer="PIPE-消防")

    read_semantic_entity(entity)

    assert entity.deleted is False
    assert entity.moved is False


def test_semantic_reader_rejects_invalid_document_before_selectionsets_access():
    from tianzheng.semantic_reader import read_selected_tianzheng_semantic_model

    class InvalidDocument:
        Name = "not-a-document"

    try:
        read_selected_tianzheng_semantic_model(InvalidDocument())
    except RuntimeError as exc:
        assert "Invalid AutoCAD Document" in str(exc)
        assert "SelectionSets" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_semantic_reader_empty_selection_raises_no_selection_error():
    from tianzheng.semantic_reader import read_selected_tianzheng_semantic_model
    from tianzheng.selection_utils import NoSelectionError

    try:
        read_selected_tianzheng_semantic_model(FakeDocument([]))
    except NoSelectionError as exc:
        assert exc.error_code == "NO_SELECTION"
        assert str(exc) == "No entity selected."
    else:  # pragma: no cover
        raise AssertionError("expected NoSelectionError")


def test_tdb_pipe_fitting_is_read_as_fitting():
    from tianzheng.semantic_reader import read_tdb_pipe_fitting

    result = read_tdb_pipe_fitting(FakeEntity("TDbPipeFitting", handle="F1", layer="PIPE-消防"))

    assert result["semantic_type"] == "fitting"
    assert result["object_name"] == "TDbPipeFitting"


def test_tdb_pipe_fitting_infers_fire_system_from_layer():
    from tianzheng.semantic_reader import read_tdb_pipe_fitting

    result = read_tdb_pipe_fitting(FakeEntity("TDbPipeFitting", layer="PIPE-消防"))

    assert result["system_type"] == "消防"


def test_tdb_pipe_fitting_outputs_center_width_and_height():
    from tianzheng.semantic_reader import read_tdb_pipe_fitting

    result = read_tdb_pipe_fitting(
        FakeEntity(
            "TDbPipeFitting",
            bounding_box=([100.0, 200.0, 0.0], [300.0, 500.0, 0.0]),
        )
    )

    assert result["inferred_geometry"]["center"] == [200.0, 350.0, 0.0]
    assert result["inferred_geometry"]["width"] == 200.0
    assert result["inferred_geometry"]["height"] == 300.0
    assert result["inferred_geometry"]["source"] == "bounding_box_inference"


def test_summary_includes_fitting_and_does_not_count_it_as_unknown():
    from tianzheng.semantic_reader import read_selected_tianzheng_semantic_model

    model = read_selected_tianzheng_semantic_model(
        FakeDocument(
            [
                FakeEntity("TDbPipe", handle="P1", layer="PIPE-消防"),
                FakeEntity("TDbPipeValve", handle="V1", layer="VALVE_消防"),
                FakeEntity("TDbPipeFitting", handle="F1", layer="PIPE-消防"),
            ]
        )
    )

    assert model["summary"]["fitting"] == 1
    assert model["summary"]["unknown_tianzheng"] == 0


def test_probe_entity_properties_reads_successful_properties():
    from tianzheng.semantic_reader import probe_entity_properties

    result = probe_entity_properties(
        FakeEntity("TDbPipe", Radius=50.0, PipeDN="DN100"),
        ["Radius", "PipeDN"],
    )

    assert result["properties"]["Radius"] == 50.0
    assert result["properties"]["PipeDN"] == "DN100"
    assert result["readable_properties"] == ["Radius", "PipeDN"]


def test_probe_entity_properties_records_failed_properties_without_crashing():
    from tianzheng.semantic_reader import probe_entity_properties

    result = probe_entity_properties(
        FakeEntity("TDbPipe", Radius=50.0, fail_attrs={"PipeDN"}),
        ["Radius", "PipeDN"],
    )

    assert result["properties"]["Radius"] == 50.0
    assert "PipeDN" in result["failed_properties"]


def test_probe_entity_properties_converts_tuple_values_to_json_lists():
    from tianzheng.semantic_reader import probe_entity_properties

    result = probe_entity_properties(
        FakeEntity("TDbPipeFitting", Center=(10.0, 20.0, 0.0)),
        ["Center"],
    )

    assert result["properties"]["Center"] == [10.0, 20.0, 0.0]
    json.dumps(result, ensure_ascii=False)


def test_detailed_first_20_entities_contains_properties_and_inferred_geometry():
    from tianzheng.semantic_reader import (
        read_selected_tianzheng_semantic_model,
        semantic_model_diagnostics,
    )

    model = read_selected_tianzheng_semantic_model(
        FakeDocument([FakeEntity("TDbPipeFitting", handle="F1", layer="PIPE-消防")])
    )
    diagnostics = semantic_model_diagnostics(model)
    first = diagnostics["first_20_entities"][0]

    assert first["semantic_type"] == "fitting"
    assert "properties" in first
    assert "inferred_geometry" in first
    assert "xdata" in first
    assert "extension_dictionary_keys" in first


def test_pipe_first_20_summary_includes_diameter_radius_length_and_elevation():
    from tianzheng.semantic_reader import (
        read_selected_tianzheng_semantic_model,
        semantic_model_diagnostics,
    )

    model = read_selected_tianzheng_semantic_model(
        FakeDocument(
            [
                FakeEntity(
                    "TDbPipe",
                    handle="P1",
                    layer="PIPE-消防",
                    Radius=1.5,
                    DNDiameter=100,
                    Length=1142.8,
                    SElevation=1.2,
                    EElevation=1.5,
                )
            ]
        )
    )
    diagnostics = semantic_model_diagnostics(model)
    first = diagnostics["first_20_entities"][0]

    assert first["handle"] == "P1"
    assert first["layer"] == "PIPE-消防"
    assert first["system_type"] == "消防"
    assert first["diameter"]["normalized"] == "DN100"
    assert first["diameter"]["source"] == "TDbPipe.DNDiameter"
    assert first["diameter"]["confidence"] == 0.95
    assert first["display_radius"] == 1.5
    assert first["length"] == 1142.8
    assert first["elevation"]["start"] == 1.2
    assert first["elevation"]["end"] == 1.5


def test_fitting_semantic_model_is_json_serializable():
    from tianzheng.semantic_reader import read_selected_tianzheng_semantic_model

    model = read_selected_tianzheng_semantic_model(
        FakeDocument([FakeEntity("TDbPipeFitting", handle="F1", layer="PIPE-消防")])
    )

    json.dumps(model, ensure_ascii=False)
