from __future__ import annotations


def test_dry_run_simulates_without_real_cad_and_report_summarizes() -> None:
    from mcp.repair_actions.dry_run import dry_run_repair_plan
    from mcp.repair_actions.models import RepairAction, RepairPlanV2
    from mcp.repair_actions.report import generate_repair_action_report

    action = RepairAction(
        "a1", "add_pipe", "cad_modelspace", {"type": "polyline", "points": [[0, 0], [100, 0]]},
        "给水", "DN50", "PIPE-给水", "p1", "vision", 0.9, True, "missing", "valid", [], {}
    )
    plan = RepairPlanV2("plan", "ref", "target", [action], [], [], 0.9, [], [], {})

    dry_run = dry_run_repair_plan(plan, {})
    report = generate_repair_action_report(plan, dry_run)

    assert dry_run.valid is True
    assert dry_run.simulated_entities[0]["dry_run"] is True
    assert report["summary"]["auto_executable"] == 1

