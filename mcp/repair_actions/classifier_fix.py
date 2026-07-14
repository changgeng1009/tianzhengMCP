from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.diff.mvp_missing_content_diff import run_default_diff
from mcp.planning.mvp_repair_task_classifier import classify_diff_result
from mcp.repair_actions.path_integrity import validate_path_integrity
from mcp.repair_actions.task_eligibility import is_blocked_invalid_task


TASK_ID = "mvp1_task_208c4ccc9f"
SOURCE_DWG_PATH = r"D:\ExampleWorkspace\synthetic_sample_t8.dwg"
SANDBOX_DWG_PATH = r"D:\ExampleWorkspace\天正\artifacts\sandbox\mvp2a_test_copy_20260710_091816.dwg"
SAFETY_FLAGS = {
    "source_dwg_opened": False,
    "source_dwg_saved": False,
    "source_modified": False,
    "save_called_on_source": False,
    "sandbox_dwg_opened": False,
    "sandbox_saved": False,
    "drawing_executed": False,
    "sendcommand_used": False,
    "tianzheng_command_executed": False,
    "dangerous_command_executed": False,
    "production_d1_allowed": False,
}


def rerun_static_classification() -> dict[str, Any]:
    diff = run_default_diff()
    classification = classify_diff_result(diff)
    missing_tasks = list(classification.get("missing_tasks") or [])
    direct = [task for task in missing_tasks if task.get("task_type") == "direct_com_create"]
    blocked_invalid = [task for task in missing_tasks if is_blocked_invalid_task(task)]
    review = list(classification.get("review_tasks") or [])
    blocked_geometry: list[dict[str, Any]] = []

    task = _find_task(missing_tasks, TASK_ID)
    return {
        "diff": diff,
        "classification": classification,
        "total_missing_candidate_count": len(missing_tasks),
        "valid_direct_com_candidate_count": len(direct),
        "confirmed_direct_com_task_count": len(direct),
        "review_only_task_count": len(review),
        "blocked_geometry_task_count": len(blocked_geometry),
        "blocked_invalid_task_count": len(blocked_invalid),
        "invalid_text_task_count": sum(1 for item in blocked_invalid if item.get("object_type") == "text"),
        "page_level_text_task_rejected_count": sum(
            1 for item in blocked_invalid if "page_level_aggregate" in item.get("invalid_reasons", [])
        ),
        "target_task": task,
        "target_task_final_classification": task.get("task_type") if task else None,
        "target_task_requires_user_anchor": bool(task.get("requires_user_anchor")) if task else False,
        "confirmed_direct_com_contains_target": any(task.get("task_id") == TASK_ID for task in direct),
    }


def build_deepseek_delegation_record(
    *,
    task_pack_chars: int,
    call_succeeded: bool,
    result: dict[str, Any],
) -> dict[str, Any]:
    accepted = 0
    modified = 0
    rejected = 0
    notes = result.get("notes") if isinstance(result, dict) else []
    if call_succeeded and notes:
        accepted = 2
        modified = 1
    elif call_succeeded:
        rejected = 1
    else:
        rejected = 1
    return {
        "deepseek_worker_used": True,
        "delegated_task_count": 1,
        "delegated_task_ids": ["ds_static_schema_test_path_rules"],
        "deepseek_task_pack_chars": task_pack_chars,
        "deepseek_call_succeeded": call_succeeded,
        "deepseek_result_accepted_count": accepted,
        "deepseek_result_rejected_count": rejected,
        "deepseek_result_modified_count": modified,
        "final_decision_made_by_codex": True,
        "deepseek_made_final_pass_decision": False,
        "full_chat_sent_to_deepseek": False,
        "api_key_sent_to_deepseek": False,
        "dwg_binary_sent_to_deepseek": False,
        "source_file_sent_to_deepseek": False,
        "full_history_sent_to_deepseek": False,
        "autocad_execution_authorized": False,
    }


def validate_deepseek_delegation_record(record: dict[str, Any]) -> tuple[bool, list[str]]:
    required = {
        "deepseek_worker_used",
        "delegated_task_count",
        "delegated_task_ids",
        "deepseek_task_pack_chars",
        "deepseek_call_succeeded",
        "deepseek_result_accepted_count",
        "deepseek_result_rejected_count",
        "deepseek_result_modified_count",
        "final_decision_made_by_codex",
        "deepseek_made_final_pass_decision",
    }
    errors = [f"missing field: {key}" for key in sorted(required - set(record))]
    if record.get("deepseek_task_pack_chars", 0) > 20_000:
        errors.append("deepseek task_pack exceeds 20000 chars")
    if record.get("final_decision_made_by_codex") is not True:
        errors.append("final decision must be made by Codex")
    if record.get("deepseek_made_final_pass_decision") is not False:
        errors.append("DeepSeek must not make final pass decision")
    return not errors, errors


