from __future__ import annotations

from typing import Any


def find_text_entities_by_keyword(model: dict[str, Any], keyword: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not keyword:
        return results

    for entity in model.get("entities", []):
        if entity.get("type") not in {"text", "mtext", "dimension"}:
            continue
        text = str(
            entity.get("properties", {}).get("text")
            or entity.get("properties", {}).get("text_override")
            or ""
        )
        if keyword not in text:
            continue
        results.append(
            {
                "id": entity.get("id"),
                "handle": entity.get("handle"),
                "text": text,
                "position": _first_point(entity),
            }
        )
    return results


def _first_point(entity: dict[str, Any]) -> dict[str, Any] | None:
    points = entity.get("geometry", {}).get("points", []) or []
    if not points:
        return None
    point = points[0]
    if isinstance(point, dict):
        return {
            "x": float(point.get("x", 0.0)),
            "y": float(point.get("y", 0.0)),
            "coordinate_system": point.get("coordinate_system", "cad_world"),
        }
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return {"x": float(point[0]), "y": float(point[1]), "coordinate_system": "cad_world"}
    return None
