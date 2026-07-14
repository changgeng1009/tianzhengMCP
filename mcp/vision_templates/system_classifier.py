from __future__ import annotations

from mcp.vision_templates.models import ClassifiedSystem


KEYWORDS = [
    ("sprinkler", ["喷淋", "自动喷水"], 0.92),
    ("fire_hydrant", ["消火栓", "消防"], 0.9),
    ("domestic_water", ["生活给水", "给水"], 0.88),
    ("drainage", ["排水", "污水", "废水", "雨水"], 0.88),
]


def classify_system_text(text: str) -> ClassifiedSystem:
    raw = str(text or "")
    for system_type, keywords, confidence in KEYWORDS:
        if any(keyword in raw for keyword in keywords):
            return ClassifiedSystem(raw, system_type, confidence)
    return ClassifiedSystem(raw, "unknown", 0.3, warnings=["system type unknown"])

