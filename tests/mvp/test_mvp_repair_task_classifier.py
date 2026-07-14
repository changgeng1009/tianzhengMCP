from __future__ import annotations

from mcp.planning.mvp_repair_task_classifier import (
    build_gpt_visual_review_items,
    classify_diff_result,
    classify_repair_task,
)


def _obj(object_type: str, object_name: str, confidence: float = 0.9) -> dict:
    return {
        "object_id": f"reference_dwg:{object_name}",
        "source": "reference_dwg",
        "object_type": object_type,
        "geometry": {"center": [0, 0]},
        "semantic": {"object_name": object_name},
        "layer": "A",
        "confidence": confidence,
        "requires_visual_review": confidence < 0.5,
    }


def test_acdbline_classified_as_direct_com_create() -> None:
    task = classify_repair_task(_obj("line", "AcDbLine"))
    assert task["task_type"] == "direct_com_create"
    assert task["suggested_executor"] == "dry_run_direct_com_plan"


def test_tdb_object_classified_as_manual_tianzheng_required() -> None:
    task = classify_repair_task(_obj("tdb_pipe", "TDbPipe"))
    assert task["task_type"] == "manual_tianzheng_required"
    assert task["suggested_executor"] == "manual_tianzheng"


def test_ambiguous_pdf_object_classified_as_review_only() -> None:
    task = classify_repair_task(
        {
            "object_id": "reference_pdf:ambiguous",
            "source": "reference_pdf",
            "object_type": "unknown",
            "geometry": {},
            "semantic": {},
            "layer": "pdf",
            "confidence": 0.2,
            "requires_visual_review": True,
        }
    )
    assert task["task_type"] == "review_only"


def test_blocked_task_cannot_require_source_modification() -> None:
    obj = _obj("line", "AcDbLine")
    obj["semantic"]["requires_source_modification"] = True
    task = classify_repair_task(obj)
    assert task["task_type"] == "blocked"
    assert task["suggested_executor"] == "none"


def test_classification_counts_and_visual_review_items() -> None:
    diff = {
        "missing_objects": [{"reference_object": _obj("line", "AcDbLine"), "reason": "missing"}],
        "uncertain_objects": [{"reference_object": _obj("unknown", "Unknown", 0.2), "reason": "ambiguous"}],
    }
    result = classify_diff_result(diff)
    visual = build_gpt_visual_review_items(result["review_tasks"])
    assert result["direct_com_task_count"] == 1
    assert result["review_task_count"] == 1
    assert visual[0]["required_input_for_gpt"]

