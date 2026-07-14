from __future__ import annotations

import logging
import math
from collections import Counter
from typing import Any

from cad.document_resolver import validate_autocad_document
from tianzheng.selection_utils import (
    NoSelectionError,
    delete_selection_set_if_exists,
    safe_delete_selection_set,
    selection_set_item,
)
from tianzheng.object_inspector import inspect_entity
from tianzheng.tdbpipe_deep_probe import dndiameter_result


logger = logging.getLogger(__name__)

TEMP_SELECTION_SET_NAME = "__TianzhengSemanticReaderTemp__"

PROPERTY_PROBE_NAMES = (
    "Radius",
    "DNDiameter",
    "Diameter",
    "PipeDiameter",
    "PipeDN",
    "DN",
    "NominalDiameter",
    "PipeType",
    "SystemType",
    "Material",
    "SysType",
    "SElevation",
    "EElevation",
    "ModelType",
    "SysLabel",
    "DrawLabel",
    "EntityType",
    "LabelLayer",
    "InsulateMaterial",
    "PaintType",
    "PipeWeight",
    "TextColor",
    "TextHeight",
    "TextStyle",
    "Elevation",
    "StartPoint",
    "EndPoint",
    "Center",
    "Position",
    "Location",
    "TextString",
    "TextOverride",
    "Measurement",
    "DimensionText",
    "PrimaryText",
    "Rotation",
    "Angle",
    "Direction",
    "Width",
    "Height",
    "Length",
    "StyleName",
    "Name",
    "Type",
    "FittingType",
    "ValveType",
    "EffectiveName",
    "InsertionPoint",
    "ScaleFactor",
    "XScaleFactor",
    "YScaleFactor",
    "ZScaleFactor",
)


def read_tdb_pipe(entity: Any) -> dict[str, Any]:
    inspection = inspect_entity(entity)
    warnings: list[str] = []
    properties_probe = probe_entity_properties(entity, PROPERTY_PROBE_NAMES)
    radius = properties_probe["properties"].get("Radius")
    radius_value = _float_or_none(radius)
    diameter_probe = dndiameter_result(
        properties_probe["properties"].get("DNDiameter"),
        "DNDiameter" not in properties_probe["failed_properties"],
    )
    diameter = {
        "raw": diameter_probe["dn_diameter_raw"],
        "normalized": diameter_probe["normalized_diameter"],
        "source": diameter_probe["diameter_source"],
        "confidence": diameter_probe["diameter_confidence"],
        "requires_confirmation": diameter_probe["normalized_diameter"] is None,
    }
    bbox = inspection.get("bounding_box")
    inferred_geometry = _pipe_geometry_from_bounding_box(bbox)
    layer_system_type = infer_system_type(inspection.get("layer"))
    sys_type_raw = properties_probe["properties"].get("SysType")
    elevation = {
        "start": properties_probe["properties"].get("SElevation"),
        "end": properties_probe["properties"].get("EElevation"),
        "source": (
            "TDbPipe.SElevation / TDbPipe.EElevation"
            if (
                "SElevation" in properties_probe["properties"]
                or "EElevation" in properties_probe["properties"]
            )
            else None
        ),
    }

    properties = {
        **properties_probe["properties"],
        "display_radius": radius_value,
        "readable_properties": properties_probe["readable_properties"],
        "failed_properties": properties_probe["failed_properties"],
    }
    if radius_value is not None:
        warnings.append("Radius 仅保留为显示 / 几何属性，不能当作真实 DN 管径。")
    elif "Radius" in properties_probe["failed_properties"]:
        warnings.append(f"Radius 读取失败: {properties_probe['failed_properties']['Radius']}")
    if _system_type_conflicts(sys_type_raw, layer_system_type):
        warnings.append(
            f"SysType 与 layer 推断结果可能冲突: SysType={sys_type_raw}, layer={layer_system_type}"
        )

    return {
        "semantic_type": "pipe",
        "object_name": inspection.get("object_name"),
        "handle": inspection.get("handle"),
        "layer": inspection.get("layer"),
        "system_type": layer_system_type,
        "system_type_source": "layer_inference",
        "system_type_raw": sys_type_raw,
        "system_type_raw_source": "TDbPipe.SysType" if sys_type_raw is not None else None,
        "diameter": diameter,
        "elevation": elevation,
        "bounding_box": bbox,
        "inferred_geometry": inferred_geometry,
        "properties": properties,
        "xdata": _xdata_from_inspection(inspection),
        "extension_dictionary": _extension_dictionary_from_inspection(inspection),
        "diagnostic": {
            "read_radius_success": radius_value is not None,
            "read_geometry_success": inferred_geometry["orientation"] != "unknown",
            "read_bounding_box_success": bool(
                inspection.get("diagnostic", {}).get("read_bounding_box_success")
            ),
            "warnings": _warnings(inspection) + warnings,
        },
    }


