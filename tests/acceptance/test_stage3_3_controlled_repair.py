from __future__ import annotations

from pathlib import Path
import inspect

from mcp.acceptance import stage3_3_controlled_repair as stage3_3


def _draft(**updates) -> dict:
    value = {
        "task_id": "repair_1",
        "candidate_id": "missing_1",
        "classification": "MISSING_HIGH_CONFIDENCE",
        "confidence": 0.965,
        "route": "direct_com_candidate",
        "object_name": "AcDbLine",
        "layer": "0",
        "target_wcs_geometry": {"start_point": [10, 10, 0], "end_point": [20, 10, 0]},
        "geometry_source": "transformed_reference_geometry",
        "one_to_many_conflict": False,
        "many_to_one_conflict": False,
        "nearby_duplicate_found": False,
        "automatic_fallback": False,
        "required_capabilities": ["create_acdb_line"],
    }
    value.update(updates)
    return value


def _stage2(status: str = "PASS_MISSING_DETECTION_EVIDENCE_READY") -> dict:
    return {
        "status": status,
        "alignment_contradiction": False,
        "alignment_evidence_mode": "conditional_geometry_dominant",
        "user_authorized_stage3_2": True,
        "user_authorized_automatic_stage3_3_transition": True,
        "reference_target_roles_preserved": True,
        "translation_direction": "reference_wcs_to_target_wcs",
        "stage1_seed_line_excluded": True,
        "title_frame_drawing_name_excluded": True,
        "target_virtual_block_entities_participated": True,
        "one_to_one_conflicts_handled": True,
        "compound_matching_conflicts_handled": True,
        "source_hashes_unchanged": True,
        "automatic_fallback": False,
        "production_d1_allowed": False,
    }


def _r2() -> dict:
    return {"production_d1_allowed": False}


def test_stage3_2_non_pass_cannot_enter_stage3_3() -> None:
    gate = stage3_3.automatic_transition_gate(_stage2("PARTIAL_MISSING_DETECTION_REVIEW_REQUIRED"), _r2(), [_draft()])
    assert gate["passed"] is False
    assert "stage3_2_formal_pass" in gate["blockers"]


def test_stage3_2_formal_pass_automatically_enters_gate() -> None:
    gate = stage3_3.automatic_transition_gate(_stage2(), _r2(), [_draft()])
    assert gate["passed"] is True


def test_automatic_approval_accepts_only_high_confidence_direct_com() -> None:
    result = stage3_3.approve_execution_tasks([_draft()])
    assert len(result["approved"]) == 1
    assert result["approved"][0]["execution_allowed"] is True
    assert result["approved"][0]["selected_backend"] == "com"


def test_tdb_is_never_automatically_approved() -> None:
    result = stage3_3.approve_execution_tasks([_draft(object_name="TDbPipe")])
    assert result["approved"] == []


def test_review_required_is_not_approved() -> None:
    result = stage3_3.approve_execution_tasks([_draft(classification="MISSING_REVIEW_REQUIRED")])
    assert result["approved"] == []


def test_ambiguous_match_is_not_approved() -> None:
    result = stage3_3.approve_execution_tasks([_draft(classification="AMBIGUOUS_MATCH", one_to_many_conflict=True)])
    assert result["approved"] == []


def test_incomplete_geometry_is_not_approved() -> None:
    result = stage3_3.approve_execution_tasks([_draft(target_wcs_geometry={"start_point": [1, 2, 0]})])
    assert result["approved"] == []


def test_low_confidence_is_not_approved() -> None:
    assert stage3_3.approve_execution_tasks([_draft(confidence=0.949)])["approved"] == []


def test_source_path_cannot_be_sandbox_path() -> None:
    result = stage3_3.validate_preflight(
        stage3_3.approve_execution_tasks([_draft()])["approved"], stage3_3.TARGET_SOURCE, [0, 0, 100, 100]
    )
    assert result["passed"] is False
    assert "sandbox path equals a source path" in result["errors"]


