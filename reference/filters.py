from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_RULES = {
    "ignored_layers": ["TITLE", "A-TITLE", "BORDER", "DEFPOINTS"],
    "ignored_text_patterns": ["图签", "标题栏", "设计说明"],
}


class ReferenceEntityFilter:
    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        self.rules = rules or DEFAULT_RULES

    @classmethod
    def from_json_file(cls, path: str | Path) -> "ReferenceEntityFilter":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def filter_entities(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [entity for entity in entities if not self._is_ignored(entity)]

    def filter_model(self, model: dict[str, Any]) -> dict[str, Any]:
        result = dict(model)
        result["entities"] = self.filter_entities(list(model.get("entities", [])))
        return result

    def _is_ignored(self, entity: dict[str, Any]) -> bool:
        layer = str(entity.get("layer") or entity.get("properties", {}).get("layer") or "")
        if layer.upper() in {item.upper() for item in self.rules.get("ignored_layers", [])}:
            return True

        text = str(entity.get("properties", {}).get("text") or "")
        return any(
            re.search(pattern, text, flags=re.IGNORECASE)
            for pattern in self.rules.get("ignored_text_patterns", [])
        )
