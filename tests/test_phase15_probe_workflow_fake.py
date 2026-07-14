from __future__ import annotations


def test_probe_workflow_fake_mode_generates_structured_result(tmp_path) -> None:
    from mcp.acceptance.probe_workflow import run_probe_workflow

    result = run_probe_workflow(str(tmp_path), {"fake_mode": True})

    assert result.status == "success"
    assert result.probe_result_path.endswith("t30_probe_result.json")
    assert result.candidate_methods

