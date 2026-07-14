from __future__ import annotations


def test_snapper_snaps_near_pipe_endpoint_but_not_far_endpoint() -> None:
    from mcp.repair_actions.models import RepairAction, RepairPlanV2
    from mcp.repair_actions.snapper import snap_repair_actions_to_target_graph

    action = RepairAction(
        "a1",
        "add_pipe",
        "cad_modelspace",
        {"type": "polyline", "points": [[1.0, 1.0], [500.0, 500.0]]},
        "给水",
        "DN50",
        "PIPE-给水",
        "p1",
        "vision",
        0.9,
        True,
        "missing",
        "pending",
        [],
        {},
    )
    plan = RepairPlanV2("plan", "ref", "target", [action], [], [], 0.9, [], [], {})
    snapped = snap_repair_actions_to_target_graph(
        plan,
        {"nodes": [{"id": "n1", "position": [0.0, 0.0, 0]}]},
        {"tolerance": 5.0},
    )

    points = snapped.actions[0].geometry["points"]
    assert points[0] == [0.0, 0.0]
    assert points[1] == [500.0, 500.0]
    assert snapped.actions[0].metadata["snap_applied"] is True

