from __future__ import annotations

import uuid

import pytest

from mcp.agents.agent_budget import AgentBudget
from mcp.agents.deepseek_worker import run_deepseek_worker
from mcp.agents.task_pack_builder import build_task_pack


def test_worker_dry_run_returns_valid_result_without_autocad(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    task_pack = build_task_pack(
        phase="AGENT-DS1",
        goal="编写非视觉报告草稿",
        allowed_files=["mcp/agents/deepseek_worker.py"],
    )

    result = run_deepseek_worker(task_pack, dry_run=True)

    assert result["status"] == "PARTIAL"
    assert result["safety_result"]["opened_source_dwg"] is False
    assert result["safety_result"]["saved_source_dwg"] is False
    assert result["safety_result"]["used_sendcommand"] is False
    assert result["safety_result"]["executed_tianzheng_command"] is False


def test_worker_rejects_task_pack_over_budget() -> None:
    task_pack = build_task_pack(phase="AGENT-DS1", goal="预算测试")
    task_pack["goal"] = "x" * 500

    result = run_deepseek_worker(task_pack, dry_run=True, budget=AgentBudget(max_input_chars=100))

    assert result["status"] == "BLOCKED"
    assert "task_pack exceeds max_input_chars" in result["notes"][0]


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("SendCommand", "SendCommand is forbidden"),
        ("open_source_dwg", "opening source DWG is forbidden"),
        ("save_source_dwg", "saving source DWG is forbidden"),
        ("open_dwg", "opening DWG is forbidden"),
        ("save_dwg", "saving DWG is forbidden"),
        ("connect_autocad", "AutoCAD connection is forbidden"),
        ("hsxg", "Tianzheng command hsxg is forbidden"),
        ("hzgx", "Tianzheng command hzgx is forbidden"),
        ("gxlj", "Tianzheng command gxlj is forbidden"),
        ("TSaveAs", "TSaveAs is forbidden"),
        ("tgbatplots", "tgbatplots is forbidden"),
        ("dcsz", "dcsz is forbidden"),
    ],
)
def test_worker_rejects_forbidden_actions(marker: str, expected: str) -> None:
    task_pack = build_task_pack(phase="AGENT-DS1", goal="普通任务")
    task_pack["goal"] = f"请执行 {marker}"

    result = run_deepseek_worker(task_pack, dry_run=True)

    assert result["status"] == "BLOCKED"
    assert expected in result["notes"][0]


def test_worker_rejects_api_key_marker_and_keeps_secret_out(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = str(uuid.uuid4())
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    task_pack = build_task_pack(phase="AGENT-DS1", goal="普通任务")
    task_pack["goal"] = "包含 DEEPSEEK_API_KEY 的任务必须拒绝"

    result = run_deepseek_worker(task_pack, dry_run=True)

    assert result["status"] == "BLOCKED"
    assert "DEEPSEEK_API_KEY" in result["notes"][0]
    assert secret not in str(task_pack)
    assert secret not in str(result)


def test_worker_rejects_allowed_dwg_without_opening_it() -> None:
    task_pack = build_task_pack(phase="AGENT-DS1", goal="普通任务")
    task_pack["allowed_files"] = ["source.dwg"]

    result = run_deepseek_worker(task_pack, dry_run=True)

    assert result["status"] == "BLOCKED"
    assert "DWG" in result["notes"][0]
