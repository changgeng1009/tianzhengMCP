from __future__ import annotations


EXPECTED_STAGE_ORDER = [
    "load_dwg",
    "load_png",
    "build_semantic_graph",
    "align_buildings",
    "detect_missing_elements",
    "generate_repair_plan",
    "validate_repair_plan",
    "apply_to_cad",
    "generate_report",
]


def test_pipeline_runs_strict_order_and_updates_session_state() -> None:
    from mcp.adapter_t30 import T30WritebackAdapter
    from mcp.pipeline import PipelineEngine

    engine = PipelineEngine(adapter=T30WritebackAdapter(real_com_mode=False))
    session = engine.create_session(
        dwg_path="D:/sample/current.dwg",
        png_path="D:/sample/reference.png",
    )

    result = engine.run(session.session_id)
    stored = engine.get_session(session.session_id)

    assert result["session_id"] == session.session_id
    assert result["stage"] == "generate_report"
    assert result["status"] == "success"
    assert result["error"] is None
    assert stored.pipeline_state.completed_stages == EXPECTED_STAGE_ORDER
    assert stored.dwg_path == "D:/sample/current.dwg"
    assert stored.png_path == "D:/sample/reference.png"
    assert stored.dwg_graph["nodes"] == []
    assert stored.png_graph["edges"][0]["semantic_type"] == "pipe"
    assert stored.alignment_map["mapping"][0]["confidence"] >= 0.8
    assert stored.missing_result["missing_pipes"][0]["reference_edge_id"] == "png_edge_001"
    assert stored.repair_plan["actions"][0]["type"] == "add_pipe"
    assert stored.repair_plan["validation"]["valid"] is True
    assert stored.applied_actions[0]["status"] == "committed"
    assert stored.applied_actions[0]["result"]["handle"] == "MOCK-PIPE-0001"
    assert stored.pipeline_state.action_log[-1]["stage"] == "generate_report"


def test_pipeline_failure_can_retry_from_checkpoint_without_rerunning_completed_steps() -> None:
    from mcp.pipeline import PipelineEngine

    calls = {"load_dwg": 0, "load_png": 0}

    def load_dwg(session):
        calls["load_dwg"] += 1
        return {
            "nodes": [],
            "edges": [],
            "systems": [],
            "buildings": [{"id": "dwg_bldg_01", "label": "A栋"}],
        }

    def flaky_load_png(session):
        calls["load_png"] += 1
        if calls["load_png"] == 1:
            raise RuntimeError("PNG reference is temporarily unavailable")
        return {
            "nodes": [
                {"id": "png_node_001", "position": [0.0, 0.0, 0.0]},
                {"id": "png_node_002", "position": [1000.0, 0.0, 0.0]},
            ],
            "edges": [
                {
                    "id": "png_edge_001",
                    "semantic_type": "pipe",
                    "start_node_id": "png_node_001",
                    "end_node_id": "png_node_002",
                    "diameter": "DN50",
                    "system_type": "给水",
                    "layer": "PIPE-给水",
                    "geometry": {
                        "start_point": [0.0, 0.0, 0.0],
                        "end_point": [1000.0, 0.0, 0.0],
                    },
                }
            ],
            "systems": [{"system_type": "给水"}],
            "buildings": [{"id": "png_bldg_a", "label": "A栋"}],
        }

    engine = PipelineEngine(
        stage_overrides={
            "load_dwg": load_dwg,
            "load_png": flaky_load_png,
        }
    )
    session = engine.create_session("current.dwg", "reference.png")

    first = engine.run(session.session_id)
    after_failure = engine.get_session(session.session_id)
    second = engine.retry(session.session_id)
    after_retry = engine.get_session(session.session_id)

    assert first["status"] == "failed"
    assert first["stage"] == "load_png"
    assert after_failure.pipeline_state.completed_stages == ["load_dwg"]
    assert after_failure.pipeline_state.failed_stage == "load_png"
    assert second["status"] == "success"
    assert calls == {"load_dwg": 1, "load_png": 2}
    assert after_retry.pipeline_state.completed_stages == EXPECTED_STAGE_ORDER
    assert after_retry.pipeline_state.failed_stage is None


def test_pipeline_tools_are_registered_on_mcp_server() -> None:
    import asyncio

    async def run() -> None:
        from server import create_mcp

        mcp_server = create_mcp()
        tools = await mcp_server.list_tools()
        tool_names = {tool.name for tool in tools}

        assert {
            "create_pipeline_session",
            "run_pipeline",
            "retry_pipeline_stage",
            "get_pipeline_session",
            "probe_t30_capabilities",
        }.issubset(tool_names)

    asyncio.run(run())
