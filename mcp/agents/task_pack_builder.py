from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Iterable

from .agent_budget import AgentBudget, validate_budget
from .agent_result_schema import RESULT_SCHEMA


REQUIRED_TASK_PACK_FIELDS = [
    "phase",
    "goal",
    "allowed_files",
    "forbidden_files",
    "forbidden_actions",
    "safety_rules",
    "expected_outputs",
    "test_commands",
    "output_schema",
    "max_input_chars",
    "max_output_tokens",
]

FORBIDDEN_ACTIONS = [
    "connect_autocad",
    "open_dwg",
    "open_source_dwg",
    "save_dwg",
    "save_source_dwg",
    "SendCommand",
    "hsxg",
    "hzgx",
    "gxlj",
    "TSaveAs",
    "tgbatplots",
    "dcsz",
    "modify_source",
    "read_api_key",
    "log_api_key",
    "send_full_chat",
]

SAFETY_RULES = [
    "d1_allowed=false",
    "production_d1_allowed=false",
    "production_d1_executed=false",
    "source_modification_allowed=false",
    "source_dwg_opened=false",
    "source_dwg_saved=false",
    "save_called_on_source=false",
    "production_allowed=false",
    "API key 只能由 deepseek_client 从运行环境读取，不得进入 task_pack",
    "不得包含完整对话原文、DWG 二进制内容、source DWG 内容或无关历史报告全文",
]

SENSITIVE_MARKERS = [
    "DEEPSEEK_API_KEY",
    "full_chat_history",
    "完整聊天历史",
    "BEGIN CONVERSATION",
    "source dwg binary",
]


def _as_list(value: Iterable[str] | None) -> list[str]:
    return list(value or [])


def _assert_no_sensitive_content(task_pack: dict[str, Any]) -> None:
    serialized = json.dumps(task_pack, ensure_ascii=False)
    for marker in SENSITIVE_MARKERS:
        if marker in serialized:
            raise ValueError(f"task_pack contains forbidden marker: {marker}")

    for field in ("allowed_files", "forbidden_files"):
        for item in task_pack.get(field, []):
            suffix = Path(str(item)).suffix.lower()
            if field == "allowed_files" and suffix == ".dwg":
                raise ValueError("DWG files are not allowed in allowed_files")


def build_task_pack(
    *,
    phase: str,
    goal: str,
    allowed_files: Iterable[str] | None = None,
    forbidden_files: Iterable[str] | None = None,
    forbidden_actions: Iterable[str] | None = None,
    safety_rules: Iterable[str] | None = None,
    expected_outputs: Iterable[str] | None = None,
    test_commands: Iterable[str] | None = None,
    output_schema: dict[str, Any] | None = None,
    budget: AgentBudget | None = None,
) -> dict[str, Any]:
    active_budget = budget or AgentBudget()
    task_pack = {
        "phase": phase,
        "goal": goal,
        "allowed_files": _as_list(allowed_files),
        "forbidden_files": _as_list(forbidden_files),
        "forbidden_actions": sorted(set(FORBIDDEN_ACTIONS + _as_list(forbidden_actions))),
        "safety_rules": _as_list(safety_rules) or list(SAFETY_RULES),
        "expected_outputs": _as_list(expected_outputs),
        "test_commands": _as_list(test_commands),
        "output_schema": deepcopy(output_schema or RESULT_SCHEMA),
        "max_input_chars": active_budget.max_input_chars,
        "max_output_tokens": active_budget.max_output_tokens,
    }

    missing = [key for key in REQUIRED_TASK_PACK_FIELDS if key not in task_pack]
    if missing:
        raise ValueError(f"task_pack missing required fields: {missing}")

    _assert_no_sensitive_content(task_pack)
    budget_result = validate_budget(task_pack, active_budget)
    if not budget_result.ok:
        raise ValueError("; ".join(budget_result.errors))
    return task_pack
