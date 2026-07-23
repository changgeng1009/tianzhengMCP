"""S5 evidence 入口不启动 AutoCAD 的合同测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_nextgen.backends.real_autocad_com import RealAutoCadComBackendError
from mcp_nextgen.backends.autocad_launcher import AutoCadLauncherError
from mcp_nextgen.backends.autocad_com_gateway import AutoCadComGatewayError
from scripts.run_s5_synthetic_integration import (
    EVIDENCE_FILES, create_s5_evidence_run_root, main, write_s5_evidence_bundle,
)


def test_evidence_bundle_writes_exact_fixed_outputs_without_tokens(tmp_path: Path) -> None:
    target = tmp_path / "one-run"
    result = {
        "synthetic": True, "entities_created": 3, "persistence_verified": True,
        "idempotency_results": ["ALREADY_APPLIED"] * 3,
        "com_identity": {"version": "25.1", "process_id": 1},
        "document_identity": {"canonical_path": "synthetic.dwg", "synthetic": True},
    }
    write_s5_evidence_bundle(evidence_dir=target, status="COMPLETED", result=result)
    assert {item.name for item in target.iterdir()} == set(EVIDENCE_FILES)
    assert "ownership_token" not in "".join(path.read_text(encoding="utf-8") for path in target.iterdir())


def test_cli_default_gate_writes_blocked_evidence_without_importing_com(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CAD_S5_AUTOCAD_INTEGRATION", raising=False)
    evidence = tmp_path / "blocked"
    exit_code = main(["--evidence-dir", str(evidence), "--artifact-root", str(tmp_path), "--plan-hash", "a" * 64])
    assert exit_code == 2
    assert json.loads((evidence / "s5_execution_summary.json").read_text(encoding="utf-8"))["status"] == "BLOCKED"


def test_cli_rejects_run_root_outside_artifact_parent_before_creating_it(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CAD_S5_AUTOCAD_INTEGRATION", raising=False)
    outside = tmp_path / "outside-run"
    with pytest.raises(RealAutoCadComBackendError) as error:
        main([
            "--evidence-dir", str(outside), "--artifact-root", str(tmp_path / "artifact-parent"),
            "--plan-hash", "a" * 64,
        ])
    assert error.value.code == "S5_EVIDENCE_DIRECTORY_UNSAFE"
    assert not outside.exists()


def test_registered_run_root_can_hold_sandbox_before_evidence_without_overwrite(tmp_path: Path) -> None:
    root = create_s5_evidence_run_root(tmp_path / "run")
    assert (root.path / "sandbox").is_dir()
    write_s5_evidence_bundle(evidence_dir=root.path, run_root=root, status="FAILED", result=None)
    assert (root.path / "s5_final_report.md").is_file()
    try:
        write_s5_evidence_bundle(evidence_dir=root.path, run_root=root, status="FAILED", result=None)
    except Exception as error:
        assert getattr(error, "code", "") == "S5_EVIDENCE_OVERWRITE_FORBIDDEN"
    else:  # pragma: no cover
        raise AssertionError("同名 evidence 不得覆盖")
    assert {item.name for item in root.path.iterdir()} == {"sandbox", *EVIDENCE_FILES}
    assert "ownership_token" not in "".join(
        path.read_text(encoding="utf-8") for path in root.path.iterdir() if path.is_file()
    )


def test_evidence_bundle_rejects_token_bearing_payload(tmp_path: Path) -> None:
    with pytest.raises(RealAutoCadComBackendError) as error:
        write_s5_evidence_bundle(
            evidence_dir=tmp_path / "token-rejected", status="COMPLETED",
            result={"document_identity": {"ownership_token": "must-never-be-written"}},
        )
    assert error.value.code == "S5_EVIDENCE_SECRET_FORBIDDEN"


def test_evidence_uses_launcher_error_code_not_only_backend_code(tmp_path: Path) -> None:
    root = tmp_path / "launcher-error"
    write_s5_evidence_bundle(
        evidence_dir=root, status="FAILED", result=None,
        error=AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVED", "missing"),
    )
    summary = json.loads((root / "s5_execution_summary.json").read_text(encoding="utf-8"))
    assert summary["error_code"] == "AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVED"


def test_failed_integration_evidence_records_stage_but_never_raw_error_secret(tmp_path: Path) -> None:
    secret = "S5_DO_NOT_EXPOSE_APPROVAL_OR_DOCUMENT_SECRET"
    root = tmp_path / "entity-failure"
    write_s5_evidence_bundle(
        evidence_dir=root, status="FAILED", result=None,
        error=AutoCadComGatewayError("AUTOCAD_ENTITY_CREATION_FAILED", secret, stage="CREATE_LINE"),
    )
    summary = json.loads((root / "s5_execution_summary.json").read_text(encoding="utf-8"))
    assert summary["error_code"] == "AUTOCAD_ENTITY_CREATION_FAILED"
    assert summary["error_stage"] == "CREATE_LINE"
    assert summary["error_present"] is True
    assert secret not in "".join(path.read_text(encoding="utf-8") for path in root.iterdir())
