from __future__ import annotations

import inspect
import json
from pathlib import Path
from tests.acceptance.run_config_fixture import set_parameter

import pytest

from mcp import skill_cli
from mcp.acceptance.stage3_3_controlled_repair import approve_execution_tasks, duplicate_risk, unexpected_change_check
from mcp.orchestration import stage4_mvp as stage4


@pytest.fixture(autouse=True)
def original_synthetic_run_config(monkeypatch, tmp_path):
    import hashlib
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage4_mvp.reference_sha256", hashlib.sha256(b"synthetic reference").hexdigest())
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage4_mvp.target_sha256", hashlib.sha256(b"synthetic target").hexdigest())
    set_parameter(monkeypatch, tmp_path, "stage45.translation", [12, 24, 0])


def _paths(tmp_path: Path) -> stage4.Stage4Paths:
    root = tmp_path / "stage4_test"
    paths = stage4.Stage4Paths(
        "stage4_test", root, root / "input", root / "copies", root / "scans",
        root / "alignment", root / "diff", root / "tasks", root / "execution",
        root / "qa", root / "previews", root / "reports",
    )
    paths.create(new_run=True)
    return paths


def _line_draft(task_id: str = "repair_1") -> dict:
    return {
        "task_id": task_id,
        "candidate_id": task_id.replace("repair_", "missing_"),
        "classification": "MISSING_HIGH_CONFIDENCE",
        "confidence": 0.965,
        "route": "direct_com_candidate",
        "object_name": "AcDbLine",
        "layer": "0",
        "target_wcs_geometry": {"start_point": [10, 10, 0], "end_point": [20, 10, 0], "bbox": [[10, 10, 0], [20, 10, 0]]},
        "geometry_source": "transformed_reference_geometry",
        "one_to_many_conflict": False,
        "many_to_one_conflict": False,
        "nearby_duplicate_found": False,
        "automatic_fallback": False,
        "required_capabilities": ["create_acdb_line"],
        "preferred_backend": "com",
        "allowed_backends": ["com"],
        "fallback_policy": "block",
        "execution_allowed": False,
        "executed": False,
    }


def test_exact_input_hash_pair_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_cad_factory) -> None:
    reference, target = tmp_path / "reference.dwg", tmp_path / "target.dwg"
    synthetic_cad_factory(reference)
    synthetic_cad_factory(target)
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage4_mvp.reference_sha256", stage4.sha256_file(reference))
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage4_mvp.target_sha256", stage4.sha256_file(target))
    result = stage4.freeze_inputs(reference, target)
    assert result["hash_pair_matches"] is True


def test_test_evidence_requires_explicit_pass() -> None:
    assert stage4._test_evidence_passed({"full_pytest": "1196 passed"}) is True
    assert stage4._test_evidence_passed({}) is False
    assert stage4._test_evidence_passed({"full_pytest": "1 failed, 1195 passed"}) is False


def test_changed_hash_cannot_reuse_alignment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_cad_factory) -> None:
    reference, target = tmp_path / "reference.dwg", tmp_path / "target.dwg"
    synthetic_cad_factory(reference)
    synthetic_cad_factory(target)
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage4_mvp.reference_sha256", "0" * 64)
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage4_mvp.target_sha256", stage4.sha256_file(target))
    assert stage4.freeze_inputs(reference, target)["hash_pair_matches"] is False


def test_source_dwl_lock_blocks(tmp_path: Path, synthetic_cad_factory) -> None:
    reference, target = tmp_path / "reference.dwg", tmp_path / "target.dwg"
    synthetic_cad_factory(reference); synthetic_cad_factory(target)
    reference.with_suffix(".dwl").write_text("lock", encoding="utf-8")
    audit = stage4.source_lock_audit(reference, target)
    assert audit["source_locked"] is True
    assert audit["reference_lock_files"] == [str(reference.with_suffix(".dwl"))]


def test_source_dwl2_lock_blocks(tmp_path: Path, synthetic_cad_factory) -> None:
    reference, target = tmp_path / "reference.dwg", tmp_path / "target.dwg"
    synthetic_cad_factory(reference); synthetic_cad_factory(target)
    target.with_suffix(".dwl2").write_text("lock", encoding="utf-8")
    assert stage4.source_lock_audit(reference, target)["target_lock_files"] == [str(target.with_suffix(".dwl2"))]


