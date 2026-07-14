# -*- coding: utf-8 -*-
"""D0.2: macro_discovery module tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

def test_import_macro_discovery():
    from scripts.tianzheng.macro_discovery import discover_macros, _clean_macro, _extract_item_robust
    assert discover_macros is not None

def test_clean_macro_empty():
    from scripts.tianzheng.macro_discovery import _clean_macro
    assert _clean_macro("") == ""
    assert _clean_macro(None) == ""

def test_clean_macro_ctrl_chars():
    from scripts.tianzheng.macro_discovery import _clean_macro
    result = _clean_macro("\x00\x01TEST\x02")
    assert "TEST" in result

def test_discover_macros_no_acad():
    from scripts.tianzheng.macro_discovery import discover_macros
    session = discover_macros(None)
    assert session is not None
    assert len(session.errors) > 0

def test_macro_discovery_py_compile():
    import py_compile
    target = Path(__file__).parent.parent / "scripts" / "tianzheng" / "macro_discovery.py"
    py_compile.compile(str(target), doraise=True)

def test_safe_get_functions():
    from scripts.tianzheng.macro_discovery import _safe_get, _safe_str
    assert _safe_get(None, "anything") == ""
    assert _safe_str(None) == ""