from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


@dataclass
class MacroDiscoverySession:
    entries: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    menugroup_count: int = 0


@dataclass
class MacroEntry:
    source_type: str
    menu_group: str
    parent_name: str
    item_name: str
    caption: str
    tag: str
    help_string: str
    macro_raw: str
    macro_clean: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _safe_get(obj: Any, attr: str, default: Any = "") -> Any:
    try:
        value = getattr(obj, attr, default)
        return default if value is None else value
    except Exception:
        return default


def _safe_str(obj: Any, max_len: int = 500) -> str:
    if obj is None:
        return ""
    try:
        return str(obj)[:max_len]
    except Exception:
        return ""


def _clean_macro(macro: Any) -> str:
    if not macro:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(macro))
    return re.sub(r" +", " ", cleaned).strip()


def _extract_item_robust(item: Any, source_type: str, group_name: str, parent_name: str) -> MacroEntry | None:
    if item is None:
        return None
    caption = _safe_str(_safe_get(item, "Caption"))
    item_name = _safe_str(_safe_get(item, "Name"))
    macro = _safe_str(
        _safe_get(item, "Macro") or _safe_get(item, "MenuMacro") or _safe_get(item, "Command"),
        max_len=2000,
    )
    if not caption and not item_name and not macro:
        return None
    return MacroEntry(
        source_type=source_type,
        menu_group=group_name,
        parent_name=parent_name,
        item_name=item_name,
        caption=caption,
        tag=_safe_str(_safe_get(item, "Tag")),
        help_string=_safe_str(_safe_get(item, "HelpString")),
        macro_raw=macro,
        macro_clean=_clean_macro(macro),
    )


def discover_macros(acad: Any) -> MacroDiscoverySession:
    session = MacroDiscoverySession()
    if acad is None:
        session.errors.append("acad is None")
        return session
    menu_groups = _safe_get(acad, "MenuGroups", None)
    if menu_groups is None:
        session.errors.append("MenuGroups is unavailable")
        return session
    try:
        session.menugroup_count = int(_safe_get(menu_groups, "Count", 0) or 0)
    except (TypeError, ValueError):
        session.errors.append("MenuGroups.Count is invalid")
    return session
