from __future__ import annotations

from mcp.acceptance import stage3_1_real_sample_alignment as stage3


def test_missing_key_is_deferred_not_blocking() -> None:
    result = stage3.run_precondition_gate(environment={})

    assert result["stage2_closure_status"] == "PARTIAL_DEEPSEEK_DEFERRED"
    assert result["deepseek_external_environment_reported_available"] is True
    assert result["deepseek_codex_subprocess_available"] is False
    assert result["deepseek_closure_deferred"] is True
    assert result["stage3_1_final_status"] == "PRECONDITION_READY"


def test_amendment_never_fabricates_deepseek_result() -> None:
    result = stage3.amended_precondition_status({})

    assert result["deepseek_call_succeeded"] is False
    assert result["deepseek_result_fabricated"] is False


def test_key_presence_is_recorded_without_exposing_value() -> None:
    result = stage3.amended_precondition_status({"DEEPSEEK_API_KEY": "secret-value"})

    assert result["deepseek_codex_subprocess_available"] is True
    assert "secret-value" not in str(result)


def test_all_safety_flags_default_false() -> None:
    flags = stage3._safety_flags()

    assert flags
    assert all(value is False for value in flags.values())
    assert flags["production_d1_allowed"] is False


def test_stage3_2_remains_disallowed_in_manifest() -> None:
    report = {
        "phase": "STAGE3.1", "run_id": "run", "stage2_closure_status": "PARTIAL_DEEPSEEK_DEFERRED",
        "reference_source_path": "r.dwg", "target_source_path": "t.dwg",
        "reference_source_sha256_before": "a", "target_source_sha256_before": "b",
        "reference_copy_path": "rc.dwg", "target_copy_path": "tc.dwg",
        "stage3_1_final_status": "PASS_TRANSLATION", "safety_flags": stage3._safety_flags(),
    }

    manifest = stage3._manifest_from_report(report)

    assert manifest["stage3_2_allowed"] is False
