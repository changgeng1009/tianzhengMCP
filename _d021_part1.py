# -*- coding: utf-8 -*-
"""D0.2.1 修复脚本: macro_discovery + manual recording"""
import os

BASE = r"C:\Users\example-user\.agents\skills\autocad-dwg-redraw-skill-main\autocad-dwg-redraw-skill-main\skills\autocad-dwg-redraw"
SCR = os.path.join(BASE, "scripts", "tianzheng")

def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.lstrip())
    print(f"Written: {os.path.basename(path)} ({len(content)} chars)")

# ============================================================
# 1. Update macro_models.py - add diagnostic fields
# ============================================================
path = os.path.join(SCR, "macro_models.py")
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = """    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    session_mode: str = "readonly\""""
new = """    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    session_mode: str = "readonly"
    # D0.2.1: enumeration diagnostics
    toolbar_containers_seen: int = 0
    menu_containers_seen: int = 0
    toolbar_items_attempted: int = 0
    menu_items_attempted: int = 0
    toolbar_items_read: int = 0
    menu_items_read: int = 0
    item_read_errors: list[str] = field(default_factory=list)
    macro_empty_count: int = 0
    macro_nonempty_count: int = 0
    groups_with_read_failures: list[str] = field(default_factory=list)"""
content = content.replace(old, new)

old2 = """            "warnings": self.warnings,
            "errors": self.errors,
            "session_mode": self.session_mode,"""
new2 = """            "warnings": self.warnings,
            "errors": self.errors,
            "session_mode": self.session_mode,
            "toolbar_containers_seen": self.toolbar_containers_seen,
            "menu_containers_seen": self.menu_containers_seen,
            "toolbar_items_attempted": self.toolbar_items_attempted,
            "menu_items_attempted": self.menu_items_attempted,
            "toolbar_items_read": self.toolbar_items_read,
            "menu_items_read": self.menu_items_read,
            "item_read_errors": self.item_read_errors[:50],
            "macro_empty_count": self.macro_empty_count,
            "macro_nonempty_count": self.macro_nonempty_count,
            "groups_with_read_failures": self.groups_with_read_failures,"""
content = content.replace(old2, new2)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("macro_models.py updated")
