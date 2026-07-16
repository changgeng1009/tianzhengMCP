"""S4 控制面 job、审批、checkpoint 与 journal 的独立合同测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from mcp_nextgen.control_server.service import (
    ControlJobStatus,
    ControlPlaneJobError,
    ControlPlaneService,
)
from mcp_nextgen.journal.store import JournalCorrupted


_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _identity() -> dict[str, str]:
    return {
        "document_full_path": "mock://s4-contract/document",
        "document_sha256": _SHA_A,
        "document_role": "MOCK_DOCUMENT",
    }


def _create(service: ControlPlaneService, *, job_id: str = "s4-contract-job"):
    return service.create_job(
        job_id=job_id,
        request_id="s4-contract-request",
        idempotency_key="s4-contract-idempotency",
        plan_hash=_SHA_B,
        operation="inspect",
        product="offline_analysis",
        execution_runtime="mock",
        backend="nextgen_mock",
        document_identity=_identity(),
        tasks=[
            {"task_id": "s4-contract-task-a", "batch_id": "s4-contract-batch", "operation": "inspect"},
            {"task_id": "s4-contract-task-b", "batch_id": "s4-contract-batch", "operation": "inspect"},
        ],
    )


def _approval(job_id: str = "s4-contract-job") -> dict[str, object]:
    return {
        "job_id": job_id,
        "plan_hash": _SHA_B,
        "operation": "inspect",
        "product": "offline_analysis",
        "runtime": "mock",
        "allowed_operations": ["inspect"],
        "single_use": True,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "production_allowed": False,
        "production_d1_allowed": False,
    }


def test_s4_job_never_auto_approves_and_can_be_cancelled(tmp_path: Path) -> None:
    service = ControlPlaneService(tmp_path / "service")
    job = _create(service)

    assert job.status is ControlJobStatus.PLANNED
    with pytest.raises(ControlPlaneJobError) as caught:
        service.run(job.job_id)
    assert caught.value.code == "INVALID_JOB_TRANSITION"

    cancelled = service.cancel(job.job_id)
    assert cancelled.status is ControlJobStatus.CANCELLED
    assert cancelled.error_code == "CANCELLED_BY_REQUEST"
    assert [event.event for event in service.progress_events(job.job_id)] == [
        "PLAN_CREATED",
        "JOB_CANCELLED",
    ]


def test_s4_approval_and_mock_progress_are_bound_and_auditable(tmp_path: Path) -> None:
    service = ControlPlaneService(tmp_path / "service")
    observed = []
    service.subscribe_progress(observed.append)
    job = _create(service)
    service.approve(job.job_id, _approval())
    completed = service.run(job.job_id)

    result = service.status(job.job_id)
    assert completed.status is ControlJobStatus.COMPLETED
    assert result["progress"] == 100
    assert result["completed_task_count"] == 2
    assert result["completed_batch_count"] == 1
    assert result["last_completed_batch_id"] == "s4-contract-batch"
    assert result["production_allowed"] is False
    assert result["production_d1_allowed"] is False
    assert result["real_backend"] is False
    assert result["real_cad_access"] is False
    assert [event.sequence for event in observed] == list(range(1, len(observed) + 1))
    assert [event.completed_count for event in observed] == [0, 0, 0, 1, 2, 2]
    assert [event.total_count for event in observed] == [2] * 6


def test_s4_recovery_rejects_tampered_append_only_journal(tmp_path: Path) -> None:
    root = tmp_path / "service"
    service = ControlPlaneService(root)
    job = _create(service)
    path = service._journal.path_for(job.job_id)  # 验证外部文件被篡改时的恢复闭环。
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["payload"]["job"]["product"] = "tianzheng_water"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

    with pytest.raises(JournalCorrupted):
        ControlPlaneService(root).recover(job.job_id)


def test_s4_runtime_backend_and_duplicate_plan_conflicts_fail_closed(tmp_path: Path) -> None:
    service = ControlPlaneService(tmp_path / "service")
    job = _create(service)

    with pytest.raises(ControlPlaneJobError) as caught:
        service.create_job(
            job_id=job.job_id,
            request_id="s4-contract-request",
            idempotency_key="s4-contract-idempotency",
            plan_hash=_SHA_B,
            operation="inspect",
            product="offline_analysis",
            execution_runtime="mock",
            backend="nextgen_mock",
            document_identity=_identity(),
            tasks=[{"task_id": "different-task", "batch_id": "s4-contract-batch", "operation": "inspect"}],
        )
    assert caught.value.code == "IDEMPOTENCY_CONFLICT"

    with pytest.raises(ControlPlaneJobError) as caught:
        service.create_job(
            job_id="s4-contract-bad-backend",
            request_id="request",
            idempotency_key="key",
            plan_hash=_SHA_B,
            operation="inspect",
            product="offline_analysis",
            execution_runtime="mock",
            backend="nextgen_real",
            document_identity=_identity(),
            tasks=[{"task_id": "task", "batch_id": "batch"}],
        )
    assert caught.value.code == "BACKEND_UNAVAILABLE"