def test_repair_sandbox_uses_filesystem_copy(tmp_path: Path, synthetic_cad_factory) -> None:
    source = synthetic_cad_factory(tmp_path / "source.dwg")
    destination = synthetic_cad_factory(
        tmp_path / "run" / "copies" / "sandbox.dwg", create=False
    )
    result = stage3_3.create_filesystem_sandbox(source, destination, stage3_3.file_hash(source))
    assert destination.read_bytes() == source.read_bytes()
    assert result["copy_method"] == "python_shutil_copyfile"
    assert result["hashes_match"] is True


def test_duplicate_object_risk_is_detected() -> None:
    approved = stage3_3.approve_execution_tasks([_draft()])["approved"][0]
    scan = [{"handle": "A", "object_name": "AcDbLine", "layer": "0", "start_point": [10, 10, 0], "end_point": [20, 10, 0]}]
    assert stage3_3.duplicate_risk(approved, scan)["duplicate"] is True


def test_only_frozen_task_ids_are_in_plan_contract() -> None:
    source = Path(stage3_3.__file__).read_text(encoding="utf-8")
    assert "frozen_ids" in source
    assert "BLOCKED_NOT_FROZEN" in source
    assert '"automatic_append_allowed": False' in source


def test_unapproved_tasks_keep_execution_disabled() -> None:
    rejected = stage3_3.approve_execution_tasks([_draft(route="manual_review")])["rejected"][0]
    assert rejected["execution_allowed"] is False
    assert rejected["executed"] is False


def test_single_task_failure_has_no_fallback() -> None:
    approved = stage3_3.approve_execution_tasks([_draft()])["approved"][0]
    assert approved["automatic_fallback"] is False
    assert approved["selected_backend"] == "com"


def test_new_line_geometry_can_be_verified_with_reversed_endpoints() -> None:
    assert stage3_3.lines_equivalent(
        {"start_point": [0, 0, 0], "end_point": [10, 0, 0]},
        {"start_point": [10, 0, 0], "end_point": [0, 0, 0]},
    ) is True


def test_existing_object_modification_is_detected() -> None:
    before = {"A": {"object_name": "AcDbLine", "layer": "0"}}
    after = {"A": {"object_name": "AcDbLine", "layer": "CHANGED"}}
    result = stage3_3.unexpected_change_check(before, after, [])
    assert result["existing_object_modified_count"] == 1
    assert result["passed"] is False


def test_existing_object_deletion_is_detected() -> None:
    result = stage3_3.unexpected_change_check({"A": {"layer": "0"}}, {}, [])
    assert result["existing_object_deleted_count"] == 1
    assert result["passed"] is False


def test_unexpected_new_object_is_detected() -> None:
    result = stage3_3.unexpected_change_check({}, {"X": {"layer": "0"}}, [])
    assert result["unexpected_new_object_count"] == 1
    assert result["passed"] is False


def test_expected_new_handle_passes_change_check() -> None:
    result = stage3_3.unexpected_change_check({}, {"X": {"layer": "0"}}, ["X"])
    assert result["passed"] is True


def test_source_hash_mismatch_blocks_copy(tmp_path: Path, synthetic_cad_factory) -> None:
    source = synthetic_cad_factory(tmp_path / "source.dwg")
    try:
        stage3_3.create_filesystem_sandbox(source, tmp_path / "copy" / "sandbox.dwg", "0" * 64)
    except RuntimeError as exc:
        assert "hash differs" in str(exc)
    else:
        raise AssertionError("hash mismatch must block")


def test_forbidden_command_paths_are_absent() -> None:
    source = Path(stage3_3.__file__).read_text(encoding="utf-8")
    forbidden = ("SendCommand(", "CopyObjects(", "Explode(", "SaveAs(", "Close(True)", "Dispatch(")
    assert not any(token in source for token in forbidden)


