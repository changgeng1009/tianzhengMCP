from __future__ import annotations

import json
import logging
import re
from typing import Any


logger = logging.getLogger(__name__)


PIPE_PROPERTY_NAMES = (
    "Radius",
    "DNDiameter",
    "Diameter",
    "PipeDiameter",
    "PipeDN",
    "DN",
    "NominalDiameter",
    "DiameterValue",
    "PipeSize",
    "Size",
    "Caliber",
    "Calibre",
    "Dn",
    "dn",
    "管径",
    "管径值",
    "标注",
    "Label",
    "PipeLabel",
    "PipeText",
    "DiameterLabel",
    "DnText",
    "DNText",
    "Annotation",
    "Text",
    "TextString",
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
    "PipeMaterial",
    "SystemType",
    "PipeType",
    "Category",
    "Type",
    "Name",
    "Description",
    "Note",
    "Elevation",
    "StartPoint",
    "EndPoint",
    "Length",
    "Angle",
    "Direction",
)

XDATA_APP_NAMES = (
    "",
    None,
    "TWT",
    "TCH",
    "TANGENT",
    "TG_PIPE",
    "TG_PIPELABEL",
    "TG_PIPELABEL_THICK_SHOW",
    "TDbPipe",
    "TPIPE",
    "PIPE",
    "TIANZHENG",
)

EXTENSION_PROPERTY_NAMES = (
    "Name",
    "ObjectName",
    "Handle",
    "TextString",
    "Contents",
    "Value",
    "Label",
    "PipeDN",
    "DN",
    "Diameter",
    "Description",
)

DIR_SUSPICIOUS_KEYWORDS = (
    "pipe",
    "dn",
    "diameter",
    "label",
    "text",
    "material",
    "type",
    "size",
    "caliber",
    "calibre",
    "管径",
    "标注",
)

DIAMETER_PATTERN = re.compile(r"(?i)(DN\s*\d+|De\s*\d+|D\s*\d+|Φ\s*\d+)")


def probe_tdbpipe(entity: Any) -> dict[str, Any]:
    object_name = _safe_get(entity, "ObjectName")
    if str(object_name or "") != "TDbPipe":
        return {
            "success": False,
            "error_code": "NOT_TDBPIPE",
            "message": "Selected object is not TDbPipe.",
            "handle": _json_value(_safe_get(entity, "Handle")),
            "object_name": _json_value(object_name),
            "layer": _json_value(_safe_get(entity, "Layer")),
        }

    warnings: list[str] = []
    candidates: list[dict[str, Any]] = []
    bounding_box = _read_bounding_box(entity, warnings)
    property_probe = _probe_properties(entity, PIPE_PROPERTY_NAMES, candidates)
    diameter_result = dndiameter_result(
        property_probe["known_properties"].get("DNDiameter"),
        "DNDiameter" not in property_probe["failed_properties"],
    )
    if diameter_result["normalized_diameter"] is not None:
        _append_diameter_candidate(
            candidates,
            diameter_result["normalized_diameter"],
            str(diameter_result["dn_diameter_raw"]),
            "property",
            "DNDiameter",
            0.95,
        )
    xdata = _probe_xdata(entity, candidates, warnings)
    extension_dictionary = _probe_extension_dictionary(entity, candidates, warnings)
    typeinfo = _probe_typeinfo(entity, warnings)
    dir_probe = _probe_dir(entity)

    has_dn = any(str(candidate.get("diameter", "")).upper().startswith("DN") for candidate in candidates)
    has_label = bool(candidates) or any(
        name in property_probe["known_properties"]
        for name in ("Label", "PipeLabel", "PipeText", "DiameterLabel", "Text", "TextString")
    )

    return {
        "success": True,
        "handle": _json_value(_safe_get(entity, "Handle")),
        "object_name": "TDbPipe",
        "entity_name": _json_value(_safe_get(entity, "EntityName")),
        "layer": _json_value(_safe_get(entity, "Layer")),
        "bounding_box": bounding_box,
        "known_properties": property_probe["known_properties"],
        "candidate_pipe_properties": property_probe["candidate_pipe_properties"],
        "failed_properties": property_probe["failed_properties"],
        **diameter_result,
        "xdata": xdata,
        "extension_dictionary": extension_dictionary,
        "typeinfo": typeinfo,
        "dir_probe": dir_probe,
        "diameter_candidates": candidates,
        "diagnostic": {
            "has_dn": has_dn,
            "has_label": has_label,
            "warnings": warnings,
        },
    }


