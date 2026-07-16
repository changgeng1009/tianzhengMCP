from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "autocad-tianzheng-automation"
CLI_PATH = SKILL_ROOT / "scripts" / "skill_cli.py"
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

_SPEC = importlib.util.spec_from_file_location("cad_config_s2_skill_cli", CLI_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"无法加载 Skill CLI: {CLI_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

build_parser = _MODULE.build_parser
main = _MODULE.main
