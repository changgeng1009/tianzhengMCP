from __future__ import annotations

import json


class FakeTDbPipe:
    ObjectName = "TDbPipe"
    EntityName = "TDbPipe"
    Handle = "P1"
    Layer = "PIPE-消防"
    Radius = 1.5

    def __init__(self, fail_attrs: set[str] | None = None, **attrs) -> None:
        self.deleted = False
        self.moved = False
        self._fail_attrs = fail_attrs or set()
        for key, value in attrs.items():
            setattr(self, key, value)

    def __getattribute__(self, name: str):
        if name not in {
            "_fail_attrs",
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
        return ([0.0, 0.0, 0.0], [100.0, 20.0, 0.0])

    def GetXData(self, app_name=""):
        if app_name in ("", None, "TG_PIPE"):
            return ([1001, 1000], ["TG_PIPE", "DN150"])
        raise RuntimeError(f"no xdata for {app_name}")

    def GetExtensionDictionary(self):
        return FakeDictionary([FakeDictionaryItem("PIPE_META", TextString="DN100")])

    def Delete(self):  # pragma: no cover
        self.deleted = True
        raise AssertionError("deep probe must be read-only")

    def Move(self, *_args):  # pragma: no cover
        self.moved = True
        raise AssertionError("deep probe must be read-only")


class FakeDictionary:
    def __init__(self, items: list[object]) -> None:
        self._items = items
        self.Count = len(items)

    def __iter__(self):
        return iter(self._items)

    def Item(self, index: int):
        return self._items[index]


class FakeDictionaryItem:
    ObjectName = "TDbPipeDictionaryRecord"
    Handle = "D1"

    def __init__(self, name: str, **attrs) -> None:
        self.Name = name
        for key, value in attrs.items():
            setattr(self, key, value)


class FakeEntity:
    ObjectName = "AcDbLine"
    EntityName = "AcDbLine"
    Handle = "L1"
    Layer = "0"


class FakeOleObj:
    def GetTypeInfo(self):
        return FakeTypeInfo()


class FakeTypeInfo:
    def GetTypeAttr(self):
        return {"type": "FakeTypeAttr"}

    def GetNames(self, _memid=0):
        return ["TDbPipe", "PipeDN", "Radius"]


def test_tdbpipe_radius_can_be_read():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe())

    assert result["known_properties"]["Radius"] == 1.5
    assert result["handle"] == "P1"
    assert result["success"] is True


def test_pipe_dn_property_is_detected_as_diameter_candidate():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe(PipeDN="DN200"))

    assert any(candidate["diameter"] == "DN200" for candidate in result["diameter_candidates"])
    assert result["diagnostic"]["has_dn"] is True


def test_dndiameter_number_normalizes_to_dn():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe(DNDiameter=100))

    assert result["known_properties"]["DNDiameter"] == 100
    assert result["dn_diameter_raw"] == 100
    assert result["normalized_diameter"] == "DN100"
    assert result["diameter_source"] == "TDbPipe.DNDiameter"
    assert result["diameter_confidence"] == 0.95


def test_dndiameter_numeric_string_normalizes_to_dn():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe(DNDiameter="100"))

    assert result["normalized_diameter"] == "DN100"


def test_dndiameter_existing_dn_string_is_preserved():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe(DNDiameter="DN100"))

    assert result["normalized_diameter"] == "DN100"


def test_dndiameter_read_failure_keeps_normalized_null():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe(fail_attrs={"DNDiameter"}))

    assert result["dn_diameter_raw"] is None
    assert result["normalized_diameter"] is None
    assert result["diameter_source"] is None
    assert result["diameter_confidence"] == 0.0
    assert "DNDiameter" in result["failed_properties"]


def test_typeinfo_exposed_properties_are_read():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(
        FakeTDbPipe(
            DNDiameter=100,
            SysType="消防",
            SElevation=1.2,
            EElevation=1.5,
            ModelType="室内管",
            DrawLabel=True,
            LabelLayer="TWT_DIM",
            PipeWeight=12.5,
            TextHeight=350,
            TextStyle="Standard",
            TextColor=1,
        )
    )

    assert result["known_properties"]["SysType"] == "消防"
    assert result["known_properties"]["SElevation"] == 1.2
    assert result["known_properties"]["EElevation"] == 1.5
    assert result["known_properties"]["ModelType"] == "室内管"
    assert result["known_properties"]["DrawLabel"] is True
    assert result["known_properties"]["LabelLayer"] == "TWT_DIM"
    assert result["known_properties"]["PipeWeight"] == 12.5
    assert result["known_properties"]["TextHeight"] == 350
    assert result["known_properties"]["TextStyle"] == "Standard"
    assert result["known_properties"]["TextColor"] == 1


def test_text_string_diameter_is_detected():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe(TextString="管径 DN200"))

    assert any(candidate["diameter"] == "DN200" for candidate in result["diameter_candidates"])
    assert result["diagnostic"]["has_label"] is True


def test_xdata_string_diameter_is_detected():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe())

    assert "TG_PIPE" in result["xdata"]["groups"]
    assert any(candidate["diameter"] == "DN150" for candidate in result["diameter_candidates"])


def test_extension_dictionary_failure_does_not_crash():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    class FailingDictionaryPipe(FakeTDbPipe):
        def GetExtensionDictionary(self):
            raise RuntimeError("dictionary unavailable")

    result = probe_tdbpipe(FailingDictionaryPipe())

    assert result["extension_dictionary"]["available"] is False
    assert result["diagnostic"]["warnings"]


def test_typeinfo_unavailable_does_not_crash():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe())

    assert result["typeinfo"]["available"] is False
    assert result["diagnostic"]["warnings"]


def test_typeinfo_available_is_recorded():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe(_oleobj_=FakeOleObj()))

    assert result["typeinfo"]["available"] is True
    assert "PipeDN" in result["typeinfo"]["names"]


def test_dir_probe_filters_suspicious_field_names():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeTDbPipe(PipeLabel="DN200", OtherValue="x"))

    assert "PipeLabel" in result["dir_probe"]["suspicious_names"]
    assert "OtherValue" not in result["dir_probe"]["suspicious_names"]


def test_non_tdbpipe_returns_clear_error():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    result = probe_tdbpipe(FakeEntity())

    assert result["success"] is False
    assert result["error_code"] == "NOT_TDBPIPE"
    assert result["object_name"] == "AcDbLine"


def test_probe_output_is_json_serializable_and_read_only():
    from tianzheng.tdbpipe_deep_probe import probe_tdbpipe

    pipe = FakeTDbPipe(PipeDN="DN200", StartPoint=(0.0, 0.0, 0.0), EndPoint=(10.0, 0.0, 0.0))

    result = probe_tdbpipe(pipe)

    assert result["known_properties"]["StartPoint"] == [0.0, 0.0, 0.0]
    json.dumps(result, ensure_ascii=False)
    assert pipe.deleted is False
    assert pipe.moved is False
