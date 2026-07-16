"""S4 控制面作业服务仅使用 synthetic identity 与 pytest 临时目录。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mcp_nextgen.control_server.service import (
    ControlJobStatus,
    ControlPlaneJobError,
    ControlPlaneService,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def _identity() -> dict[str, str]:
    return {
        "document_full_path": "mock://s4/document-1",
        "document_sha256": SHA_A,
        "document_role": "MOCK_DOCUMENT",
    }


def _service(tmp_path):
    return ControlPlaneService(tmp_path / "control-plane")


def _job(service: ControlPlaneService, *, runtime: str = "mock"):
    return service.create_job(
        job_id="s4-job-1",
        request_id="s4-request-1",
        idempotency_key="s4-idempotency-1",
        plan_hash=SHA_B,
        operation="inspect",
        product="generic_autocad",
        execution_runtime=runtime,
        backend="nextgen_mock" if runtime == "mock" else "offline",
        document_identity=_identity(),
        tasks=[
            {"task_id": "s4-task-1", "batch_id": "s4-batch-a", "operation": "inspect"},
            {"task_id": "s4-task-2", "batch_id": "s4-batch-a", "operation": "inspect"},
        ],
    )


def _approval() -> dict[str, object]:
    return {
        "job_id": "s4-job-1",
        "plan_hash": SHA_B,
        "operation": "inspect",
        "product": "generic_autocad",
        "runtime": "mock",
        "allowed_operations": ["inspect"],
        "single_use": True,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "production_allowed": False,
        "production_d1_allowed": False,
    }


def test_s4_lifecycle_uses_exact_approved_state_and_mock_simulation(tmp_path) -> None:
    service = _service(tmp_path)
    job = _job(service)
    assert job.status is ControlJobStatus.PLANNED
    job = service.approve(job.job_id, _approval())
    assert job.status is ControlJobStatus.APPROVED
    completed = service.run(job.job_id)
    assert completed.status is ControlJobStatus.COMPLETED
    assert completed.completed_task_count == 2
    assert completed.completed_batch_count == 1
    assert completed.to_dict()["real_cad_access"] is False
    assert [item.event for item in service.progress_events(job.job_id)] == [
        "PLAN_CREATED", "APPROVAL_BOUND", "JOB_STARTED", "TASK_COMPLETED", "TASK_COMPLETED", "JOB_COMPLETED",
    ]


def test_s4_approval_is_bound_to_product_runtime_and_expiry(tmp_path) -> None:
    service = _service(tmp_path)
    job = _job(service)
    invalid = _approval()
    invalid["runtime"] = "offline"
    with pytest.raises(ControlPlaneJobError, match="runtime") as caught:
        service.approve(job.job_id, invalid)
    assert caught.value.code == "APPROVAL_BINDING_MISMATCH"
    expired = _approval()
    expired["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(ControlPlaneJobError) as caught:
        service.approve(job.job_id, expired)
    assert caught.value.code == "APPROVAL_EXPIRED"


def test_s4_rejects_real_cad_path_and_unavailable_runtime_without_opening_files(tmp_path) -> None:
    service = _service(tmp_path)
    identity = _identity()
    identity["document_full_path"] = "D:/user-drawings/source.dwg"
    with pytest.raises(ControlPlaneJobError) as caught:
        service.create_job(
            job_id="s4-job-real", request_id="r", idempotency_key="i", plan_hash=SHA_B,
            operation="inspect", product="generic_autocad", execution_runtime="mock", backend="nextgen_mock",
            document_identity=identity, tasks=[{"task_id": "t", "batch_id": "b"}],
        )
    assert caught.value.code == "REAL_CAD_PATH_BLOCKED"
    with pytest.raises(ControlPlaneJobError) as caught:
        _job(service, runtime="objectarx")
    assert caught.value.code == "RUNTIME_UNAVAILABLE"


def test_s4_atomic_checkpoint_hash_chain_and_recovery(tmp_path) -> None:
    service = _service(tmp_path)
    job = _job(service)
    service.approve(job.job_id, _approval())
    service.run(job.job_id)
    recovered = ControlPlaneService(tmp_path / "control-plane").recover(job.job_id)
    assert recovered.status is ControlJobStatus.COMPLETED
    assert recovered.completed_task_ids == ["s4-task-1", "s4-task-2"]
    assert recovered.completed_batch_ids == ["s4-batch-a"]


def test_s4_approved_recovery_preserves_bound_approval_for_resume(tmp_path) -> None:
    service = _service(tmp_path)
    job = _job(service)
    service.approve(job.job_id, _approval())
    recovered_service = ControlPlaneService(tmp_path / "control-plane")
    recovered = recovered_service.recover(job.job_id)
    assert recovered.status is ControlJobStatus.APPROVED
    assert recovered.approval is not None
    assert recovered.approval["runtime"] == "mock"
    assert recovered_service.run(job.job_id).status is ControlJobStatus.COMPLETED


def test_s4_cancel_is_terminal_and_does_not_execute_tasks(tmp_path) -> None:
    service = _service(tmp_path)
    job = _job(service)
    cancelled = service.cancel(job.job_id)
    assert cancelled.status is ControlJobStatus.CANCELLED
    assert cancelled.completed_task_count == 0
    with pytest.raises(ControlPlaneJobError) as caught:
        service.run(job.job_id)
    assert caught.value.code == "INVALID_JOB_TRANSITION"


def test_s4_mock_executor_real_backend_claim_fails_closed(tmp_path) -> None:
    service = _service(tmp_path)
    job = _job(service)
    service.approve(job.job_id, _approval())
    with pytest.raises(ControlPlaneJobError) as caught:
        service.run(job.job_id, executor=lambda _job, _task: {"real_backend": True})
    assert caught.value.code == "REAL_BACKEND_BLOCKED"
    assert service.get_job(job.job_id).status is ControlJobStatus.FAILED
