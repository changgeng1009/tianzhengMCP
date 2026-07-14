from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.vision.confidence import combine_confidences
from mcp.vision.contour_detector import detect_building_contours
from mcp.vision.coordinate_mapper import CoordinateMapper
from mcp.vision.image_preprocess import preprocess_image
from mcp.vision.models import SemanticGraph, VisionElement, VisionParseResult
from mcp.vision.ocr_provider import StubOCRProvider
from mcp.vision.pdf_renderer import render_pdf_to_images
from mcp.vision.pipe_detector_v1 import detect_pipes_v1
from mcp.vision.provider import BasicVisionProvider
from mcp.vision.semantic_builder import build_semantic_graph
from mcp.vision.sprinkler_detector_v1 import detect_sprinklers_v1
from mcp.vision.text_detector import detect_texts
from mcp.vision.valve_detector_v1 import detect_valves_v1
from mcp.vision_templates.symbol_classifier import classify_symbols_from_matches
from mcp.vision_templates.template_matcher import match_templates


class CVVisionProvider(BasicVisionProvider):
    def __init__(
        self,
        ocr_provider: Any | None = None,
        use_template_library: bool = True,
        template_store: Any | None = None,
        template_match_threshold: float = 0.85,
    ) -> None:
        super().__init__(ocr_provider=ocr_provider or StubOCRProvider())
        self.use_template_library = bool(use_template_library)
        self.template_store = template_store
        self.template_match_threshold = float(template_match_threshold)

    def parse_png(self, path: str, metadata: dict[str, Any] | None = None) -> VisionParseResult:
        metadata = {"source_type": "png", **dict(metadata or {})}
        if not Path(path).exists() and not metadata.get("allow_missing_fixture") and not metadata.get("fixture_elements"):
            warnings = [f"image file not found: {path}"]
            return _failed_result(path, "png", warnings)
        return self._parse_image_v1(path, "png", path, 0, metadata, [])

    def parse_pdf(self, path: str, metadata: dict[str, Any] | None = None) -> VisionParseResult:
        metadata = dict(metadata or {})
        rendered = render_pdf_to_images(path, output_dir=metadata.get("output_dir"))
        if rendered["status"] != "success" or not rendered["images"]:
            warnings = list(rendered.get("warnings", []))
            return _failed_result(path, "pdf", warnings)
        first = rendered["images"][0]
        image_metadata = {"source_type": "pdf", **metadata}
        return self._parse_image_v1(
            str(first["path"]),
            "pdf",
            path,
            int(first["page_index"]),
            image_metadata,
            list(rendered.get("warnings", [])),
        )

    def _parse_image_v1(
        self,
        image_path: str,
        source_type: str,
        source_path: str,
        page_index: int,
        metadata: dict[str, Any],
        initial_warnings: list[str],
    ) -> VisionParseResult:
        warnings = list(initial_warnings)
        if not is_opencv_available():
            warnings.append("OpenCV not available; CVVisionProvider used fixture/stub detectors only")

        preprocessed = preprocess_image(image_path, metadata)
        warnings.extend(preprocessed.get("warnings", []))

        elements: list[VisionElement] = []
        elements.extend(detect_building_contours(preprocessed))
        elements.extend(detect_pipes_v1(preprocessed))
        elements.extend(detect_sprinklers_v1(preprocessed))
        elements.extend(detect_valves_v1(preprocessed))
        text_result = detect_texts(preprocessed, self.ocr_provider)
        elements.extend(text_result.get("elements", []))
        warnings.extend(text_result.get("warnings", []))
        if self.use_template_library and self.template_store is not None:
            template_warnings: list[str] = []
            matches = match_templates(
                preprocessed,
                self.template_store,
                options={
                    "threshold": self.template_match_threshold,
                    "warnings": template_warnings,
                },
            )
            classified = classify_symbols_from_matches(matches)
            elements.extend(_template_symbols_to_elements(classified, source_path, page_index))
            warnings.extend(template_warnings)
        elif self.use_template_library and self.template_store is None and metadata.get("template_fixture_matches"):
            warnings.append("template fixture matches ignored because no template_store was provided")

        if not elements:
            warnings.append("CVVisionProvider detected no visual elements")

        width = int(metadata.get("image_width") or preprocessed.get("image_width") or 1)
        height = int(metadata.get("image_height") or preprocessed.get("image_height") or 1)
        coordinate_metadata = CoordinateMapper(width, height).metadata()
        graph_dict = build_semantic_graph(
            elements,
            provider="CVVisionProvider",
            coordinate_metadata=coordinate_metadata,
        )
        graph_warnings = graph_dict.get("metadata", {}).get("warnings", [])
        warnings.extend(warning for warning in graph_warnings if warning not in warnings)
        confidence = combine_confidences([element.confidence for element in elements])
        if not elements:
            confidence = 0.0
        graph_dict["metadata"]["confidence"] = confidence
        graph_dict["metadata"]["warnings"] = list(dict.fromkeys(warnings + graph_warnings))

        return VisionParseResult(
            source_path=source_path,
            source_type=source_type,
            page_index=page_index,
            elements=elements,
            warnings=graph_dict["metadata"]["warnings"],
            confidence=confidence,
            semantic_graph=SemanticGraph(**graph_dict),
        )


def is_opencv_available() -> bool:
    try:
        __import__("cv2")
        return True
    except ImportError:
        return False


def _failed_result(path: str, source_type: str, warnings: list[str]) -> VisionParseResult:
    graph = {
        "buildings": [],
        "pipes": [],
        "valves": [],
        "sprinklers": [],
        "texts": [],
        "symbols": [],
        "metadata": {
            "source": "vision",
            "provider": "CVVisionProvider",
            "status": "failed",
            "confidence": 0.0,
            "warnings": warnings,
            "coordinate_space": "normalized_image",
        },
    }
    return VisionParseResult(
        source_path=path,
        source_type=source_type,
        page_index=0,
        elements=[],
        warnings=warnings,
        confidence=0.0,
        semantic_graph=SemanticGraph(**graph),
    )


def _template_symbols_to_elements(symbols, source_path: str, page_index: int) -> list[VisionElement]:
    elements: list[VisionElement] = []
    for symbol in symbols:
        metadata = dict(symbol.metadata)
        metadata["matched_template_id"] = symbol.matched_template_id
        metadata["method"] = symbol.method
        metadata["template_warnings"] = list(symbol.warnings)
        elements.append(
            VisionElement(
                element_id=symbol.symbol_id,
                element_type=symbol.symbol_type,
                bbox=list(symbol.bbox),
                points=[list(symbol.center)],
                text=None,
                confidence=float(symbol.confidence),
                source={"provider": "template_library", "source_path": source_path, "page_index": page_index},
                metadata=metadata,
            )
        )
    return elements
