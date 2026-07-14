from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from cad.blocks import read_block_reference_properties
from cad.connection import AutoCADConnectionManager
from cad.geometry import coordinates_to_points, normalize_point, read_bounding_box
from cad.layers import read_layers


logger = logging.getLogger(__name__)


OBJECT_TYPE_MAP = {
    "AcDbLine": "line",
    "AcDbPolyline": "polyline",
    "AcDb2dPolyline": "polyline",
    "AcDb3dPolyline": "polyline",
    "AcDbCircle": "circle",
    "AcDbArc": "arc",
    "AcDbText": "text",
    "AcDbMText": "mtext",
    "AcDbBlockReference": "block_reference",
}


SUMMARY_KEYS = {
    "line": "lines",
    "polyline": "polylines",
    "circle": "circles",
    "arc": "arcs",
    "text": "texts",
    "mtext": "mtexts",
    "block_reference": "blocks",
    "dimension": "dimensions",
    "unknown_cad_entity": "unknown",
}


class CADReader:
    def __init__(self, manager: AutoCADConnectionManager) -> None:
        self.manager = manager

    def read_current_drawing(self) -> dict[str, Any]:
        try:
            document = self.manager.require_active_document()
            model = self.read_document(document)
            return {"success": True, "model": model}
        except Exception as exc:
            logger.exception("读取当前 AutoCAD 图纸失败")
            return {"success": False, "error": str(exc)}

    def read_selected_entities(self) -> dict[str, Any]:
        try:
            document = self.manager.require_active_document()
            selected = self._selected_entities(document)
            model = self._build_model(document, selected, source_kind="current_autocad")
            return {
                "success": True,
                "selection_count": len(selected),
                "model": model,
            }
        except Exception as exc:
            logger.exception("读取当前 AutoCAD 选择集失败")
            return {"success": False, "selection_count": 0, "error": str(exc)}

    def summarize_current_drawing(self) -> dict[str, Any]:
        result = self.read_current_drawing()
        if not result.get("success"):
            return {"success": False, "summary": {}, "error": result.get("error")}
        counter = Counter(
            SUMMARY_KEYS.get(entity["type"], "unknown")
            for entity in result["model"]["entities"]
        )
        summary = {key: 0 for key in SUMMARY_KEYS.values()}
        summary.update(counter)
        return {
            "success": True,
            "active_document": result["model"]["source"]["active_document"],
            "summary": summary,
        }

    def read_document(
        self,
        document: Any,
        source_kind: str = "current_autocad",
        reader_name: str = "real_current_cad_reader_mvp",
    ) -> dict[str, Any]:
        return self._build_model(
            document,
            self._iter_drawing_entities(document),
            source_kind=source_kind,
            reader_name=reader_name,
        )

    def _build_model(
        self,
        document: Any,
        entities: list[Any],
        source_kind: str,
        reader_name: str = "real_current_cad_reader_mvp",
    ) -> dict[str, Any]:
        parsed_entities = [
            self._entity_to_model(entity, index, source_kind)
            for index, entity in enumerate(entities, start=1)
        ]
        return {
            "source": {
                "kind": source_kind,
                "active_document": _safe_get(document, "Name"),
                "full_name": _safe_get(document, "FullName"),
                "reader": reader_name,
            },
            "layers": read_layers(document),
            "global_uncertainties": [],
            "entities": parsed_entities,
        }

    def _iter_drawing_entities(self, document: Any) -> list[Any]:
        entities: list[Any] = []
        for space_name in ("ModelSpace", "PaperSpace"):
            space = _safe_get(document, space_name)
            if space is not None:
                entities.extend(_iter_collection(space))
        return entities

    def _selected_entities(self, document: Any) -> list[Any]:
        for attr in ("ActiveSelectionSet", "PickfirstSelectionSet"):
            selection = _safe_get(document, attr)
            if selection is not None:
                return _iter_collection(selection)
        return []

    def _entity_to_model(self, entity: Any, index: int, source_kind: str) -> dict[str, Any]:
        object_name = str(_safe_get(entity, "ObjectName") or _safe_get(entity, "EntityName") or "")
        entity_type = _entity_type(object_name)
        handle = str(_safe_get(entity, "Handle") or f"entity_{index:04d}")
        geometry, properties = self._read_geometry_and_properties(entity, entity_type)
        bounding_box = read_bounding_box(entity, geometry.get("points", []))
        output_geometry = _serialize_geometry(geometry, bounding_box)
        known = entity_type != "unknown_cad_entity"
        common_properties = {
            "handle": handle,
            "object_name": object_name,
            "layer": _safe_get(entity, "Layer"),
            "color": _safe_get(entity, "Color"),
            "linetype": _safe_get(entity, "Linetype"),
            **properties,
        }
        return {
            "id": handle,
            "handle": handle,
            "type": entity_type,
            "object_name": object_name,
            "layer": _safe_get(entity, "Layer"),
            "geometry": output_geometry,
            "bounding_box": bounding_box,
            "properties": common_properties,
            "confidence": 1.0 if known else 0.5,
            "status": "Confirmed" if known else "Uncertain",
            "evidence": "Read from current AutoCAD drawing via COM.",
            "uncertainties": [] if known else ["Unsupported CAD object type."],
            "source": source_kind,
            "reason": "Read from supported CAD entity." if known else "Unsupported CAD object type.",
        }

    def _read_geometry_and_properties(self, entity: Any, entity_type: str) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            if entity_type == "line":
                start = normalize_point(_safe_get(entity, "StartPoint"))
                end = normalize_point(_safe_get(entity, "EndPoint"))
                return (
                    {
                        "coordinate_system": "cad_world",
                        "points": [start, end],
                        "start": start,
                        "end": end,
                    },
                    {},
                )
            if entity_type == "polyline":
                points = coordinates_to_points(_safe_get(entity, "Coordinates"))
                return {"coordinate_system": "cad_world", "points": points}, {}
            if entity_type == "circle":
                center = normalize_point(_safe_get(entity, "Center"))
                radius = float(_safe_get(entity, "Radius") or 0.0)
                return (
                    {
                        "coordinate_system": "cad_world",
                        "points": [center],
                        "center": center,
                        "radius": radius,
                    },
                    {"radius": radius},
                )
            if entity_type == "arc":
                center = normalize_point(_safe_get(entity, "Center"))
                radius = float(_safe_get(entity, "Radius") or 0.0)
                properties = {
                    "radius": radius,
                    "start_angle": _safe_get(entity, "StartAngle"),
                    "end_angle": _safe_get(entity, "EndAngle"),
                }
                return (
                    {
                        "coordinate_system": "cad_world",
                        "points": [center],
                        "center": center,
                        **properties,
                    },
                    properties,
                )
            if entity_type in {"text", "mtext"}:
                position = normalize_point(_safe_get(entity, "InsertionPoint"))
                text = _safe_get(entity, "TextString") or _safe_get(entity, "Contents") or ""
                height = _safe_get(entity, "Height")
                return (
                    {
                        "coordinate_system": "cad_world",
                        "points": [position],
                        "position": position,
                    },
                    {"text": text, "height": height},
                )
            if entity_type == "block_reference":
                properties = read_block_reference_properties(entity)
                point = properties.get("insertion_point")
                points = [point] if point else []
                return (
                    {
                        "coordinate_system": "cad_world",
                        "points": points,
                        "position": point,
                    },
                    properties,
                )
            if entity_type == "dimension":
                text_position = _safe_get(entity, "TextPosition")
                points = [normalize_point(text_position)] if text_position is not None else []
                return (
                    {"coordinate_system": "cad_world", "points": points},
                    {
                        "measurement": _safe_get(entity, "Measurement"),
                        "text_override": _safe_get(entity, "TextOverride"),
                    },
                )
        except Exception:
            logger.info("读取 CAD 对象几何失败: object_name=%s", _safe_get(entity, "ObjectName"), exc_info=True)
        return {"coordinate_system": "cad_world", "points": []}, {}


def _entity_type(object_name: str) -> str:
    if "Dimension" in object_name:
        return "dimension"
    return OBJECT_TYPE_MAP.get(object_name, "unknown_cad_entity")


def _serialize_geometry(geometry: dict[str, Any], bounding_box: dict[str, Any] | None) -> dict[str, Any]:
    serialized = dict(geometry)
    serialized["points"] = [_point_to_dict(point) for point in geometry.get("points", [])]
    serialized["bounding_box"] = bounding_box
    return serialized


def _point_to_dict(point: list[float]) -> dict[str, Any]:
    normalized = normalize_point(point)
    return {
        "x": normalized[0],
        "y": normalized[1],
        "coordinate_system": "cad_world",
    }


def _iter_collection(collection: Any) -> list[Any]:
    try:
        return list(collection)
    except Exception:
        logger.info("COM collection is not directly iterable; trying Count/Item", exc_info=True)

    count = int(_safe_get(collection, "Count") or 0)
    result: list[Any] = []
    for index in range(count):
        try:
            result.append(collection.Item(index))
            continue
        except Exception:
            pass
        try:
            result.append(collection.Item(index + 1))
        except Exception:
            logger.info("COM collection Item lookup failed: index=%s", index, exc_info=True)
    return result


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None
