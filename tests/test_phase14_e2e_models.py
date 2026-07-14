from __future__ import annotations


def test_e2e_models_are_json_serializable() -> None:
    from mcp.e2e.models import E2EMetrics, E2ERunConfig, E2ERunResult, E2EScenario

    scenario = E2EScenario(
        scenario_id="scn1",
        name="样例场景",
        reference_sources=[{"type": "png", "path": "ref.png"}],
        target_dwg_path="target.dwg",
        expected_missing=[{"id": "p1"}],
    )
    config = E2ERunConfig(run_id="run1", scenario_id="scn1")
    metrics = E2EMetrics(detected_missing_count=1, generated_action_count=1)
    result = E2ERunResult(
        run_id="run1",
        scenario_id="scn1",
        status="success",
        metrics=metrics.to_dict(),
    )

    assert scenario.to_dict()["reference_sources"][0]["type"] == "png"
    assert config.to_dict()["dry_run_only"] is True
    assert result.to_dict()["metrics"]["generated_action_count"] == 1