def test_three_filesystem_copies_are_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_cad_factory) -> None:
    paths = _paths(tmp_path)
    reference, target = tmp_path / "reference.dwg", tmp_path / "target.dwg"
    synthetic_cad_factory(reference); synthetic_cad_factory(target)
    for name in (
        "reference_analysis_copy.dwg",
        "target_analysis_copy.dwg",
        "target_repair_sandbox.dwg",
    ):
        synthetic_cad_factory(paths.copies / name, create=False)
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage4_mvp.reference_sha256", stage4.sha256_file(reference))
    set_parameter(monkeypatch, tmp_path, "mcp.orchestration.stage4_mvp.target_sha256", stage4.sha256_file(target))
    result = stage4.create_stage4_copies(paths, reference, target)
    assert result["all_paths_distinct"] is True
    assert result["source_hashes_unchanged"] is True
    assert {path.name for path in paths.copies.iterdir()} == {
        "reference_analysis_copy.dwg", "target_analysis_copy.dwg", "target_repair_sandbox.dwg",
    }


def test_source_path_is_never_passed_to_analysis_open() -> None:
    source = inspect.getsource(stage4.scan_analysis_copies)
    assert "reference_copy" in source and "target_copy" in source
    assert "scan_copy_r1(acad, reference," not in source
    assert "scan_copy_r1(acad, target," not in source


def test_analysis_copy_scan_never_saves() -> None:
    source = inspect.getsource(stage4.scan_analysis_copies)
    assert ".Save(" not in source
    assert "_scan_copy_with_retry" in source
    assert "scan_copy_r1" in inspect.getsource(stage4._scan_copy_with_retry)


def test_inherited_transform_direction_is_reference_to_target() -> None:
    assert stage4.TRANSLATION is None  # No private transform is bundled.
    assert "stage45.translation" in inspect.getsource(stage4.revalidate_inherited_alignment)
    source = inspect.getsource(stage4.revalidate_inherited_alignment)
    assert '"direction": "reference_wcs_to_target_wcs"' in source


def test_alignment_contradiction_blocks_pipeline() -> None:
    source = inspect.getsource(stage4.run_stage4)
    assert '"BLOCKED_ALIGNMENT_CONTRADICTION"' in source
    assert 'alignment["validation"]["alignment_contradiction"]' in source


def test_target_virtual_entities_participate_in_alignment() -> None:
    source = inspect.getsource(stage4.revalidate_inherited_alignment)
    assert "target_block_audit" in source
    assert '"target_virtual_entities_used"' in source


def test_stage1_seed_line_is_explicitly_excluded() -> None:
    source = inspect.getsource(stage4.revalidate_inherited_alignment)
    assert "fixture_seed_handle" in source
    assert "stage1_seed_excluded" in source


