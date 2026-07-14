from __future__ import annotations


def test_conflict_checker_moves_duplicate_pipe_to_review() -> None:
    from mcp.repair_actions.conflict_checker import check_repair_action_conflicts
    from mcp.repair_actions.models import RepairAction, RepairPlanV2

    action = RepairAction(
        "a1", "add_pipe", "cad_modelspace", {"type": "polyline", "points": [[0, 0], [100, 0]]},
        "给水", "DN50", "PIPE-给水", "p1", "vision", 0.9, True, "missing", "pending", [], {}
    )
    plan = RepairPlanV2("plan", "ref", "target", [action], [], [], 0.9, [], [], {})

    checked = check_repair_action_conflicts(
        plan,
        {"pipes": [{"id": "target_p", "start": [0.5, 0, 0], "end": [100.5, 0, 0]}]},
        {"tolerance": 2.0},
    )

    assert checked.actions == []
    assert checked.review_actions[0].metadata["conflict"] == "duplicate_existing_pipe"

