from __future__ import annotations


class FakeCVProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def parse_png(self, path: str):
        self.calls.append(("png", path))
        from mcp.vision.models import SemanticGraph, VisionParseResult

        graph = SemanticGraph(
            buildings=[],
            pipes=[
                {
                    "id": "pipe_from_cv",
                    "source_element_id": "pipe_from_cv",
                    "start": [0, 0, 0.0],
                    "end": [100, 0, 0.0],
                    "dn": 50,
                    "system_type": "给水",
                    "confidence": 0.7,
                    "metadata": {"detector": "pipe_detector_v1"},
                }
            ],
            valves=[],
            sprinklers=[],
            texts=[],
            symbols=[],
            metadata={
                "source": "vision",
                "provider": "CVVisionProvider",
                "confidence": 0.7,
                "warnings": ["medium confidence visual parse"],
                "coordinate_space": "normalized_image",
            },
        )
        return VisionParseResult(
            source_path=path,
            source_type="png",
            page_index=0,
            elements=[],
            warnings=["medium confidence visual parse"],
            confidence=0.7,
            semantic_graph=graph,
        )

    def parse_pdf(self, path: str):
        self.calls.append(("pdf", path))
        raise RuntimeError("cv failed")

    def to_semantic_graph(self, result):
        return result.semantic_graph.to_dict()


def test_source_loader_prefers_cv_provider_for_png_without_semantic_graph() -> None:
    from mcp.source_loader import MultiSourceSemanticLoader

    provider = FakeCVProvider()
    loader = MultiSourceSemanticLoader(vision_provider=provider)

    result = loader.load_sources([{"type": "png", "path": "fixture.png"}])

    assert provider.calls == [("png", "fixture.png")]
    assert result["semantic_graph"]["pipes"][0]["id"] == "pipe_from_cv"
    assert result["confidence"] == 0.7
    assert "medium confidence visual parse" in result["warnings"]


def test_source_loader_keeps_direct_semantic_graph_path_without_cv_call() -> None:
    from mcp.source_loader import MultiSourceSemanticLoader

    provider = FakeCVProvider()
    loader = MultiSourceSemanticLoader(vision_provider=provider)

    result = loader.load_sources(
        [
            {
                "type": "png",
                "path": "already.json",
                "semantic_graph": {
                    "buildings": [],
                    "pipes": [{"id": "direct"}],
                    "valves": [],
                    "sprinklers": [],
                },
            }
        ]
    )

    assert provider.calls == []
    assert result["semantic_graph"]["pipes"][0]["id"] == "direct"
