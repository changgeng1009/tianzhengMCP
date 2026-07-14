from __future__ import annotations

from copy import deepcopy
from typing import Any

from mcp.spatial.models import BBox2D, Point2D, Transform2D
from mcp.spatial.transform import TransformEstimator


GRAPH_KEYS = ("buildings", "pipes", "valves", "sprinklers", "texts", "symbols")


def map_reference_graph_to_target_space(
    reference_graph: dict[str, Any],
    transform: Transform2D,
) -> dict[str, Any]:
    if transform.transform_type == "unknown":
        mapped = deepcopy(reference_graph)
        metadata = dict(mapped.get("metadata", {}))
        warnings = list(metadata.get("warnings", []))
        warnings.append("transform unavailable; graph not mapped")
        metadata["warnings"] = warnings
        mapped["metadata"] = metadata
        return mapped

    estimator = TransformEstimator()
    mapped = {key: [] for key in GRAPH_KEYS}
    warnings: list[str] = []

    for building in reference_graph.get("buildings", []):
        mapped["buildings"].append(_map_entity(building, transform, estimator, warnings, has_bbox=True))
    for pipe in reference_graph.get("pipes", []):
        mapped["pipes"].append(_map_entity(pipe, transform, estimator, warnings, has_line=True))
    for valve in reference_graph.get("valves", []):
        mapped["valves"].append(_map_entity(valve, transform, estimator, warnings, has_position=True))
    for sprinkler in reference_graph.get("sprinklers", []):
        mapped["sprinklers"].append(_map_entity(sprinkler, transform, estimator, warnings, has_position=True))
    for text in reference_graph.get("texts", []):
        mapped["texts"].append(_map_entity(text, transform, estimator, warnings, has_bbox=True))
    for symbol in reference_graph.get("symbols", []):
        mapped["symbols"].append(_map_entity(symbol, transform, estimator, warnings, has_bbox=True))

    mapped["metadata"] = {
        **dict(reference_graph.get("metadata", {})),
        "coordinate_space": "cad_modelspace",
        "transform": transform.to_dict(),
        "warnings": warnings,
    }
    return mapped


def _map_entity(
    entity: dict[str, Any],
    transform: Transform2D,
    estimator: TransformEstimator,
    warnings: list[str],
    has_bbox: bool = False,
    has_line: bool = False,
    has_position: bool = False,
) -> dict[str, Any]:
    item = deepcopy(entity)
    original = _geometry(entity)
    mapped_geometry: dict[str, Any] = {}

    try:
        if has_line and entity.get("start") and entity.get("end"):
            start = estimator.apply_point(transform, Point2D(float(entity["start"][0]), float(entity["start"][1])))
            end = estimator.apply_point(transform, Point2D(float(entity["end"][0]), float(entity["end"][1])))
            mapped_geometry["start"] = [start.x, start.y, 0.0]
            mapped_geometry["end"] = [end.x, end.y, 0.0]
            item["start"] = mapped_geometry["start"]
            item["end"] = mapped_geometry["end"]
        if has_position and entity.get("position"):
            point = estimator.apply_point(transform, Point2D(float(entity["position"][0]), float(entity["position"][1])))
            mapped_geometry["position"] = [point.x, point.y, 0.0]
            item["position"] = mapped_geometry["position"]
        if has_bbox and entity.get("bbox"):
            bbox = entity["bbox"]
            mapped_bbox = estimator.apply_bbox(
                transform,
                BBox2D(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
            )
            mapped_geometry["bbox"] = [
                mapped_bbox.min_x,
                mapped_bbox.min_y,
                mapped_bbox.max_x,
                mapped_bbox.max_y,
            ]
            item["bbox"] = mapped_geometry["bbox"]
    except Exception as exc:
        warnings.append(f"mapping failed for {entity.get('id')}: {exc}")

    item["original_geometry"] = original
    item["mapped_geometry"] = mapped_geometry
    item["mapped_confidence"] = round(float(entity.get("confidence", 0.6)) * transform.confidence, 4)
    return item


def _geometry(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(entity[key])
        for key in ("start", "end", "position", "bbox", "points")
        if key in entity
    }

