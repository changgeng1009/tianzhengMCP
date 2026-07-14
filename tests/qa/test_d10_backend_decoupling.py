from __future__ import annotations

from pathlib import Path

from mcp.qa.d10_auto_qa_validator import run_d10_qa


def test_d10_requires_explicit_paths_and_does_not_scan_by_default(tmp_path: Path) -> None:
    result = run_d10_qa(report_path=tmp_path / "report.json")
    assert result["acceptance_decision"] == "BLOCKED"
    assert result["live_scan_attempted"] is False
    assert result["source_dwg_opened"] is False


def test_d10_accepts_injected_serializable_scanner(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    sandbox = tmp_path / "copy.bin"
    source.write_bytes(b"source")
    sandbox.write_bytes(b"copy")

    def scanner(path: str) -> dict:
        assert path == str(sandbox)
        return {
            "sandbox_opened": True,
            "modelspace_accessible": True,
            "total_entities": 1,
            "detected_handles": ["A1"],
            "scan_backend_id": "mock",
        }

    result = run_d10_qa(
        source_path=str(source),
        sandbox_path=str(sandbox),
        live_scanner=scanner,
        report_path=tmp_path / "report.json",
    )
    assert result["qa_passed"] is True
    assert result["scan_backend_id"] == "mock"
    assert result["source_hash_unchanged"] is True
