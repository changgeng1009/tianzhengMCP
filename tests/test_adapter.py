from __future__ import annotations


def test_probe_t30_capabilities_reads_fake_com_insert_support() -> None:
    from mcp.probe import probe_t30_capabilities

    result = probe_t30_capabilities(
        {
            "TDbPipe.Insert": True,
            "TDbValve.Insert": False,
            "TDbSprinkler.Insert": True,
            "TDbPipeFitting.Insert": True,
        }
    )

    assert result["TDbPipe.Insert"] is True
    assert result["TDbValve.Insert"] is False
    assert result["TDbSprinkler.Insert"] is True
    assert result["TDbPipeFitting.Insert"] is True
    assert result["source"] == "provided_capability_source"


def test_mock_t30_adapter_inserts_pipe_and_records_action_log() -> None:
    from mcp.adapter_t30 import T30WritebackAdapter

    adapter = T30WritebackAdapter(real_com_mode=False)

    result = adapter.insert_pipe(
        action_id="act_pipe_1",
        start=[0.0, 0.0, 0.0],
        end=[1000.0, 0.0, 0.0],
        dn=50,
        layer="PIPE-给水",
        system_type="给水",
    )

    assert result["success"] is True
    assert result["mode"] == "mock"
    assert result["object_type"] == "TDbPipe"
    assert result["method"] == "TDbPipe.Insert"
    assert result["handle"] == "MOCK-PIPE-0001"
    assert adapter.action_log[0]["action_id"] == "act_pipe_1"
    assert adapter.action_log[0]["status"] == "mock_inserted"


def test_real_mode_blocks_insert_when_capability_is_missing() -> None:
    from mcp.adapter_t30 import T30WritebackAdapter

    adapter = T30WritebackAdapter(
        real_com_mode=True,
        capabilities={
            "TDbPipe.Insert": True,
            "TDbValve.Insert": False,
            "TDbSprinkler.Insert": True,
            "TDbPipeFitting.Insert": True,
        },
    )

    result = adapter.insert_valve(
        action_id="act_valve_1",
        position=[500.0, 0.0, 0.0],
        on_pipe="pipe_1",
        valve_type="闸阀",
        layer="VALVE-给水",
    )

    assert result["success"] is False
    assert result["status"] == "capability_missing"
    assert result["method"] == "TDbValve.Insert"
    assert adapter.action_log[0]["status"] == "blocked"
