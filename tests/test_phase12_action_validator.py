from __future__ import annotations


def test_validator_blocks_missing_dn_or_system_from_auto_execute() -> None:
    from mcp.repair_actions.action_validator import validate_repair_plan_v2
    from mcp.repair_actions.models import RepairAction, RepairPlanV2

    action = RepairAction(
        "a1", "add_pipe", "cad_modelspace", {"type": "polyline", "points": [[0, 0], [100, 0]]},
        None, None, "PIPE", "p1", "vision", 0.9, True, "missing", "pending", [], {}
    )
    plan = RepairPlanV2("plan", "ref", "target", [action], [], [], 0.9, [], [], {})

    result = validate_repair_plan_v2(plan, {})

    assert result["valid"] is False
    assert result["auto_executable"] == []
    assert result["rejected"][0]["action_id"] == "a1"

