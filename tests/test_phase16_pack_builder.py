from __future__ import annotations


def test_build_acceptance_pack_generates_all_required_files(tmp_path) -> None:
    from mcp.acceptance_pack.pack_builder import build_acceptance_pack

    result = build_acceptance_pack(str(tmp_path), project_name="T30验收")

    expected = {
        "README.md",
        "scenario_template.json",
        "manual_confirmation_template.example.json",
        "run_probe.bat",
        "run_dry_acceptance.bat",
        "run_real_sandbox_acceptance.bat",
        "checklist.md",
    }
    assert result["status"] == "success"
    assert expected.issubset({item["name"] for item in result["files"]})
    assert "enable-real-writeback true" in (tmp_path / "run_real_sandbox_acceptance.bat").read_text(encoding="utf-8")
    assert "原始 DWG 不会被修改" in (tmp_path / "README.md").read_text(encoding="utf-8")

