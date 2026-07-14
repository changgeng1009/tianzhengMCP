from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
REPORT_PATH = ROOT / "reports/stage2_skill_packaging.json"


def load_report() -> dict:
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def test_stage2_report_has_scope_override_fields() -> None:
    report = load_report()
    assert report["active_professional_domain"] == "water_supply_and_drainage"
    assert report["water_supply_and_drainage_status"] == "active"
    assert report["hvac_status"] == "deferred"
    assert report["hvac_implementation_completed"] is False
    assert report["opened_test_drawings_used"] is False
    assert report["opened_test_drawings_saved"] is False
    assert report["stage3_reference_path_confirmed"] is False
    assert report["stage3_target_path_confirmed"] is False
    assert report["controlled_fixture_used_as_real_sample"] is False
    assert report["real_sample_repair_completed"] is False
    assert report["production_d1_allowed"] is False


def test_stage2_report_does_not_fabricate_deepseek_or_stage3_readiness() -> None:
    report = load_report()
    assert report["status"] == "PARTIAL_DEEPSEEK_DEFERRED"
    assert report["deepseek_worker_used"] is True
    assert report["deepseek_available"] is False
    assert report["deepseek_external_environment_reported_available"] is True
    assert report["deepseek_codex_subprocess_available"] is False
    assert report["deepseek_closure_deferred"] is True
    assert report["deepseek_result_fabricated"] is False
    assert report["call_succeeded"] is False
    assert report["accepted_count"] == 0
    assert report["modified_count"] == 0
    assert report["rejected_count"] == 0
    assert report["can_enter_stage3_real_sample_validation"] is True


def test_stage2_report_safety_flags_are_false_and_utf8_is_intact() -> None:
    report = load_report()
    flags = [
        "autocad_connected", "source_dwg_opened", "source_dwg_saved", "source_modified",
        "save_called_on_source", "sandbox_dwg_opened", "sandbox_saved",
        "opened_test_drawings_accessed", "opened_test_drawings_saved", "drawing_executed",
        "sendcommand_used", "tianzheng_command_executed", "dangerous_command_executed",
        "production_d1_allowed",
    ]
    assert all(report[name] is False for name in flags)
    assert "????" not in REPORT_PATH.read_text(encoding="utf-8")
    assert "????" not in (ROOT / "reports/stage2_skill_packaging.md").read_text(encoding="utf-8")
