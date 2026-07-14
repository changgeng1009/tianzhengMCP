from __future__ import annotations

import logging
from typing import Any

from cad.connection import AutoCADConnectionManager
from cad.document_resolver import resolve_active_document


logger = logging.getLogger(__name__)


NOT_DETECTED_MESSAGE = (
    "Tianzheng T30 environment is not detected. Please launch AutoCAD through 天正给排水 T30 V1.0."
)


class TianzhengEnvironmentDetector:
    def __init__(self, manager: AutoCADConnectionManager) -> None:
        self.manager = manager

    def detect(self) -> dict[str, Any]:
        try:
            app = self.manager.require_application()
            resolved_document = resolve_active_document(app)
            document = resolved_document.get("document")
            signals = {
                "caption": _safe_get(app, "Caption"),
                "version": _safe_get(app, "Version"),
                "active_document": resolved_document.get("document_name"),
                "active_document_full_name": resolved_document.get("document_full_name"),
                "documents_count": resolved_document.get("documents_count", 0),
                "document_validation": resolved_document.get("document_validation"),
                "menu_groups": _menu_group_names(app),
                "support_path": _support_path(app),
                "trusted_paths": _trusted_paths(app),
                "menuname": _document_variable(document, "MENUNAME"),
                "acadver": _document_variable(document, "ACADVER"),
            }
            detected = _has_tianzheng_signal(signals)
            return {
                "success": True,
                "detected": detected,
                "message": (
                    "Tianzheng T30 environment detected."
                    if detected
                    else NOT_DETECTED_MESSAGE
                ),
                "signals": signals,
                "command_probe": {
                    "send_command_allowed": False,
                    "reserved_only": True,
                    "message": "Phase 6.0 does not call Tianzheng drawing commands.",
                },
            }
        except Exception as exc:
            logger.exception("天正环境检测失败")
            return {
                "success": False,
                "detected": False,
                "message": NOT_DETECTED_MESSAGE,
                "error": str(exc),
            }


def _has_tianzheng_signal(signals: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            str(signals.get("caption") or ""),
            str(signals.get("support_path") or ""),
            str(signals.get("trusted_paths") or ""),
            str(signals.get("menuname") or ""),
            " ".join(str(name) for name in signals.get("menu_groups", [])),
        ]
    ).lower()
    keywords = ("tianzheng", "tangent", "t30", "天正")
    return any(keyword.lower() in haystack for keyword in keywords)


def _menu_group_names(app: Any) -> list[str]:
    groups = _safe_get(app, "MenuGroups")
    if groups is None:
        return []
    result: list[str] = []
    count = int(_safe_get(groups, "Count") or 0)
    group_items = _items_by_index_base(groups, count, 0)
    if len(group_items) != count:
        group_items = _items_by_index_base(groups, count, 1)

    if group_items:
        for group in group_items:
            name = _safe_get(group, "Name")
            if name:
                result.append(str(name))
        return result

    try:
        for group in groups:
            name = _safe_get(group, "Name")
            if name:
                result.append(str(name))
        if result:
            return result
    except Exception:
        pass

    for index in range(count):
        group = _collection_item(groups, index)
        if group is None:
            result.append(f"<read_error:index={index}>")
            continue
        name = _safe_get(group, "Name")
        if name:
            result.append(str(name))
    return result


def _items_by_index_base(collection: Any, count: int, index_base: int) -> list[Any]:
    result: list[Any] = []
    for offset in range(count):
        index = offset + index_base
        try:
            result.append(collection.Item(index))
        except Exception:
            return result
    return result


def _collection_item(collection: Any, index: int) -> Any:
    try:
        return collection.Item(index)
    except Exception as exc0:
        try:
            return collection.Item(index + 1)
        except Exception as exc1:
            logger.info("COM collection Item failed: index=%s errors=%s | %s", index, exc0, exc1)
            return None


def _support_path(app: Any) -> str | None:
    files = _preferences_files(app)
    return _safe_get(files, "SupportPath") if files is not None else None


def _trusted_paths(app: Any) -> str | None:
    files = _preferences_files(app)
    return _safe_get(files, "TrustedPaths") if files is not None else None


def _preferences_files(app: Any) -> Any | None:
    preferences = _safe_get(app, "Preferences")
    return _safe_get(preferences, "Files") if preferences is not None else None


def _document_variable(document: Any, name: str) -> Any:
    try:
        return document.GetVariable(name)
    except Exception:
        return None


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None
