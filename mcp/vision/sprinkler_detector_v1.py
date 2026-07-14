from __future__ import annotations

from typing import Any

from mcp.vision.fixtures import fixture_elements
from mcp.vision.models import VisionElement


def detect_sprinklers_v1(
    image: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> list[VisionElement]:
    return _with_symbol_metadata(
        fixture_elements(image, {"sprinkler_candidate"}, "sprinkler_detector_v1"),
        "sprinkler_detector_v1",
    )


def _with_symbol_metadata(elements: list[VisionElement], detector: str) -> list[VisionElement]:
    output: list[VisionElement] = []
    for element in elements:
        metadata = dict(element.metadata)
        metadata["detector"] = detector
        metadata.setdefault("method", "fixture")
        output.append(
            VisionElement(
                element_id=element.element_id,
                element_type=element.element_type,
                bbox=list(element.bbox),
                points=[list(point) for point in element.points],
                text=element.text,
                confidence=element.confidence,
                source=dict(element.source),
                metadata=metadata,
            )
        )
    return output

