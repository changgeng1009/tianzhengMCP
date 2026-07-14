from __future__ import annotations

import logging
import uuid

import pytest

from mcp.agents.deepseek_client import call_deepseek
from mcp.agents.task_pack_builder import build_task_pack


def test_missing_api_key_returns_graceful_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    task_pack = build_task_pack(phase="AGENT-DS1", goal="测试 graceful failure")

    result = call_deepseek(task_pack, dry_run=False)

    assert not result.ok
    assert result.status == "BLOCKED"
    assert result.error
    assert "not set" in result.error


def test_api_key_does_not_appear_in_logs_or_result(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = str(uuid.uuid4())
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    task_pack = build_task_pack(phase="AGENT-DS1", goal="测试 dry_run")

    with caplog.at_level(logging.DEBUG):
        result = call_deepseek(task_pack, dry_run=True)

    assert result.ok
    assert secret not in caplog.text
    assert secret not in str(result.to_dict())
    assert secret not in str(task_pack)


def test_dry_run_mode_runs_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    task_pack = build_task_pack(phase="AGENT-DS1", goal="测试 dry_run")

    result = call_deepseek(task_pack, dry_run=True)

    assert result.ok
    assert result.content
    assert result.content["status"] == "PARTIAL"