def test_stage3_baseline_semantic_task_set_is_stable(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    stage2 = stage4.read_json(stage4.STAGE2_REPORT)
    root = Path(stage2["run_root"])
    drafts = stage4.read_json(root / "repair_task_drafts.json")["items"]
    missing = stage4.read_json(root / "missing_candidates.json")["items"]
    result = stage4.compare_stage3_baseline(paths, {
        "counts": dict(stage4.STAGE3_BASELINE),
        "classified": {"repair_task_drafts": drafts, "missing_candidates": missing},
    })
    assert result["passed"] is True


def test_tdb_never_enters_direct_com_approval() -> None:
    task = _line_draft()
    task["object_name"] = "TDbPipe"
    assert approve_execution_tasks([task])["approved"] == []


def test_automatic_approval_uses_ordinary_whitelist() -> None:
    assert len(approve_execution_tasks([_line_draft()])["approved"]) == 1
    circle = _line_draft(); circle["object_name"] = "AcDbCircle"
    assert approve_execution_tasks([circle])["approved"] == []


def test_frozen_execution_plan_cannot_append_tasks(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    for path in (paths.alignment / "alignment_revalidation.json", paths.diff / "missing_candidates.json", paths.tasks / "repair_task_drafts.json"):
        path.write_text("{}", encoding="utf-8")
    draft = _line_draft()
    result = stage4.freeze_execution_plan(paths, {
        "classified": {"repair_task_drafts": [draft], "missing_candidates": [draft], "tianzheng_manual_tasks": []},
    }, {"passed": True})
    assert result["plan"]["frozen"] is True
    assert result["plan"]["automatic_append_allowed"] is False
    assert result["plan"]["approved_task_ids"] == ["repair_1"]


def test_single_task_failure_cannot_fallback() -> None:
    approved = approve_execution_tasks([_line_draft()])["approved"][0]
    assert approved["automatic_fallback"] is False
    assert approved["selected_backend"] == "com"


def test_duplicate_precheck_detects_equivalent_line() -> None:
    approved = approve_execution_tasks([_line_draft()])["approved"][0]
    scan = [{"handle": "A", "object_name": "AcDbLine", "layer": "0", "start_point": [20, 10, 0], "end_point": [10, 10, 0]}]
    assert duplicate_risk(approved, scan)["duplicate"] is True


def test_existing_modified_deleted_zero_passes() -> None:
    before = {"A": {"object_name": "AcDbLine", "layer": "0"}}
    assert unexpected_change_check(before, dict(before), [])["passed"] is True


def test_unexpected_new_object_blocks() -> None:
    result = unexpected_change_check({}, {"X": {"object_name": "AcDbLine", "layer": "0"}}, [])
    assert result["unexpected_new_object_count"] == 1
    assert result["passed"] is False


def test_persistence_qa_is_required_for_execution_pass() -> None:
    source = inspect.getsource(stage4.run_execution)
    assert 'live["persistence_qa_passed"]' in source
    assert '"FAILED_PERSISTENCE_QA"' in source


def test_second_pass_idempotency_passes_with_zero_repeat() -> None:
    result = stage4.evaluate_idempotency(
        first_pass_safe_task_count=16, first_pass_success_count=16,
        second_pass_safe_task_count=0, repaired_objects_now_existing_count=16,
        first_task_keys={"A"}, second_task_keys=set(), sandbox_hash_unchanged=True,
    )
    assert result["idempotency_passed"] is True
    assert result["repeated_task_count"] == 0


def test_repaired_object_still_missing_fails_idempotency() -> None:
    result = stage4.evaluate_idempotency(
        first_pass_safe_task_count=16, first_pass_success_count=16,
        second_pass_safe_task_count=1, repaired_objects_now_existing_count=15,
        first_task_keys={"A"}, second_task_keys={"A"}, sandbox_hash_unchanged=True,
    )
    assert result["idempotency_passed"] is False


def test_resume_checkpoint_advances_deterministically(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    stage4.checkpoint(paths, "INPUT_FROZEN")
    data = stage4.read_json(paths.root / "workflow_checkpoints.json")
    assert data["resume_checkpoint"] == "COPIES_CREATED"
    stage4.checkpoint(paths, "COPIES_CREATED")
    assert stage4.read_json(paths.root / "workflow_checkpoints.json")["completed"] == ["INPUT_FROZEN", "COPIES_CREATED"]


def test_repeat_run_returns_existing_final_pass_without_execution() -> None:
    source = inspect.getsource(stage4.run_stage4)
    assert 'prior.get("stage4_final_status") == "PASS_MVP_END_TO_END_REPEATABLE"' in source
    assert "return prior" in source


def test_source_hash_is_rechecked_at_finalization() -> None:
    source = inspect.getsource(stage4.run_stage4)
    assert 'final_hashes = {"reference": sha256_file(reference), "target": sha256_file(target)}' in source


def test_production_d1_and_stage5_execution_remain_false() -> None:
    flags = stage4._safety_flags()
    assert flags["production_d1_allowed"] is False
    assert flags["stage5_executed"] is False


def test_cli_has_single_full_safe_pipeline_entry() -> None:
    args = skill_cli.build_parser().parse_args([
        "full-safe-pipeline", "--reference", "reference.dwg", "--target", "target.dwg",
        "--mode", "stage4-mvp", "--execute-safe-ordinary", "--alignment-evidence", "alignment.json",
    ])
    assert args.command == "full-safe-pipeline"
    assert args.execute_safe_ordinary is True


def test_stage4_has_no_forbidden_execution_calls() -> None:
    source = Path(stage4.__file__).read_text(encoding="utf-8")
    forbidden = ("SendCommand(", "CopyObjects(", "Explode(", "SaveAs(", "Close(True)", "NETLOAD")
    assert not any(token in source for token in forbidden)


def test_manual_tdb_package_keeps_execution_disabled(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    manual = stage4.build_manual_package(paths, [{
        "candidate_id": "T1", "reference_handle": "R1", "object_name": "TDbPipe",
        "semantic_type": "TDbPipe", "target_wcs_geometry": {"bbox": [[0, 0, 0], [10, 10, 0]]},
    }])
    assert manual[0]["execution_allowed"] is False
    assert manual[0]["executed"] is False
    assert "preview_reference" in manual[0]


def test_encoding_replacement_character_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="encoding replacement"):
        stage4.freeze_inputs(tmp_path / "bad�.dwg", tmp_path / "target.dwg")


def test_stage4_run_directory_has_required_bands(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    assert all(path.is_dir() for path in (
        paths.input, paths.copies, paths.scans, paths.alignment, paths.diff,
        paths.tasks, paths.execution, paths.qa, paths.previews, paths.reports,
    ))


def test_automatic_unattended_alignment_is_always_false() -> None:
    assert stage4._safety_flags()["automatic_unattended_alignment"] is False
    config = json.loads((stage4.ROOT / "skill" / "configs" / "stage4_mvp.json").read_text(encoding="utf-8"))
    assert config["automatic_unattended_alignment"] is False


def test_stage5_is_never_called_by_stage4() -> None:
    source = Path(stage4.__file__).read_text(encoding="utf-8").lower()
    assert "run_stage5" not in source
    assert '"stage5_executed": false' in source
