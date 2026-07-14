from __future__ import annotations

from copy import deepcopy


def _roi():
    from roi.models import ROIRegion

    return ROIRegion(
        id="pump_room_roi",
        name="水泵房大样图区域",
        coordinate_system="cad_world",
        min_x=0,
        min_y=0,
        max_x=100,
        max_y=100,
    )


def test_point_inside_roi_is_kept():
    from roi.filter import filter_entities_by_roi

    entity = {
        "id": "line_1",
        "type": "line",
        "geometry": {
            "coordinate_system": "cad_world",
            "points": [{"x": 50, "y": 50, "coordinate_system": "cad_world"}],
        },
    }

    result = filter_entities_by_roi([entity], _roi())

    assert result["kept_entities"] == [entity]
    assert result["excluded_entities_count"] == 0


def test_bounding_box_intersection_keeps_entity():
    from roi.filter import filter_entities_by_roi

    entity = {
        "id": "polyline_1",
        "type": "polyline",
        "bounding_box": {
            "x_min": 90,
            "y_min": 90,
            "x_max": 120,
            "y_max": 120,
            "coordinate_system": "cad_world",
        },
        "geometry": {"coordinate_system": "cad_world", "points": []},
    }

    result = filter_entities_by_roi([entity], _roi())

    assert len(result["kept_entities"]) == 1


def test_entity_completely_outside_roi_is_excluded():
    from roi.filter import filter_entities_by_roi

    entity = {
        "id": "outside",
        "type": "line",
        "bounding_box": {
            "x_min": 200,
            "y_min": 200,
            "x_max": 300,
            "y_max": 300,
            "coordinate_system": "cad_world",
        },
        "geometry": {
            "coordinate_system": "cad_world",
            "points": [{"x": 250, "y": 250, "coordinate_system": "cad_world"}],
        },
    }

    result = filter_entities_by_roi([entity], _roi())

    assert result["kept_entities"] == []
    assert result["excluded_entities_count"] == 1


def test_text_insertion_point_inside_roi_is_kept():
    from roi.filter import filter_entities_by_roi

    entity = {
        "id": "text_1",
        "type": "text",
        "geometry": {
            "coordinate_system": "cad_world",
            "position": [20, 30, 0],
            "points": [],
        },
        "properties": {"text": "水泵房大样图"},
    }

    result = filter_entities_by_roi([entity], _roi())

    assert result["kept_entities"][0]["id"] == "text_1"


def test_roi_summary_counts_kept_types_and_excluded_count():
    from roi.filter import filter_entities_by_roi

    entities = [
        {
            "id": "line_1",
            "type": "line",
            "geometry": {
                "coordinate_system": "cad_world",
                "points": [{"x": 10, "y": 10, "coordinate_system": "cad_world"}],
            },
        },
        {
            "id": "text_1",
            "type": "text",
            "geometry": {
                "coordinate_system": "cad_world",
                "points": [{"x": 300, "y": 300, "coordinate_system": "cad_world"}],
            },
        },
    ]

    result = filter_entities_by_roi(entities, _roi())

    assert result["roi_summary"]["total_before_roi"] == 2
    assert result["roi_summary"]["total_after_roi"] == 1
    assert result["roi_summary"]["entity_type_summary"] == {"line": 1}
    assert result["excluded_entities_count"] == 1


def test_roi_filter_does_not_modify_original_entities():
    from roi.filter import filter_entities_by_roi

    entities = [
        {
            "id": "line_1",
            "type": "line",
            "geometry": {
                "coordinate_system": "cad_world",
                "points": [{"x": 10, "y": 10, "coordinate_system": "cad_world"}],
            },
        }
    ]
    original = deepcopy(entities)

    filter_entities_by_roi(entities, _roi())

    assert entities == original


def test_find_text_entities_by_keyword_returns_positions_and_handles():
    from roi.selector import find_text_entities_by_keyword

    model = {
        "entities": [
            {
                "id": "text_1",
                "handle": "T1",
                "type": "text",
                "geometry": {
                    "coordinate_system": "cad_world",
                    "points": [{"x": 10, "y": 20, "coordinate_system": "cad_world"}],
                },
                "properties": {"text": "水泵房大样图"},
            }
        ]
    }

    result = find_text_entities_by_keyword(model, "水泵房")

    assert result == [
        {
            "id": "text_1",
            "handle": "T1",
            "text": "水泵房大样图",
            "position": {"x": 10.0, "y": 20.0, "coordinate_system": "cad_world"},
        }
    ]
