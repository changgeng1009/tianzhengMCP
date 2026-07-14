from __future__ import annotations

from typing import Any

from mcp.vision.fixtures import fixture_elements
from mcp.vision.models import VisionElement


def detect_building_contours(
    image: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> list[VisionElement]:
    elements = fixture_elements(
        image,
        {"building_candidate", "building_outline"},
        "contour_detector",
    )
    result: list[VisionElement] = []
    for element in elements:
        metadata = dict(element.metadata)
        metadata.setdefault("detector", "contour_detector")
        metadata.setdefault("candidate_only", True)
        result.append(
            VisionElement(
                element_id=element.element_id,
                element_type="building_candidate",
                bbox=list(element.bbox),
                points=[list(point) for point in element.points],
                text=element.text,
                confidence=element.confidence,
                source=dict(element.source),
                metadata=metadata,
            )
        )
    return result

