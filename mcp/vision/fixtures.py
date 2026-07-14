from __future__ import annotations

from typing import Any

from mcp.vision.models import VisionElement


def fixture_elements(
    image: dict[str, Any],
    element_types: set[str],
    detector: str,
    method: str = "fixture",
) -> list[VisionElement]:
    metadata = image.get("metadata", {})
    source = {
        "type": metadata.get("source_type", "image"),
        "path": image.get("image_path"),
    }
    elements: list[VisionElement] = []
    for item in metadata.get("fixture_elements", []):
        item_type = item.get("element_type") or item.get("type")
        if item_type not in element_types:
            continue
        item_data = dict(item)
        item_metadata = dict(item_data.get("metadata", {}))
        item_metadata.setdefault("detector", detector)
        item_metadata.setdefault("method", method)
        item_data["metadata"] = item_metadata
        elements.append(VisionElement.from_dict(item_data, source))
    return elements


def image_dimensions(image: dict[str, Any]) -> tuple[int, int]:
    metadata = image.get("metadata", {})
    width = metadata.get("image_width") or image.get("image_width") or 1
    height = metadata.get("image_height") or image.get("image_height") or 1
    return int(width), int(height)

