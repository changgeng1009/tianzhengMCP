from __future__ import annotations


def _scenario(tmp_path, synthetic_cad_factory):
    from mcp.e2e.models import E2EScenario

    dwg = synthetic_cad_factory(tmp_path / "target.dwg")
    return E2EScenario(
        scenario_id="scn1",
        name="fake e2e",
        reference_sources=[
            {
                "type": "png",
                "role": "reference",
                "path": "reference.png",
                "semantic_graph": {
                    "metadata": {"coordinate_space": "cad_modelspace"},
                    "pipes": [
                        {
                            "id": "p1",
                            "mapped_geometry": {"start": [0, 0, 0], "end": [100, 0, 0]},
                            "mapped_confidence": 0.92,
                            "dn": "DN50",
                            "system_type": "给水",
                            "layer": "PIPE",
                        }
                    ],
                },
            }
        ],
        target_dwg_path=str(dwg),
        options={"target_semantic_graph": {"metadata": {"coordinate_space": "cad_modelspace"}, "pipes": []}},
    )


def test_scenario_runner_default_dry_run_does_not_write_cad(tmp_path, synthetic_cad_factory) -> None:
    from mcp.e2e.models import E2ERunConfig
    from mcp.e2e.scenario_runner import E2EScenarioRunner

    scenario = _scenario(tmp_path, synthetic_cad_factory)
    result = E2EScenarioRunner().run_scenario(scenario, E2ERunConfig(run_id="run1", scenario_id="scn1"))

    assert result.status in {"success", "warning"}
    assert result.writeback_result in ({}, None)
    assert result.repair_plan_v2["actions"]


def test_scenario_runner_fake_writeback_and_reread_verification(tmp_path, synthetic_cad_factory, register_t30_sandbox_outputs) -> None:
    from mcp.e2e.models import E2ERunConfig
    from mcp.e2e.scenario_runner import E2EScenarioRunner

    scenario = _scenario(tmp_path, synthetic_cad_factory)
    register_t30_sandbox_outputs(tmp_path / "sandbox", "target.dwg")
    config = E2ERunConfig(
        run_id="run2",
        scenario_id="scn1",
        dry_run_only=False,
        enable_t30_writeback=True,
        verification_mode="fake",
        sandbox_dir=str(tmp_path / "sandbox"),
    )
    result = E2EScenarioRunner().run_scenario(scenario, config)

    assert result.status == "success"
    assert result.writeback_result["status"] == "committed"
    assert result.reread_verification["status"] == "verified"
