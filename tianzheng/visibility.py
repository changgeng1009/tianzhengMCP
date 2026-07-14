from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from cad.connection import AutoCADConnectionManager
from cad.reader import CADReader


logger = logging.getLogger(__name__)


class TianzhengVisibilityDiagnostic:
    def __init__(self, manager: AutoCADConnectionManager) -> None:
        self.manager = manager

    def diagnose_current_drawing(self) -> dict[str, Any]:
        try:
            result = CADReader(self.manager).read_current_drawing()
            if not result.get("success"):
                return result
            model = result["model"]
            entities = model.get("entities", [])
            object_names = Counter(str(entity.get("object_name") or "") for entity in entities)
            summary = {
                "active_document": model.get("source", {}).get("active_document"),
                "total_entities": len(entities),
                "object_name_counts": dict(object_names),
                "proxy_entities": sum(1 for entity in entities if _is_proxy(entity)),
                "tianzheng_like_entities": sum(1 for entity in entities if _is_tianzheng_like(entity)),
                "unknown_cad_entities": sum(
                    1 for entity in entities if entity.get("type") == "unknown_cad_entity"
                ),
                "visible_basic_entities": sum(
                    1 for entity in entities if entity.get("type") != "unknown_cad_entity"
                ),
            }
            return {"success": True, "model": model, "summary": summary}
        except Exception as exc:
            logger.exception("天正对象可见性诊断失败")
            return {"success": False, "error": str(exc)}

    def diagnose_selected_entities(self) -> dict[str, Any]:
        try:
            document = self.manager.require_active_document()
            selected = _selected_entities(document)
            return {
                "success": True,
                "selection_count": len(selected),
                "entities": [_entity_identity(entity) for entity in selected],
            }
        except Exception as exc:
            logger.exception("读取用户选择对象失败")
            return {"success": False, "selection_count": 0, "entities": [], "error": str(exc)}


def _selected_entities(document: Any) -> list[Any]:
    for attr in ("ActiveSelectionSet", "PickfirstSelectionSet"):
        selection = _safe_get(document, attr)
        if selection is not None:
            return _iter_collection(selection)
    return []


def _entity_identity(entity: Any) -> dict[str, Any]:
    object_name = _safe_get(entity, "ObjectName") or _safe_get(entity, "EntityName")
    return {
        "handle": _safe_get(entity, "Handle"),
        "object_name": object_name,
        "entity_name": _safe_get(entity, "EntityName"),
        "layer": _safe_get(entity, "Layer"),
        "color": _safe_get(entity, "Color"),
        "linetype": _safe_get(entity, "Linetype"),
        "is_proxy": _is_proxy_name(str(object_name or "")),
        "is_tianzheng_like": _is_tianzheng_name(str(object_name or "")),
    }


def _is_proxy(entity: dict[str, Any]) -> bool:
    return _is_proxy_name(str(entity.get("object_name") or ""))


def _is_tianzheng_like(entity: dict[str, Any]) -> bool:
    return _is_tianzheng_name(str(entity.get("object_name") or ""))


def _is_proxy_name(name: str) -> bool:
    return "proxy" in name.lower()


def _is_tianzheng_name(name: str) -> bool:
    lowered = name.lower()
    return any(keyword in lowered for keyword in ("tianzheng", "tangent", "tz", "twt", "天正"))


def _iter_collection(collection: Any) -> list[Any]:
    try:
        return list(collection)
    except Exception:
        logger.info("Selection collection is not directly iterable", exc_info=True)
    result: list[Any] = []
    count = int(_safe_get(collection, "Count") or 0)
    for index in range(count):
        try:
            result.append(collection.Item(index))
        except Exception:
            try:
                result.append(collection.Item(index + 1))
            except Exception:
                logger.info("Selection Item lookup failed: index=%s", index, exc_info=True)
    return result


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None
