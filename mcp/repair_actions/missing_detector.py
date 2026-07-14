from __future__ import annotations

from typing import Any

from mcp.repair_actions.geometry_utils import is_near_duplicate_geometry


def detect_coordinate_missing(
    aligned_reference_graph: dict[str, Any],
    target_graph: dict[str, Any],
    options: dict | None = None,
) -> dict[str, Any]:
    options = options or {}
    tolerance = float(options.get("tolerance", 10.0))
    result = {
        "true_missing": [],
        "already_exists": [],
        "uncertain": [],
        "geometry_conflict": [],
        "unsupported": [],
        "warnings": [],
        "confidence": 0.0,
    }
    _classify_elements("pipe", aligned_reference_graph.get("pipes", []), target_graph.get("pipes", []), tolerance, result)
    _classify_elements("sprinkler", aligned_reference_graph.get("sprinklers", []), target_graph.get("sprinklers", []), tolerance, result)
    _classify_elements("valve", aligned_reference_graph.get("valves", []), target_graph.get("valves", []), tolerance, result)
    result["confidence"] = _confidence(result)
    return result


def _classify_elements(
    element_type: str,
    reference_elements: list[dict[str, Any]],
    target_elements: list[dict[str, Any]],
    tolerance: float,
    result: dict[str, Any],
) -> None:
    for element in reference_elements:
        confidence = float(element.get("mapped_confidence", element.get("confidence", 0.0)))
        mapped = element.get("mapped_geometry")
        if confidence < 0.6:
            result["uncertain"].append(_item(element_type, element, "low confidence reference element"))
            continue
        if not mapped:
            result["uncertain"].append(_item(element_type, element, "missing mapped_geometry"))
            continue
        existing = _find_existing(element_type, mapped, target_elements, tolerance)
        if existing is not None:
            item = _item(element_type, element, "near duplicate exists in target")
            item["target_element_id"] = existing.get("id")
            result["already_exists"].append(item)
            continue
        result["true_missing"].append(_item(element_type, element, f"missing {element_type} in target graph"))


def _find_existing(
    element_type: str,
    mapped_geometry: dict[str, Any],
    target_elements: list[dict[str, Any]],
    tolerance: float,
) -> dict[str, Any] | None:
    for target in target_elements:
        target_geom = _target_geometry(element_type, target)
        if is_near_duplicate_geometry(mapped_geometry, target_geom, tolerance):
            return target
    return None


def _target_geometry(element_type: str, target: dict[str, Any]) -> dict[str, Any]:
    if element_type == "pipe":
        return {"start": target.get("start"), "end": target.get("end")}
    position = target.get("position")
    return {"points": [position, position]} if position else {}


def _item(element_type: str, element: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "element_type": element_type,
        "element_id": element.get("id"),
        "source_element_id": element.get("source_element_id"),
        "element": element,
        "confidence": float(element.get("mapped_confidence", element.get("confidence", 0.0))),
        "reason": reason,
    }


def _confidence(result: dict[str, Any]) -> float:
    items = result["true_missing"] + result["already_exists"] + result["uncertain"]
    if not items:
        return 1.0
    return round(sum(float(item.get("confidence", 0.0)) for item in items) / len(items), 4)

