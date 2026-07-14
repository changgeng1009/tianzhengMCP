from __future__ import annotations

import json
from pathlib import Path

from mcp.recognition.mvp_visual_evidence_builder import build_visual_evidence


def test_mvp_1_2_no_source_or_command_execution() -> None:
    report = build_visual_evidence()

    assert report["source_dwg_opened"] is False
    assert report["source_dwg_saved"] is False
    assert report["source_modified"] is False
    assert report["sendcommand_used"] is False
    assert report["tianzheng_command_executed"] is False
    assert report["dangerous_command_executed"] is False
    assert report["production_d1_allowed"] is False


def test_mvp_1_2_reports_do_not_contain_execution_flags_true() -> None:
    report_path = Path("reports/mvp_1_2_visual_evidence.json")
    if not report_path.exists():
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for key in (
        "source_dwg_opened",
        "source_dwg_saved",
        "source_modified",
        "sendcommand_used",
        "tianzheng_command_executed",
        "dangerous_command_executed",
        "production_d1_allowed",
    ):
        assert report[key] is False
