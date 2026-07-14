from __future__ import annotations

from pathlib import Path

import pytest

from mcp.acceptance.stage1_final_acceptance import (
    BASE_SANDBOX,
    SOURCE_DWG,
    VALIDATION_LAYER,
    acceptance_status,
    build_deepseek_task_pack,
    build_executable_tasks,
    derive_seed_geometry,
    is_forbidden_fixture_path,
    run_deepseek_delegation,
    semantic_pipeline,
    validate_execution_task,
    validate_line_geometry,
    validate_open_target,
    validate_save_target,
)


def entity(handle: str, layer: str = "BASE", start=None, end=None) -> dict:
    payload = {"ObjectName": "AcDbLine", "Handle": handle, "Layer": layer}
    if start is not None:
        payload["StartPoint"] = start
    if end is not None:
        payload["EndPoint"] = end
    return payload


def executable_task() -> dict:
    return {
        "task_id": "fixture_task",
        "classification": "confirmed_direct_com",
        "task_type": "direct_com_create",
        "action": "direct_com_create",
        "object_type": "line",
        "execution_allowed": True,
        "validation_fixture_only": True,
        "cad_geometry": {"start_point": [10.0, 20.0, 0.0], "end_point": [15.0, 20.0, 0.0]},
        "geometry_source": "reference_dwg_entity_geometry",
        "geometry_confidence": 0.95,
        "layer": VALIDATION_LAYER,
        "sendcommand_required": False,
        "tianzheng_command_required": False,
    }


def test_fixture_reference_extra_line_produces_one_missing_and_one_task():
    target = [entity("1")]
    reference = target + [entity("2", VALIDATION_LAYER, [10.0, 20.0, 0.0], [15.0, 20.0, 0.0])]
    result = semantic_pipeline(reference, target)
    assert result["diff"]["missing_count"] == 1
    assert result["tasks"]["planned_direct_com_task_count"] == 1
    task = result["tasks"]["tasks"][0]
    assert task["cad_geometry"]["start_point"] == [10.0, 20.0, 0.0]
    assert task["cad_geometry"]["end_point"] == [15.0, 20.0, 0.0]


def test_line_task_still_passes_eligibility_and_geometry_gate():
    valid, errors = validate_execution_task(executable_task())
    assert valid is True
    assert errors == []


@pytest.mark.parametrize(
    "geometry",
    [
        {},
        {"start_point": [1.0, 1.0, 0.0], "end_point": [1.0, 1.0, 0.0], "geometry_source": "reference_dwg_entity_geometry", "geometry_confidence": 0.95},
        {"start_point": [1.0, 1.0, 0.0], "end_point": [2.0, 1.0, 0.0], "geometry_source": "guessed_geometry", "geometry_confidence": 0.95},
        {"start_point": [1.0, 1.0, 0.0], "end_point": [2.0, 1.0, 0.0], "geometry_source": "hardcoded_coordinate", "geometry_confidence": 0.95},
        {"start_point": [1.0, 1.0, 0.0], "end_point": [2.0, 1.0, 0.0], "geometry_source": "default_origin", "geometry_confidence": 0.95},
    ],
)
def test_invalid_geometry_never_executes(geometry):
    ok, _ = validate_line_geometry(geometry)
    assert ok is False


@pytest.mark.parametrize("classification", ["review_only", "blocked_invalid_task"])
def test_non_confirmed_tasks_do_not_execute(classification):
    task = executable_task()
    task["classification"] = classification
    valid, _ = validate_execution_task(task)
    assert valid is False


@pytest.mark.parametrize("marker", ["TDbPipe", "hsxg", "SendCommand"])
def test_tianzheng_and_command_tasks_do_not_execute(marker):
    task = executable_task()
    task["unexpected_marker"] = marker
    valid, _ = validate_execution_task(task)
    assert valid is False


