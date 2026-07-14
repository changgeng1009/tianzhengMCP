from __future__ import annotations

import re
from typing import Any


DIAMETER_PATTERN = re.compile(
    r"\b(?P<prefix>DN|De)\s*(?P<size>50|65|75|80|100|110|150|160|200|250|300)\b",
    re.IGNORECASE,
)


class PipeDiameterExtractor:
    def extract_from_text(self, text: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for match in DIAMETER_PATTERN.finditer(text or ""):
            results.append(
                {
                    "diameter": _normalize_diameter(match.group("prefix"), match.group("size")),
                    "raw_text": match.group(0),
                    "confidence": 0.9,
                    "status": "Need User Confirmation",
                    "reason": (
                        "Diameter text recognized, but pipe association is not determined "
                        "in Phase 5.5."
                    ),
                }
            )
        return results

    def extract_from_model(self, model: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for entity in model.get("entities", []):
            if entity.get("type") not in {"text", "mtext", "dimension"}:
                continue
            text = _entity_text(entity)
            for item in self.extract_from_text(text):
                results.append(
                    {
                        "entity_id": entity.get("id"),
                        "handle": entity.get("handle"),
                        "raw_text": text,
                        "diameter": item["diameter"],
                        "confidence": item["confidence"],
                        "status": item["status"],
                        "reason": item["reason"],
                    }
                )
        return results


def _normalize_diameter(prefix: str, size: str) -> str:
    normalized_prefix = "De" if prefix.lower() == "de" else "DN"
    return f"{normalized_prefix}{int(size)}"


def _entity_text(entity: dict[str, Any]) -> str:
    properties = entity.get("properties", {})
    return str(
        properties.get("text")
        or properties.get("text_override")
        or properties.get("dimension")
        or ""
    )