def read_tdb_pipe_valve(entity: Any) -> dict[str, Any]:
    inspection = inspect_entity(entity)
    bbox = inspection.get("bounding_box")
    geometry = _valve_geometry_from_bounding_box(bbox)
    layer = inspection.get("layer")
    probe = probe_entity_properties(entity, PROPERTY_PROBE_NAMES)
    return {
        "semantic_type": "valve",
        "object_name": inspection.get("object_name"),
        "handle": inspection.get("handle"),
        "layer": layer,
        "system_type": infer_system_type(layer),
        "valve_type_guess": infer_valve_type(layer),
        "bounding_box": bbox,
        "inferred_geometry": geometry,
        "properties": {
            **probe["properties"],
            "readable_properties": probe["readable_properties"],
            "failed_properties": probe["failed_properties"],
        },
        "xdata": _xdata_from_inspection(inspection),
        "extension_dictionary": _extension_dictionary_from_inspection(inspection),
        "diagnostic": {
            "read_bounding_box_success": bool(
                inspection.get("diagnostic", {}).get("read_bounding_box_success")
            ),
            "warnings": _warnings(inspection),
        },
    }


def read_tdb_pipe_fitting(entity: Any) -> dict[str, Any]:
    inspection = inspect_entity(entity)
    bbox = inspection.get("bounding_box")
    geometry = _valve_geometry_from_bounding_box(bbox)
    probe = probe_entity_properties(entity, PROPERTY_PROBE_NAMES)
    return {
        "semantic_type": "fitting",
        "object_name": inspection.get("object_name"),
        "handle": inspection.get("handle"),
        "layer": inspection.get("layer"),
        "system_type": infer_system_type(inspection.get("layer")),
        "fitting_type_guess": _infer_fitting_type(probe["properties"]),
        "bounding_box": bbox,
        "inferred_geometry": geometry,
        "properties": {
            **probe["properties"],
            "readable_properties": probe["readable_properties"],
            "failed_properties": probe["failed_properties"],
        },
        "xdata": _xdata_from_inspection(inspection),
        "extension_dictionary": _extension_dictionary_from_inspection(inspection),
        "diagnostic": {
            "read_bounding_box_success": bool(
                inspection.get("diagnostic", {}).get("read_bounding_box_success")
            ),
            "warnings": _warnings(inspection),
        },
    }


def read_tdb_dimension(entity: Any) -> dict[str, Any]:
    inspection = inspect_entity(entity)
    probe = probe_entity_properties(entity, PROPERTY_PROBE_NAMES)
    properties = probe["properties"]
    warnings = _warnings(inspection)
    warnings.extend(f"{name} 读取失败: {error}" for name, error in probe["failed_properties"].items())
    text = _first_present(
        properties,
        ("TextOverride", "TextString", "DimensionText", "PrimaryText"),
    )
    measurement = properties.get("Measurement")
    return {
        "semantic_type": "dimension",
        "object_name": inspection.get("object_name"),
        "handle": inspection.get("handle"),
        "layer": inspection.get("layer"),
        "bounding_box": inspection.get("bounding_box"),
        "text": text,
        "measurement": _float_or_none(measurement),
        "properties": {
            **properties,
            "readable_properties": probe["readable_properties"],
            "failed_properties": probe["failed_properties"],
        },
        "xdata": _xdata_from_inspection(inspection),
        "extension_dictionary": _extension_dictionary_from_inspection(inspection),
        "diagnostic": {
            "read_text_success": text is not None,
            "read_measurement_success": measurement is not None,
            "warnings": warnings,
        },
    }


