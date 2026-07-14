from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GEOMETRY_OBJECT_TYPES = {
    "AcDbLine": "line",
    "AcDbPolyline": "polyline",
    "AcDbCircle": "circle",
    "AcDbArc": "arc",
    "AcDbText": "text",
    "AcDbMText": "text",
    "AcDbBlockReference": "block",
}

TDB_OBJECT_TYPES = {
    "TDbDoubleLinePipe": "tdb_pipe",
    "TDbPipe": "tdb_pipe",
    "TDbPipeValve": "tdb_valve",
    "TDbPipeFitting": "tdb_fitting",
    "TDbDimension2": "dimension",
    "TDbPump": "equipment",
    "TDbWaterTank": "equipment",
    "TDbEquipment": "equipment",
}

DIRECT_COM_OBJECT_TYPES = {"line", "polyline", "text", "block"}
MANUAL_TIANZHENG_OBJECT_NAMES = set(TDB_OBJECT_TYPES)


@dataclass(frozen=True)
class SemanticObject:
    object_id: str
    source: str
    object_type: str
    geometry: dict[str, Any] = field(default_factory=dict)
    semantic: dict[str, Any] = field(default_factory=dict)
    layer: str = ""
    confidence: float = 0.0
    requires_visual_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "source": self.source,
            "object_type": self.object_type,
            "geometry": dict(self.geometry),
            "semantic": dict(self.semantic),
            "layer": self.layer,
            "confidence": self.confidence,
            "requires_visual_review": self.requires_visual_review,
        }


def normalize_object_name(object_name: str | None) -> str:
    return str(object_name or "").strip()


def semantic_type_from_object_name(object_name: str | None) -> str:
    normalized = normalize_object_name(object_name)
    if normalized in GEOMETRY_OBJECT_TYPES:
        return GEOMETRY_OBJECT_TYPES[normalized]
    if normalized in TDB_OBJECT_TYPES:
        return TDB_OBJECT_TYPES[normalized]
    return "unknown"


def semantic_object_from_dwg_entity(
    entity: dict[str, Any],
    *,
    source: str,
    index: int,
    confidence: float = 0.75,
) -> dict[str, Any]:
    object_name = normalize_object_name(entity.get("ObjectName") or entity.get("object_name"))
    handle = str(entity.get("Handle") or entity.get("handle") or f"idx_{index}")
    object_type = semantic_type_from_object_name(object_name)
    layer = str(entity.get("Layer") or entity.get("layer") or "")

    semantic = {
        "object_name": object_name,
        "handle": handle,
        "diameter": entity.get("DNDiameter") or entity.get("diameter"),
        "system_type": entity.get("SysType") or entity.get("system_type"),
    }
    geometry: dict[str, Any] = {
        "bbox": entity.get("bbox"),
        "center": entity.get("center"),
        "start_point": entity.get("StartPoint") or entity.get("start_point"),
        "end_point": entity.get("EndPoint") or entity.get("end_point"),
        "length": entity.get("length"),
    }
    geometry = {key: value for key, value in geometry.items() if value is not None}

    return SemanticObject(
        object_id=f"{source}:{handle}",
        source=source,
        object_type=object_type,
        geometry=geometry,
        semantic=semantic,
        layer=layer,
        confidence=confidence if object_type != "unknown" else min(confidence, 0.4),
        requires_visual_review=object_type == "unknown",
    ).to_dict()


def semantic_object_from_pdf_item(
    item: dict[str, Any],
    *,
    index: int,
    confidence: float = 0.6,
) -> dict[str, Any]:
    object_type = str(item.get("object_type") or "text")
    return SemanticObject(
        object_id=str(item.get("object_id") or f"reference_pdf:item_{index}"),
        source="reference_pdf",
        object_type=object_type,
        geometry=dict(item.get("geometry") or {}),
        semantic=dict(item.get("semantic") or {}),
        layer=str(item.get("layer") or "pdf"),
        confidence=float(item.get("confidence", confidence)),
        requires_visual_review=bool(item.get("requires_visual_review", False)),
    ).to_dict()


def validate_semantic_object_schema(obj: dict[str, Any]) -> tuple[bool, list[str]]:
    required = {
        "object_id": str,
        "source": str,
        "object_type": str,
        "geometry": dict,
        "semantic": dict,
        "layer": str,
        "confidence": (int, float),
        "requires_visual_review": bool,
    }
    errors: list[str] = []
    for key, expected_type in required.items():
        if key not in obj:
            errors.append(f"missing field: {key}")
        elif not isinstance(obj[key], expected_type):
            errors.append(f"invalid field type: {key}")
    return not errors, errors


def validate_semantic_objects(objects: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for index, obj in enumerate(objects):
        ok, item_errors = validate_semantic_object_schema(obj)
        if not ok:
            errors.extend(f"objects[{index}].{error}" for error in item_errors)
    return not errors, errors

