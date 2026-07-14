from __future__ import annotations

import json


class FakeTextEntity:
    def __init__(self, object_name: str = "AcDbText", handle: str = "T1", layer: str = "TEXT", **attrs):
        self.ObjectName = object_name
        self.EntityName = object_name
        self.Handle = handle
        self.Layer = layer
        self.deleted = False
        for key, value in attrs.items():
            setattr(self, key, value)

    def Delete(self):  # pragma: no cover
        self.deleted = True
        raise AssertionError("diameter label reader must be read-only")


def text_entity(text: str, handle: str = "T1") -> dict:
    return {
        "semantic_type": "text",
        "object_name": "AcDbText",
        "handle": handle,
        "layer": "TEXT",
        "text": text,
        "bounding_box": [0.0, 0.0, 0.0, 100.0, 20.0, 0.0],
        "properties": {"TextString": text},
    }


def test_dn200_is_recognized_as_dn200():
    from tianzheng.diameter_label_reader import normalize_pipe_diameter

    assert normalize_pipe_diameter("DN200") == "DN200"


def test_dn_with_space_is_normalized():
    from tianzheng.diameter_label_reader import normalize_pipe_diameter

    assert normalize_pipe_diameter("DN 200") == "DN200"


def test_lowercase_dn_is_normalized():
    from tianzheng.diameter_label_reader import normalize_pipe_diameter

    assert normalize_pipe_diameter("dn200") == "DN200"


def test_de_with_space_is_normalized():
    from tianzheng.diameter_label_reader import normalize_pipe_diameter

    assert normalize_pipe_diameter("De 110") == "De110"


def test_phi_with_space_is_normalized():
    from tianzheng.diameter_label_reader import normalize_pipe_diameter

    assert normalize_pipe_diameter("Φ 100") == "Φ100"


def test_textstring_dn_is_extracted():
    from tianzheng.diameter_label_reader import extract_pipe_diameter_labels

    labels = extract_pipe_diameter_labels([text_entity("DN 200")])

    assert labels[0]["normalized_diameter"] == "DN200"
    assert labels[0]["raw_text"] == "DN 200"
    assert labels[0]["confidence"] == 1.0


def test_mtext_contents_dn_is_extracted():
    from tianzheng.diameter_label_reader import extract_pipe_diameter_labels

    labels = extract_pipe_diameter_labels(
        [
            {
                "semantic_type": "mtext",
                "object_name": "AcDbMText",
                "handle": "MT1",
                "layer": "TEXT",
                "bounding_box": [0.0, 0.0, 0.0, 100.0, 20.0, 0.0],
                "properties": {"Contents": "De 160"},
            }
        ]
    )

    assert labels[0]["normalized_diameter"] == "De160"


def test_tdb_dimension_without_text_does_not_crash():
    from tianzheng.diameter_label_reader import extract_pipe_diameter_labels

    labels = extract_pipe_diameter_labels(
        [
            {
                "semantic_type": "dimension",
                "object_name": "TDbDimension2",
                "handle": "D1",
                "layer": "TWT_DIM",
                "bounding_box": [0.0, 0.0, 0.0, 100.0, 20.0, 0.0],
                "properties": {},
            }
        ]
    )

    assert labels[0]["status"] == "need_user_confirmation"
    assert labels[0]["reason"] == "No readable text property found"


def test_text_property_probe_converts_tuple_to_json_list():
    from tianzheng.diameter_label_reader import probe_text_properties

    result = probe_text_properties(FakeTextEntity(TextString="DN100", Position=(1.0, 2.0, 0.0)))

    assert result["readable_text_properties"]["TextString"] == "DN100"
    assert result["readable_text_properties"]["Position"] == [1.0, 2.0, 0.0]
    json.dumps(result, ensure_ascii=False)


def test_diameter_label_reader_does_not_write_to_cad():
    from tianzheng.diameter_label_reader import extract_pipe_diameter_labels

    entity = FakeTextEntity(TextString="DN100")

    labels = extract_pipe_diameter_labels([entity])

    assert labels[0]["normalized_diameter"] == "DN100"
    assert entity.deleted is False
