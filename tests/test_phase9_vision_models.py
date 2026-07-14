from __future__ import annotations

import pytest


def test_vision_element_and_parse_result_serialize_to_json_dict() -> None:
    from mcp.vision.models import SemanticGraph, VisionElement, VisionParseResult

    element = VisionElement(
        element_id="pipe_1",
        element_type="pipe_candidate",
        bbox=[0.0, 0.0, 100.0, 10.0],
        points=[[0.0, 5.0], [100.0, 5.0]],
        text=None,
        confidence=0.62,
        source={"type": "png", "path": "fixture.png"},
        metadata={"detector": "fixture"},
    )
    graph = SemanticGraph(
        buildings=[],
        pipes=[{"id": "pipe_1", "confidence": 0.62}],
        valves=[],
        sprinklers=[],
        texts=[],
        symbols=[],
        metadata={"source": "vision", "confidence": 0.62, "warnings": []},
    )
    result = VisionParseResult(
        source_path="fixture.png",
        source_type="png",
        page_index=0,
        elements=[element],
        warnings=["low confidence visual parse"],
        confidence=0.62,
        semantic_graph=graph,
    )

    data = result.to_dict()

    assert data["source_path"] == "fixture.png"
    assert data["elements"][0]["element_type"] == "pipe_candidate"
    assert data["semantic_graph"]["pipes"][0]["id"] == "pipe_1"
    assert data["confidence"] == 0.62


def test_vision_element_rejects_invalid_confidence() -> None:
    from mcp.vision.models import VisionElement

    with pytest.raises(ValueError, match="confidence"):
        VisionElement(
            element_id="bad",
            element_type="pipe_candidate",
            bbox=[],
            points=[],
            text=None,
            confidence=1.2,
            source={},
            metadata={},
        )