def test_no_safe_task_prevents_connection_gate() -> None:
    gate = stage3_3.automatic_transition_gate(_stage2(), _r2(), [])
    assert gate["passed"] is False
    assert "safe_ordinary_task_exists" in gate["blockers"]


def test_duplicate_check_is_idempotent_across_repeated_runs() -> None:
    approved = stage3_3.approve_execution_tasks([_draft()])["approved"][0]
    scan = [{"handle": "PERSISTED", "object_name": "AcDbLine", "layer": "0", "start_point": [10, 10, 0], "end_point": [20, 10, 0]}]
    first = stage3_3.duplicate_risk(approved, scan)
    second = stage3_3.duplicate_risk(approved, scan)
    assert first == second
    assert first["duplicate"] is True


def test_block_reference_requires_complete_definition_metadata() -> None:
    block = _draft(
        object_name="AcDbBlockReference",
        target_wcs_geometry={"insert_point": [10, 10, 0]},
        required_capabilities=["create_block_reference"],
    )
    assert stage3_3.approve_execution_tasks([block])["approved"] == []


def test_manual_tianzheng_review_never_enables_execution() -> None:
    items = stage3_3.build_tianzheng_manual_review([{
        "candidate_id": "T1", "reference_handle": "R1", "object_name": "TDbPipe",
        "semantic_type": "TDbPipe", "target_wcs_geometry": {"bbox": [[0, 0, 0], [10, 10, 0]]},
    }])
    assert items[0]["execution_allowed"] is False
    assert items[0]["executed"] is False


def test_geometry_outside_region_fails_preflight(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mcp.backends.com_backend.importlib.util.find_spec", lambda _name: object()
    )
    approved = stage3_3.approve_execution_tasks([_draft(target_wcs_geometry={"start_point": [1000, 1000, 0], "end_point": [1010, 1000, 0]})])["approved"]
    result = stage3_3.validate_preflight(approved, tmp_path / "sandbox.dwg", [0, 0, 100, 100])
    assert result["passed"] is False
    assert any("outside confirmed local region" in error for error in result["errors"])


def test_source_lock_files_are_detected_before_cad_connection(tmp_path: Path, synthetic_cad_factory) -> None:
    source = synthetic_cad_factory(tmp_path / "target.dwg")
    source.with_suffix(".dwl").write_text("lock", encoding="utf-8")
    locks = stage3_3.source_lock_files(source)
    assert locks == [str(source.with_suffix(".dwl"))]


def test_frozen_stage3_3_resume_keeps_all_sixteen_task_ids() -> None:
    run_root = stage3_3.RUNS_ROOT / "stage3_3_20260711_090728"
    result = stage3_3.verify_frozen_resume(run_root)
    assert result["passed"] is True
    assert result["approved_task_count"] == 16
    assert result["approved_task_ids_unchanged"] is True
    assert result["task_artifact_hashes_match"] is True
    assert result["semantic_gate_fields_match"] is True


def test_resume_never_reruns_stage3_2_or_refilters_tasks() -> None:
    source = inspect.getsource(stage3_3.resume_stage3_3)
    assert "run_stage3_2" not in source
    assert "approve_execution_tasks" not in source
    assert 'plan.get("tasks", [])' in source


def test_blocked_execution_output_separates_blocked_from_manual_items() -> None:
    rejected = [
        {"candidate_id": "C", "classification": "BLOCKED_UNSUPPORTED_OBJECT", "route": "blocked"},
        {"candidate_id": "T", "classification": "MISSING_HIGH_CONFIDENCE", "route": "manual_tianzheng_review"},
    ]
    blocked = stage3_3.select_blocked_execution_items(rejected)
    assert [item["candidate_id"] for item in blocked] == ["C"]


def test_live_executor_accepts_stage_specific_forbidden_source_paths() -> None:
    signature = inspect.signature(stage3_3.execute_live_plan)
    assert "forbidden_source_paths" in signature.parameters
