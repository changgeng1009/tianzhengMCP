from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


TIANZHENG_NAME_KEYWORDS = ("tch", "twt", "tianzheng", "tangent", "tarch", "天正")
PLUMBING_LAYER_KEYWORDS = (
    "给水",
    "排水",
    "给排水",
    "管",
    "阀",
    "泵",
    "地漏",
    "pipe",
    "drain",
    "water",
    "valve",
    "pump",
    "twt",
    "tch",
)

AVAILABLE_PROPERTY_CANDIDATES = (
    "Handle",
    "ObjectName",
    "EntityName",
    "Layer",
    "Color",
    "Linetype",
    "Visible",
    "StartPoint",
    "EndPoint",
    "Coordinates",
    "InsertionPoint",
    "TextString",
    "Contents",
    "Name",
    "EffectiveName",
    "Radius",
    "Center",
    "Rotation",
    "Measurement",
    "TextOverride",
)

GEOMETRY_PROPERTY_CANDIDATES = (
    "StartPoint",
    "EndPoint",
    "Coordinates",
    "InsertionPoint",
    "Center",
)


def inspect_entity(entity: Any) -> dict[str, Any]:
    errors: list[str] = []
    handle = _safe_get(entity, "Handle", errors)
    object_name = _safe_get(entity, "ObjectName", errors)
    entity_name = _safe_get(entity, "EntityName", errors)
    layer = _safe_get(entity, "Layer", errors)
    color = _safe_get(entity, "Color", errors)
    linetype = _safe_get(entity, "Linetype", errors)

    bounding_box, bbox_success = _read_bounding_box(entity, errors)
    geometry, geometry_success = _read_geometry(entity, errors)
    available_properties = _available_properties(entity)
    xdata_available, xdata, xdata_error = _read_xdata(entity)
    extension_available, extension_keys, extension_error = _read_extension_dictionary(entity)

    proxy = _is_proxy_name(object_name) or _is_proxy_name(entity_name)
    tianzheng_like = _is_tianzheng_like(
        object_name=object_name,
        entity_name=entity_name,
        layer=layer,
        is_proxy=proxy,
        xdata_available=xdata_available,
        extension_dictionary_available=extension_available,
    )

    if xdata_error:
        errors.append(f"GetXData: {xdata_error}")
    if extension_error:
        errors.append(f"GetExtensionDictionary: {extension_error}")

    return {
        "handle": _json_value(handle),
        "object_name": _json_value(object_name),
        "entity_name": _json_value(entity_name),
        "layer": _json_value(layer),
        "color": _json_value(color),
        "linetype": _json_value(linetype),
        "bounding_box": bounding_box,
        "geometry": geometry,
        "available_properties": available_properties,
        "xdata_available": xdata_available,
        "xdata": xdata,
        "xdata_error": xdata_error,
        "extension_dictionary_available": extension_available,
        "extension_dictionary_keys": extension_keys,
        "extension_dictionary_error": extension_error,
        "diagnostic": {
            "is_proxy": proxy,
            "is_tianzheng_like": tianzheng_like,
            "read_geometry_success": geometry_success,
            "read_bounding_box_success": bbox_success,
            "errors": errors,
        },
    }


def summarize_inspection(result: dict[str, Any], index: int, active_document: str | None) -> dict[str, Any]:
    return {
        "index": index,
        "active_document": active_document,
        "picked_entity": {
            "handle": result.get("handle"),
            "object_name": result.get("object_name"),
            "entity_name": result.get("entity_name"),
            "layer": result.get("layer"),
            "bounding_box": result.get("bounding_box"),
        },
        "diagnostic": {
            "is_proxy": result.get("diagnostic", {}).get("is_proxy", False),
            "is_tianzheng_like": result.get("diagnostic", {}).get("is_tianzheng_like", False),
            "xdata_available": result.get("xdata_available", False),
            "extension_dictionary_available": result.get(
                "extension_dictionary_available", False
            ),
            "errors": result.get("diagnostic", {}).get("errors", []),
        },
        "full_result": result,
    }


