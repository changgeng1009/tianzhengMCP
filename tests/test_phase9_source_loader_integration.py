from __future__ import annotations


class FakeVisionProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def parse_png(self, path: str):
        self.calls.append(("png", path))
        from mcp.vision.models import SemanticGraph, VisionElement, VisionParseResult

        element = VisionElement(
            element_id="p_fixture",
            element_type="pipe_candidate",
            bbox=[0, 0, 100, 10],
            points=[[0, 5], [100, 5]],
            text=None,
            confidence=0.63,
            source={"type": "png", "path": path},
            metadata={"dn": 50, "system_type": "给水"},
        )
        graph = SemanticGraph(
            buildings=[],
            pipes=[
                {
                    "id": "p_fixture",
                    "start": [0, 5, 0.0],
                    "end": [100, 5, 0.0],
                    "dn": 50,
                    "system_type": "给水",
                    "confidence": 0.63,
                }
            ],
            valves=[],
            sprinklers=[],
            texts=[],
            symbols=[],
            metadata={"source": "vision", "confidence": 0.63, "warnings": ["low confidence visual parse"]},
        )
        return VisionParseResult(
            source_path=path,
            source_type="png",
            page_index=0,
            elements=[element],
            warnings=["low confidence visual parse"],
            confidence=0.63,
            semantic_graph=graph,
        )

    def parse_pdf(self, path: str):
        self.calls.append(("pdf", path))
        raise RuntimeError("pdf parse failed")

    def to_semantic_graph(self, result):
        return result.semantic_graph.to_dict()


def test_source_loader_calls_vision_provider_for_png_without_semantic_graph() -> None:
    from mcp.source_loader import MultiSourceSemanticLoader

    provider = FakeVisionProvider()
    loader = MultiSourceSemanticLoader(vision_provider=provider)

    result = loader.load_sources([{"type": "png", "path": "fixture.png", "role": "reference"}])

    assert provider.calls == [("png", "fixture.png")]
    assert result["semantic_graph"]["pipes"][0]["id"] == "p_fixture"
    assert result["confidence"] == 0.63
    assert "low confidence visual parse" in result["warnings"]


def test_source_loader_safely_downgrades_when_vision_provider_fails() -> None:
    from mcp.source_loader import MultiSourceSemanticLoader

    provider = FakeVisionProvider()
    loader = MultiSourceSemanticLoader(vision_provider=provider)

    result = loader.load_sources([{"type": "pdf", "path": "bad.pdf"}])

    assert provider.calls == [("pdf", "bad.pdf")]
    assert result["semantic_graph"]["pipes"] == []
    assert result["confidence"] < 0.8
    assert any("vision parse failed" in warning for warning in result["warnings"])


def test_basic_vision_provider_parse_png_uses_fixture_elements_and_warns_low_confidence() -> None:
    from mcp.vision.provider import BasicVisionProvider

    provider = BasicVisionProvider()
    result = provider.parse_png(
        "fixture.png",
        metadata={
            "fixture_elements": [
                {
                    "element_id": "p1",
                    "element_type": "pipe_candidate",
                    "bbox": [0, 0, 100, 10],
                    "points": [[0, 5], [100, 5]],
                    "confidence": 0.64,
                    "metadata": {"dn": 50, "system_type": "给水"},
                }
            ]
        },
    )

    data = result.to_dict()

    assert data["source_type"] == "png"
    assert data["semantic_graph"]["pipes"][0]["id"] == "p1"
    assert data["confidence"] == 0.64
    assert "low confidence visual parse" in data["warnings"]
