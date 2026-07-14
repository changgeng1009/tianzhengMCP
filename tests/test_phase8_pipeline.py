from __future__ import annotations


def test_safe_t30_writeback_v2_runs_transaction_stages_and_blocks_review_actions() -> None:
    from mcp.adapter_t30 import T30WritebackAdapter
    from mcp.writeback_v2 import SafeT30WritebackV2

    writeback = SafeT30WritebackV2(adapter=T30WritebackAdapter(real_com_mode=False))
    plan = {
        "actions": [
            {
                "action_id": "auto_1",
                "type": "add_pipe",
                "start": [0.0, 0.0, 0.0],
                "end": [100.0, 0.0, 0.0],
                "dn": 50,
                "layer": "PIPE-给水",
                "system_type": "给水",
                "confidence": 0.91,
                "auto_execute": True,
            },
            {
                "action_id": "review_1",
                "type": "add_pipe",
                "start": [0.0, 100.0, 0.0],
                "end": [100.0, 100.0, 0.0],
                "dn": 50,
                "layer": "PIPE-给水",
                "system_type": "给水",
                "confidence": 0.72,
                "auto_execute": False,
            },
        ]
    }

    result = writeback.safe_apply(plan, target_graph={"pipes": []})

    assert result["status"] == "success"
    assert result["transaction_stages"] == ["validate", "simulate", "execute", "verify", "commit"]
    assert result["committed_actions"][0]["action_id"] == "auto_1"
    assert result["blocked_actions"][0]["action_id"] == "review_1"
    assert result["rollback_plan"]["available"] is True
    assert result["rollback_plan"]["actions"][0]["action_id"] == "auto_1"


def test_phase8_pipeline_runs_new_stages_and_returns_confidence_envelope() -> None:
    from mcp.pipeline_v2 import Phase8PipelineEngine

    engine = Phase8PipelineEngine()
    session = engine.create_session(
        sources=[
            {
                "type": "png",
                "path": "reference.png",
                "role": "reference",
                "semantic_graph": {
                    "buildings": [{"id": "A栋", "label": "A栋", "pipe_ids": ["p1"]}],
                    "pipes": [
                        {
                            "id": "p1",
                            "building_id": "A栋",
                            "start": [0.0, 0.0, 0.0],
                            "end": [100.0, 0.0, 0.0],
                            "dn": 50,
                            "system_type": "给水",
                            "confidence": 0.93,
                        }
                    ],
                    "valves": [],
                    "sprinklers": [],
                },
            },
            {
                "type": "dwg",
                "path": "target.dwg",
                "role": "target",
                "semantic_graph": {
                    "buildings": [{"id": "Bldg_03", "label": "A栋", "pipe_ids": []}],
                    "pipes": [],
                    "valves": [],
                    "sprinklers": [],
                },
            },
        ]
    )

    result = engine.run(session.session_id)
    stored = engine.get_session(session.session_id)

    assert result["status"] == "success"
    assert result["stage"] == "generate_report_v2"
    assert result["confidence"] > 0.85
    assert result["warnings"] == []
    assert stored.pipeline_state.completed_stages == [
        "build_multi_source_graph",
        "compute_structural_fingerprint",
        "align_buildings_v2",
        "semantic_diff_v2",
        "optimize_repair_plan",
        "confidence_filter",
        "safe_apply_to_cad_v2",
        "generate_report_v2",
    ]
    assert stored.repair_plan["actions"][0]["auto_execute"] is True
    assert stored.applied_actions[0]["action_id"] == "repair_p1"


def test_phase8_pipeline_tool_is_registered_on_mcp_server() -> None:
    import asyncio

    async def run() -> None:
        from server import create_mcp

        mcp_server = create_mcp()
        tools = await mcp_server.list_tools()
        tool_names = {tool.name for tool in tools}

        assert "run_phase8_pipeline" in tool_names

    asyncio.run(run())
