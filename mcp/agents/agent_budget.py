from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True)
class AgentBudget:
    max_input_chars: int = 20_000
    max_output_tokens: int = 4_000
    allowed_file_count: int = 20
    allowed_context_sections: int = 8
    reject_if_task_pack_too_large: bool = True


@dataclass(frozen=True)
class BudgetValidation:
    ok: bool
    estimated_chars: int
    errors: list[str]


def estimate_chars(value: Any) -> int:
    """估算 task_pack 序列化后的字符数，不读取外部文件。"""
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True))


def validate_budget(task_pack: dict[str, Any], budget: AgentBudget | None = None) -> BudgetValidation:
    active_budget = budget or AgentBudget()
    errors: list[str] = []
    estimated = estimate_chars(task_pack)

    max_input_chars = int(task_pack.get("max_input_chars", active_budget.max_input_chars))
    max_output_tokens = int(task_pack.get("max_output_tokens", active_budget.max_output_tokens))
    allowed_files = task_pack.get("allowed_files", [])
    context_sections = task_pack.get("context_sections", [])

    if max_input_chars > active_budget.max_input_chars:
        errors.append("max_input_chars exceeds worker budget")
    if max_output_tokens > active_budget.max_output_tokens:
        errors.append("max_output_tokens exceeds worker budget")
    if not isinstance(allowed_files, list):
        errors.append("allowed_files must be a list")
    elif len(allowed_files) > active_budget.allowed_file_count:
        errors.append("allowed_files exceeds worker budget")
    if context_sections and len(context_sections) > active_budget.allowed_context_sections:
        errors.append("context_sections exceeds worker budget")
    if active_budget.reject_if_task_pack_too_large and estimated > active_budget.max_input_chars:
        errors.append("task_pack exceeds max_input_chars")

    return BudgetValidation(ok=not errors, estimated_chars=estimated, errors=errors)

