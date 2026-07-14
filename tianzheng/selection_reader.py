from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Callable

from tianzheng.object_inspector import inspect_entity
from tianzheng.selection_utils import (
    NoSelectionError,
    delete_selection_set_if_exists,
    safe_delete_selection_set,
    selection_set_item,
)


logger = logging.getLogger(__name__)

TEMP_SELECTION_SET_NAME = "__TianzhengSelectionReaderTemp__"


Inspector = Callable[[Any], dict[str, Any]]


def read_selected_entities(
    document: Any,
    *,
    inspector: Inspector = inspect_entity,
    prompt: str | None = "请在 AutoCAD 中框选需要识别的区域对象，然后按 Enter。",
) -> dict[str, Any]:
    if prompt:
        print(prompt)

    delete_selection_set_if_exists(document, TEMP_SELECTION_SET_NAME)
    selection_set = None
    try:
        selection_set = document.SelectionSets.Add(TEMP_SELECTION_SET_NAME)
        selection_set.SelectOnScreen()

        count = int(_safe_get(selection_set, "Count") or 0)
        if count < 1:
            raise NoSelectionError()

        entities = [
            _selected_entity_to_model(inspector(selection_set_item(selection_set, index)))
            for index in range(count)
        ]
        return {
            "source": "selected_tianzheng_entities",
            "active_document": _safe_get(document, "Name"),
            "selection_count": len(entities),
            "entities": entities,
            "summary": summarize_selected_entities(entities),
        }
    finally:
        safe_delete_selection_set(document, TEMP_SELECTION_SET_NAME, selection_set)


def summarize_selected_entities(entities: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(entities),
        "line": 0,
        "polyline": 0,
        "block_reference": 0,
        "text": 0,
        "mtext": 0,
        "dimension": 0,
        "proxy": 0,
        "tianzheng_like": 0,
        "unknown": 0,
    }
    for entity in entities:
        kind = _classify_object_name(str(entity.get("object_name") or ""))
        if kind in summary:
            summary[kind] += 1
        if entity.get("is_proxy"):
            summary["proxy"] += 1
        if entity.get("is_tianzheng_like"):
            summary["tianzheng_like"] += 1
    return summary


def selected_model_diagnostics(model: dict[str, Any]) -> dict[str, Any]:
    entities = model.get("entities", [])
    object_names = Counter(str(entity.get("object_name") or "") for entity in entities)
    layers = Counter(str(entity.get("layer") or "") for entity in entities)
    return {
        "active_document": model.get("active_document"),
        "selection_count": model.get("selection_count", 0),
        "object_name_top_20": object_names.most_common(20),
        "layer_top_20": layers.most_common(20),
        "proxy": model.get("summary", {}).get("proxy", 0),
        "tianzheng_like": model.get("summary", {}).get("tianzheng_like", 0),
        "unknown": model.get("summary", {}).get("unknown", 0),
        "first_20_entities": [
            {
                "handle": entity.get("handle"),
                "object_name": entity.get("object_name"),
                "layer": entity.get("layer"),
                "is_proxy": entity.get("is_proxy"),
                "is_tianzheng_like": entity.get("is_tianzheng_like"),
                "errors": entity.get("diagnostic", {}).get("errors", []),
            }
            for entity in entities[:20]
        ],
    }


def _selected_entity_to_model(inspection: dict[str, Any]) -> dict[str, Any]:
    diagnostic = inspection.get("diagnostic", {})
    return {
        "handle": inspection.get("handle"),
        "object_name": inspection.get("object_name"),
        "entity_name": inspection.get("entity_name"),
        "layer": inspection.get("layer"),
        "color": inspection.get("color"),
        "linetype": inspection.get("linetype"),
        "bounding_box": inspection.get("bounding_box"),
        "is_proxy": diagnostic.get("is_proxy", False),
        "is_tianzheng_like": diagnostic.get("is_tianzheng_like", False),
        "diagnostic": {"errors": diagnostic.get("errors", [])},
        "inspection": inspection,
    }


def _classify_object_name(object_name: str) -> str:
    lowered = object_name.lower()
    if "proxy" in lowered:
        return "proxy_entity"
    if "blockreference" in lowered:
        return "block_reference"
    if "mtext" in lowered:
        return "mtext"
    if "text" in lowered:
        return "text"
    if "dimension" in lowered:
        return "dimension"
    if "polyline" in lowered:
        return "polyline"
    if "line" in lowered:
        return "line"
    return "unknown"


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None
