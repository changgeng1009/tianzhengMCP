from __future__ import annotations

from mcp.planning.mvp_repair_task_classifier import classify_repair_task
from mcp.repair_actions.classifier_fix import (
    SAFETY_FLAGS,
    build_deepseek_delegation_record,
    rerun_static_classification,
    validate_deepseek_delegation_record,
)
from mcp.repair_actions.manual_anchor_validator import validate_user_anchor_input
from mcp.repair_actions.path_integrity import detect_corrupted_path, utf8_round_trip, validate_path_integrity
from mcp.repair_actions.task_eligibility import (
    blocked_invalid_enters_anchor_or_loop,
    validate_direct_com_candidate,
)


def _text_obj(**overrides: object) -> dict:
    obj = {
        "object_id": "reference_pdf:page_1:span_1",
        "source": "reference_pdf",
        "object_type": "text",
        "geometry": {"bbox": [10, 20, 30, 40]},
        "semantic": {"text": "水泵房大样图"},
        "crop_id": "crop_1",
        "reference_entity_id": "reference_pdf:span_1",
        "target_status": "missing",
        "confidence": 0.85,
    }
    obj.update(overrides)
    return obj


def test_object_type_text_alone_cannot_enter_direct_com() -> None:
    task = classify_repair_task({"object_id": "x", "object_type": "text", "semantic": {}, "geometry": {}, "confidence": 0.9})

    assert task["task_type"] == "blocked_invalid_task"
    assert "empty_expected_text" in task["invalid_reasons"]


def test_empty_expected_text_is_blocked_invalid_task() -> None:
    task = classify_repair_task(_text_obj(semantic={"text": ""}))

    assert task["task_type"] == "blocked_invalid_task"
    assert "empty_expected_text" in task["invalid_reasons"]


def test_empty_semantic_text_preview_is_blocked_for_page_level_task() -> None:
    task = classify_repair_task(
        _text_obj(
            object_id="reference_pdf:page_1:text",
            geometry={"page": 1, "width": 2384, "height": 3370},
            semantic={"text": "整页文字", "page_level_aggregate": True},
        )
    )

    assert task["task_type"] == "blocked_invalid_task"
    assert "empty_semantic_text_preview" in task["invalid_reasons"]


def test_page_level_source_object_id_is_rejected() -> None:
    task = classify_repair_task(_text_obj(object_id="reference_pdf:page_1:text", geometry={"page": 1, "width": 1, "height": 2}))

    assert task["task_type"] == "blocked_invalid_task"
    assert "page_level_aggregate" in task["invalid_reasons"]


def test_missing_object_level_evidence_is_rejected() -> None:
    task = classify_repair_task(_text_obj(geometry={}, crop_id=None, reference_entity_id=None))

    assert task["task_type"] == "blocked_invalid_task"
    assert "missing_object_bbox" in task["invalid_reasons"]
    assert "missing_reference_entity" in task["invalid_reasons"]


def test_missing_bbox_crop_reference_entity_is_rejected() -> None:
    gate = validate_direct_com_candidate(_text_obj(geometry={}, crop_id=None, reference_entity_id=None), reason="missing object")

    assert gate["valid"] is False
    assert "missing_object_bbox" in gate["invalid_reasons"]


def test_specific_text_with_object_evidence_can_be_candidate() -> None:
    task = classify_repair_task(_text_obj(), reason="no matching target object")

    assert task["task_type"] == "direct_com_create"
    assert task["suggested_executor"] == "dry_run_direct_com_plan"


def test_blocked_invalid_task_does_not_enter_anchor_workflow() -> None:
    request = {"task_id": "bad", "classification": "blocked_invalid_task", "object_type": "text"}
    user_input = {
        "task_id": "bad",
        "user_provided_geometry": {"insert_point": [10, 20, 0]},
        "coordinate_space": "target_sandbox_cad_space",
        "provided_by_user": True,
        "source_dwg_used": False,
    }

    result = validate_user_anchor_input([request], user_input)

    assert result["valid"] is False
    assert "blocked_invalid_task" in result["reason"]


def test_blocked_invalid_task_does_not_enter_sandbox_repair_loop() -> None:
    task = {"task_type": "blocked_invalid_task", "requires_user_anchor": False, "requires_geometry_localization": False, "execution_allowed": False}

    assert blocked_invalid_enters_anchor_or_loop(task) is False


def test_review_only_tianzheng_sendcommand_do_not_enter_direct_com() -> None:
    assert validate_direct_com_candidate({"task_type": "review_only", "object_type": "text", "confidence": 0.9})["valid"] is False
    assert validate_direct_com_candidate({"object_type": "tdb_pipe", "semantic": {"object_name": "TDbPipe"}, "confidence": 0.9})["valid"] is False
    assert validate_direct_com_candidate({"object_type": "text", "semantic": {"text": "A", "cmd": "SendCommand"}, "confidence": 0.9})["valid"] is False


def test_chinese_path_utf8_round_trip() -> None:
    assert utf8_round_trip(r"D:\ExampleWorkspace\synthetic_sample_t8.dwg")


def test_ascii_question_mark_corrupted_path_detection() -> None:
    check = validate_path_integrity(r"D:\ExampleWorkspace\????????????20251219_t8.dwg")

    assert detect_corrupted_path(check["path"]) is True
    assert check["safe_for_source_operation"] is False


def test_stage_has_no_autocad_or_dwg_write_flags() -> None:
    assert SAFETY_FLAGS == {
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


def test_deepseek_call_record_fields_are_complete() -> None:
    record = build_deepseek_delegation_record(task_pack_chars=1234, call_succeeded=True, result={"notes": ["schema", "tests"]})

    ok, errors = validate_deepseek_delegation_record(record)

    assert ok, errors
    assert record["final_decision_made_by_codex"] is True
    assert record["deepseek_made_final_pass_decision"] is False


def test_current_sample_reclassifies_target_as_blocked_invalid() -> None:
    result = rerun_static_classification()

    assert result["target_task_final_classification"] == "blocked_invalid_task"
    assert result["confirmed_direct_com_contains_target"] is False
    assert result["blocked_invalid_task_count"] >= 1
    assert result["page_level_text_task_rejected_count"] >= 1
