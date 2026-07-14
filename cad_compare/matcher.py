from __future__ import annotations

from typing import Any

from cad_compare.similarity import entity_text
from cad_compare.similarity import max_point_distance, points


class EntityMatcher:
    def __init__(self, tolerance: float = 1.0) -> None:
        self.tolerance = float(tolerance)

    def is_match(self, reference: dict[str, Any], current: dict[str, Any]) -> bool:
        if reference.get("type") != current.get("type"):
            return False
        reference_points = points(reference)
        current_points = points(current)
        if not reference_points and not current_points:
            return self._stable_key(reference) == self._stable_key(current)
        return max_point_distance(reference_points, current_points) <= self.tolerance

    def is_stable_match(self, reference: dict[str, Any], current: dict[str, Any]) -> bool:
        if reference.get("type") != current.get("type"):
            return False
        if reference.get("type") in {"text", "mtext", "dimension"}:
            text = entity_text(reference)
            return bool(text) and text == entity_text(current)
        reference_key = self._stable_key(reference)
        return any(reference_key[1:]) and reference_key == self._stable_key(current)

    def _stable_key(self, entity: dict[str, Any]) -> tuple[Any, ...]:
        properties = entity.get("properties", {})
        return (
            entity.get("type"),
            properties.get("text"),
            properties.get("block_name"),
            properties.get("dimension"),
        )
