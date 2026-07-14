from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
SKILL = ROOT / "skill"


def test_required_skill_files_exist() -> None:
    required = [
        "SKILL.md", "README.md", "docs/architecture.md", "docs/backend_architecture.md",
        "docs/backend_contract.md", "docs/backend_migration_guide.md", "docs/safety_model.md",
        "docs/capability_matrix.md", "docs/limitations.md", "docs/troubleshooting.md", "docs/cli_reference.md",
        "configs/default.yaml", "configs/safety.yaml", "configs/backends.yaml", "configs/classification.yaml",
        "schemas/backend_capabilities.schema.json", "schemas/backend_selection.schema.json",
        "schemas/backend_result.schema.json", "schemas/skill_run_manifest.schema.json",
    ]
    assert [name for name in required if not (SKILL / name).exists()] == []


def test_skill_business_goal_is_not_line_only_and_scope_is_water_first() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "完整天正给排水参考 PDF" in text
    assert "管道、阀门、管件、设备或标注" in text
    assert "HVAC 只保留 disabled" in text
    assert "real_sample_repair_completed=false" in text


def test_workflow_schema_and_example_counts() -> None:
    workflows = sorted(path.name for path in (SKILL / "workflows").glob("*.md"))
    schemas = sorted(path.name for path in (SKILL / "schemas").glob("*.json"))
    examples = sorted(path.name for path in (SKILL / "examples").iterdir() if path.is_dir())
    assert len(workflows) == 8
    assert len(schemas) == 9
    assert len(examples) == 6


def test_all_json_schemas_are_valid_json_and_have_schema_keyword() -> None:
    for path in (SKILL / "schemas").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["$schema"].startswith("https://json-schema.org/")


def test_repair_task_schema_has_domain_and_backend_fields() -> None:
    schema = json.loads((SKILL / "schemas/repair_task.schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    assert {"professional_domain", "system_type", "domain_object_type", "required_capabilities"} - set(schema["properties"]) == set()
    assert {"professional_domain", "domain_object_type", "required_capabilities"} <= required


def test_stage3_sample_config_does_not_guess_open_drawing_paths() -> None:
    config = json.loads((SKILL / "configs/default.yaml").read_text(encoding="utf-8"))
    sample = config["stage3_sample"]
    assert sample["enabled"] is False
    assert sample["reference_dwg"] is None
    assert sample["target_dwg"] is None
    assert sample["exact_paths_confirmed"] is False


def test_safety_defaults_are_all_closed() -> None:
    safety = json.loads((SKILL / "configs/safety.yaml").read_text(encoding="utf-8"))
    assert safety["source_open_allowed"] is False
    assert safety["sendcommand_allowed"] is False
    assert safety["tianzheng_execution_allowed"] is False
    assert safety["production_d1_allowed"] is False
    assert safety["allow_automatic_fallback"] is False


def test_new_skill_files_do_not_contain_broken_question_mark_paths() -> None:
    offenders = []
    for path in SKILL.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".yaml", ".py"}:
            if "????" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(SKILL)))
    assert offenders == []
