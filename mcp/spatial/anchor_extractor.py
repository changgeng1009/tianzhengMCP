from __future__ import annotations

from typing import Any

from mcp.spatial.models import AnchorPoint, Point2D


def extract_reference_anchors(reference_graph: dict[str, Any]) -> list[AnchorPoint]:
    return _extract_anchors(reference_graph, "reference")


def extract_target_anchors(target_graph: dict[str, Any]) -> list[AnchorPoint]:
    return _extract_anchors(target_graph, "target")


def _extract_anchors(graph: dict[str, Any], source: str) -> list[AnchorPoint]:
    anchors: list[AnchorPoint] = []
    for building in graph.get("buildings", []):
        bbox = building.get("bbox")
        if _valid_bbox(bbox):
            center = Point2D((float(bbox[0]) + float(bbox[2])) / 2, (float(bbox[1]) + float(bbox[3])) / 2)
            anchors.append(_anchor(source, building, center, "building_centroid"))
            for index, point in enumerate(
                [
                    Point2D(float(bbox[0]), float(bbox[1])),
                    Point2D(float(bbox[2]), float(bbox[1])),
                    Point2D(float(bbox[2]), float(bbox[3])),
                    Point2D(float(bbox[0]), float(bbox[3])),
                ]
            ):
                anchors.append(_anchor(source, building, point, "building_bbox_corner", suffix=str(index)))

    for pipe in graph.get("pipes", []):
        for field in ("start", "end"):
            point = _point_from(pipe.get(field))
            if point is not None:
                anchors.append(_anchor(source, pipe, point, "pipe_endpoint", suffix=field))

    for sprinkler in graph.get("sprinklers", []):
        point = _point_from(sprinkler.get("position"))
        if point is not None:
            anchors.append(_anchor(source, sprinkler, point, "sprinkler_center"))

    for valve in graph.get("valves", []):
        point = _point_from(valve.get("position"))
        if point is not None:
            anchors.append(_anchor(source, valve, point, "valve_center"))

    for text in graph.get("texts", []):
        bbox = text.get("bbox")
        if _valid_bbox(bbox):
            point = Point2D((float(bbox[0]) + float(bbox[2])) / 2, (float(bbox[1]) + float(bbox[3])) / 2)
            anchors.append(_anchor(source, text, point, "text_label_center"))

    for node in graph.get("nodes", []):
        point = _point_from(node.get("position"))
        if point is not None:
            anchors.append(_anchor(source, node, point, "graph_node"))

    return anchors


def _anchor(
    source: str,
    element: dict[str, Any],
    point: Point2D,
    element_type: str,
    suffix: str = "",
) -> AnchorPoint:
    element_id = str(element.get("id") or element.get("source_element_id") or element_type)
    anchor_id = f"{source}_{element_id}_{element_type}{('_' + suffix) if suffix else ''}"
    return AnchorPoint(
        anchor_id=anchor_id,
        source=source,
        point=point,
        element_id=element_id,
        element_type=element_type,
        confidence=float(element.get("confidence", 0.6)),
        metadata={"source_element": element},
    )


def _point_from(value: Any) -> Point2D | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return Point2D(float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None


def _valid_bbox(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 4

