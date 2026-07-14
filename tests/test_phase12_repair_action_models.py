from __future__ import annotations


def test_repair_action_and_plan_serialize() -> None:
    from mcp.repair_actions.models import RepairAction, RepairPlanV2

    action = RepairAction(
        action_id="act_1",
        action_type="add_pipe",
        target_space="cad_modelspace",
        geometry={"type": "polyline", "points": [[0, 0], [100, 0]]},
        system="给水",
        dn="DN50",
        layer="PIPE-给水",
        source_element_id="p1",
        source_type="vision",
        confidence=0.91,
        auto_execute=True,
        reason="missing pipe",
        validation_status="pending",
        warnings=[],
        metadata={},
    )
    plan = RepairPlanV2(
        plan_id="plan_1",
        source_reference_graph_id="ref",
        target_graph_id="target",
        actions=[action],
        review_actions=[],
        rejected_actions=[],
        confidence=0.91,
        warnings=[],
        errors=[],
        metadata={},
    )

    data = plan.to_dict()

    assert data["actions"][0]["action_type"] == "add_pipe"
    assert data["actions"][0]["target_space"] == "cad_modelspace"

