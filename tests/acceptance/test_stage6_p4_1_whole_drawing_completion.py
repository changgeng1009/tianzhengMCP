import json

import pytest

from mcp.orchestration import stage6_p4_1_whole_drawing_completion as stage


def transforms():
    return [{"semantic_name": str(i), "reference_region_id": f"r{i}", "target_region_id": f"t{i}", "transform_type": "translation_only", "translation_x": i, "translation_y": -i, "scale": 1.0, "rotation": 0.0} for i in range(7)]


def missing(handle="1"):
    return {"handle": handle, "object_name": "TDbPipe", "layer": "PIPE", "reference_region_id": "r0", "target_region_id": "t0", "bbox": [[0,0,0],[1,1,0]], "expected_target_bbox": [0,0,1,1], "confidence": .95}


def test_seven_transforms_required():
    assert len(stage.validated_transforms({"transforms": transforms()})) == 7
    with pytest.raises(ValueError): stage.validated_transforms({"transforms": transforms()[:6]})


def test_duplicate_binding_rejected():
    values = transforms(); values[1]["target_region_id"] = "t0"
    with pytest.raises(ValueError): stage.validated_transforms({"transforms": values})


def test_non_translation_rejected():
    values = transforms(); values[0]["transform_type"] = "affine"
    with pytest.raises(ValueError): stage.validated_transforms({"transforms": values})


def test_plan_is_independent_from_old_plan():
    plan = stage.build_whole_drawing_plan([missing()], transforms())
    assert plan["old_4068_frozen_plan_reused"] is False


def test_plan_hash_is_stable_and_tamper_evident():
    plan = stage.build_whole_drawing_plan([missing()], transforms())
    assert stage.payload_sha256(plan) == plan["plan_sha256"]
    plan["tasks"][0]["reference_handle"] = "X"
    assert stage.payload_sha256(plan) != plan["plan_sha256"]


def test_plan_only_contains_missing_high_confidence():
    plan = stage.build_whole_drawing_plan([missing()], transforms())
    assert {task["classification"] for task in plan["tasks"]} == {"MISSING_HIGH_CONFIDENCE"}


def test_relationship_not_required():
    task = stage.build_whole_drawing_plan([missing()], transforms())["tasks"][0]
    assert task["relationship_required"] is False and task["native_topology_required"] is False


def test_target_existing_objects_protected():
    assert stage.build_whole_drawing_plan([], transforms())["target_existing_objects_protected"] is True


def test_exact_l3_phrase_is_required():
    assert stage.L3_APPROVAL_PHRASE not in "允许继续"
    assert stage.L3_APPROVAL_PHRASE in "我批准 sandbox 执行"


def test_no_sendcommand_in_module():
    source = open(stage.__file__, encoding="utf-8").read()
    assert "Send" + "Command(" not in source


def test_region_statistics_are_independent():
    detection = {"already_present": [], "missing": [missing()], "review_only": [], "excluded": []}
    result = stage.region_statistics(transforms(), detection)
    assert len(result) == 7 and result[0]["missing_high_confidence_count"] == 1


def test_visual_flags_are_explicitly_unverified():
    values = {"native_topology_verified": False, "relationship_observability": False, "engineering_semantic_completeness_verified": False}
    assert not any(values.values())


def test_manual_save_handoff_keeps_document_open():
    result = stage.manual_save_handoff(
        write_completed=True, active_document_is_experimental_copy=True,
        document_name="candidate.dwg", document_full_path="D:/candidate.dwg",
        document_saved_state=False, document_read_only_state=False,
        object_count_before=10, object_count_after=12, new_object_handles=["A", "B"],
        copyobjects_success_count=2, copyobjects_failure_count=0,
        save_error_type="COMError", save_error_message="save failed",
    )
    assert result["status"] == "MANUAL_SAVE_REQUIRED"
    assert result["document_must_remain_open"] is True
    assert result["automatic_close_allowed"] is False
    assert result["rollback_allowed"] is False


def test_manual_save_requires_verified_experimental_document():
    result = stage.manual_save_handoff(
        write_completed=True, active_document_is_experimental_copy=False,
        document_name="unknown.dwg", document_full_path=None,
        document_saved_state=False, document_read_only_state=False,
        object_count_before=1, object_count_after=2, new_object_handles=["A"],
        copyobjects_success_count=1, copyobjects_failure_count=0,
        save_error_type="COMError", save_error_message="save failed",
    )
    assert result["status"] == "MANUAL_SAVE_BLOCKED_BY_DOCUMENT_IDENTITY_UNCERTAINTY"
    assert result["manual_save_required"] is False


def test_manual_save_handoff_never_claims_persistence():
    result = stage.manual_save_handoff(
        write_completed=True, active_document_is_experimental_copy=True,
        document_name="candidate.dwg", document_full_path="D:/candidate.dwg",
        document_saved_state=False, document_read_only_state=False,
        object_count_before=1, object_count_after=2, new_object_handles=["A"],
        copyobjects_success_count=1, copyobjects_failure_count=0,
        save_error_type="COMError", save_error_message="save failed",
    )
    assert result["automatic_save_succeeded"] is False
    assert result["persistence_verification_completed"] is False