def test_only_validation_fixture_paths_can_open_and_save(tmp_path):
    reference = tmp_path / "reference.dwg"
    target = tmp_path / "target.dwg"
    validate_open_target(reference, [reference, target])
    validate_open_target(target, [reference, target])
    validate_save_target(target, target)
    with pytest.raises(ValueError):
        validate_open_target(SOURCE_DWG, [reference, target])
    with pytest.raises(ValueError):
        validate_open_target(BASE_SANDBOX, [reference, target])
    with pytest.raises(ValueError):
        validate_save_target(reference, target)


def test_forbidden_paths_are_explicit():
    assert is_forbidden_fixture_path(SOURCE_DWG)
    assert is_forbidden_fixture_path(BASE_SANDBOX)


def test_seed_geometry_is_extents_derived_non_zero_and_internal():
    geometry = derive_seed_geometry([-100.0, -50.0, 0.0], [900.0, 450.0, 0.0])
    assert geometry["length"] > 0
    assert -100.0 < geometry["start_point"][0] < 900.0
    assert -100.0 < geometry["end_point"][0] < 900.0


def test_acceptance_requires_persisted_delta_and_geometry_match():
    report = {
        "validation_mode": "controlled_known_good_fixture",
        "real_sample_repair_completed": False,
        "source_hash_unchanged": True,
        "base_sandbox_hash_unchanged": True,
        "reference_seed_delta": 1,
        "reference_fixture_saved": True,
        "reference_fixture_reopened": True,
        "reference_seed_persisted": True,
        "missing_candidate_count": 1,
        "confirmed_direct_com_task_count": 1,
        "planned_direct_com_task_count": 1,
        "executed_direct_com_task_count": 1,
        "target_draw_delta": 1,
        "target_validation_layer_count_before": 0,
        "target_validation_layer_count_after_reopen": 1,
        "target_saved": True,
        "target_reopened": True,
        "persisted_delta": 1,
        "geometry_match": True,
        "layer_match": True,
        "review_only_executed_count": 0,
        "blocked_invalid_task_executed_count": 0,
        "real_sample_review_only_items_included_count": 0,
        "blocked_invalid_task_included_count": 0,
        "manual_anchor_task_included_count": 0,
        "deepseek_worker_used": True,
        "delegated_task_count": 1,
        "delegated_task_ids": ["ds_stage1_fixture_schema_review"],
        "deepseek_task_pack_chars": 1000,
        "deepseek_call_succeeded": True,
        "final_decision_made_by_codex": True,
        "deepseek_made_final_pass_decision": False,
        "full_chat_sent_to_deepseek": False,
        "api_key_sent_to_deepseek": False,
        "dwg_binary_sent_to_deepseek": False,
        "source_file_sent_to_deepseek": False,
        "full_history_sent_to_deepseek": False,
        "autocad_execution_authorized": False,
        "errors": [],
    }
    assert acceptance_status(report) == "PASS"
    report["persisted_delta"] = 0
    assert acceptance_status(report) == "PARTIAL"
    report["persisted_delta"] = 1
    report["geometry_match"] = False
    assert acceptance_status(report) == "PARTIAL"


def test_acceptance_requires_reference_seed_persistence_and_controlled_delegation():
    report = {
        "validation_mode": "controlled_known_good_fixture",
        "real_sample_repair_completed": False,
        "source_hash_unchanged": True,
        "base_sandbox_hash_unchanged": True,
        "reference_seed_delta": 1,
        "reference_fixture_saved": True,
        "reference_fixture_reopened": True,
        "reference_seed_persisted": False,
        "missing_candidate_count": 1,
        "confirmed_direct_com_task_count": 1,
        "planned_direct_com_task_count": 1,
        "executed_direct_com_task_count": 1,
        "target_draw_delta": 1,
        "target_validation_layer_count_before": 0,
        "target_validation_layer_count_after_reopen": 1,
        "target_saved": True,
        "target_reopened": True,
        "persisted_delta": 1,
        "geometry_match": True,
        "layer_match": True,
        "review_only_executed_count": 0,
        "blocked_invalid_task_executed_count": 0,
        "real_sample_review_only_items_included_count": 0,
        "blocked_invalid_task_included_count": 0,
        "manual_anchor_task_included_count": 0,
        "deepseek_worker_used": True,
        "delegated_task_count": 1,
        "delegated_task_ids": ["ds_stage1_fixture_schema_review"],
        "deepseek_task_pack_chars": 1000,
        "deepseek_call_succeeded": True,
        "final_decision_made_by_codex": True,
        "deepseek_made_final_pass_decision": False,
        "full_chat_sent_to_deepseek": False,
        "api_key_sent_to_deepseek": False,
        "dwg_binary_sent_to_deepseek": False,
        "source_file_sent_to_deepseek": False,
        "full_history_sent_to_deepseek": False,
        "autocad_execution_authorized": False,
        "errors": [],
    }
    assert acceptance_status(report) == "PARTIAL"
    report["reference_seed_persisted"] = True
    report["deepseek_task_pack_chars"] = 20_001
    assert acceptance_status(report) == "PARTIAL"
    report["deepseek_task_pack_chars"] = 1000
    report["api_key_sent_to_deepseek"] = True
    assert acceptance_status(report) == "PARTIAL"


