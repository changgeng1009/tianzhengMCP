from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from tests.config_driven.conftest import canonical_manifest_value


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "autocad-tianzheng-automation"
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))


@pytest.fixture
def cli_manifest(tmp_path) -> tuple[Path, dict]:
    value = canonical_manifest_value()
    path = tmp_path / "project_manifest.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path, deepcopy(value)


@pytest.fixture
def cli_legacy_manifest(tmp_path) -> Path:
    value = {
        "schema_version": "1.0",
        "project_id": "legacy-fictional",
        "project_name": "虚构旧项目",
        "task_type": "inspect_drawing",
        "runtime_mode": "plain_autocad",
        "product": "autocad",
        "workflow": "generic_autocad_redraw_offline",
        "approval_level": "L1_DRY_RUN",
        "production_allowed": False,
        "preferred_backend": "offline",
        "visual_review_required": True,
        "engineering_review_required": True,
    }
    path = tmp_path / "legacy_manifest.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path
