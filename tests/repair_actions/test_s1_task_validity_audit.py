from __future__ import annotations

import json
from pathlib import Path

from mcp.repair_actions.task_validity_audit import (
    build_task_validity_audit,
    reclassification_payload,
    write_audit_outputs,
)


def test_page_level_pdf_text_task_is_blocked_invalid(tmp_path: Path) -> None:
    # Original page-level fixture, not a redacted historical drawing export.
    task_path = tmp_path / "synthetic_page_task.json"
    task_path.write_text(json.dumps({
        "task_id": "mvp1_task_208c4ccc9f",
        "task_type": "direct_com_create",
        "source_object_id": "reference_pdf:page_1:text",
        "geometry": {"page": 1, "width": 100, "height": 100},
        "semantic": {},
    }), encoding="utf-8")
    evidence_path = tmp_path / "synthetic_empty_evidence.json"
    evidence_path.write_text("{}", encoding="utf-8")
    audit = build_task_validity_audit(
        task_files=[task_path], evidence_files=[evidence_path]
    )

    assert audit["task_id"] == "mvp1_task_208c4ccc9f"
    assert audit["original_classification"] == "direct_com_create"
    assert audit["revised_classification"] == "blocked_invalid_task"
    assert audit["classification_valid"] is False
    assert audit["expected_text"] is None
    assert audit["is_pdf_page_text_layer_aggregate"] is True
    assert audit["object_level_evidence_found"] is False
    assert audit["pdf_bbox_found"] is False
    assert audit["crop_found"] is False
    assert audit["reference_entity_found"] is False
    assert audit["should_remain_direct_com"] is False
    assert audit["needs_user_coordinate_capture"] is False


def test_reclassification_payload_matches_required_shape() -> None:
    payload = reclassification_payload(build_task_validity_audit())

    assert payload == {
        "task_id": "mvp1_task_208c4ccc9f",
        "original_classification": "direct_com_create",
        "revised_classification": "blocked_invalid_task",
        "expected_text": None,
        "object_level_evidence_found": False,
        "pdf_bbox_found": False,
        "crop_found": False,
        "reference_entity_found": False,
        "classification_valid": False,
        "reclassification_reason": payload["reclassification_reason"],
    }
    assert "direct_com minimum conditions failed" in payload["reclassification_reason"]


def test_outputs_are_utf8_and_preserve_chinese(tmp_path: Path) -> None:
    audit = build_task_validity_audit()
    audit["tests_passed"] = True
    audit["pytest_result"] = "unit-test"
    audit["synthetic_utf8_probe"] = "合成测试文字"

    paths = write_audit_outputs(
        audit,
        json_path=tmp_path / "s1_task_validity_audit.json",
        markdown_path=tmp_path / "s1_task_validity_audit.md",
        reclassified_path=tmp_path / "s1_task_audit_reclassified_tasks.json",
    )

    json_text = Path(paths["json_path"]).read_text(encoding="utf-8")
    md_text = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    reclassified = json.loads(Path(paths["reclassified_path"]).read_text(encoding="utf-8"))

    assert "合成测试文字" in json_text
    assert "\\u5408" not in json_text
    assert "????" not in json_text
    assert "S1-TASK-AUDIT" in md_text
    assert reclassified["revised_classification"] == "blocked_invalid_task"


def test_safety_flags_remain_false() -> None:
    audit = build_task_validity_audit()

    assert audit["safety"] == {
        "source_dwg_opened": False,
        "source_modified": False,
        "drawing_executed": False,
        "sandbox_saved": False,
        "sendcommand_used": False,
        "tianzheng_command_executed": False,
    }
