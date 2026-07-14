from __future__ import annotations

from typing import Any

from mcp.vision.models import VisionElement


def detect_pipe_lines(image: dict[str, Any]) -> dict[str, Any]:
    elements = _fixture_elements(image, {"pipe_candidate", "building_outline"})
    warnings: list[str] = []
    if not elements:
        warnings.append("pipe line detector found no candidates")
    return {
        "elements": elements,
        "warnings": warnings,
    }


def _fixture_elements(image: dict[str, Any], allowed_types: set[str]) -> list[VisionElement]:
    metadata = image.get("metadata", {})
    source = {"type": metadata.get("source_type", "image"), "path": image.get("image_path")}
    return [
        VisionElement.from_dict(item, source)
        for item in metadata.get("fixture_elements", [])
        if (item.get("element_type") or item.get("type")) in allowed_types
    ]