def _safe_get(entity: Any, attr: str, errors: list[str]) -> Any:
    try:
        return getattr(entity, attr)
    except Exception as exc:
        logger.info("读取对象属性失败: %s", attr, exc_info=True)
        errors.append(f"{attr}: {exc}")
        return None


def _available_properties(entity: Any) -> list[str]:
    available: list[str] = []
    for attr in AVAILABLE_PROPERTY_CANDIDATES:
        try:
            getattr(entity, attr)
            available.append(attr)
        except Exception:
            continue
    return available


def _read_bounding_box(entity: Any, errors: list[str]) -> tuple[list[float] | None, bool]:
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
            ], True
        errors.append(f"GetBoundingBox: unexpected result {type(raw).__name__}")
    except Exception as exc:
        logger.info("读取对象 BoundingBox 失败", exc_info=True)
        errors.append(f"GetBoundingBox: {exc}")
    return None, False


def _read_geometry(entity: Any, errors: list[str]) -> tuple[dict[str, Any], bool]:
    geometry: dict[str, Any] = {"coordinate_system": "cad_world", "properties": {}}
    success = False
    for attr in GEOMETRY_PROPERTY_CANDIDATES:
        try:
            value = getattr(entity, attr)
        except Exception:
            continue
        geometry["properties"][attr] = _json_value(value)
        success = True
    if not success:
        errors.append("geometry: no readable geometry properties")
    return geometry, success


def _read_xdata(entity: Any) -> tuple[bool, dict[str, Any], str | None]:
    if not hasattr(entity, "GetXData"):
        return False, {}, None
    last_error: Exception | None = None
    for app_name in ("", None):
        try:
            raw = entity.GetXData(app_name)
            parsed = _parse_xdata(raw)
            return True, parsed, None
        except Exception as exc:
            last_error = exc
    return False, {}, str(last_error) if last_error else "GetXData failed"


def _parse_xdata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, tuple | list) and len(raw) == 2:
        return {"types": _json_value(raw[0]), "values": _json_value(raw[1])}
    return {"raw": _json_value(raw)}


def _read_extension_dictionary(entity: Any) -> tuple[bool, list[str], str | None]:
    if not hasattr(entity, "GetExtensionDictionary"):
        return False, [], None
    try:
        dictionary = entity.GetExtensionDictionary()
        keys = _dictionary_keys(dictionary)
        return True, keys, None
    except Exception as exc:
        logger.info("读取对象 ExtensionDictionary 失败", exc_info=True)
        return False, [], str(exc)


def _dictionary_keys(dictionary: Any) -> list[str]:
    keys: list[str] = []
    try:
        for item in dictionary:
            name = _get_optional(item, "Name")
            keys.append(str(name if name is not None else item))
        return keys
    except Exception:
        pass

    count = int(_get_optional(dictionary, "Count") or 0)
    for index in range(count):
        item = None
        try:
            item = dictionary.Item(index)
        except Exception:
            try:
                item = dictionary.Item(index + 1)
            except Exception:
                continue
        name = _get_optional(item, "Name")
        keys.append(str(name if name is not None else item))
    return keys


def _get_optional(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None


def _is_proxy_name(name: Any) -> bool:
    return "proxy" in str(name or "").lower()


def _is_tianzheng_like(
    *,
    object_name: Any,
    entity_name: Any,
    layer: Any,
    is_proxy: bool,
    xdata_available: bool,
    extension_dictionary_available: bool,
) -> bool:
    object_text = str(object_name or "").lower()
    entity_text = str(entity_name or "").lower()
    layer_text = str(layer or "").lower()
    name_signal = any(keyword in object_text for keyword in TIANZHENG_NAME_KEYWORDS) or any(
        keyword in entity_text for keyword in TIANZHENG_NAME_KEYWORDS
    )
    layer_signal = any(keyword.lower() in layer_text for keyword in PLUMBING_LAYER_KEYWORDS)
    metadata_signal = xdata_available or extension_dictionary_available
    return bool(name_signal or layer_signal or is_proxy or metadata_signal)


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
