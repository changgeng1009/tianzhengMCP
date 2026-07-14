from __future__ import annotations


def test_reread_verifier_fake_mode_marks_created_entities_verified(tmp_path, synthetic_cad_factory) -> None:
    from mcp.e2e.reread_verifier import verify_sandbox_dwg_after_writeback

    sandbox = synthetic_cad_factory(tmp_path / "sandbox.dwg")
    result = verify_sandbox_dwg_after_writeback(
        str(sandbox),
        {
            "status": "committed",
            "created_entities": [{"handle": "FAKE-PIPE-0001"}],
            "executed_actions": [{"action": {"action_id": "a1"}}],
            "metadata": {"mode": "fake"},
        },
        options={"verification_mode": "fake"},
    )

    assert result["status"] == "verified"
    assert result["metrics"]["confirmed_count"] == 1


def test_reread_verifier_real_hook_returns_unverified_warning(tmp_path, synthetic_cad_factory) -> None:
    from mcp.e2e.reread_verifier import verify_sandbox_dwg_after_writeback

    sandbox = synthetic_cad_factory(tmp_path / "sandbox.dwg")
    result = verify_sandbox_dwg_after_writeback(
        str(sandbox),
        {"status": "committed", "created_entities": [{"handle": "REAL-1"}], "metadata": {"mode": "real"}},
        options={"verification_mode": "reread_dwg"},
    )

    assert result["status"] == "unverified"
    assert result["warnings"]
