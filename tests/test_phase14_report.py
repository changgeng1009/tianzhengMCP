from __future__ import annotations


def test_report_generates_json_and_markdown(tmp_path) -> None:
    from mcp.e2e.models import E2ERunResult, E2EScenario
    from mcp.e2e.report import generate_e2e_report

    scenario = E2EScenario("scn1", "场景", [{"type": "png", "path": "ref.png"}], "target.dwg")
    result = E2ERunResult(
        run_id="run1",
        scenario_id="scn1",
        status="success",
        metrics={"generated_action_count": 1},
        warnings=["需要人工审核"],
    )

    report = generate_e2e_report(scenario, result, str(tmp_path))

    assert report["status"] == "success"
    assert report["json_path"].endswith(".json")
    assert report["markdown_path"].endswith(".md")
    assert "场景" in (tmp_path / "run1.md").read_text(encoding="utf-8")

