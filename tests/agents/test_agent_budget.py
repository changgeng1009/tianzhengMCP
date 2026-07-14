from __future__ import annotations

from mcp.agents.agent_budget import AgentBudget, estimate_chars, validate_budget


def test_estimate_chars_counts_serialized_task_pack() -> None:
    assert estimate_chars({"phase": "AGENT-DS1", "goal": "测试"}) > 0


def test_task_pack_over_budget_is_rejected() -> None:
    task_pack = {
        "phase": "AGENT-DS1",
        "goal": "x" * 200,
        "allowed_files": [],
        "max_input_chars": 50,
        "max_output_tokens": 100,
    }
    result = validate_budget(task_pack, AgentBudget(max_input_chars=50, max_output_tokens=100))
    assert not result.ok
    assert "task_pack exceeds max_input_chars" in result.errors


def test_allowed_file_count_is_enforced() -> None:
    task_pack = {
        "phase": "AGENT-DS1",
        "goal": "测试",
        "allowed_files": [f"file_{index}.py" for index in range(3)],
        "max_input_chars": 20_000,
        "max_output_tokens": 100,
    }
    result = validate_budget(task_pack, AgentBudget(allowed_file_count=2))
    assert not result.ok
    assert "allowed_files exceeds worker budget" in result.errors

