from __future__ import annotations


def _model(entities: list[dict]):
    return {
        "source": "tianzheng_semantic_reader",
        "active_document": "pump-room.dwg",
        "selection_count": len(entities),
        "entities": entities,
    }


def _pipe(
    handle: str,
    start: tuple[float, float],
    end: tuple[float, float],
    diameter: str = "DN100",
    system_type: str = "消防",
    layer: str = "PIPE-消防",
):
    return {
        "handle": handle,
        "object_name": "TDbPipe",
        "semantic_type": "pipe",
        "system_type": system_type,
        "layer": layer,
        "diameter": {
            "raw": diameter,
            "normalized": diameter,
            "source": "TDbPipe.DNDiameter",
            "confidence": 0.95,
            "requires_confirmation": False,
        },
        "inferred_geometry": {
            "orientation": "horizontal" if start[1] == end[1] else "vertical",
            "start_point": [start[0], start[1], 0.0],
            "end_point": [end[0], end[1], 0.0],
            "length": abs(end[0] - start[0]) + abs(end[1] - start[1]),
            "source": "bounding_box_inference",
        },
        "bounding_box": [start[0], start[1], 0.0, end[0], end[1], 0.0],
    }


def _valve(handle: str, center: tuple[float, float], system_type: str = "消防"):
    return {
        "handle": handle,
        "object_name": "TDbPipeValve",
        "semantic_type": "valve",
        "system_type": system_type,
        "layer": f"VALVE_{system_type}",
        "inferred_geometry": {
            "center": [center[0], center[1], 0.0],
            "width": 20.0,
            "height": 20.0,
            "source": "bounding_box_inference",
        },
    }


def _fitting(handle: str, center: tuple[float, float], system_type: str = "消防"):
    return {
        "handle": handle,
        "object_name": "TDbPipeFitting",
        "semantic_type": "fitting",
        "system_type": system_type,
        "layer": f"PIPE-{system_type}",
        "fitting_type_guess": "三通",
        "inferred_geometry": {
            "center": [center[0], center[1], 0.0],
            "width": 0.0,
            "height": 0.0,
            "source": "bounding_box_inference",
        },
    }


def test_builds_pipe_edges_and_merges_shared_endpoint_nodes():
    from pipe_network.graph_builder import PipeNetworkGraphBuilder

    graph = PipeNetworkGraphBuilder(node_tolerance=5.0).build(
        _model(
            [
                _pipe("P1", (0.0, 0.0), (100.0, 0.0)),
                _pipe("P2", (100.0, 0.0), (200.0, 0.0)),
            ]
        )
    )

    assert len(graph["edges"]) == 2
    assert len(graph["nodes"]) == 3
    shared_nodes = [
        node for node in graph["nodes"] if set(node["source_handles"]) == {"P1", "P2"}
    ]
    assert len(shared_nodes) == 1


def test_pipe_edge_keeps_dndiameter_system_and_source_handle():
    from pipe_network.graph_builder import PipeNetworkGraphBuilder

    graph = PipeNetworkGraphBuilder().build(_model([_pipe("P1", (0.0, 0.0), (100.0, 0.0))]))

    edge = graph["edges"][0]
    assert edge["source_handle"] == "P1"
    assert edge["semantic_type"] == "pipe"
    assert edge["diameter"] == "DN100"
    assert edge["diameter_source"] == "TDbPipe.DNDiameter"
    assert edge["system_type"] == "消防"


def test_valve_and_fitting_attach_to_nearby_network_nodes():
    from pipe_network.graph_builder import PipeNetworkGraphBuilder

    graph = PipeNetworkGraphBuilder(node_tolerance=10.0).build(
        _model(
            [
                _pipe("P1", (0.0, 0.0), (100.0, 0.0)),
                _valve("V1", (100.0, 0.0)),
                _fitting("F1", (0.0, 0.0)),
            ]
        )
    )

    valve_nodes = [node for node in graph["nodes"] if "V1" in node["source_handles"]]
    fitting_nodes = [node for node in graph["nodes"] if "F1" in node["source_handles"]]
    assert valve_nodes[0]["node_type"] == "valve"
    assert fitting_nodes[0]["node_type"] == "fitting"


def test_systems_summarize_edges_nodes_and_diameters():
    from pipe_network.graph_builder import PipeNetworkGraphBuilder

    graph = PipeNetworkGraphBuilder().build(
        _model(
            [
                _pipe("P1", (0.0, 0.0), (100.0, 0.0), diameter="DN100", system_type="消防"),
                _pipe("P2", (0.0, 100.0), (100.0, 100.0), diameter="DN25", system_type="给水", layer="PIPE-给水"),
            ]
        )
    )

    systems = {system["system_type"]: system for system in graph["systems"]}
    assert systems["消防"]["edge_count"] == 1
    assert systems["消防"]["diameters"] == ["DN100"]
    assert systems["给水"]["edge_count"] == 1
    assert systems["给水"]["diameters"] == ["DN25"]


def test_subgraphs_are_connected_components_by_system():
    from pipe_network.graph_builder import PipeNetworkGraphBuilder

    graph = PipeNetworkGraphBuilder(node_tolerance=5.0).build(
        _model(
            [
                _pipe("P1", (0.0, 0.0), (100.0, 0.0)),
                _pipe("P2", (100.0, 0.0), (200.0, 0.0)),
                _pipe("P3", (1000.0, 0.0), (1100.0, 0.0)),
            ]
        )
    )

    subgraphs = sorted(graph["subgraphs"], key=lambda item: item["edge_count"])
    assert [item["edge_count"] for item in subgraphs] == [1, 2]
    assert all(item["system_type"] == "消防" for item in subgraphs)


def test_invalid_pipe_geometry_is_recorded_as_uncertain_not_crash():
    from pipe_network.graph_builder import PipeNetworkGraphBuilder

    graph = PipeNetworkGraphBuilder().build(
        _model(
            [
                {
                    "handle": "BAD",
                    "semantic_type": "pipe",
                    "object_name": "TDbPipe",
                    "system_type": "消防",
                    "diameter": {"normalized": "DN100"},
                }
            ]
        )
    )

    assert graph["edges"] == []
    assert graph["diagnostics"]["skipped_entities"][0]["handle"] == "BAD"
    assert graph["diagnostics"]["skipped_entities"][0]["reason"] == "missing_pipe_endpoints"
