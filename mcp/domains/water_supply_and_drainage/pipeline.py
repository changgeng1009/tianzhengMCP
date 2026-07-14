from __future__ import annotations

from typing import Any

from mcp.diff.mvp_missing_content_diff import compare_missing_content
from mcp.planning.mvp_repair_task_classifier import classify_diff_result

from .adapter import WaterSupplyAndDrainageDomain


def build_water_repair_plan(reference_objects: list[dict[str, Any]], target_objects: list[dict[str, Any]]) -> dict[str, Any]:
    """从 backend 已扫描并标准化的对象构建给排水 repair plan，不接触任何 CAD API。"""
    diff = compare_missing_content(reference_objects, target_objects, include_review_only=True)
    classification = classify_diff_result(diff)
    domain = WaterSupplyAndDrainageDomain()
    tasks = [domain.enrich_task(task) for task in classification.get("missing_tasks", [])]
    return {
        "professional_domain": domain.domain_id,
        "diff": diff,
        "classification": {**classification, "missing_tasks": tasks},
        "tasks": tasks,
        "real_sample_repair_completed": False,
        "production_d1_allowed": False,
    }
