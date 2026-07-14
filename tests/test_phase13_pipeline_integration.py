from __future__ import annotations


def _sources(dwg_path: str) -> list[dict]:
    return [
        {
            "type": "png",
            "role": "reference",
            "path": "reference.png",
            "semantic_graph": {
                "metadata": {"coordinate_space": "cad_modelspace"},
                "buildings": [],
                "pipes": [
                    {
                        "id": "p1",
                        "source_element_id": "p1",
                        "mapped_geometry": {"start": [0, 0, 0], "end": [100, 0, 0]},
                        "mapped_confidence": 0.92,
                        "dn": "DN50",
                        "system_type": "给水",
                        "layer": "PIPE-给水",
                    }
                ],
                "valves": [],
                "sprinklers": [],
            },
        },
        {
            "type": "dwg",
            "role": "target",
            "path": dwg_path,
            "semantic_graph": {
                "metadata": {"coordinate_space": "cad_modelspace"},
                "buildings": [],
                "pipes": [],
                "valves": [],
                "sprinklers": [],
            },
        },
    ]


def test_pipeline_v2_default_skips_t30_writeback_stage(tmp_path, synthetic_cad_factory) -> None:
    from mcp.pipeline_v2 import Phase8PipelineEngine

    dwg = synthetic_cad_factory(tmp_path / "target.dwg")
    engine = Phase8PipelineEngine(enable_coordinate_repair_actions=True)
    session = engine.create_session(_sources(str(dwg)))
    engine.run(session.session_id)
    stored = engine.get_session(session.session_id)

    assert "apply_t30_writeback_v2" not in stored.pipeline_state.completed_stages


def test_pipeline_v2_t30_writeback_stage_runs_in_fake_mode(tmp_path, synthetic_cad_factory, register_t30_sandbox_outputs) -> None:
    from mcp.pipeline_v2 import Phase8PipelineEngine

    dwg = synthetic_cad_factory(tmp_path / "target.dwg")
    original_bytes = dwg.read_bytes()
    register_t30_sandbox_outputs(tmp_path / ".t30_writeback_sandbox", dwg.name)
    engine = Phase8PipelineEngine(
        enable_coordinate_repair_actions=True,
        enable_t30_real_writeback=True,
        t30_writeback_options={"dry_run_only": False},
    )
    session = engine.create_session(_sources(str(dwg)))
    result = engine.run(session.session_id)
    stored = engine.get_session(session.session_id)

    assert result["status"] == "success"
    assert "apply_t30_writeback_v2" in stored.pipeline_state.completed_stages
    assert stored.phase13_t30_writeback_result["status"] == "committed"
    assert dwg.read_bytes() == original_bytes
