from __future__ import annotations


def _sources() -> list[dict]:
    return [
        {
            "type": "png",
            "role": "reference",
            "path": "reference.png",
            "semantic_graph": {
                "metadata": {"coordinate_space": "normalized_image"},
                "buildings": [],
                "pipes": [{"id": "p1", "start": [0, 0, 0], "end": [1, 0, 0], "confidence": 0.92, "dn": 50, "system_type": "给水"}],
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


def test_pipeline_v2_default_does_not_add_spatial_stage() -> None:
    from mcp.pipeline_v2 import Phase8PipelineEngine

    engine = Phase8PipelineEngine()
    session = engine.create_session(_sources())
    result = engine.run(session.session_id)
    stored = engine.get_session(session.session_id)

    assert result["status"] == "success"
    assert "align_reference_to_target_coordinates" not in stored.pipeline_state.completed_stages


def test_pipeline_v2_optional_spatial_stage_executes_with_manual_anchors() -> None:
    from mcp.pipeline_v2 import Phase8PipelineEngine

    engine = Phase8PipelineEngine(enable_spatial_alignment=True)
    session = engine.create_session(_sources())
    session.phase11_manual_anchor_pairs = [
        {
            "reference": {"x": 0, "y": 0},
            "target": {"x": 100, "y": 200},
            "confidence": 0.9,
            "reason": ["manual_anchor"],
        }
    ]

    result = engine.run(session.session_id)
    stored = engine.get_session(session.session_id)

    assert result["status"] == "success"
    assert "align_reference_to_target_coordinates" in stored.pipeline_state.completed_stages
    assert stored.phase8_reference_graph["metadata"]["coordinate_space"] == "cad_modelspace"
