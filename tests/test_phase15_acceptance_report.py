from __future__ import annotations


def test_acceptance_report_blocks_real_success_without_reread_verification(tmp_path) -> None:
    from mcp.acceptance.acceptance_report import generate_acceptance_report
    from mcp.acceptance.models import AcceptanceRunResult

    result = AcceptanceRunResult(
        run_id="run1",
        status="warning",
        confirmed_schema_status={"confirmed_object_types": ["TDbPipe"], "unconfirmed_object_types": []},
        e2e_result={"status": "warning"},
        writeback_result={"status": "committed", "metadata": {"mode": "real"}},
        reread_verification={"status": "unverified"},
    )

    report = generate_acceptance_report(result, str(tmp_path))
    markdown = (tmp_path / "run1.md").read_text(encoding="utf-8")

    assert report["status"] == "success"
    assert report["can_claim_real_success"] is False
    assert "不能声明真实补图成功" in markdown


def test_acceptance_report_marks_dry_run_as_not_real_write(tmp_path) -> None:
    from mcp.acceptance.acceptance_report import generate_acceptance_report
    from mcp.acceptance.models import AcceptanceRunResult

    result = AcceptanceRunResult(run_id="dry", status="warning", writeback_result={}, reread_verification={})

    generate_acceptance_report(result, str(tmp_path))
    markdown = (tmp_path / "dry.md").read_text(encoding="utf-8")

    assert "本次未执行真实 CAD 写回" in markdown

