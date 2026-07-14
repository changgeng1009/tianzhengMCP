from __future__ import annotations


def _sources() -> list[dict]:
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
            "path": "target.dwg",
            "semantic_graph": {
                "metadata": {"coordinate_space": "cad_modelspace"},
                "buildings": [],
                "pipes": [],
                "valves": [],
                "sprinklers": [],
            },
        },
    ]


def test_pipeline_v2_default_skips_coordinate_repair_actions() -> None:
    from mcp.pipeline_v2 import Phase8PipelineEngine

    engine = Phase8PipelineEngine()
    session = engine.create_session(_sources())
    engine.run(session.session_id)
    stored = engine.get_session(session.session_id)

    assert "generate_coordinate_repair_actions" not in stored.pipeline_state.completed_stages


def test_pipeline_v2_optional_coordinate_repair_actions_stage_runs() -> None:
    from mcp.pipeline_v2 import Phase8PipelineEngine

    engine = Phase8PipelineEngine(enable_coordinate_repair_actions=True)
    session = engine.create_session(_sources())
    result = engine.run(session.session_id)
    stored = engine.get_session(session.session_id)

    assert result["status"] == "success"
    assert "generate_coordinate_repair_actions" in stored.pipeline_state.completed_stages
    assert stored.phase12_repair_plan_v2["actions"][0]["action_type"] == "add_pipe"
