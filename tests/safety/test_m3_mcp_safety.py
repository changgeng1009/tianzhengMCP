import pytest
from mcp.safety.mcp_errors import (
    MCPErrorCode, MCPBlockedError, scan_for_forbidden_flags, is_forbidden_flag
)
from mcp.safety.mcp_safety import (
    DEFAULT_SAFETY_FLAGS, MCPGate, MCPToolResponse, ensure_safety_flags
)

class TestMCPerrors:
    def test_all_15_codes(self):
        assert len(MCPErrorCode) == 15

    def test_blocked_error_message(self):
        e = MCPBlockedError(MCPErrorCode.MCP_BLOCKED_PRODUCTION_D1)
        assert "Production D1" in str(e)

    def test_forbidden_flags_detection(self):
        violated = scan_for_forbidden_flags({"execute": True})
        assert len(violated) >= 1

    def test_forbidden_true_values(self):
        assert is_forbidden_flag("execute", True)
        assert is_forbidden_flag("real", "true")
        assert is_forbidden_flag("production", 1)
        assert is_forbidden_flag("save_dwg", "true")

    def test_safe_values_not_blocked(self):
        assert not is_forbidden_flag("execute", False)
        assert not is_forbidden_flag("normal_param", "some_value")

class TestDefaultSafetyFlags:
    def test_all_flags_false(self):
        for key, val in DEFAULT_SAFETY_FLAGS.items():
            assert val is False, f"{key} should be False"

    def test_key_count(self):
        assert len(DEFAULT_SAFETY_FLAGS) == 15

class TestMCPGate:
    def test_check_forbidden_raises(self):
        with pytest.raises(MCPBlockedError):
            MCPGate.check_forbidden_input({"execute": True})

    def test_check_safe_passes(self):
        MCPGate.check_forbidden_input({"action_type": "add_pipe"})

    def test_get_safety_status(self):
        status = MCPGate.get_safety_status()
        assert status["d1_allowed"] is False

class TestEnsureSafetyFlags:
    def test_adds_missing_flags(self):
        result = ensure_safety_flags({"data": "test"})
        assert "safety_flags" in result
        assert result["safety_flags"]["d1_allowed"] is False

    def test_preserves_existing_flags(self):
        result = ensure_safety_flags({"safety_flags": {"d1_allowed": False}})
        assert result["safety_flags"]["d1_allowed"] is False
