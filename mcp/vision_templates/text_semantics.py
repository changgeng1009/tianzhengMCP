from __future__ import annotations

from mcp.vision_templates.diameter_parser import parse_diameter_text
from mcp.vision_templates.system_classifier import classify_system_text


def extract_text_semantics(text_elements: list[dict]) -> dict:
    diameters: list[dict] = []
    systems: list[dict] = []
    building_labels: list[dict] = []
    legends: list[dict] = []
    warnings: list[str] = []
    if not text_elements:
        return {
            "diameters": [],
            "systems": [],
            "building_labels": [],
            "legends": [],
            "warnings": ["no OCR/text elements available"],
        }
    for item in text_elements:
        text = str(item.get("text") or "")
        text_id = item.get("id") or item.get("source_element_id")
        diameter = parse_diameter_text(text)
        if diameter:
            diameter.source_text_id = text_id
            diameters.append(diameter.to_dict())
        system = classify_system_text(text)
        system.source_text_id = text_id
        if system.system_type != "unknown":
            systems.append(system.to_dict())
        if "栋" in text or "楼" in text:
            building_labels.append({"text": text, "source_text_id": text_id, "confidence": item.get("confidence", 0.6)})
        if "图例" in text:
            legends.append({"text": text, "source_text_id": text_id, "confidence": item.get("confidence", 0.6)})
    if not diameters:
        warnings.append("no diameter text parsed")
    if not systems:
        warnings.append("no system text classified")
    return {
        "diameters": diameters,
        "systems": systems,
        "building_labels": building_labels,
        "legends": legends,
        "warnings": warnings,
    }

