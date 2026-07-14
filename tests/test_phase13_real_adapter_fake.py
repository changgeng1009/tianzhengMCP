from __future__ import annotations


def _repair_plan_v2() -> dict:
    return {
        "actions": [
            {
                "action_id": "repair_pipe_1",
                "action_type": "add_pipe",
                "target_space": "cad_modelspace",
                "geometry": {"start": [0, 0, 0], "end": [100, 0, 0]},
                "system": "给水",
                "dn": "DN50",
                "layer": "PIPE",
                "confidence": 0.91,
                "auto_execute": True,
            }
        ],
        "review_actions": [],
        "rejected_actions": [],
    }


def test_real_adapter_defaults_to_simulation_and_does_not_modify_original(tmp_path, synthetic_cad_factory, register_t30_sandbox_outputs) -> None:
    from mcp.t30_writeback.real_adapter import RealT30WritebackAdapter

    original = synthetic_cad_factory(tmp_path / "target.dwg")
    original_bytes = original.read_bytes()
    register_t30_sandbox_outputs(tmp_path / ".t30_writeback_sandbox", original.name)
    adapter = RealT30WritebackAdapter()

    result = adapter.apply_repair_plan_v2(_repair_plan_v2(), str(original), {"dry_run_only": False})

    assert result.status == "committed"
    assert result.metadata["mode"] == "fake"
    assert original.read_bytes() == original_bytes


def test_real_adapter_dry_run_only_skips_execution(tmp_path, synthetic_cad_factory) -> None:
    from mcp.t30_writeback.real_adapter import RealT30WritebackAdapter

    original = synthetic_cad_factory(tmp_path / "target.dwg")

    result = RealT30WritebackAdapter().apply_repair_plan_v2(_repair_plan_v2(), str(original), {"dry_run_only": True})

    assert result.status == "dry_run"
    assert result.executed_actions == []
