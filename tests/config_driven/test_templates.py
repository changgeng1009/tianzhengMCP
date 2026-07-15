from __future__ import annotations

import json
from pathlib import Path

from config import ManifestLoader
from runtime.execution_plan import ExecutionPlanBuilder


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "autocad-tianzheng-automation"
TEMPLATE_ROOT = SKILL_ROOT / "templates"


def test_all_ten_project_templates_validate_and_plan():
    catalog = json.loads((TEMPLATE_ROOT / "template_catalog.json").read_text(encoding="utf-8"))
    entries = catalog["templates"]
    assert len(entries) == 10
    for entry in entries:
        path = TEMPLATE_ROOT / entry["template_id"] / "project_manifest.json"
        manifest = ManifestLoader().load(path)
        ManifestLoader().validate(manifest)
        plan = ExecutionPlanBuilder().build(manifest)
        assert len(plan["plan_hash"]) == 64
        assert manifest["safety"]["production_allowed"] is False
        assert manifest["safety"]["real_cad_access_allowed"] is False


def test_templates_do_not_contain_environment_specific_roots():
    for path in TEMPLATE_ROOT.glob("*/project_manifest.json"):
        text = path.read_text(encoding="utf-8")
        assert "D:/CodexWork" not in text
        assert "C:/Users" not in text
        assert "学号" not in text