def read_semantic_entity(entity: Any) -> dict[str, Any]:
    object_name = str(_safe_get(entity, "ObjectName") or _safe_get(entity, "EntityName") or "")
    lowered = object_name.lower()
    if lowered == "tdbpipe":
        return read_tdb_pipe(entity)
    if lowered == "tdbpipevalve":
        return read_tdb_pipe_valve(entity)
    if lowered == "tdbpipefitting":
        return read_tdb_pipe_fitting(entity)
    if lowered == "tdbdimension2":
        return read_tdb_dimension(entity)
    if "mtext" in lowered:
        return _read_text(entity, "mtext")
    if "text" in lowered:
        return _read_text(entity, "text")
    if "blockreference" in lowered:
        return _read_block(entity)
    return _read_unknown_tianzheng(entity)


def read_selected_tianzheng_semantic_model(document: Any) -> dict[str, Any]:
    validation = validate_autocad_document(document)
    if not validation["success"]:
        raise RuntimeError(
            "Invalid AutoCAD Document: object has no SelectionSets / Utility / ModelSpace. "
            f"errors={validation['errors']}"
        )
    print("请在 AutoCAD 中框选需要语义读取的水泵房区域对象，然后按 Enter。")
    delete_selection_set_if_exists(document, TEMP_SELECTION_SET_NAME)
    selection_set = None
    try:
        selection_set = document.SelectionSets.Add(TEMP_SELECTION_SET_NAME)
        selection_set.SelectOnScreen()
        count = int(_safe_get(selection_set, "Count") or 0)
        if count < 1:
            raise NoSelectionError()
        entities = [read_semantic_entity(selection_set_item(selection_set, index)) for index in range(count)]
        return {
            "source": "tianzheng_semantic_reader",
            "active_document": _safe_get(document, "Name"),
            "selection_count": len(entities),
            "entities": entities,
            "summary": summarize_semantic_entities(entities),
        }
    finally:
        safe_delete_selection_set(document, TEMP_SELECTION_SET_NAME, selection_set)


def summarize_semantic_entities(entities: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(entities),
        "pipe": 0,
        "valve": 0,
        "fitting": 0,
        "dimension": 0,
        "text": 0,
        "block": 0,
        "unknown_tianzheng": 0,
    }
    for entity in entities:
        semantic_type = str(entity.get("semantic_type") or "unknown_tianzheng")
        if semantic_type in summary:
            summary[semantic_type] += 1
        else:
            summary["unknown_tianzheng"] += 1
    return summary


def semantic_model_diagnostics(model: dict[str, Any]) -> dict[str, Any]:
    entities = model.get("entities", [])
    object_names = Counter(str(entity.get("object_name") or "") for entity in entities)
    semantic_types = Counter(str(entity.get("semantic_type") or "") for entity in entities)
    system_types = Counter(str(entity.get("system_type") or "unknown") for entity in entities)
    return {
        "active_document": model.get("active_document"),
        "tianzheng_detected": True,
        "selection_count": model.get("selection_count", 0),
        "semantic_summary": model.get("summary", {}),
        "pipe_count": model.get("summary", {}).get("pipe", 0),
        "valve_count": model.get("summary", {}).get("valve", 0),
        "dimension_count": model.get("summary", {}).get("dimension", 0),
        "text_count": model.get("summary", {}).get("text", 0),
        "block_count": model.get("summary", {}).get("block", 0),
        "unknown_tianzheng_count": model.get("summary", {}).get("unknown_tianzheng", 0),
        "object_name_top_20": object_names.most_common(20),
        "semantic_type_counts": dict(semantic_types),
        "system_type_counts": dict(system_types),
        "first_20_entities": [
            {
                "handle": entity.get("handle"),
                "semantic_type": entity.get("semantic_type"),
                "object_name": entity.get("object_name"),
                "layer": entity.get("layer"),
                "system_type": entity.get("system_type"),
                "diameter": entity.get("diameter"),
                "display_radius": entity.get("properties", {}).get("display_radius"),
                "length": entity.get("properties", {}).get("Length"),
                "elevation": entity.get("elevation"),
                "bounding_box": entity.get("bounding_box"),
                "inferred_geometry": entity.get("inferred_geometry"),
                "properties": entity.get("properties", {}),
                "readable_properties": _readable_properties(entity),
                "failed_properties": _failed_properties(entity),
                "xdata": entity.get("xdata"),
                "extension_dictionary_keys": entity.get("extension_dictionary", {}).get("keys", []),
                "warnings": entity.get("diagnostic", {}).get("warnings", []),
            }
            for entity in entities[:20]
        ],
    }


