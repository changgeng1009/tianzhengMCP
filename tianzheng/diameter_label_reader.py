from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


TEXT_PROPERTY_NAMES = (
    "TextString",
    "Contents",
    "Text",
    "MText",
    "TextOverride",
    "DimensionText",
    "PrimaryText",
    "Measurement",
    "Label",
    "Name",
    "Value",
    "Position",
    "InsertionPoint",
)

DEFAULT_PATTERNS = (r"DN\s*\d+", r"De\s*\d+", r"D\s*\d+", r"Φ\s*\d+")


def extract_pipe_diameter_labels(entities: list[Any]) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    patterns = _load_patterns()
    for entity in entities:
        probe = probe_text_properties(entity)
        source = _source_object(entity)
        bbox = _entity_value(entity, "bounding_box") or _entity_value(entity, "BoundingBox")
        position = _position_from_entity(entity, probe)
        matches = _find_matches(probe["readable_text_properties"], patterns)
        if matches:
            for raw_text in matches:
                normalized = normalize_pipe_diameter(raw_text)
                labels.append(
                    {
                        "label_id": f"label_{len(labels) + 1:03d}",
                        "raw_text": raw_text,
                        "normalized_diameter": normalized,
                        "source_object": source,
                        "position": position,
                        "bounding_box": bbox,
                        "confidence": 1.0,
                        "readable_text_properties": probe["readable_text_properties"],
                        "failed_text_properties": probe["failed_text_properties"],
                    }
                )
        elif _is_possible_diameter_annotation(entity):
            labels.append(
                {
                    "label_id": f"label_{len(labels) + 1:03d}",
                    "raw_text": None,
                    "normalized_diameter": None,
                    "source_object": source,
                    "position": position,
                    "bounding_box": bbox,
                    "confidence": 0.0,
                    "status": "need_user_confirmation",
                    "reason": "No readable text property found",
                    "readable_text_properties": probe["readable_text_properties"],
                    "failed_text_properties": probe["failed_text_properties"],
                }
            )
    return labels


def normalize_pipe_diameter(value: str) -> str:
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


def probe_text_properties(entity: Any, property_names: tuple[str, ...] | list[str] = TEXT_PROPERTY_NAMES) -> dict[str, Any]:
    readable: dict[str, Any] = {}
    failed: dict[str, str] = {}
    for name in property_names:
        found, value, error = _try_read_property(entity, name)
        if found:
            readable[name] = _json_value(value)
        elif error:
            failed[name] = error
    return {
        "readable_text_properties": readable,
        "failed_text_properties": failed,
    }


def _find_matches(readable_properties: dict[str, Any], patterns: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for value in readable_properties.values():
        if isinstance(value, list | dict):
            candidate = json.dumps(value, ensure_ascii=False)
        else:
            candidate = str(value)
        for pattern in compiled:
            for match in pattern.findall(candidate):
                text = match if isinstance(match, str) else "".join(match)
                if text and text not in matches:
                    matches.append(text)
    return matches


def _load_patterns() -> tuple[str, ...]:
    path = Path(__file__).resolve().parents[1] / "config" / "pipe_diameter_patterns.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        patterns = payload.get("patterns") or []
        return tuple(str(pattern) for pattern in patterns) or DEFAULT_PATTERNS
    except Exception:
        return DEFAULT_PATTERNS


def _source_object(entity: Any) -> dict[str, Any]:
    return {
        "handle": _entity_value(entity, "handle") or _entity_value(entity, "Handle"),
        "object_name": _entity_value(entity, "object_name") or _entity_value(entity, "ObjectName"),
        "layer": _entity_value(entity, "layer") or _entity_value(entity, "Layer"),
    }


def _position_from_entity(entity: Any, probe: dict[str, Any]) -> list[float] | None:
    readable = probe.get("readable_text_properties", {})
    for key in ("Position", "InsertionPoint"):
        value = readable.get(key)
        point = _point_or_none(value)
        if point is not None:
            return point
    bbox = _entity_value(entity, "bounding_box") or _entity_value(entity, "BoundingBox")
    return _bbox_center(bbox)


def _is_possible_diameter_annotation(entity: Any) -> bool:
    semantic_type = str(_entity_value(entity, "semantic_type") or "").lower()
    object_name = str(_entity_value(entity, "object_name") or _entity_value(entity, "ObjectName") or "").lower()
    return semantic_type == "dimension" or object_name in {"tdbdimension2"}


def _try_read_property(entity: Any, name: str) -> tuple[bool, Any, str | None]:
    if isinstance(entity, dict):
        if name in entity:
            return True, entity[name], None
        properties = entity.get("properties")
        if isinstance(properties, dict) and name in properties:
            return True, properties[name], None
        if name == "TextString" and entity.get("text") is not None:
            return True, entity.get("text"), None
        return False, None, None
    try:
        return True, getattr(entity, name), None
    except Exception as exc:
        return False, None, str(exc)


def _entity_value(entity: Any, name: str) -> Any:
    if isinstance(entity, dict):
        return entity.get(name)
    try:
        return getattr(entity, name)
    except Exception:
        return None


def _bbox_center(bbox: Any) -> list[float] | None:
    if not bbox or len(bbox) < 6:
        return None
    values = [float(value) for value in bbox[:6]]
    return [
        (values[0] + values[3]) / 2.0,
        (values[1] + values[4]) / 2.0,
        (values[2] + values[5]) / 2.0,
    ]


def _point_or_none(value: Any) -> list[float] | None:
    if value is None:
        return None
    try:
        values = list(value)
    except Exception:
        return None
    if len(values) < 2:
        return None
    return [
        float(values[0]),
        float(values[1]),
        float(values[2]) if len(values) > 2 else 0.0,
    ]


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
