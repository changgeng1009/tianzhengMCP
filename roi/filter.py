from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from roi.models import ROIRegion


def filter_entities_by_roi(entities: list[dict[str, Any]], roi: ROIRegion) -> dict[str, Any]:
    kept: list[dict[str, Any]] = []
    for entity in entities:
        if _entity_intersects_roi(entity, roi):
            kept.append(deepcopy(entity))

    summary = Counter(entity.get("type", "unknown") for entity in kept)
    return {
        "kept_entities": kept,
        "excluded_entities_count": len(entities) - len(kept),
        "roi_summary": {
            "roi": roi.to_dict(),
            "total_before_roi": len(entities),
            "total_after_roi": len(kept),
            "excluded_entities_count": len(entities) - len(kept),
            "entity_type_summary": dict(summary),
        },
    }


def filter_model_by_roi(model: dict[str, Any], roi: ROIRegion) -> dict[str, Any]:
    result = deepcopy(model)
    filtered = filter_entities_by_roi(list(model.get("entities", [])), roi)
    result["entities"] = filtered["kept_entities"]
    result["roi"] = roi.to_dict()
    result["roi_summary"] = filtered["roi_summary"]
    return result


def _entity_intersects_roi(entity: dict[str, Any], roi: ROIRegion) -> bool:
    bbox = entity.get("bounding_box") or entity.get("geometry", {}).get("bounding_box")
    if _valid_bbox(bbox) and roi.intersects_bbox(bbox):
        return True

    if _valid_bbox(bbox):
        center_x = (float(bbox["x_min"]) + float(bbox["x_max"])) / 2
        center_y = (float(bbox["y_min"]) + float(bbox["y_max"])) / 2
        if roi.contains_point(center_x, center_y):
            return True

    for point in _entity_points(entity):
        if roi.contains_point(point["x"], point["y"]):
            return True

    return False


def _valid_bbox(value: Any) -> bool:
    return isinstance(value, dict) and all(
        key in value for key in ("x_min", "y_min", "x_max", "y_max")
    )


def _entity_points(entity: dict[str, Any]) -> list[dict[str, float]]:
    geometry = entity.get("geometry", {})
    result: list[dict[str, float]] = []
    for point in geometry.get("points", []) or []:
        converted = _point_to_xy(point)
        if converted:
            result.append(converted)

    for key in ("position", "insertion_point", "start", "end"):
        converted = _point_to_xy(geometry.get(key) or entity.get("properties", {}).get(key))
        if converted:
            result.append(converted)
    return result


def _point_to_xy(value: Any) -> dict[str, float] | None:
    if isinstance(value, dict) and "x" in value and "y" in value:
        return {"x": float(value["x"]), "y": float(value["y"])}
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return {"x": float(value[0]), "y": float(value[1])}
    return None
