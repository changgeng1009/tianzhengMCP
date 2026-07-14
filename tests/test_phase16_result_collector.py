from __future__ import annotations

import json


def test_result_collector_identifies_missing_and_present_artifacts(tmp_path) -> None:
    from mcp.acceptance_pack.result_collector import collect_acceptance_results

    (tmp_path / "t30_probe_result.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    reports = tmp_path / "acceptance_reports"
    reports.mkdir()
    (reports / "run.json").write_text(json.dumps({"status": "warning", "warnings": ["w1"]}), encoding="utf-8")
    (reports / "run.md").write_text("# report", encoding="utf-8")

    result = collect_acceptance_results(str(tmp_path))

    assert result["status"] in {"warning", "success"}
    assert any(item["type"] == "probe_result" for item in result["artifacts"])
    assert "manual_confirmation.json" in result["missing_artifacts"]
    assert "w1" in result["warnings"]

