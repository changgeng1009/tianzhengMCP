from __future__ import annotations

import json


def test_acceptance_report_adds_review_action_cleanup_summary(tmp_path) -> None:
    from mcp.acceptance.acceptance_report import generate_acceptance_report
    from mcp.acceptance.models import AcceptanceRunResult

    result = AcceptanceRunResult(
        run_id="cleanup",
        status="warning",
        e2e_result={
            "repair_plan_v2": {
                "actions": [],
                "review_actions": [
                    {
                        "action_id": "r1",
                        "action_type": "add_pipe",
                        "geometry": {"type": "polyline", "points": [[0, 0], [100, 0]]},
                        "confidence": 0.0,
                        "auto_execute": False,
                        "validation_status": "review_required",
                        "dn": None,
                        "metadata": {"review_only": True},
                    }
                ],
                "rejected_actions": [],
            },
            "pipeline_result": {"data": {"report": {}}},
        },
    )

    report = generate_acceptance_report(result, str(tmp_path))

    payload = json.loads((tmp_path / "cleanup.json").read_text(encoding="utf-8"))
    summary = payload["review_action_cleanup_summary"]
    assert report["review_action_cleanup_summary"]["input_review_actions"] == 1
    assert summary["auto_executable_after_cleanup"] == 0
    assert summary["groups"] == 1
    assert payload["e2e_result"]["review_action_cleanup"]["groups"][0]["auto_execute"] is False
    markdown = (tmp_path / "cleanup.md").read_text(encoding="utf-8")
    assert "review_action_cleanup_summary" in markdown