def _readable_properties(entity: dict[str, Any]) -> list[str]:
    properties = entity.get("properties", {})
    if isinstance(properties, dict):
        return list(properties.get("readable_properties", []))
    return []


def _failed_properties(entity: dict[str, Any]) -> dict[str, str]:
    properties = entity.get("properties", {})
    if isinstance(properties, dict):
        failed = properties.get("failed_properties", {})
        return failed if isinstance(failed, dict) else {}
    return {}


def probe_entity_properties(entity: Any, property_names: tuple[str, ...] | list[str]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    readable: list[str] = []
    failed: dict[str, str] = {}
    for name in property_names:
        try:
            value = getattr(entity, name)
            properties[name] = _json_value(value)
            readable.append(name)
        except Exception as exc:
            failed[name] = str(exc)
    return {
        "properties": properties,
        "readable_properties": readable,
        "failed_properties": failed,
    }


def infer_system_type(layer: Any) -> str:
    text = str(layer or "")
    if "消防" in text:
        return "消防"
    if "喷淋" in text:
        return "喷淋"
    if "给水" in text:
        return "给水"
    if "排水" in text:
        return "排水"
    return "unknown"


def _system_type_conflicts(sys_type_raw: Any, layer_system_type: str) -> bool:
    if sys_type_raw in (None, "") or layer_system_type == "unknown":
        return False
    raw_text = str(sys_type_raw)
    if layer_system_type in raw_text:
        return False
    known_types = ("消防", "喷淋", "给水", "排水")
    return any(system_type in raw_text for system_type in known_types)


def infer_valve_type(layer: Any) -> str:
    text = str(layer or "")
    system_type = infer_system_type(text)
    if text.upper().startswith("EVALVE") and system_type == "喷淋":
        return "喷淋电动阀"
    if text.upper().startswith("EVALVE"):
        return "电动阀"
    if text.upper().startswith("VALVE") and system_type == "消防":
        return "消防阀门"
    return "unknown"


def _infer_fitting_type(properties: dict[str, Any]) -> str:
    value = properties.get("FittingType") or properties.get("Type")
    return str(value) if value not in (None, "") else "unknown"


def _pipe_geometry_from_bounding_box(bbox: Any) -> dict[str, Any]:
    if not bbox or len(bbox) < 6:
        return _unknown_pipe_geometry()
    min_x, min_y, min_z, max_x, max_y, max_z = [float(value) for value in bbox[:6]]
    dx = max_x - min_x
    dy = max_y - min_y
    length = math.sqrt(dx * dx + dy * dy)
    if _close(dx, 0.0) and _close(dy, 0.0):
        orientation = "point_like"
    elif _close(dx, 0.0):
        orientation = "vertical"
    elif _close(dy, 0.0):
        orientation = "horizontal"
    else:
        orientation = "diagonal"
    return {
        "orientation": orientation,
        "start_point": [min_x, min_y, min_z],
        "end_point": [max_x, max_y, max_z],
        "length": length,
        "source": "bounding_box_inference",
    }


def _unknown_pipe_geometry() -> dict[str, Any]:
    return {
        "orientation": "unknown",
        "start_point": None,
        "end_point": None,
        "length": 0.0,
        "source": "bounding_box_inference",
    }


def _valve_geometry_from_bounding_box(bbox: Any) -> dict[str, Any]:
    if not bbox or len(bbox) < 6:
        return {"center": None, "width": 0.0, "height": 0.0, "source": "bounding_box_inference"}
    min_x, min_y, min_z, max_x, max_y, max_z = [float(value) for value in bbox[:6]]
    return {
        "center": [
            (min_x + max_x) / 2.0,
            (min_y + max_y) / 2.0,
            (min_z + max_z) / 2.0,
        ],
        "width": max_x - min_x,
        "height": max_y - min_y,
        "source": "bounding_box_inference",
    }


def _read_text(entity: Any, semantic_type: str) -> dict[str, Any]:
    inspection = inspect_entity(entity)
    probe = probe_entity_properties(entity, PROPERTY_PROBE_NAMES)
    text = _first_present(probe["properties"], ("TextString", "TextOverride", "Contents"))
    return {
        "semantic_type": semantic_type,
        "object_name": inspection.get("object_name"),
        "handle": inspection.get("handle"),
        "layer": inspection.get("layer"),
        "bounding_box": inspection.get("bounding_box"),
        "text": text,
        "properties": {
            **probe["properties"],
            "readable_properties": probe["readable_properties"],
            "failed_properties": probe["failed_properties"],
        },
        "xdata": _xdata_from_inspection(inspection),
        "extension_dictionary": _extension_dictionary_from_inspection(inspection),
        "diagnostic": {"warnings": _warnings(inspection)},
    }


def _read_block(entity: Any) -> dict[str, Any]:
    inspection = inspect_entity(entity)
    probe = probe_entity_properties(entity, PROPERTY_PROBE_NAMES)
    return {
        "semantic_type": "block",
        "object_name": inspection.get("object_name"),
        "handle": inspection.get("handle"),
        "layer": inspection.get("layer"),
        "bounding_box": inspection.get("bounding_box"),
        "name": probe["properties"].get("Name"),
        "effective_name": probe["properties"].get("EffectiveName"),
        "properties": {
            **probe["properties"],
            "readable_properties": probe["readable_properties"],
            "failed_properties": probe["failed_properties"],
        },
        "xdata": _xdata_from_inspection(inspection),
        "extension_dictionary": _extension_dictionary_from_inspection(inspection),
        "diagnostic": {"warnings": _warnings(inspection)},
    }


def _read_unknown_tianzheng(entity: Any) -> dict[str, Any]:
    inspection = inspect_entity(entity)
    probe = probe_entity_properties(entity, PROPERTY_PROBE_NAMES)
    return {
        "semantic_type": "unknown_tianzheng",
        "object_name": inspection.get("object_name"),
        "handle": inspection.get("handle"),
        "layer": inspection.get("layer"),
        "bounding_box": inspection.get("bounding_box"),
        "properties": {
            **probe["properties"],
            "readable_properties": probe["readable_properties"],
            "failed_properties": probe["failed_properties"],
        },
        "xdata": _xdata_from_inspection(inspection),
        "extension_dictionary": _extension_dictionary_from_inspection(inspection),
        "diagnostic": {"warnings": _warnings(inspection)},
    }


def _xdata_from_inspection(inspection: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": inspection.get("xdata_available", False),
        **(inspection.get("xdata") or {}),
        "error": inspection.get("xdata_error"),
    }


def _extension_dictionary_from_inspection(inspection: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": inspection.get("extension_dictionary_available", False),
        "keys": inspection.get("extension_dictionary_keys", []),
        "error": inspection.get("extension_dictionary_error"),
    }


def _warnings(inspection: dict[str, Any]) -> list[str]:
    warnings = list(inspection.get("diagnostic", {}).get("errors", []))
    if inspection.get("xdata_error"):
        warnings.append(f"XData 读取失败: {inspection['xdata_error']}")
    if inspection.get("extension_dictionary_error"):
        warnings.append(f"ExtensionDictionary 读取失败: {inspection['extension_dictionary_error']}")
    return warnings


def _first_present(properties: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = properties.get(name)
        if value not in (None, ""):
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _close(left: float, right: float) -> bool:
    return abs(left - right) < 1e-9


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if hasattr(value, "value"):
        return _json_value(value.value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    try:
        return list(value)
    except Exception:
        return str(value)
