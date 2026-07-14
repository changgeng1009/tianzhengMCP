from __future__ import annotations

from typing import Any

from mcp.vision.models import SemanticGraph, VisionElement


LOW_CONFIDENCE_THRESHOLD = 0.7


def build_semantic_graph(
    elements: list[VisionElement],
    provider: str = "BasicVisionProvider",
    coordinate_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    buildings: list[dict[str, Any]] = []
    pipes: list[dict[str, Any]] = []
    valves: list[dict[str, Any]] = []
    sprinklers: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []

    for element in elements:
        if element.element_type in {"building_outline", "building_candidate"}:
            buildings.append(_building(element))
        elif element.element_type == "pipe_candidate":
            pipes.append(_pipe(element))
        elif element.element_type == "valve_candidate":
            valves.append(_point_symbol(element, "valve"))
            symbols.append(_symbol(element))
        elif element.element_type == "sprinkler_candidate":
            sprinklers.append(_point_symbol(element, "sprinkler"))
            symbols.append(_symbol(element))
        elif element.element_type in {"fitting_candidate", "legend_candidate"}:
            symbols.append(_symbol(element))
        elif element.element_type == "text_candidate":
            texts.append(_text(element))
        else:
            symbols.append(_symbol(element))

    confidence = _graph_confidence(elements)
    warnings: list[str] = []
    if not elements:
        warnings.append("no visual elements detected")
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        warnings.append("low confidence visual parse")

    return SemanticGraph(
        buildings=buildings,
        pipes=pipes,
        valves=valves,
        sprinklers=sprinklers,
        texts=texts,
        symbols=symbols,
        metadata={
            "source": "vision",
            "provider": provider,
            "confidence": confidence,
            "warnings": warnings,
            "coordinate_space": (coordinate_metadata or {}).get(
                "coordinate_space", "normalized_image"
            ),
            **(coordinate_metadata or {}),
        },
    ).to_dict()


def _building(element: VisionElement) -> dict[str, Any]:
    label = element.metadata.get("label") or element.element_id
    return {
        "id": element.element_id,
        "source_element_id": element.element_id,
        "label": label,
        "bbox": list(element.bbox),
        "points": [list(point) for point in element.points],
        "confidence": element.confidence,
        "source": "vision",
        "metadata": dict(element.metadata),
    }


def _pipe(element: VisionElement) -> dict[str, Any]:
    start = _point3d(element.points[0]) if len(element.points) >= 1 else [element.bbox[0], element.bbox[1], 0.0]
    end = _point3d(element.points[-1]) if len(element.points) >= 2 else [element.bbox[2], element.bbox[3], 0.0]
    return {
        "id": element.element_id,
        "source_element_id": element.element_id,
        "building_id": element.metadata.get("building_id"),
        "start": start,
        "end": end,
        "dn": element.metadata.get("dn"),
        "system_type": element.metadata.get("system_type", "unknown"),
        "confidence": element.confidence,
        "bbox": list(element.bbox),
        "points": [list(point) for point in element.points],
        "source": "vision",
        "metadata": dict(element.metadata),
    }


def _point_symbol(element: VisionElement, symbol_type: str) -> dict[str, Any]:
    return {
        "id": element.element_id,
        "source_element_id": element.element_id,
        "building_id": element.metadata.get("building_id"),
        "position": _bbox_center(element.bbox),
        "symbol_type": symbol_type,
        "confidence": element.confidence,
        "bbox": list(element.bbox),
        "points": [list(point) for point in element.points],
        "source": "vision",
        "metadata": dict(element.metadata),
    }


def _text(element: VisionElement) -> dict[str, Any]:
    return {
        "id": element.element_id,
        "source_element_id": element.element_id,
        "text": element.text,
        "bbox": list(element.bbox),
        "points": [list(point) for point in element.points],
        "confidence": element.confidence,
        "source": "vision",
        "metadata": dict(element.metadata),
    }


def _symbol(element: VisionElement) -> dict[str, Any]:
    return {
        "id": element.element_id,
        "source_element_id": element.element_id,
        "symbol_type": element.element_type,
        "bbox": list(element.bbox),
        "points": [list(point) for point in element.points],
        "confidence": element.confidence,
        "source": "vision",
        "metadata": dict(element.metadata),
    }


def _point3d(point: list[float]) -> list[float]:
    values = [float(value) for value in point]
    return values + [0.0] * (3 - len(values))


def _bbox_center(bbox: list[float]) -> list[float]:
    if len(bbox) < 4:
        return [0.0, 0.0, 0.0]
    return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2, 0.0]


def _graph_confidence(elements: list[VisionElement]) -> float:
    if not elements:
        return 0.0
    return round(sum(element.confidence for element in elements) / len(elements), 4)
