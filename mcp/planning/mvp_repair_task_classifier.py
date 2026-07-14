from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from mcp.diff.mvp_missing_content_diff import run_default_diff
from mcp.repair_actions.task_eligibility import (
    classify_invalid_task,
    validate_direct_com_candidate,
)


DIRECT_COM_TYPES = {"line", "polyline", "text"}
MANUAL_TDB_TYPES = {"tdb_pipe", "tdb_valve", "tdb_fitting", "equipment"}
DANGEROUS_COMMANDS = {"hsxg", "hzgx", "gxlj", "TSaveAs", "tgbatplots", "dcsz"}


def _stable_task_id(prefix: str, value: object) -> str:
    digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def classify_repair_task(obj: dict[str, Any], *, reason: str = "") -> dict[str, Any]:
    object_type = str(obj.get("object_type") or "unknown")
    semantic = dict(obj.get("semantic") or {})
    object_name = str(semantic.get("object_name") or "")

    if semantic.get("requires_source_modification") or semantic.get("save_as_source"):
        task_type = "blocked"
        suggested_executor = "none"
        task_reason = "requires source modification or SaveAs source"
    elif any(command.lower() in str(semantic).lower() for command in DANGEROUS_COMMANDS):
        task_type = "blocked"
        suggested_executor = "none"
        task_reason = "requires dangerous command"
    elif object_type in MANUAL_TDB_TYPES or object_name.startswith("TDb"):
        task_type = "manual_tianzheng_required"
        suggested_executor = "manual_tianzheng"
        task_reason = reason or "TDb object requires manual Tianzheng workflow"
    elif object_type in DIRECT_COM_TYPES:
        gate = validate_direct_com_candidate(obj, reason=reason)
        if not gate["valid"]:
            return classify_invalid_task(obj, gate["invalid_reasons"])
        task_type = "direct_com_create"
        suggested_executor = "dry_run_direct_com_plan"
        task_reason = reason or "simple geometry can be planned for direct COM creation later"
    elif obj.get("requires_visual_review") or obj.get("confidence", 0) < 0.5:
        task_type = "review_only"
        suggested_executor = "gpt_visual_review"
        task_reason = reason or "ambiguous object requires visual review"
    else:
        task_type = "uncertain"
        suggested_executor = "manual_review"
        task_reason = reason or "insufficient confidence for automatic classification"

    return {
        "task_id": _stable_task_id("mvp1_task", obj.get("object_id", "")),
        "task_type": task_type,
        "source_object_id": obj.get("object_id", ""),
        "target_status": "missing_or_review",
        "geometry": dict(obj.get("geometry") or {}),
        "semantic": semantic,
        "suggested_executor": suggested_executor,
        "confidence": float(obj.get("confidence", 0.0)),
        "reason": task_reason,
    }


def classify_diff_result(diff_result: dict[str, Any]) -> dict[str, Any]:
    missing_tasks = [
        classify_repair_task(item["reference_object"], reason=item.get("reason", "missing object"))
        for item in diff_result.get("missing_objects", [])
    ]
    review_tasks = [
        {
            "task_id": f"mvp1_review_{index:04d}",
            "review_reason": item.get("reason", "manual review required"),
            "object_summary": item.get("reference_object", {}),
            "suggested_review_method": "GPT visual review with source crop or overlay evidence",
            "gpt_visual_review_required": True,
        }
        for index, item in enumerate(diff_result.get("uncertain_objects", []), start=1)
    ]

    manual_tasks = []
    for task in missing_tasks:
        if task["task_type"] == "manual_tianzheng_required":
            manual_tasks.append(
                {
                    "task_id": task["task_id"],
                    "required_command": "manual_only_no_auto_execution",
                    "expected_tdb_object": task["semantic"].get("object_name") or task["semantic"].get("expected_tdb_object", ""),
                    "geometry": task["geometry"],
                    "semantic": task["semantic"],
                    "user_instruction": "由用户在天正界面手动确认，禁止自动执行 hsxg/hzgx/gxlj。",
                    "before_after_scan_required": True,
                }
            )

    blocked_tasks = [task for task in missing_tasks if task["task_type"] in {"blocked", "blocked_invalid_task"}]
    blocked_invalid_tasks = [task for task in missing_tasks if task["task_type"] == "blocked_invalid_task"]
    return {
        "phase": "MVP-1",
        "mode": "dry_run_gpt_fallback",
        "missing_tasks": missing_tasks,
        "manual_tianzheng_tasks": manual_tasks,
        "review_tasks": review_tasks,
        "blocked_tasks": blocked_tasks,
        "blocked_invalid_tasks": blocked_invalid_tasks,
        "direct_com_task_count": sum(1 for task in missing_tasks if task["task_type"] == "direct_com_create"),
        "manual_tianzheng_task_count": len(manual_tasks),
        "review_task_count": len(review_tasks),
        "blocked_task_count": len(blocked_tasks),
        "blocked_invalid_task_count": len(blocked_invalid_tasks),
        "invalid_text_task_count": sum(1 for task in blocked_invalid_tasks if task.get("object_type") == "text"),
        "page_level_text_task_rejected_count": sum(
            1
            for task in blocked_invalid_tasks
            if "page_level_aggregate" in task.get("invalid_reasons", [])
        ),
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "sendcommand_used": False,
        "tianzheng_command_executed": False,
        "dangerous_command_executed": False,
        "production_d1_allowed": False,
    }


def build_gpt_visual_review_items(review_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, task in enumerate(review_tasks, start=1):
        summary = task.get("object_summary", {})
        items.append(
            {
                "item_id": f"mvp1_visual_{index:04d}",
                "source": summary.get("source", "reference_pdf"),
                "reason": task.get("review_reason", "ambiguous object requires visual review"),
                "related_object_ids": [summary.get("object_id", "")],
                "suggested_visual_review_method": task.get("suggested_review_method", "GPT visual review"),
                "required_input_for_gpt": ["reference crop", "target crop", "overlay snapshot"],
                "priority": "high" if summary.get("source") == "reference_pdf" else "normal",
            }
        )
    return items


def run_default_classification() -> dict[str, Any]:
    return classify_diff_result(run_default_diff())


def main() -> None:
    print(json.dumps(run_default_classification(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
