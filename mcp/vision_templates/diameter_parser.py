from __future__ import annotations

import re

from mcp.vision_templates.models import ParsedDiameter


DIAMETER_PATTERN = re.compile(r"(?i)(DN|DE|D|Φ|φ)?\s*([0-9]{2,4})")


def parse_diameter_text(text: str) -> ParsedDiameter | None:
    if not text:
        return None
    match = DIAMETER_PATTERN.search(str(text))
    if not match:
        return None
    raw_unit = match.group(1) or ""
    value = int(match.group(2))
    if not raw_unit:
        return ParsedDiameter(str(text), str(value), value, "", 0.55, warnings=["numeric diameter without unit"])
    unit_upper = raw_unit.upper()
    if raw_unit in {"Φ", "φ"}:
        unit = "Φ"
        normalized = f"Φ{value}"
    elif unit_upper == "DE":
        unit = "De"
        normalized = f"De{value}"
    else:
        unit = unit_upper
        normalized = f"{unit}{value}"
    confidence = 0.95 if unit in {"DN", "De", "Φ"} else 0.8
    return ParsedDiameter(str(text), normalized, value, unit, confidence)

