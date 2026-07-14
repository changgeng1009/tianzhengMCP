from __future__ import annotations

import math
from typing import Any

from mcp.vision.confidence import clamp_confidence
from mcp.vision.fixtures import fixture_elements
from mcp.vision.models import VisionElement


def detect_pipes_v1(image: dict[str, Any], options: dict[str, Any] | None = None) -> list[VisionElement]:
    elements = fixture_elements(image, {"pipe_candidate"}, "pipe_detector_v1")
    if elements:
        return [_with_pipe_metrics(element) for element in elements]
    return []


def _with_pipe_metrics(element: VisionElement) -> VisionElement:
    metadata = dict(element.metadata)
    if len(element.points) >= 2:
        start = element.points[0]
        end = element.points[-1]
        dx = float(end[0]) - float(start[0])
        dy = float(end[1]) - float(start[1])
        length = math.hypot(dx, dy)
        angle = round(math.degrees(math.atan2(dy, dx)), 4)
    else:
        length = 0.0
        angle = 0.0
    metadata["length"] = round(length, 4)
    metadata["angle"] = angle
    metadata["detector"] = "pipe_detector_v1"
    confidence = clamp_confidence(element.confidence)
    return VisionElement(
        element_id=element.element_id,
        element_type=element.element_type,
        bbox=list(element.bbox),
        points=[list(point) for point in element.points],
        text=element.text,
        confidence=confidence,
        source=dict(element.source),
        metadata=metadata,
    )

