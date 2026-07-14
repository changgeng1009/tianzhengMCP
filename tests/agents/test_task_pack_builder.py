from __future__ import annotations

import os
import uuid

import pytest

from mcp.agents.task_pack_builder import REQUIRED_TASK_PACK_FIELDS, build_task_pack


def test_task_pack_contains_required_fields_and_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = str(uuid.uuid4())
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    task_pack = build_task_pack(
        phase="AGENT-DS1",
        goal="编写 schema 草稿",
        allowed_files=["mcp/agents/agent_result_schema.py"],
        expected_outputs=["结构化 JSON"],
    )

    for field in REQUIRED_TASK_PACK_FIELDS:
        assert field in task_pack
    assert secret not in str(task_pack)
    assert "DEEPSEEK_API_KEY" not in str(task_pack)
    assert "full_chat_history" not in str(task_pack)
    assert "完整聊天历史" not in str(task_pack)


def test_task_pack_rejects_allowed_dwg() -> None:
    with pytest.raises(ValueError, match="DWG"):
        build_task_pack(
            phase="AGENT-DS1",
            goal="分析文件",
            allowed_files=["source.dwg"],
        )


def test_task_pack_rejects_sensitive_marker() -> None:
    with pytest.raises(ValueError, match="forbidden marker"):
        build_task_pack(
            phase="AGENT-DS1",
            goal="full_chat_history should not pass",
            allowed_files=[],
        )

