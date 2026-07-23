from __future__ import annotations

from mcp_nextgen.control_server.service import ControlPlaneService
from mcp_nextgen.s6.contracts import CadOperation, CadOperationPlan, EntitySpec
from mcp_nextgen.s6.control_plane_adapter import S6MockControlPlaneAdapter, S6ControlPlaneAdapterError
from mcp_nextgen.s6.fake_backend import SyntheticCadBackend


def _plan():
    return CadOperationPlan("s6job", "s6token", (CadOperation("arc.1", "CREATE_ARC", EntitySpec("arc", {"center": [0, 0], "radius": 1, "start_angle": 0, "end_angle": 1})),))


def test_s6_adapter_reuses_s4_mock_job_approval_journal_and_checkpoint(tmp_path):
    plan = _plan(); backend = SyntheticCadBackend(job_id=plan.job_id, document_token=plan.document_token)
    adapter = S6MockControlPlaneAdapter(ControlPlaneService(tmp_path), backend)
    submitted = adapter.submit(plan, request_id="request.1", idempotency_key="key.1")
    assert submitted["backend"] == "nextgen_mock"
    result = adapter.approve_and_run(plan.job_id)
    assert result["job"]["status"] == "COMPLETED"
    assert result["real_backend"] is False
    assert result["operation_result"].results[0].status == "CREATED"


def test_s6_adapter_rejects_real_or_non_generic_route(tmp_path):
    plan = _plan(); adapter = S6MockControlPlaneAdapter(ControlPlaneService(tmp_path), SyntheticCadBackend(job_id=plan.job_id, document_token=plan.document_token))
    try:
        adapter.submit(plan, request_id="request.1", idempotency_key="key.1", execution_runtime="com", backend="real_autocad_com")
    except S6ControlPlaneAdapterError:
        pass
    else:
        raise AssertionError("不得将 S6 Mock adapter 伪装为 Real COM")
