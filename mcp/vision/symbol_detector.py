from __future__ import annotations

from typing import Any

from mcp.vision.models import VisionElement


SYMBOL_TYPES = {"sprinkler_candidate", "valve_candidate", "fitting_candidate"}


def detect_symbols(image: dict[str, Any]) -> dict[str, Any]:
    metadata = image.get("metadata", {})
    source = {"type": metadata.get("source_type", "image"), "path": image.get("image_path")}
    elements = [
        VisionElement.from_dict(item, source)
        for item in metadata.get("fixture_elements", [])
        if (item.get("element_type") or item.get("type")) in SYMBOL_TYPES
    ]
    warnings: list[str] = []
    if not elements:
        warnings.append("symbol detector found no sprinkler/valve/fitting candidates")
    return {
        "elements": elements,
        "warnings": warnings,
    }