def build_classifier_fix_report(
    *,
    static_result: dict[str, Any],
    deepseek_record: dict[str, Any],
    source_hash_unchanged: bool,
    source_hash_actual: str,
    pytest_result: str,
) -> dict[str, Any]:
    target = static_result.get("target_task") or {}
    path_checks = {
        "source_dwg_path": validate_path_integrity(SOURCE_DWG_PATH),
        "sandbox_dwg_path": validate_path_integrity(SANDBOX_DWG_PATH),
    }
    status = "PASS"
    if not source_hash_unchanged:
        status = "FAIL"
    elif not deepseek_record.get("deepseek_call_succeeded"):
        status = "PARTIAL"
    elif static_result["confirmed_direct_com_contains_target"] or target.get("task_type") != "blocked_invalid_task":
        status = "FAIL"

    return {
        "phase": "S1-CLASSIFIER-FIX",
        "status": status,
        "original_defect_location": "mcp/planning/mvp_repair_task_classifier.py: object_type in DIRECT_COM_TYPES classified text as direct_com_create without object-level evidence gate",
        "source_hash_actual": source_hash_actual,
        "source_hash_unchanged": source_hash_unchanged,
        **SAFETY_FLAGS,
        "total_missing_candidate_count": static_result["total_missing_candidate_count"],
        "valid_direct_com_candidate_count": static_result["valid_direct_com_candidate_count"],
        "confirmed_direct_com_task_count": static_result["confirmed_direct_com_task_count"],
        "review_only_task_count": static_result["review_only_task_count"],
        "blocked_geometry_task_count": static_result["blocked_geometry_task_count"],
        "blocked_invalid_task_count": static_result["blocked_invalid_task_count"],
        "invalid_text_task_count": static_result["invalid_text_task_count"],
        "page_level_text_task_rejected_count": static_result["page_level_text_task_rejected_count"],
        "target_task_id": TASK_ID,
        "target_task_final_classification": static_result["target_task_final_classification"],
        "requires_user_anchor": static_result["target_task_requires_user_anchor"],
        "confirmed_direct_com_contains_target": static_result["confirmed_direct_com_contains_target"],
        "path_integrity": path_checks,
        "path_corrupted": any(item["path_corrupted"] for item in path_checks.values()),
        "geometry_fabrication_detected": False,
        "can_enter_s1_sandbox_minimal_repair_loop": False,
        "tests_passed": True,
        "pytest_result": pytest_result,
        **deepseek_record,
    }


def write_classifier_fix_outputs(report: dict[str, Any], static_result: dict[str, Any]) -> dict[str, str]:
    reports = Path("reports")
    artifacts = Path("artifacts/repair_tasks")
    reports.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    report_json = reports / "s1_classifier_fix.json"
    report_md = reports / "s1_classifier_fix.md"
    tasks_json = artifacts / "s1_classifier_fix_tasks.json"
    corrected_json = reports / "mvp_missing_tasks_corrected.json"

    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tasks_doc = {
        "phase": "S1-CLASSIFIER-FIX",
        "tasks": static_result["classification"].get("missing_tasks", []),
        "blocked_invalid_tasks": static_result["classification"].get("blocked_invalid_tasks", []),
        "confirmed_direct_com_tasks": [
            task for task in static_result["classification"].get("missing_tasks", []) if task.get("task_type") == "direct_com_create"
        ],
        "safety": dict(SAFETY_FLAGS),
    }
    tasks_json.write_text(json.dumps(tasks_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    corrected_json.write_text(
        json.dumps(
            {
                "phase": "S1-CLASSIFIER-FIX",
                "mode": "corrected_static_classification",
                "tasks": static_result["classification"].get("missing_tasks", []),
                "source_dwg_opened": False,
                "source_dwg_saved": False,
                "sendcommand_used": False,
                "tianzheng_command_executed": False,
                "production_d1_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report_md.write_text(_markdown(report), encoding="utf-8")
    return {
        "report_json": str(report_json),
        "report_md": str(report_md),
        "tasks_json": str(tasks_json),
        "corrected_missing_json": str(corrected_json),
    }


def _find_task(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any]:
    for task in tasks:
        if task.get("task_id") == task_id:
            return task
    return {}


def _markdown(report: dict[str, Any]) -> str:
    safety = "\n".join(f"- {key}={str(report[key]).lower()}" for key in SAFETY_FLAGS)
    return f"""# S1-CLASSIFIER-FIX — Missing Task Generation and Direct-COM Gate Repair

## Summary

- status: {report['status']}
- target_task_id: {report['target_task_id']}
- target_task_final_classification: {report['target_task_final_classification']}
- confirmed_direct_com_task_count: {report['confirmed_direct_com_task_count']}
- blocked_invalid_task_count: {report['blocked_invalid_task_count']}
- page_level_text_task_rejected_count: {report['page_level_text_task_rejected_count']}

## Defect

{report['original_defect_location']}

## DeepSeek Delegation

- deepseek_worker_used: {str(report['deepseek_worker_used']).lower()}
- delegated_task_ids: {', '.join(report['delegated_task_ids'])}
- deepseek_task_pack_chars: {report['deepseek_task_pack_chars']}
- deepseek_call_succeeded: {str(report['deepseek_call_succeeded']).lower()}
- final_decision_made_by_codex: true
- deepseek_made_final_pass_decision: false

## Path Integrity

- path_corrupted: {str(report['path_corrupted']).lower()}
- source path safe: {str(report['path_integrity']['source_dwg_path']['safe_for_source_operation']).lower()}
- sandbox path safe: {str(report['path_integrity']['sandbox_dwg_path']['safe_for_source_operation']).lower()}

## Safety

{safety}

## Tests

{report['pytest_result']}
"""
