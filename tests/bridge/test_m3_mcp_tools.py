import pytest
from mcp.bridge.mcp_tools import (
    tianzheng_validate_action,
    tianzheng_validate_action_batch,
    tianzheng_dry_run_action_batch,
    tianzheng_build_scan_report,
    tianzheng_manual_review_intake,
    tianzheng_safety_gate_status,
    tianzheng_explain_blockers,
    call_tool,
)

class TestValidateAction:
    def test_valid_add_pipe(self):
        r = tianzheng_validate_action({"action_type": "add_pipe", "object_type": "TDbPipe"})
        assert r["success"] is True
        assert r["safety_flags"]["d1_allowed"] is False

    def test_invalid_action_type(self):
        r = tianzheng_validate_action({"action_type": "fake_action"})
        assert r["success"] is False

    def test_rejects_execute_flag(self):
        r = tianzheng_validate_action({"action_type": "add_pipe", "execute": "true"})
        assert r["success"] is False

    def test_rejects_real_flag(self):
        r = tianzheng_validate_action({"action_type": "add_pipe", "real": True})
        assert r["success"] is False

class TestValidateActionBatch:
    def test_valid_batch(self):
        r = tianzheng_validate_action_batch({"actions": [
            {"action_type": "add_pipe", "object_type": "TDbPipe"},
            {"action_type": "add_valve", "object_type": "TDbPipeValve"},
        ]})
        assert r["success"] is True
        assert r["data"]["total"] == 2

    def test_conflict_detection(self):
        r = tianzheng_validate_action_batch({"actions": [
            {"action_type": "add_pipe", "object_type": "TDbPipe", "geometry": {"x": 0, "y": 0}},
            {"action_type": "add_pipe", "object_type": "TDbPipe", "geometry": {"x": 10, "y": 10}},
        ]})
        assert r["data"]["conflict_count"] >= 1

class TestDryRunActionBatch:
    def test_dry_run_result(self):
        r = tianzheng_dry_run_action_batch({"actions": [
            {"action_type": "add_pipe", "object_type": "TDbPipe"},
        ]})
        assert r["success"] is True
        assert r["data"]["executable_actions"] == 0

    def test_no_autocad_connect(self):
        r = tianzheng_dry_run_action_batch({"actions": []})
        assert r["safety_flags"]["autocad_connected"] is False

class TestBuildScanReport:
    def test_empty_report(self):
        r = tianzheng_build_scan_report({"output_format": "markdown"})
        assert r["success"] is True
        assert "markdown" in r["data"].get("report", {})

class TestManualReviewIntake:
    def test_pass_visual_only(self):
        r = tianzheng_manual_review_intake({"decision": "PASS_VISUAL_ONLY"})
        assert r["success"] is True
        d1 = r["data"]["next_phase_recommendation"]["d1_allowed"]
        assert d1 is False

    def test_fail_visual(self):
        r = tianzheng_manual_review_intake({"decision": "FAIL_VISUAL"})
        assert r["success"] is True
        assert r["blocking_issues"]

class TestSafetyGateStatus:
    def test_default_all_false(self):
        r = tianzheng_safety_gate_status()
        s = r["data"]["safety_status"]
        assert s["d1_allowed"] is False
        assert s["production_d1_allowed"] is False
        assert s["source_modification_allowed"] is False
        assert s["autocad_connected"] is False

class TestExplainBlockers:
    def test_has_blockers(self):
        r = tianzheng_explain_blockers({})
        assert r["success"] is True
        assert r["data"]["blocker_count"] >= 4

class TestCallTool:
    def test_valid_tool(self):
        r = call_tool("tianzheng_safety_gate_status")
        assert r["success"] is True

    def test_unknown_tool(self):
        r = call_tool("nonexistent_tool")
        assert r["success"] is False
