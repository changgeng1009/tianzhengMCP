from __future__ import annotations


def test_manual_runner_arg_parser_defaults_are_safe() -> None:
    from mcp.e2e.manual_e2e_runner import build_arg_parser

    parser = build_arg_parser()
    args = parser.parse_args(["--scenario", "scenario.json"])

    assert args.dry_run_only == "true"
    assert args.enable_real_writeback == "false"
    assert args.real_com_mode == "false"


def test_phase14_pipeline_fake_mode_preserves_original_dwg(tmp_path, synthetic_cad_factory, register_t30_sandbox_outputs) -> None:
    from mcp.e2e.models import E2ERunConfig, E2EScenario
    from mcp.e2e.scenario_runner import E2EScenarioRunner

    dwg = synthetic_cad_factory(tmp_path / "target.dwg")
    original_bytes = dwg.read_bytes()
    register_t30_sandbox_outputs(tmp_path / ".t30_writeback_sandbox", dwg.name)
    scenario = E2EScenario(
        scenario_id="scn-pipeline",
        name="pipeline fake",
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
                            "mapped_geometry": {"start": [0, 0, 0], "end": [10, 0, 0]},
                            "mapped_confidence": 0.9,
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
    config = E2ERunConfig(
        run_id="run-pipeline",
        scenario_id="scn-pipeline",
        dry_run_only=False,
        enable_t30_writeback=True,
        verification_mode="fake",
    )

    result = E2EScenarioRunner().run_scenario(scenario, config)

    assert result.status == "success"
    assert dwg.read_bytes() == original_bytes