def test_deepseek_delegation_record_is_controlled_and_under_budget():
    pack = build_deepseek_task_pack()
    serialized = str(pack).lower()
    assert pack["max_input_chars"] == 20_000
    assert all(not str(path).lower().endswith(".dwg") for path in pack["allowed_files"])
    assert "完整聊天历史" not in serialized
    assert "deepseek_api_key" not in serialized


def test_deepseek_delegation_record_has_all_required_fields(monkeypatch):
    fake_result = {
        "phase": "STAGE1-FINAL-ACCEPTANCE",
        "status": "PASS",
        "files_modified": [],
        "tests_run": [],
        "test_result": "static review only",
        "safety_result": {
            "api_key_logged": False,
            "full_chat_sent": False,
            "opened_source_dwg": False,
            "saved_source_dwg": False,
            "used_sendcommand": False,
            "executed_tianzheng_command": False,
        },
        "notes": ["schema and hash assertions reviewed"],
        "next_recommendation": "Codex performs final review",
    }
    monkeypatch.setattr(
        "mcp.acceptance.stage1_final_acceptance.run_deepseek_worker",
        lambda *_args, **_kwargs: fake_result,
    )
    record = run_deepseek_delegation()
    required = {
        "deepseek_worker_used",
        "delegated_task_count",
        "delegated_task_ids",
        "deepseek_task_pack_chars",
        "deepseek_call_succeeded",
        "deepseek_result_accepted_count",
        "deepseek_result_modified_count",
        "deepseek_result_rejected_count",
        "final_decision_made_by_codex",
        "deepseek_made_final_pass_decision",
        "full_chat_sent_to_deepseek",
        "api_key_sent_to_deepseek",
        "dwg_binary_sent_to_deepseek",
        "source_file_sent_to_deepseek",
        "full_history_sent_to_deepseek",
        "autocad_execution_authorized",
    }
    assert required <= record.keys()
    assert record["deepseek_task_pack_chars"] <= 20_000
    assert record["final_decision_made_by_codex"] is True
    assert record["deepseek_made_final_pass_decision"] is False


def test_failed_deepseek_call_does_not_count_synthetic_review_results(monkeypatch):
    fake_result = {
        "phase": "STAGE1-FINAL-ACCEPTANCE",
        "status": "BLOCKED",
        "notes": ["DEEPSEEK_API_KEY is not set; remote call skipped safely"],
    }
    monkeypatch.setattr(
        "mcp.acceptance.stage1_final_acceptance.run_deepseek_worker",
        lambda *_args, **_kwargs: fake_result,
    )
    record = run_deepseek_delegation()
    assert record["deepseek_call_succeeded"] is False
    assert record["deepseek_result_accepted_count"] == 0
    assert record["deepseek_result_modified_count"] == 0
    assert record["deepseek_result_rejected_count"] == 0


def test_task_artifact_marks_real_sample_repair_false():
    classification = {
        "missing_tasks": [],
    }
    artifact = build_executable_tasks(classification)
    assert artifact["real_sample_repair_completed"] is False
    assert artifact["production_d1_allowed"] is False
