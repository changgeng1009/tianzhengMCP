import sys, os
import pytest
from mcp.bridge.mcp_tools import call_tool

FORBIDDEN_TOOLS_KEYWORDS = ("autocad_connected", "dwg_opened", "sendcommand_used",
    "tianzheng_command_executed", "source_write_attempted", "save_called_on_source",
    "http_bridge_called", "d1_allowed", "production_d1_allowed",
    "production_d1_executed", "source_modification_allowed", "real_execution_allowed")

ALL_M3_TOOLS = [
    "tianzheng_validate_action", "tianzheng_validate_action_batch",
    "tianzheng_dry_run_action_batch", "tianzheng_build_scan_report",
    "tianzheng_manual_review_intake", "tianzheng_safety_gate_status",
    "tianzheng_explain_blockers",
]

class TestNoRealExecution:
    def test_all_safety_flags_false(self):
        for tool_name in ALL_M3_TOOLS:
            result = call_tool(tool_name, {})
            flags = result.get("safety_flags", {})
            for key in FORBIDDEN_TOOLS_KEYWORDS:
                assert flags.get(key, None) is False, f"{tool_name}: {key} should be False but got {flags.get(key)}"

    def test_execute_true_rejected(self):
        for tool_name in ALL_M3_TOOLS:
            result = call_tool(tool_name, {"execute": True})
            assert result["success"] is False or result["safety_flags"]["real_execution_allowed"] is False, f"{tool_name} should reject execute=true"

    def test_d1_allowed_true_rejected(self):
        for tool_name in ALL_M3_TOOLS:
            result = call_tool(tool_name, {"d1_allowed": True})
            assert result["success"] is False, f"{tool_name} should reject d1_allowed=true"

    def test_connect_autocad_rejected(self):
        for tool_name in ALL_M3_TOOLS:
            result = call_tool(tool_name, {"connect_autocad": True})
            assert result["success"] is False, f"{tool_name} should reject connect_autocad=true"

    def test_open_dwg_rejected(self):
        for tool_name in ALL_M3_TOOLS:
            result = call_tool(tool_name, {"open_dwg": True})
            assert result["success"] is False, f"{tool_name} should reject open_dwg=true"

    def test_save_dwg_rejected(self):
        for tool_name in ALL_M3_TOOLS:
            result = call_tool(tool_name, {"save_dwg": True})
            assert result["success"] is False, f"{tool_name} should reject save_dwg=true"

    def test_http_bridge_rejected(self):
        for tool_name in ALL_M3_TOOLS:
            result = call_tool(tool_name, {"http_bridge_called": True})
            assert result["success"] is False, f"{tool_name} should reject http_bridge_called=true"

    def test_no_win32com_import(self):
        from mcp.bridge import mcp_tools

        assert "win32com" not in mcp_tools.__dict__
        assert "comtypes" not in mcp_tools.__dict__

    def test_no_sendcommand_in_mcp_code(self):
        import mcp.bridge.mcp_tools as mt
        source = str(mt.__dict__)
        assert "SendCommand" not in source

    def test_no_localhost_in_mcp_code(self):
        import mcp.bridge.mcp_tools as mt
        source = str(mt.__dict__)
        assert "localhost" not in source
        assert "127.0.0.1" not in source
