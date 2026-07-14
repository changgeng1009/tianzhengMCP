from __future__ import annotations

from typing import Any, Protocol

from mcp.vision.image_preprocess import preprocess_image
from mcp.vision.line_detector import detect_pipe_lines
from mcp.vision.models import SemanticGraph, VisionElement, VisionParseResult
from mcp.vision.pdf_renderer import render_pdf_to_images
from mcp.vision.semantic_builder import build_semantic_graph
from mcp.vision.symbol_detector import detect_symbols
from mcp.vision.text_detector import detect_texts


class VisionProvider(Protocol):
    def parse_pdf(self, path: str) -> VisionParseResult:
        ...

    def parse_png(self, path: str) -> VisionParseResult:
        ...

    def to_semantic_graph(self, result: VisionParseResult) -> dict[str, Any]:
        ...


class BasicVisionProvider:
    def __init__(self, ocr_provider: Any | None = None) -> None:
        self.ocr_provider = ocr_provider

    def parse_pdf(self, path: str, metadata: dict[str, Any] | None = None) -> VisionParseResult:
        metadata = dict(metadata or {})
        rendered = render_pdf_to_images(path, output_dir=metadata.get("output_dir"))
        if rendered["status"] != "success" or not rendered["images"]:
            warnings = list(rendered.get("warnings", []))
            graph = _empty_semantic_graph(0.0, warnings)
            return VisionParseResult(
                source_path=path,
                source_type="pdf",
                page_index=0,
                elements=[],
                warnings=warnings,
                confidence=0.0,
                semantic_graph=SemanticGraph(**graph),
            )

        first_image = rendered["images"][0]
        image_metadata = {**metadata, "source_type": "pdf"}
        return self._parse_image(
            image_path=first_image["path"],
            source_type="pdf",
            source_path=path,
            page_index=int(first_image["page_index"]),
            metadata=image_metadata,
            initial_warnings=list(rendered.get("warnings", [])),
        )

    def parse_png(self, path: str, metadata: dict[str, Any] | None = None) -> VisionParseResult:
        metadata = {"source_type": "png", "allow_missing_fixture": True, **dict(metadata or {})}
        return self._parse_image(
            image_path=path,
            source_type="png",
            source_path=path,
            page_index=0,
            metadata=metadata,
            initial_warnings=[],
        )

    def to_semantic_graph(self, result: VisionParseResult) -> dict[str, Any]:
        return result.semantic_graph.to_dict()

    def _parse_image(
        self,
        image_path: str,
        source_type: str,
        source_path: str,
        page_index: int,
        metadata: dict[str, Any],
        initial_warnings: list[str],
    ) -> VisionParseResult:
        preprocessed = preprocess_image(image_path, metadata)
        detector_results = [
            detect_pipe_lines(preprocessed),
            detect_symbols(preprocessed),
            detect_texts(preprocessed, self.ocr_provider),
        ]
        elements: list[VisionElement] = []
        warnings = list(initial_warnings) + list(preprocessed.get("warnings", []))
        for detector_result in detector_results:
            elements.extend(detector_result.get("elements", []))
            warnings.extend(detector_result.get("warnings", []))

        graph_dict = build_semantic_graph(elements)
        graph_warnings = list(graph_dict.get("metadata", {}).get("warnings", []))
        warnings.extend(warning for warning in graph_warnings if warning not in warnings)
        confidence = float(graph_dict.get("metadata", {}).get("confidence", 0.0))

        return VisionParseResult(
            source_path=source_path,
            source_type=source_type,
            page_index=page_index,
            elements=elements,
            warnings=warnings,
            confidence=confidence,
            semantic_graph=SemanticGraph(**graph_dict),
        )


def _empty_semantic_graph(confidence: float, warnings: list[str]) -> dict[str, Any]:
    return {
        "buildings": [],
        "pipes": [],
        "valves": [],
        "sprinklers": [],
        "texts": [],
        "symbols": [],
        "metadata": {
            "source": "vision",
            "confidence": confidence,
            "warnings": warnings,
        },
    }
