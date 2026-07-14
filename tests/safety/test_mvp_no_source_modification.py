from __future__ import annotations

import json
from pathlib import Path

from mcp.diff.mvp_missing_content_diff import run_default_diff
from mcp.planning.mvp_repair_task_classifier import classify_diff_result
from mcp.recognition.mvp_reference_dwg_reader import read_reference_dwg
from mcp.recognition.mvp_reference_pdf_reader import read_reference_pdf
from mcp.recognition.mvp_target_dwg_reader import read_target_dwg


def test_mvp_recognition_keeps_source_safety_closed() -> None:
    for result in (read_reference_dwg(), read_reference_pdf(), read_target_dwg(), run_default_diff()):
        assert result.get("source_dwg_opened") is False
        assert result.get("source_dwg_saved") is False
        assert result.get("sendcommand_used", False) is False
        assert result.get("production_d1_allowed", False) is False


def test_no_sendcommand_or_tianzheng_auto_execution() -> None:
    classification = classify_diff_result(run_default_diff())
    assert classification["sendcommand_used"] is False
    assert classification["tianzheng_command_executed"] is False
    assert classification["dangerous_command_executed"] is False
    for task in classification["manual_tianzheng_tasks"]:
        assert task["required_command"] == "manual_only_no_auto_execution"
        assert task["before_after_scan_required"] is True


def test_deepseek_real_call_false_does_not_block_report_when_present() -> None:
    report_path = Path("reports/phase_agent_ds1_controlled_deepseek_worker.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PARTIAL"
    mvp_report_path = Path("reports/mvp_1_reference_recognition.json")
    if mvp_report_path.exists():
        mvp_report = json.loads(mvp_report_path.read_text(encoding="utf-8"))
        assert mvp_report["deepseek_worker_real_call"] is False
        assert mvp_report["mode"] == "dry_run_gpt_fallback"
        assert mvp_report.get("acceptance_decision", "MVP-1 PARTIAL") != "MVP-1 BLOCKED"


def test_no_hsxg_hzgx_gxlj_auto_execution_in_mvp_reports() -> None:
    for report_name in (
        "mvp_manual_tianzheng_tasks.json",
        "mvp_missing_tasks.json",
        "mvp_review_tasks.json",
        "mvp_gpt_visual_review_required.json",
    ):
        report_path = Path("reports") / report_name
        if not report_path.exists():
            continue
        text = report_path.read_text(encoding="utf-8").lower()
        assert "required_command\": \"hsxg" not in text
        assert "required_command\": \"hzgx" not in text
        assert "required_command\": \"gxlj" not in text
        if report_name == "mvp_manual_tianzheng_tasks.json":
            data = json.loads(report_path.read_text(encoding="utf-8"))
            for task in data.get("tasks", []):
                assert task["required_command"] == "manual_only_no_auto_execution"


def test_mvp_report_schema_complete_if_generated() -> None:
    report_path = Path("reports/mvp_1_reference_recognition.json")
    if not report_path.exists():
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    required = {
        "phase",
        "mode",
        "deepseek_worker_real_call",
        "deepseek_worker_available",
        "reference_dwg_loaded",
        "reference_pdf_loaded",
        "target_copy_loaded",
        "source_dwg_opened",
        "source_dwg_saved",
        "reference_object_count",
        "target_object_count",
        "pdf_text_count",
        "pdf_vector_count",
        "recognized_reference_objects_count",
        "recognized_target_objects_count",
        "matched_count",
        "missing_count",
        "extra_count",
        "changed_count",
        "uncertain_count",
        "direct_com_task_count",
        "manual_tianzheng_task_count",
        "review_task_count",
        "blocked_task_count",
        "gpt_visual_review_required_count",
        "sendcommand_used",
        "tianzheng_command_executed",
        "dangerous_command_executed",
        "production_d1_allowed",
    }
    assert required <= set(report)
    assert report["deepseek_worker_real_call"] is False
    assert report["mode"] == "dry_run_gpt_fallback"
