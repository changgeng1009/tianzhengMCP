from __future__ import annotations


def test_semantic_builder_maps_vision_elements_to_phase8_graph() -> None:
    from mcp.vision.models import VisionElement
    from mcp.vision.semantic_builder import build_semantic_graph

    elements = [
        VisionElement(
            element_id="b1",
            element_type="building_outline",
            bbox=[0, 0, 200, 200],
            points=[],
            text=None,
            confidence=0.7,
            source={"type": "png"},
            metadata={"label": "A栋"},
        ),
        VisionElement(
            element_id="p1",
            element_type="pipe_candidate",
            bbox=[0, 0, 100, 10],
            points=[[0, 5], [100, 5]],
            text=None,
            confidence=0.66,
            source={"type": "png"},
            metadata={"building_id": "b1", "dn": 50, "system_type": "给水"},
        ),
        VisionElement(
            element_id="v1",
            element_type="valve_candidate",
            bbox=[40, 0, 60, 20],
            points=[],
            text=None,
            confidence=0.61,
            source={"type": "png"},
            metadata={"building_id": "b1"},
        ),
        VisionElement(
            element_id="s1",
            element_type="sprinkler_candidate",
            bbox=[80, 80, 90, 90],
            points=[],
            text=None,
            confidence=0.58,
            source={"type": "png"},
            metadata={"building_id": "b1"},
        ),
        VisionElement(
            element_id="t1",
            element_type="text_candidate",
            bbox=[0, 220, 60, 240],
            points=[],
            text="DN50",
            confidence=0.4,
            source={"type": "png"},
            metadata={},
        ),
    ]

    graph = build_semantic_graph(elements)

    assert graph["buildings"][0]["id"] == "b1"
    assert graph["pipes"][0]["id"] == "p1"
    assert graph["pipes"][0]["dn"] == 50
    assert graph["valves"][0]["id"] == "v1"
    assert graph["sprinklers"][0]["id"] == "s1"
    assert graph["texts"][0]["text"] == "DN50"
    assert graph["metadata"]["source"] == "vision"
    assert graph["metadata"]["confidence"] < 0.7
    assert graph["metadata"]["warnings"]

