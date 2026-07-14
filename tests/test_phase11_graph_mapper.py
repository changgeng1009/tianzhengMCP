from __future__ import annotations


def test_graph_mapper_preserves_original_and_mapped_geometry() -> None:
    from mcp.spatial.graph_mapper import map_reference_graph_to_target_space
    from mcp.spatial.models import Transform2D

    graph = {
        "metadata": {"coordinate_space": "normalized_image"},
        "pipes": [
            {
                "id": "p1",
                "source_element_id": "p1",
                "start": [0.0, 0.0, 0.0],
                "end": [1.0, 0.0, 0.0],
                "confidence": 0.8,
            }
        ],
        "buildings": [],
        "valves": [],
        "sprinklers": [],
        "texts": [],
        "symbols": [],
    }
    transform = Transform2D("translation", [[1, 0, 100], [0, 1, 200], [0, 0, 1]], 0.8, 0.0, {})

    mapped = map_reference_graph_to_target_space(graph, transform)

    pipe = mapped["pipes"][0]
    assert mapped["metadata"]["coordinate_space"] == "cad_modelspace"
    assert pipe["original_geometry"]["start"] == [0.0, 0.0, 0.0]
    assert pipe["mapped_geometry"]["start"] == [100.0, 200.0, 0.0]
    assert pipe["mapped_confidence"] == 0.64


def test_graph_mapper_unknown_transform_does_not_force_mapping() -> None:
    from mcp.spatial.graph_mapper import map_reference_graph_to_target_space
    from mcp.spatial.models import Transform2D

    mapped = map_reference_graph_to_target_space(
        {"metadata": {"coordinate_space": "normalized_image"}, "pipes": []},
        Transform2D("unknown", [], 0.0, None, {}),
    )

    assert mapped["metadata"]["coordinate_space"] == "normalized_image"
    assert mapped["metadata"]["warnings"][0] == "transform unavailable; graph not mapped"

