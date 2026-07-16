"""S4 dispatcher 仅连接 ControlPlaneService 的 Mock-only 合同测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mcp_nextgen.control_server.dispatcher import (
    ControlPlaneError,
    configure_control_plane_service,
    dispatch_tool,
)
from mcp_nextgen.control_server.service import ControlPlaneService
from mcp_nextgen.protocol.version import PROTOCOL_VERSION
from mcp_nextgen.schemas.tools import NEXTGEN_TOOLS


@pytest.fixture
def configured_dispatcher(tmp_path: Path):
    configure_control_plane_service(ControlPlaneService(tmp_path / "dispatcher-service"))
    try:
        yield
    finally:
        configure_control_plane_service(None)


def _document(path: str = "mock://s4-dispatcher/document") -> dict[str, object]:
    return {
        "schema_version": PROTOCOL_VERSION,
        "document_id": "s4-dispatcher-document",
        "document_full_path": path,
        "document_sha256": "a" * 64,
        "document_role": "MOCK_DOCUMENT",
        "backend_kind": "MOCK",
        "read_only": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence_paths": [],
    }


def _plan_request(
    *,
    document_path: str = "mock://s4-dispatcher/document",
    job_id: str = "s4-dispatcher-job",
) -> dict[str, object]:
    return {
        "schema_version": PROTOCOL_VERSION,
        "request_id": "s4-dispatcher-request",
        "idempotency_key": "s4-dispatcher-idempotency",
        "job_id": job_id,
        "document": _document(document_path),
        "operation": "clone",
        "product": "generic_autocad",
        "execution_runtime": "mock",
        "backend": "nextgen_mock",
        "task_ids": ["s4-dispatcher-task"],
        "dry_run": True,
        "production_allowed": False,
    }


def _approval(
    job_id: str = "s4-dispatcher-job", *, plan_hash: str = "b" * 64
) -> dict[str, object]:
    return {
        "job_id": job_id,
        "plan_hash": plan_hash,
        "operation": "clone",
        "product": "generic_autocad",
        "runtime": "mock",
        "allowed_operations": ["clone"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "single_use": True,
        "production_allowed": False,
        "production_d1_allowed": False,
    }


def test_s4_tool_registry_marks_only_actual_baseline_tools_available() -> None:
    implemented = {
        "cad.capabilities",
        "cad.documents.list",
        "cad.document.inspect",
        "cad.batch.plan",
        "cad.job.status",
        "cad.job.approve",
        "cad.job.run_mock",
        "cad.job.cancel",
        "cad.job.events",
    }
    assert {name for name, tool in NEXTGEN_TOOLS.items() if tool["available"]} == implemented
    for name, tool in NEXTGEN_TOOLS.items():
        if name in implemented:
            assert tool["status"] == "IMPLEMENTED_BASELINE"
        else:
            assert tool["status"] == "NOT_IMPLEMENTED"
            assert tool["available"] is False
        assert tool["backend_kind"] == "MOCK"
        assert tool["real_backend_available"] is False
        assert tool["production_d1_allowed"] is False


def test_s4_dispatcher_plans_approves_runs_and_queries_mock_job(configured_dispatcher) -> None:
    plan = dispatch_tool("cad.batch.plan", _plan_request())
    assert plan["status"] == "PLANNED"
    assert plan["data"]["mock_only"] is True
    assert plan["data"]["file_access_performed"] is False
    assert plan["data"]["job"]["status"] == "PLANNED"
    assert plan["data"]["job"]["approval"] is None
    assert plan["production_allowed"] is False
    assert plan["production_d1_allowed"] is False

    approval = dispatch_tool(
        "cad.job.approve",
        {
            "schema_version": PROTOCOL_VERSION,
            "request_id": "s4-dispatcher-approve-request",
            "idempotency_key": "s4-dispatcher-approve-idempotency",
            "job_id": "s4-dispatcher-job",
            "approval": _approval(plan_hash=plan["data"]["job"]["plan_hash"]),
        },
    )
    assert approval["status"] == "APPROVED"
    assert approval["data"]["job"]["approval"]["single_use"] is True

    run = dispatch_tool(
        "cad.job.run_mock",
        {
            "schema_version": PROTOCOL_VERSION,
            "request_id": "s4-dispatcher-run-request",
            "idempotency_key": "s4-dispatcher-run-idempotency",
            "job_id": "s4-dispatcher-job",
            "dry_run": True,
        },
    )
    assert run["status"] == "COMPLETED"
    assert run["data"]["job"]["completed_task_count"] == 1

    events = dispatch_tool(
        "cad.job.events",
        {
            "schema_version": PROTOCOL_VERSION,
            "request_id": "s4-dispatcher-events-request",
            "idempotency_key": "s4-dispatcher-events-idempotency",
            "job_id": "s4-dispatcher-job",
        },
    )
    assert [event["event"] for event in events["data"]["events"]] == [
        "PLAN_CREATED", "APPROVAL_BOUND", "JOB_STARTED", "TASK_COMPLETED", "JOB_COMPLETED",
    ]

    status = dispatch_tool(
        "cad.job.status",
        {
            "schema_version": PROTOCOL_VERSION,
            "request_id": "s4-dispatcher-status-request",
            "idempotency_key": "s4-dispatcher-status-idempotency",
            "job_id": "s4-dispatcher-job",
        },
    )
    assert status["status"] == "OK"
    assert status["data"]["mock_only"] is True
    assert status["data"]["job"]["progress"] == 100
    assert status["data"]["job"]["events"][0]["event"] == "PLAN_CREATED"


def test_s4_dispatcher_rejects_real_cad_path_as_string_without_file_access(configured_dispatcher) -> None:
    request = _plan_request(document_path="D:/user-drawings/source.dwg")
    with pytest.raises(ControlPlaneError) as caught:
        dispatch_tool("cad.batch.plan", request)
    assert caught.value.code == "REAL_CAD_PATH_BLOCKED"


def test_s4_dispatcher_rejects_unknown_job(configured_dispatcher) -> None:
    with pytest.raises(ControlPlaneError) as caught:
        dispatch_tool(
            "cad.job.status",
            {
                "schema_version": PROTOCOL_VERSION,
                "request_id": "s4-missing-request",
                "idempotency_key": "s4-missing-idempotency",
                "job_id": "s4-missing-job",
            },
        )
    assert caught.value.code == "JOB_NOT_FOUND"


def test_s4_dispatcher_rejects_mismatched_approval_and_cancels_unapproved_job(configured_dispatcher) -> None:
    job_id = "s4-dispatcher-cancel-job"
    plan = dispatch_tool("cad.batch.plan", _plan_request(job_id=job_id))
    invalid_approval = _approval(job_id, plan_hash=plan["data"]["job"]["plan_hash"])
    invalid_approval["runtime"] = "offline"
    with pytest.raises(ControlPlaneError) as caught:
        dispatch_tool(
            "cad.job.approve",
            {
                "schema_version": PROTOCOL_VERSION,
                "request_id": "s4-dispatcher-bad-approve-request",
                "idempotency_key": "s4-dispatcher-bad-approve-idempotency",
                "job_id": job_id,
                "approval": invalid_approval,
            },
        )
    assert caught.value.code == "APPROVAL_BINDING_MISMATCH"

    cancelled = dispatch_tool(
        "cad.job.cancel",
        {
            "schema_version": PROTOCOL_VERSION,
            "request_id": "s4-dispatcher-cancel-request",
            "idempotency_key": "s4-dispatcher-cancel-idempotency",
            "job_id": job_id,
            "reason": "S4_TEST_CANCELLED",
        },
    )
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["data"]["job"]["error_code"] == "S4_TEST_CANCELLED"
