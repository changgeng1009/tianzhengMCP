from __future__ import annotations

from mcp.acceptance.stage2_skill_packaging import (
    FINAL_DELEGATED_TASK_ID,
    build_stage2_delegation_pack,
    contains_sensitive_material,
    inventory_skill,
    run_stage2_delegation,
)


def test_stage2_deepseek_pack_is_static_safe_and_under_budget() -> None:
    pack = build_stage2_delegation_pack()
    assert pack["task_id"] == FINAL_DELEGATED_TASK_ID
    assert pack["max_input_chars"] == 20_000
    assert pack["max_output_tokens"] == 1_500
    assert contains_sensitive_material(pack) is False
    assert all(not path.lower().endswith(".dwg") for path in pack["allowed_files"])
    assert "create_tdb_pipe" in pack["goal"]
    assert "allow_automatic_fallback=false" in pack["goal"]
    assert "用户姓名" not in pack["goal"]


def test_stage2_delegation_records_safe_missing_key_without_fabrication(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("worker must not be called when the environment key is unavailable")

    monkeypatch.setattr("mcp.acceptance.stage2_skill_packaging.run_deepseek_worker", fail_if_called)
    record = run_stage2_delegation()
    assert record["deepseek_worker_used"] is True
    assert record["deepseek_available"] is False
    assert record["deepseek_call_attempted"] is False
    assert record["call_succeeded"] is False
    assert record["delegated_task_id"] == FINAL_DELEGATED_TASK_ID
    assert record["accepted_count"] == 0
    assert record["full_chat_sent_to_deepseek"] is False
    assert record["api_key_sent_to_deepseek"] is False
    assert record["autocad_execution_authorized"] is False


def test_stage2_delegation_calls_worker_only_when_key_is_present(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-placeholder")
    calls = []

    def fake_worker(pack, **kwargs):
        calls.append((pack, kwargs))
        return {"status": "PASS", "notes": ["static review complete"]}

    monkeypatch.setattr("mcp.acceptance.stage2_skill_packaging.run_deepseek_worker", fake_worker)
    record = run_stage2_delegation()

    assert len(calls) == 1
    assert calls[0][0]["task_id"] == FINAL_DELEGATED_TASK_ID
    assert record["deepseek_call_attempted"] is True
    assert record["call_succeeded"] is True


def test_skill_inventory_has_required_counts() -> None:
    inventory = inventory_skill()
    assert len(inventory["workflow_names"]) == 8
    assert len(inventory["schema_names"]) == 9
    assert len(inventory["example_names"]) == 6
    assert len(inventory["prompt_names"]) == 5
    assert len(inventory["template_names"]) == 5
