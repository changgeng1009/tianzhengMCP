from __future__ import annotations


def _scenario(target_dwg_path: str, options: dict | None = None):
    from mcp.e2e.models import E2EScenario

    return E2EScenario(
        scenario_id="path_diag",
        name="路径诊断",
        reference_sources=[{"type": "pdf", "path": "ref.pdf"}],
        target_dwg_path=target_dwg_path,
        options=dict(options or {}),
    )


def test_missing_target_dwg_lists_same_directory_candidates(tmp_path, synthetic_cad_factory) -> None:
    from mcp.e2e.dataset import E2EDatasetRegistry

    candidate = synthetic_cad_factory(tmp_path / "实际图纸.dwg")
    scenario = _scenario(str(tmp_path / "错误图纸.dwg"))

    validation = E2EDatasetRegistry().validate_scenario(scenario, require_existing_target=True)

    assert validation["valid"] is False
    assert str(candidate) in validation["dwg_candidates"]
    assert any("DWG candidate" in warning or "DWG 候选" in warning for warning in validation["warnings"])


def test_single_dwg_candidate_is_not_silently_used_without_explicit_option(tmp_path, synthetic_cad_factory) -> None:
    from mcp.e2e.dataset import E2EDatasetRegistry

    original = tmp_path / "错误图纸.dwg"
    candidate = synthetic_cad_factory(tmp_path / "实际图纸.dwg")
    scenario = _scenario(str(original), options={"allow_single_dwg_fallback": False})

    validation = E2EDatasetRegistry().validate_scenario(scenario, require_existing_target=True)

    assert validation["valid"] is False
    assert scenario.target_dwg_path == str(original)
    assert validation["resolved_target_dwg_path"] == str(original)


def test_single_dwg_candidate_can_be_used_when_explicitly_enabled(tmp_path, synthetic_cad_factory) -> None:
    from mcp.e2e.dataset import E2EDatasetRegistry

    candidate = synthetic_cad_factory(tmp_path / "实际图纸.dwg")
    scenario = _scenario(str(tmp_path / "错误图纸.dwg"), options={"allow_single_dwg_fallback": True})

    validation = E2EDatasetRegistry().validate_scenario(scenario, require_existing_target=True)

    assert validation["valid"] is True
    assert scenario.target_dwg_path == str(candidate)
    assert validation["resolved_target_dwg_path"] == str(candidate)
