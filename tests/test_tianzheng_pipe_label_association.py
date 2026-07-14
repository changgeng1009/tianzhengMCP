from __future__ import annotations

import json


def pipe(handle: str, start: list[float], end: list[float], layer: str = "PIPE-消防") -> dict:
    return {
        "semantic_type": "pipe",
        "handle": handle,
        "layer": layer,
        "system_type": "消防" if "消防" in layer else "喷淋",
        "inferred_geometry": {
            "start_point": start,
            "end_point": end,
            "source": "bounding_box_inference",
        },
        "bounding_box": [
            min(start[0], end[0]),
            min(start[1], end[1]),
            0.0,
            max(start[0], end[0]),
            max(start[1], end[1]),
            0.0,
        ],
    }


def label(label_id: str, diameter: str, position: list[float]) -> dict:
    return {
        "label_id": label_id,
        "raw_text": diameter,
        "normalized_diameter": diameter,
        "source_object": {
            "handle": label_id,
            "object_name": "AcDbText",
            "layer": "TEXT",
        },
        "position": position,
        "bounding_box": [
            position[0] - 10.0,
            position[1] - 5.0,
            0.0,
            position[0] + 10.0,
            position[1] + 5.0,
            0.0,
        ],
        "confidence": 1.0,
    }


def test_label_center_to_horizontal_pipe_distance():
    from tianzheng.pipe_label_association import distance_label_to_pipe

    distance = distance_label_to_pipe(label("L1", "DN200", [500.0, 100.0, 0.0]), pipe("P1", [0.0, 0.0, 0.0], [1000.0, 0.0, 0.0]))

    assert distance == 100.0


def test_label_center_to_vertical_pipe_distance():
    from tianzheng.pipe_label_association import distance_label_to_pipe

    distance = distance_label_to_pipe(label("L1", "DN200", [100.0, 500.0, 0.0]), pipe("P1", [0.0, 0.0, 0.0], [0.0, 1000.0, 0.0]))

    assert distance == 100.0


def test_nearest_label_becomes_pipe_candidate():
    from tianzheng.pipe_label_association import associate_diameter_labels_to_pipes

    result = associate_diameter_labels_to_pipes(
        [pipe("P1", [0.0, 0.0, 0.0], [1000.0, 0.0, 0.0])],
        [
            label("L1", "DN100", [500.0, 50.0, 0.0]),
            label("L2", "DN200", [500.0, 500.0, 0.0]),
        ],
    )

    assert result[0]["diameter_candidates"][0]["diameter"] == "DN100"
    assert result[0]["selected_diameter"] is None
    assert result[0]["status"] == "need_user_confirmation"


def test_multiple_candidates_are_not_forced_to_unique_selection():
    from tianzheng.pipe_label_association import associate_diameter_labels_to_pipes

    result = associate_diameter_labels_to_pipes(
        [pipe("P1", [0.0, 0.0, 0.0], [1000.0, 0.0, 0.0])],
        [
            label("L1", "DN100", [400.0, 50.0, 0.0]),
            label("L2", "DN150", [600.0, 60.0, 0.0]),
        ],
    )

    assert len(result[0]["diameter_candidates"]) == 2
    assert result[0]["selected_diameter"] is None


def test_association_model_is_json_serializable():
    from tianzheng.pipe_label_association import build_pipe_diameter_association_model

    model = build_pipe_diameter_association_model(
        {
            "active_document": "pump-room.dwg",
            "selection_count": 2,
            "entities": [
                pipe("P1", [0.0, 0.0, 0.0], [1000.0, 0.0, 0.0]),
                {
                    "semantic_type": "text",
                    "object_name": "AcDbText",
                    "handle": "T1",
                    "layer": "TEXT",
                    "text": "DN 200",
                    "bounding_box": [400.0, 50.0, 0.0, 500.0, 70.0, 0.0],
                    "properties": {"TextString": "DN 200"},
                },
            ],
        }
    )

    assert model["summary"]["pipes"] == 1
    assert model["summary"]["diameter_labels"] == 1
    assert model["summary"]["associations"] == 1
    json.dumps(model, ensure_ascii=False)


def test_association_does_not_write_to_pipe_objects():
    from tianzheng.pipe_label_association import associate_diameter_labels_to_pipes

    pipe_entity = pipe("P1", [0.0, 0.0, 0.0], [1000.0, 0.0, 0.0])

    associate_diameter_labels_to_pipes([pipe_entity], [label("L1", "DN100", [500.0, 50.0, 0.0])])

    assert "selected_diameter" not in pipe_entity
