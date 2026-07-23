from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mcp_nextgen.s6.contracts import CadOperation, CadOperationPlan, EntitySelector, EntitySpec
from mcp_nextgen.s6.real_com_executor import S6RealComPlanExecutor
from mcp_nextgen.backends.real_autocad_com import L3SyntheticSandboxApproval, SyntheticAutoCadDocumentIdentity


class _Backend:
    def _verify(self, _identity): pass
    def _authorize(self, _identity, _approval, _operation): pass


class _Gateway:
    def __init__(self): self.rows = []
    def query_s6_entities(self, _identity, selector=None):
        return [row for row in self.rows if selector is None or selector.operation_id is None or row["operation_key"] == selector.operation_id]
    def create_s6_entity(self, _identity, spec, operation_id):
        row = {"handle": f"H{len(self.rows)+1}", "entity_type": spec.entity_type, "layer": spec.layer, "geometry": spec.geometry, "operation_key": operation_id}; self.rows.append(row); return row
    def transform_s6_entity(self, _identity, selector, operation, _parameters, operation_id):
        row = self.query_s6_entities(None, selector)[0]
        if operation == "DELETE_ENTITY": row["deleted"] = True
        if operation == "COPY_ENTITY": row = {**row, "handle": "H2", "operation_key": operation_id}; self.rows.append(row)
        return row
    def ensure_s6_resource(self, _identity, operation, parameters):
        return {"status": "CREATED", "resource": operation, "parameters": parameters}


def test_real_executor_is_fake_testable_and_l3_bound():
    identity = SyntheticAutoCadDocumentIdentity("run", "job.1", "a"*64, "C:/sandbox/a.dwg", "token.1", "now")
    plan = CadOperationPlan("job.1", "token.1", (CadOperation("arc.1", "CREATE_ARC", EntitySpec("arc", {"center": [0,0], "radius": 1, "start_angle": 0, "end_angle": 1})),),)
    # plan hash intentionally differs from S5 identity in this fake: executor must fail closed.
    approval = L3SyntheticSandboxApproval("job.1", "a"*64, "token.1", frozenset({"CREATE_ARC"}), datetime.now(timezone.utc)+timedelta(minutes=1), single_use=False)
    executor = S6RealComPlanExecutor(_Backend(), _Gateway())
    try:
        executor.execute(identity, approval, plan)
    except ValueError as exc:
        assert "plan_hash" in str(exc)
    else: raise AssertionError("不匹配计划不得执行")


def test_real_executor_uses_existing_l3_boundary_without_com_import():
    operation = CadOperation("arc.1", "CREATE_ARC", EntitySpec("arc", {"center": [0,0], "radius": 1, "start_angle": 0, "end_angle": 1}))
    plan = CadOperationPlan("job.1", "token.1", (operation,))
    identity = SyntheticAutoCadDocumentIdentity("run", "job.1", plan.plan_hash, "C:/sandbox/a.dwg", "token.1", "now")
    approval = L3SyntheticSandboxApproval("job.1", plan.plan_hash, "token.1", frozenset({"CREATE_ARC"}), datetime.now(timezone.utc)+timedelta(minutes=1), single_use=False)
    gateway = _Gateway(); result = S6RealComPlanExecutor(_Backend(), gateway).execute(identity, approval, plan)
    assert result.results[0].status == "CREATED"
    assert result.synthetic is True and result.backend == "real_autocad_com"


def test_real_executor_replays_persisted_journal_without_process_memory_or_com():
    operation = CadOperation("arc.1", "CREATE_ARC", EntitySpec("arc", {"center": [0,0], "radius": 1, "start_angle": 0, "end_angle": 1}))
    plan = CadOperationPlan("job.1", "token.1", (operation,))
    identity = SyntheticAutoCadDocumentIdentity("run", "job.1", plan.plan_hash, "C:/sandbox/a.dwg", "token.1", "now")
    approval = L3SyntheticSandboxApproval("job.1", plan.plan_hash, "token.1", frozenset({"CREATE_ARC"}), datetime.now(timezone.utc)+timedelta(minutes=1), single_use=False)
    original = S6RealComPlanExecutor(_Backend(), _Gateway()).execute(identity, approval, plan).results[0]
    gateway = _Gateway()
    replay = S6RealComPlanExecutor(_Backend(), gateway, persisted_results={"arc.1": original}).execute(identity, approval, plan)
    assert replay.results[0].status == "ALREADY_APPLIED"
    assert gateway.rows == []


def test_real_executor_refuses_false_atomic_com_transaction():
    operation = CadOperation("arc.1", "CREATE_ARC", EntitySpec("arc", {"center": [0,0], "radius": 1, "start_angle": 0, "end_angle": 1}))
    plan = CadOperationPlan("job.1", "token.1", (operation,), batch_policy="all_or_nothing")
    identity = SyntheticAutoCadDocumentIdentity("run", "job.1", plan.plan_hash, "C:/sandbox/a.dwg", "token.1", "now")
    approval = L3SyntheticSandboxApproval("job.1", plan.plan_hash, "token.1", frozenset({"CREATE_ARC"}), datetime.now(timezone.utc)+timedelta(minutes=1), single_use=False)
    with pytest.raises(ValueError, match="TRUE_ATOMIC"):
        S6RealComPlanExecutor(_Backend(), _Gateway()).execute(identity, approval, plan)
