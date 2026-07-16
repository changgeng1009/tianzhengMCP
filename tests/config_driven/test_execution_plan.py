from __future__ import annotations

from copy import deepcopy

import pytest

from adapters.registry import BackendNotAvailable
from runtime.errors import PlanHashMismatch
from runtime.execution_plan import (
    ExecutionPlanBuilder,
    ExecutionPlanCanonicalizer,
    ExecutionPlanHasher,
    ExecutionPlanValidator,
    canonical_manifest_hash,
)


def _build(manifest: dict) -> dict:
    return ExecutionPlanBuilder().build(manifest)


def test_req_062_execution_plan_is_deterministic(canonical_manifest):
    assert _build(canonical_manifest) == _build(deepcopy(canonical_manifest))


def test_req_063_same_input_same_plan_hash(canonical_manifest):
    first = _build(canonical_manifest)
    second = _build(canonical_manifest)
    assert first["plan_hash"] == second["plan_hash"]
    assert first["plan_id"] == second["plan_id"]


def test_req_064_json_key_order_does_not_change_hash(canonical_manifest):
    reordered = {key: canonical_manifest[key] for key in reversed(canonical_manifest)}
    assert canonical_manifest_hash(reordered) == canonical_manifest_hash(canonical_manifest)
    assert _build(reordered)["plan_hash"] == _build(canonical_manifest)["plan_hash"]


def test_req_065_time_and_notes_do_not_change_hash(canonical_manifest):
    changed = deepcopy(canonical_manifest)
    changed["metadata"]["created_at"] = "2099-01-01T00:00:00Z"
    changed["metadata"]["notes"] = "非语义备注"
    assert canonical_manifest_hash(changed) == canonical_manifest_hash(canonical_manifest)
    assert _build(changed)["plan_hash"] == _build(canonical_manifest)["plan_hash"]


def test_req_066_path_separator_is_normalized(canonical_manifest):
    changed = deepcopy(canonical_manifest)
    changed["documents"]["reference_documents"][0]["path"] = r"inputs\fictional-reference.dwg"
    assert canonical_manifest_hash(changed) == canonical_manifest_hash(canonical_manifest)


def test_req_067_semantic_change_changes_hash(canonical_manifest):
    changed = deepcopy(canonical_manifest)
    changed["task"]["task_description"] = "另一项语义任务"
    assert canonical_manifest_hash(changed) != canonical_manifest_hash(canonical_manifest)
    assert _build(changed)["plan_hash"] != _build(canonical_manifest)["plan_hash"]


def test_req_068_blocked_reason_for_write_placeholder(canonical_manifest):
    canonical_manifest["runtime"]["runtime_mode"] = "tianzheng_hvac"
    canonical_manifest["product"]["requested_product"] = "tianzheng_hvac"
    canonical_manifest["product"]["prohibited_products"] = ["tianzheng_water"]
    canonical_manifest["workflow"]["workflow_id"] = "tianzheng_hvac_write_placeholder"
    plan = _build(canonical_manifest)
    assert plan["executable"] is False
    assert "WORKFLOW_NOT_EXECUTABLE_CURRENTLY" in plan["blocked_reasons"]


def test_req_069_approval_requirement_is_declarative(canonical_manifest):
    canonical_manifest["safety"]["requested_level"] = "L3_SANDBOX_WRITE"
    canonical_manifest["approval"]["required_level"] = "L3_SANDBOX_WRITE"
    canonical_manifest["approval"]["approval_required"] = True
    plan = _build(canonical_manifest)
    assert plan["approval_requirement"]["approval_verified"] is False
    assert "APPROVAL_REQUIRED" in plan["blocked_reasons"]


def test_approval_trace_is_explicit_and_unverified(canonical_manifest):
    canonical_manifest["approval"]["approval_reference"] = "offline-declaration-only"
    canonical_manifest["approval"]["approval_required"] = True

    plan = _build(canonical_manifest)
    trace = plan["approval_requirement"]

    assert trace["approval_declared"] is True
    assert trace["approval_reference_present"] is True
    assert trace["approval_verified"] is False
    assert trace["approval_consumed"] == "UNVERIFIED"
    assert trace["approval_expired"] == "UNVERIFIED"
    assert trace["approval_scope_match"] == "UNVERIFIED"
    assert "APPROVAL_REQUIRED" in plan["blocked_reasons"]
    assert plan["executable"] is False


def test_real_execution_remains_blocked_without_authority(canonical_manifest):
    canonical_manifest["backend"]["require_real_execution"] = True

    # 后端注册表在计划构建之前即 fail-closed；不得生成看似可执行的
    # Real 执行计划，也不得回退到 Mock。
    with pytest.raises(BackendNotAvailable):
        _build(canonical_manifest)


def test_req_070_verification_requirements_are_preserved(canonical_manifest):
    plan = _build(canonical_manifest)
    assert plan["verification_requirements"] == canonical_manifest["verification"]
    assert plan["verification_requirements"]["visual_review_required"] is True


def test_req_071_recovery_policy_is_preserved(canonical_manifest):
    plan = _build(canonical_manifest)
    assert plan["recovery_policy"] == canonical_manifest["recovery"]
    assert plan["recovery_policy"]["manual_save_required"] is True


def test_req_072_plan_verification(canonical_manifest):
    plan = _build(canonical_manifest)
    assert ExecutionPlanValidator.verify(plan)["ok"] is True
    assert ExecutionPlanHasher.hash(plan) == plan["plan_hash"]
    assert ExecutionPlanCanonicalizer.canonicalize(plan)["plan_id"] == plan["plan_id"]


def test_req_073_plan_hash_mismatch_is_blocked(canonical_manifest):
    plan = _build(canonical_manifest)
    plan["workflow_id"] = "tampered"
    with pytest.raises(PlanHashMismatch):
        ExecutionPlanValidator.verify(plan)
