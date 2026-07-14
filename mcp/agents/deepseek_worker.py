from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent_budget import AgentBudget, estimate_chars, validate_budget
from .agent_result_schema import RESULT_SCHEMA, default_result, validate_agent_result
from .deepseek_client import _read_api_key, call_deepseek
from .task_pack_builder import FORBIDDEN_ACTIONS, REQUIRED_TASK_PACK_FIELDS


DANGEROUS_ACTION_MARKERS = {
    "sendcommand": "SendCommand is forbidden",
    "open_source_dwg": "opening source DWG is forbidden",
    "save_source_dwg": "saving source DWG is forbidden",
    "open_dwg": "opening DWG is forbidden",
    "save_dwg": "saving DWG is forbidden",
    "connect_autocad": "AutoCAD connection is forbidden",
    "hsxg": "Tianzheng command hsxg is forbidden",
    "hzgx": "Tianzheng command hzgx is forbidden",
    "gxlj": "Tianzheng command gxlj is forbidden",
    "tsaveas": "TSaveAs is forbidden",
    "tgbatplots": "tgbatplots is forbidden",
    "dcsz": "dcsz is forbidden",
    "modify_source": "source modification is forbidden",
}


def validate_task_pack_shape(task_pack: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for field in REQUIRED_TASK_PACK_FIELDS:
        if field not in task_pack:
            errors.append(f"missing task_pack field: {field}")
    forbidden_actions = task_pack.get("forbidden_actions", [])
    if not isinstance(forbidden_actions, list):
        errors.append("forbidden_actions must be a list")
    else:
        required = {item.lower() for item in FORBIDDEN_ACTIONS}
        present = {str(item).lower() for item in forbidden_actions}
        missing = sorted(required - present)
        if missing:
            errors.append(f"missing required forbidden actions: {', '.join(missing)}")
    return not errors, errors


def validate_forbidden_actions(task_pack: dict[str, Any]) -> tuple[bool, list[str]]:
    serialized = json.dumps(task_pack, ensure_ascii=False).lower()
    errors: list[str] = []

    for marker, message in DANGEROUS_ACTION_MARKERS.items():
        goal_has_marker = marker in str(task_pack.get("goal", "")).lower()
        expected_has_marker = marker in " ".join(map(str, task_pack.get("expected_outputs", []))).lower()
        tests_have_marker = marker in " ".join(map(str, task_pack.get("test_commands", []))).lower()
        if goal_has_marker or expected_has_marker or tests_have_marker:
            errors.append(message)

    if "deepseek_api_key" in serialized:
        errors.append("task_pack must not contain DEEPSEEK_API_KEY")
    if "完整聊天历史" in serialized or "full_chat_history" in serialized:
        errors.append("task_pack must not contain full chat history")
    if any(str(path).lower().endswith(".dwg") for path in task_pack.get("allowed_files", [])):
        errors.append("allowed_files must not contain DWG files")

    return not errors, errors


def run_deepseek_worker(
    task_pack: dict[str, Any],
    *,
    dry_run: bool = True,
    budget: AgentBudget | None = None,
    timeout: float = 30.0,
    temperature: float = 0.2,
) -> dict[str, Any]:
    phase = str(task_pack.get("phase", ""))

    shape_ok, shape_errors = validate_task_pack_shape(task_pack)
    if not shape_ok:
        result = default_result(phase, "BLOCKED", "; ".join(shape_errors))
        result["next_recommendation"] = "修正 task_pack 格式后重试。"
        return result

    budget_result = validate_budget(task_pack, budget)
    if not budget_result.ok:
        result = default_result(phase, "BLOCKED", "; ".join(budget_result.errors))
        result["next_recommendation"] = "缩小 task_pack 后重试。"
        return result

    forbidden_ok, forbidden_errors = validate_forbidden_actions(task_pack)
    if not forbidden_ok:
        result = default_result(phase, "BLOCKED", "; ".join(forbidden_errors))
        result["next_recommendation"] = "移除危险动作或 DWG/source 内容后重试。"
        return result

    client_result = call_deepseek(
        task_pack,
        dry_run=dry_run,
        timeout=timeout,
        max_tokens=int(task_pack.get("max_output_tokens", 4000)),
        temperature=temperature,
    )
    if not client_result.ok:
        result = default_result(phase, client_result.status, client_result.error)
        result["next_recommendation"] = "检查环境变量或网络后重试；dry_run 不需要远程调用。"
        return result

    result = client_result.content or default_result(phase, client_result.status)
    valid, errors = validate_agent_result(result)
    if not valid:
        blocked = default_result(phase, "BLOCKED", "; ".join(errors))
        blocked["next_recommendation"] = "修正 DeepSeek 返回 JSON schema 后重试。"
        return blocked
    return result


def _build_smoke_task_pack() -> dict[str, Any]:
    return {
        "phase": "AGENT-DS1.1",
        "goal": "return structured JSON ping result",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "output_schema": RESULT_SCHEMA,
    }


def _write_smoke_reports(report: dict[str, Any]) -> None:
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    json_path = reports_dir / "phase_agent_ds1_1_real_call_smoke_test.json"
    md_path = reports_dir / "phase_agent_ds1_1_real_call_smoke_test.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    decision = report["acceptance_decision"]
    md = f"""# Phase AGENT-DS1.1 Manager Final Report

## 1. Target Phase

AGENT-DS1.1 — DeepSeek Worker Real Call Smoke Test

## 2. Smoke Task

- env_key_present: {str(report["env_key_present"]).lower()}
- task_pack_size_chars: {report["task_pack_size_chars"]}
- task_pack_budget_valid: {str(report["task_pack_budget_valid"]).lower()}
- deepseek_real_call_attempted: {str(report["deepseek_real_call_attempted"]).lower()}
- deepseek_real_call_success: {str(report["deepseek_real_call_success"]).lower()}
- response_schema_valid: {str(report["response_schema_valid"]).lower()}

## 3. Safety Result

- api_key_logged: false
- full_chat_sent: false
- opened_source_dwg: false
- saved_source_dwg: false
- used_sendcommand: false
- executed_tianzheng_command: false

## 4. Acceptance Decision

{decision}

## 5. Notes

{'; '.join(report.get("notes", []))}
"""
    md_path.write_text(md, encoding="utf-8")


def run_smoke_test(timeout: float = 30.0) -> dict[str, Any]:
    """执行最小真实调用烟测；不读取项目上下文、DWG 或聊天历史。"""
    task_pack = _build_smoke_task_pack()
    budget_result = validate_budget(task_pack, AgentBudget(max_input_chars=20_000, max_output_tokens=4_000))
    env_key_present = bool(_read_api_key())

    report: dict[str, Any] = {
        "phase": "AGENT-DS1.1",
        "env_key_present": env_key_present,
        "api_key_logged": False,
        "full_chat_sent": False,
        "task_pack_size_chars": estimate_chars(task_pack),
        "task_pack_budget_valid": budget_result.ok,
        "deepseek_real_call_attempted": False,
        "deepseek_real_call_success": False,
        "response_schema_valid": False,
        "opened_source_dwg": False,
        "saved_source_dwg": False,
        "used_sendcommand": False,
        "executed_tianzheng_command": False,
        "dangerous_command_executed": False,
        "notes": [],
        "acceptance_decision": "PARTIAL",
    }

    if not budget_result.ok:
        report["notes"].append("task_pack budget invalid: " + "; ".join(budget_result.errors))
        _write_smoke_reports(report)
        return report

    if not env_key_present:
        report["notes"].append("environment key is not present; real call skipped safely")
        _write_smoke_reports(report)
        return report

    report["deepseek_real_call_attempted"] = True
    client_result = call_deepseek(
        task_pack,
        dry_run=False,
        timeout=timeout,
        max_tokens=800,
        temperature=0.0,
    )
    report["deepseek_real_call_success"] = client_result.ok

    if client_result.content:
        schema_ok, schema_errors = validate_agent_result(client_result.content)
        report["response_schema_valid"] = schema_ok
        if schema_errors:
            report["notes"].append("response schema invalid: " + "; ".join(schema_errors))
    elif client_result.error:
        # 只记录错误类别，不写入可能包含环境细节的原始错误正文。
        report["notes"].append("real call failed safely")

    if report["deepseek_real_call_success"] and report["response_schema_valid"]:
        report["acceptance_decision"] = "PASS"
        report["notes"].append("real DeepSeek smoke call returned valid agent result schema")
    else:
        report["acceptance_decision"] = "PARTIAL"
        if not report["notes"]:
            report["notes"].append("real call completed but response schema was not valid")

    _write_smoke_reports(report)
    return report
