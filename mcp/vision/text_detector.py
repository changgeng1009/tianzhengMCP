from __future__ import annotations

from typing import Any

from mcp.vision.models import VisionElement


def detect_texts(image: dict[str, Any], ocr_provider: Any | None = None) -> dict[str, Any]:
    metadata = image.get("metadata", {})
    source = {"type": metadata.get("source_type", "image"), "path": image.get("image_path")}
    fixture_texts = [
        VisionElement.from_dict(item, source)
        for item in metadata.get("fixture_elements", [])
        if (item.get("element_type") or item.get("type")) == "text_candidate"
    ]
    if fixture_texts:
        return {"elements": fixture_texts, "warnings": []}

    if ocr_provider is None:
        return {
            "elements": [],
            "warnings": ["OCR provider not configured"],
        }

    try:
        raw_items = ocr_provider.detect_texts(image)
        return {
            "elements": [VisionElement.from_dict(item, source) for item in raw_items],
            "warnings": [],
        }
    except Exception as exc:
        return {
            "elements": [],
            "warnings": [f"OCR provider failed: {exc}"],
        }