def _probe_properties(
    entity: Any,
    property_names: tuple[str, ...],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    known: dict[str, Any] = {}
    failed: dict[str, str] = {}
    candidate_properties: dict[str, Any] = {}
    for name in property_names:
        try:
            value = getattr(entity, name)
            json_value = _json_value(value)
            known[name] = json_value
            if _is_candidate_property_name(name):
                candidate_properties[name] = json_value
            _collect_diameter_candidates(candidates, json_value, source="property", field=name)
        except Exception as exc:
            failed[name] = str(exc)
    return {
        "known_properties": known,
        "candidate_pipe_properties": candidate_properties,
        "failed_properties": failed,
    }


def _probe_xdata(
    entity: Any,
    candidates: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    failed: dict[str, str] = {}
    get_xdata = _safe_get(entity, "GetXData")
    if get_xdata is None:
        warnings.append("GetXData is not available")
        return {"available": False, "groups": groups, "failed": failed}

    for app_name in XDATA_APP_NAMES:
        key = "<None>" if app_name is None else str(app_name)
        try:
            raw = entity.GetXData(app_name)
            parsed = _parse_xdata(raw)
            groups[key] = parsed
            _collect_diameter_candidates(candidates, parsed, source="xdata", field=key)
        except Exception as exc:
            failed[key] = str(exc)
    return {"available": bool(groups), "groups": groups, "failed": failed}


def _probe_extension_dictionary(
    entity: Any,
    candidates: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    get_dictionary = _safe_get(entity, "GetExtensionDictionary")
    if get_dictionary is None:
        warnings.append("GetExtensionDictionary is not available")
        return {"available": False, "keys": [], "items": [], "error": None}
    try:
        dictionary = entity.GetExtensionDictionary()
    except Exception as exc:
        warnings.append(f"GetExtensionDictionary failed: {exc}")
        return {"available": False, "keys": [], "items": [], "error": str(exc)}

    items: list[dict[str, Any]] = []
    keys: list[str] = []
    for item in _iter_collection(dictionary):
        name = _safe_get(item, "Name")
        key = str(name if name is not None else len(items))
        keys.append(key)
        properties = _probe_simple_properties(item, EXTENSION_PROPERTY_NAMES)
        item_info = {
            "key": key,
            "object_name": _json_value(_safe_get(item, "ObjectName")),
            "handle": _json_value(_safe_get(item, "Handle")),
            "properties": properties,
        }
        items.append(item_info)
        _collect_diameter_candidates(candidates, item_info, source="extension_dictionary", field=key)
    return {"available": True, "keys": keys, "items": items, "error": None}


def _probe_typeinfo(entity: Any, warnings: list[str]) -> dict[str, Any]:
    oleobj = _safe_get(entity, "_oleobj_")
    if oleobj is None:
        warnings.append("COM TypeInfo is not available")
        return {"available": False, "error": "entity._oleobj_ is not available"}
    try:
        typeinfo = oleobj.GetTypeInfo()
    except Exception as exc:
        warnings.append(f"GetTypeInfo failed: {exc}")
        return {"available": False, "error": str(exc)}

    result: dict[str, Any] = {"available": True, "type_attr": None, "names": [], "errors": []}
    try:
        result["type_attr"] = _json_value(typeinfo.GetTypeAttr())
    except Exception as exc:
        result["errors"].append(f"GetTypeAttr: {exc}")
    for memid in (0, 1, 2, 3, 4, 5):
        try:
            names = _json_value(typeinfo.GetNames(memid))
            if isinstance(names, list):
                for name in names:
                    if name not in result["names"]:
                        result["names"].append(name)
            elif names not in result["names"]:
                result["names"].append(names)
        except Exception as exc:
            result["errors"].append(f"GetNames({memid}): {exc}")
    return result


def _probe_dir(entity: Any) -> dict[str, Any]:
    try:
        names = [str(name) for name in dir(entity)]
    except Exception as exc:
        return {"available": False, "error": str(exc), "suspicious_names": []}
    suspicious = [
        name
        for name in names
        if any(keyword.lower() in name.lower() for keyword in DIR_SUSPICIOUS_KEYWORDS)
    ]
    return {
        "available": True,
        "count": len(names),
        "suspicious_names": sorted(set(suspicious)),
    }


def _read_bounding_box(entity: Any, warnings: list[str]) -> list[float] | None:
    try:
        raw = entity.GetBoundingBox()
        if isinstance(raw, tuple | list) and len(raw) == 2:
            min_point = _point(raw[0])
            max_point = _point(raw[1])
            return [
                min(min_point[0], max_point[0]),
                min(min_point[1], max_point[1]),
                min(min_point[2], max_point[2]),
                max(min_point[0], max_point[0]),
                max(min_point[1], max_point[1]),
                max(min_point[2], max_point[2]),
            ]
        warnings.append(f"GetBoundingBox returned unexpected value: {type(raw).__name__}")
    except Exception as exc:
        warnings.append(f"GetBoundingBox failed: {exc}")
    return None


def _probe_simple_properties(obj: Any, names: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in names:
        try:
            result[name] = _json_value(getattr(obj, name))
        except Exception:
            continue
    return result


def _collect_diameter_candidates(
    candidates: list[dict[str, Any]],
    value: Any,
    *,
    source: str,
    field: str,
) -> None:
    text = _stringify(value)
    for match in DIAMETER_PATTERN.findall(text):
        diameter = _normalize_diameter(match)
        _append_diameter_candidate(candidates, diameter, match, source, field, 0.85)


def _append_diameter_candidate(
    candidates: list[dict[str, Any]],
    diameter: str,
    raw_text: str,
    source: str,
    field: str,
    confidence: float,
) -> None:
    key = (diameter, source, field)
    if any((item["diameter"], item["source"], item["field"]) == key for item in candidates):
        return
    candidates.append(
        {
            "diameter": diameter,
            "raw_text": raw_text,
            "source": source,
            "field": field,
            "confidence": confidence,
            "status": "candidate",
        }
    )


def dndiameter_result(raw_value: Any, read_success: bool) -> dict[str, Any]:
    if not read_success:
        return {
            "dn_diameter_raw": None,
            "normalized_diameter": None,
            "diameter_source": None,
            "diameter_confidence": 0.0,
        }
    normalized = normalize_dndiameter(raw_value)
    return {
        "dn_diameter_raw": _json_value(raw_value),
        "normalized_diameter": normalized,
        "diameter_source": "TDbPipe.DNDiameter" if normalized is not None else None,
        "diameter_confidence": 0.95 if normalized is not None else 0.0,
    }


def normalize_dndiameter(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        number = int(value) if float(value).is_integer() else value
        return f"DN{number}"
    text = re.sub(r"\s+", "", str(value))
    if not text:
        return None
    dn_match = re.match(r"(?i)^DN(\d+(?:\.\d+)?)$", text)
    if dn_match:
        return f"DN{dn_match.group(1)}"
    number_match = re.match(r"^\d+(?:\.\d+)?$", text)
    if number_match:
        return f"DN{text}"
    return None


def _normalize_diameter(value: str) -> str:
    text = re.sub(r"\s+", "", str(value))
    match = re.match(r"(?i)^(dn|de|d)(\d+)$", text)
    if match:
        prefix = match.group(1).lower()
        number = match.group(2)
        if prefix == "dn":
            return f"DN{number}"
        if prefix == "de":
            return f"De{number}"
        return f"D{number}"
    phi = re.match(r"^Φ(\d+)$", text)
    if phi:
        return f"Φ{phi.group(1)}"
    return text


def _parse_xdata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, tuple | list) and len(raw) == 2:
        return {"types": _json_value(raw[0]), "values": _json_value(raw[1])}
    return {"raw": _json_value(raw)}


def _iter_collection(collection: Any) -> list[Any]:
    try:
        return list(collection)
    except Exception:
        pass
    count = int(_safe_get(collection, "Count") or 0)
    zero_based = _items_by_index_base(collection, count, 0)
    if len(zero_based) == count:
        return zero_based
    one_based = _items_by_index_base(collection, count, 1)
    if one_based:
        return one_based
    return []


def _items_by_index_base(collection: Any, count: int, index_base: int) -> list[Any]:
    result: list[Any] = []
    for offset in range(count):
        try:
            result.append(collection.Item(offset + index_base))
        except Exception:
            return result
    return result


def _is_candidate_property_name(name: str) -> bool:
    lowered = name.lower()
    return any(keyword.lower() in lowered for keyword in DIR_SUSPICIOUS_KEYWORDS)


def _point(value: Any) -> list[float]:
    values = _to_list(value)
    if len(values) < 2:
        raise ValueError("point requires at least x and y")
    return [
        float(values[0]),
        float(values[1]),
        float(values[2]) if len(values) > 2 else 0.0,
    ]


def _to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "value"):
        return list(value.value)
    return list(value)


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
        return [_json_value(item) for item in value]
    except Exception:
        return str(value)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(_json_value(value), ensure_ascii=False)
    except Exception:
        return str(value)
