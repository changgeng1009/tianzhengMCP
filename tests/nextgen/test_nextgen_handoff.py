"""MCP-UPGRADE-HANDOFF NextGen 安全、恢复与兼容回归测试。

本文件仅使用内存 Mock、临时目录和无 socket 的 transport policy；不会连接
AutoCAD/天正、COM，也不会读取或写入真实 DWG。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from integrations.legacy_p4_adapter import LegacyCadBackendAdapter
from mcp_nextgen.backends import (
    BackendError,
    BackendUnavailableError,
    FailureInjection,
    MockCadBackend,
    ProtectedRegion,
)
from mcp_nextgen.control_server.dispatcher import ControlPlaneError, dispatch_tool
from mcp_nextgen.control_server.server import SERVER_IDENTITY, create_mcp, mcp
from mcp_nextgen.jobs.boundaries import (
    CancellationRequested,
    DeadlineExceeded,
    SafeBoundaryController,
)
from mcp_nextgen.jobs.coordinator import LayerDCoordinator
from mcp_nextgen.jobs.models import JobRecord as StoredJobRecord
from mcp_nextgen.jobs.models import JobStatus as StoredJobStatus
from mcp_nextgen.jobs.state_machine import InvalidJobTransition, transition
from mcp_nextgen.journal.checkpoint import FileCheckpointStore
from mcp_nextgen.journal.models import CheckpointRecord, GENESIS_HASH
from mcp_nextgen.journal.store import FileJournalStore, JournalCorrupted
from mcp_nextgen.protocol.enums import ApprovalLevel, BackendKind, DocumentRole
from mcp_nextgen.protocol.models import (
    ApprovalContext,
    DocumentIdentity,
    ExecutionPlan,
    ExecutionTask,
)
from mcp_nextgen.protocol.version import (
    PROTOCOL_VERSION,
    ProtocolVersionError,
    negotiate_version,
)
from mcp_nextgen.runtime import CancellationToken, MockPluginRuntime
from mcp_nextgen.runtime.mock_plugin import RuntimeLifecycleError
from mcp_nextgen.safety.approval import (
    ApprovalRejected,
    document_identity_digest,
    validate_approval,
    validate_write_document,
)
from mcp_nextgen.safety.gate import validate_execution_binding
from mcp_nextgen.schemas.tools import NEXTGEN_TOOLS, self_check_registry
from mcp_nextgen.transport import (
    InMemoryReplayGuard,
    JsonLineCodec,
    LocalTransportPolicy,
    ReplayConflictError,
    ReplayDecision,
    TokenAuthenticator,
    TransportMessageError,
    TransportPolicyError,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def _document(*, role: DocumentRole = DocumentRole.MOCK_DOCUMENT) -> DocumentIdentity:
    return DocumentIdentity(
        document_full_path="mock://nextgen/document-1",
        document_sha256=SHA_A,
        document_role=role,
        document_id="mock-document-1",
        backend_kind=BackendKind.MOCK,
        read_only=False,
    )


def _task(
    task_id: str,
    batch_id: str,
    *,
    operation: str = "create",
    automatic_dependency: bool = False,
) -> ExecutionTask:
    return ExecutionTask(
        request_id="request-nextgen-1",
        job_id="job-nextgen-1",
        batch_id=batch_id,
        task_id=task_id,
        operation=operation,
        idempotency_key="idempotency-nextgen-1",
        automatic_dependency=automatic_dependency,
        payload={"entity_type": "LINE", "geometry": {"bbox": [20, 20, 21, 21]}},
    )


def _plan(tasks: list[ExecutionTask], *, document: DocumentIdentity | None = None) -> ExecutionPlan:
    return ExecutionPlan(
        request_id="request-nextgen-1",
        job_id="job-nextgen-1",
        idempotency_key="idempotency-nextgen-1",
        document=document or _document(),
        operation="batch.execute",
        plan_hash=SHA_B,
        tasks=tasks,
        dry_run=True,
        production_allowed=False,
    )


def _approval(plan: ExecutionPlan, *, expires_delta: timedelta = timedelta(hours=1)) -> ApprovalContext:
    operations = sorted({task.operation for task in plan.tasks} or {plan.operation})
    return ApprovalContext(
        request_id=plan.request_id,
        job_id=plan.job_id,
        idempotency_key=plan.idempotency_key,
        document=plan.document,
        plan_hash=plan.plan_hash,
        approval_level=ApprovalLevel.L1_DRY_RUN,
        allowed_operations=operations,
        expires_at=(datetime.now(timezone.utc) + expires_delta).isoformat(),
        single_use=True,
        production_allowed=False,
        production_d1_allowed=False,
        dry_run=True,
    )


def _create_job(root: Path, tasks: list[ExecutionTask]) -> tuple[LayerDCoordinator, ExecutionPlan, StoredJobRecord]:
    coordinator = LayerDCoordinator(root)
    plan = _plan(tasks)
    job, created = coordinator.create_job(plan, _approval(plan))
    assert created is True
    return coordinator, plan, job


def _request_message() -> dict[str, object]:
    params = {
        "schema_version": PROTOCOL_VERSION,
        "request_id": "request-transport-1",
        "idempotency_key": "idempotency-transport-1",
    }
    return {
        "jsonrpc": "2.0",
        "protocol_version": PROTOCOL_VERSION,
        "id": params["request_id"],
        "idempotency_key": params["idempotency_key"],
        "method": "cad.capabilities",
        "params": params,
    }


def test_server_import_surface_does_not_auto_start() -> None:
    assert mcp.name == "tianzheng-mcp-nextgen-mock"
    assert SERVER_IDENTITY["auto_start"] is False
    assert SERVER_IDENTITY["production_d1_allowed"] is False


def test_server_factory_registers_exact_nine_tools_without_running() -> None:
    server = create_mcp()
    assert sorted(server._tool_manager._tools) == sorted(NEXTGEN_TOOLS)
    assert len(server._tool_manager._tools) == 9


def test_tool_schema_registry_is_strict_and_versioned() -> None:
    result = self_check_registry()
    assert result["tool_count"] == 9
    assert result["schema_version"] == PROTOCOL_VERSION
    assert all(tool["inputSchema"]["additionalProperties"] is False for tool in NEXTGEN_TOOLS.values())
    assert all(tool["outputSchema"]["additionalProperties"] is False for tool in NEXTGEN_TOOLS.values())


def test_protocol_version_is_semver_and_negotiated() -> None:
    assert PROTOCOL_VERSION == "1.0.0"
    assert negotiate_version(("0.9.0", "1.0.0")) == "1.0.0"


def test_protocol_version_rejects_no_common_version() -> None:
    with pytest.raises(ProtocolVersionError):
        negotiate_version(("9.9.9",))


def test_local_transport_policy_accepts_loopback_only() -> None:
    policy = LocalTransportPolicy()
    assert policy.bind_host == "127.0.0.1"
    assert policy.authentication_required is True
    assert policy.production_d1_allowed is False


def test_remote_bind_is_forbidden() -> None:
    with pytest.raises(TransportPolicyError):
        LocalTransportPolicy(bind_host="0.0.0.0")


def test_unauthenticated_candidate_is_rejected() -> None:
    token = "nextgen-local-token-0123456789abcdef"
    authenticator = TokenAuthenticator.from_token(token)
    assert authenticator.verify("") is False
    assert authenticator.verify("wrong-token") is False
    assert authenticator.verify(token) is True


def test_message_size_limit_rejects_oversize_frame() -> None:
    codec = JsonLineCodec(LocalTransportPolicy(max_message_bytes=1024))
    with pytest.raises(TransportMessageError) as caught:
        codec.decode_request(b"x" * 1025 + b"\n")
    assert caught.value.code == "MESSAGE_TOO_LARGE"


def test_request_id_round_trip_is_required_and_preserved() -> None:
    codec = JsonLineCodec()
    message = _request_message()
    decoded = codec.decode_request(codec.encode_request(message))
    assert decoded["id"] == "request-transport-1"
    assert decoded["params"]["request_id"] == decoded["id"]


def test_request_id_mismatch_is_rejected() -> None:
    codec = JsonLineCodec()
    message = _request_message()
    message["params"]["request_id"] = "different-request"
    with pytest.raises(TransportMessageError) as caught:
        codec.encode_request(message)
    assert caught.value.code == "REQUEST_ID_MISMATCH"


def test_idempotency_key_mismatch_is_rejected() -> None:
    codec = JsonLineCodec()
    message = _request_message()
    message["params"]["idempotency_key"] = "different-idempotency"
    with pytest.raises(TransportMessageError) as caught:
        codec.encode_request(message)
    assert caught.value.code == "IDEMPOTENCY_KEY_MISMATCH"


def test_unknown_transport_operation_is_rejected() -> None:
    codec = JsonLineCodec()
    message = _request_message()
    message["method"] = "execute_code"
    with pytest.raises(TransportMessageError) as caught:
        codec.encode_request(message)
    assert caught.value.code == "UNKNOWN_METHOD"


def test_duplicate_request_returns_same_replay_decision() -> None:
    guard = InMemoryReplayGuard()
    payload = {"operation": "cad.capabilities", "dry_run": True}
    assert guard.check_and_record("req-1", "idem-1", payload, now=1.0) is ReplayDecision.NEW
    assert guard.check_and_record("req-1", "idem-1", payload, now=2.0) is ReplayDecision.DUPLICATE_SAME


def test_duplicate_request_with_changed_payload_conflicts() -> None:
    guard = InMemoryReplayGuard()
    guard.check_and_record("req-1", "idem-1", {"value": 1}, now=1.0)
    with pytest.raises(ReplayConflictError):
        guard.check_and_record("req-1", "idem-1", {"value": 2}, now=2.0)


def test_job_state_transition_valid_path(tmp_path: Path) -> None:
    _, _, job = _create_job(tmp_path, [_task("task-1", "batch-1")])
    assert job.status is StoredJobStatus.READY
    transition(job, StoredJobStatus.RUNNING)
    assert job.status is StoredJobStatus.RUNNING


def test_job_state_transition_rejects_terminal_restart(tmp_path: Path) -> None:
    _, _, job = _create_job(tmp_path, [_task("task-1", "batch-1")])
    job.status = StoredJobStatus.COMPLETED
    with pytest.raises(InvalidJobTransition):
        transition(job, StoredJobStatus.RUNNING)


def test_approval_gate_accepts_bound_dry_run_plan() -> None:
    plan = _plan([_task("task-1", "batch-1")])
    validate_execution_binding(
        job_id=plan.job_id,
        document_identity=plan.document.to_dict(),
        plan_hash=plan.plan_hash,
        approval_context=_approval(plan).to_dict(),
        operations=["create"],
        dry_run=True,
    )


def test_approval_gate_rejects_wrong_job_binding() -> None:
    plan = _plan([_task("task-1", "batch-1")])
    approval = _approval(plan).to_dict()
    approval["job_id"] = "job-other"
    with pytest.raises(ApprovalRejected):
        validate_approval(
            approval,
            job_id=plan.job_id,
            document_identity=plan.document.to_dict(),
            plan_hash=plan.plan_hash,
            operations=["create"],
            required_level=1,
        )


def test_document_identity_digest_is_stable_and_sensitive() -> None:
    identity = _document().to_dict()
    assert document_identity_digest(identity) == document_identity_digest(deepcopy(identity))
    changed = deepcopy(identity)
    changed["document_sha256"] = "c" * 64
    assert document_identity_digest(identity) != document_identity_digest(changed)


def test_plan_hash_must_be_full_sha256() -> None:
    plan = _plan([_task("task-1", "batch-1")])
    with pytest.raises(ValueError, match="plan_hash"):
        validate_execution_binding(
            job_id=plan.job_id,
            document_identity=plan.document.to_dict(),
            plan_hash="short",
            approval_context=_approval(plan).to_dict(),
            operations=["create"],
            dry_run=True,
        )


def test_append_only_journal_has_sequence_and_hash_chain(tmp_path: Path) -> None:
    journal = FileJournalStore(tmp_path)
    first = journal.append("job-chain", "CREATED", {})
    second = journal.append("job-chain", "RUNNING", {}, batch_id="batch-dynamic")
    assert first.sequence == 1
    assert first.previous_hash == GENESIS_HASH
    assert second.sequence == 2
    assert second.previous_hash == first.entry_hash
    assert journal.validate("job-chain") == [first, second]


def test_journal_tamper_is_detected(tmp_path: Path) -> None:
    journal = FileJournalStore(tmp_path)
    journal.append("job-tamper", "CREATED", {"safe": True})
    path = journal.path_for("job-tamper")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["payload"]["safe"] = False
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(JournalCorrupted):
        journal.validate("job-tamper")


def test_checkpoint_write_is_atomic_and_leaves_no_temp(tmp_path: Path) -> None:
    store = FileCheckpointStore(tmp_path)
    checkpoint = CheckpointRecord(
        job_id="job-atomic",
        state="RUNNING",
        plan_hash=SHA_B,
        document_identity_digest=SHA_A,
        journal_sequence=1,
        journal_head_hash=SHA_A,
        last_completed_batch_id=None,
        completed_batch_ids=[],
        completed_task_ids=[],
        pending_task_ids=["task-1"],
        auto_dependency_task_ids=[],
    )
    path = store.save(checkpoint)
    assert path.exists()
    assert store.load("job-atomic").job_id == "job-atomic"
    assert list(path.parent.glob("*.tmp")) == []
    assert list(path.parent.glob(".*.tmp")) == []


def test_dynamic_completed_batch_ids_are_not_hardcoded(tmp_path: Path) -> None:
    tasks = [
        _task("task-alpha-1", "batch-alpha-17"),
        _task("task-alpha-2", "batch-alpha-17"),
        _task("task-zeta-1", "batch-zeta-902"),
    ]
    coordinator, _, job = _create_job(tmp_path, tasks)
    coordinator.start(job)
    coordinator.mark_task_completed(job, "task-alpha-1")
    coordinator.mark_task_completed(job, "task-alpha-2")
    assert coordinator.commit_batch(job, "batch-alpha-17") is True
    coordinator.mark_task_completed(job, "task-zeta-1")
    assert coordinator.commit_batch(job, "batch-zeta-902") is True
    checkpoint = coordinator.checkpoints.load(job.job_id)
    assert checkpoint.completed_batch_ids == ["batch-alpha-17", "batch-zeta-902"]
    assert checkpoint.last_completed_batch_id == "batch-zeta-902"


def test_checkpoint_three_counts_are_independent(tmp_path: Path) -> None:
    tasks = [
        _task("task-a", "batch-dynamic-a"),
        _task("task-b", "batch-dynamic-a"),
        _task("task-c", "batch-dynamic-b"),
    ]
    coordinator, _, job = _create_job(tmp_path, tasks)
    coordinator.start(job)
    for task_id in ("task-a", "task-b"):
        coordinator.mark_task_completed(job, task_id)
    coordinator.commit_batch(job, "batch-dynamic-a")
    checkpoint = coordinator.checkpoints.load(job.job_id)
    assert checkpoint.last_completed_batch_id == "batch-dynamic-a"
    assert checkpoint.completed_batch_count == 1
    assert checkpoint.completed_task_count == 2
    assert checkpoint.last_completed_batch_id not in {"1", "2"}


def test_crash_recovery_rebuilds_from_journal(tmp_path: Path) -> None:
    coordinator, _, job = _create_job(tmp_path, [_task("task-crash", "batch-after-crash")])
    coordinator.start(job)
    coordinator.mark_task_completed(job, "task-crash")
    coordinator.commit_batch(job, "batch-after-crash")
    recovered = LayerDCoordinator(tmp_path).recover(job.job_id).job
    assert recovered.completed_task_ids == ["task-crash"]
    assert recovered.completed_batch_ids == ["batch-after-crash"]
    assert recovered.last_completed_batch_id == "batch-after-crash"


def test_resume_does_not_repeat_completed_task(tmp_path: Path) -> None:
    coordinator, _, job = _create_job(
        tmp_path,
        [_task("task-done", "batch-first"), _task("task-pending", "batch-second")],
    )
    coordinator.start(job)
    assert coordinator.mark_task_completed(job, "task-done") is True
    coordinator.commit_batch(job, "batch-first")
    view = LayerDCoordinator(tmp_path).recover(job.job_id)
    assert "task-done" not in view.planned_task_ids
    assert view.planned_task_ids == ["task-pending"]
    assert coordinator.mark_task_completed(job, "task-done") is False


def test_auto_dependency_is_classified_separately_on_resume(tmp_path: Path) -> None:
    coordinator, _, job = _create_job(
        tmp_path,
        [
            _task("task-planned", "batch-one"),
            _task("task-auto", "batch-one", automatic_dependency=True),
        ],
    )
    view = coordinator.recover(job.job_id)
    assert view.planned_task_ids == ["task-planned"]
    assert view.auto_dependency_task_ids == ["task-auto"]


def test_manual_save_required_is_checkpointed_and_recoverable(tmp_path: Path) -> None:
    coordinator, _, job = _create_job(tmp_path, [_task("task-save", "batch-save")])
    coordinator.start(job)
    coordinator.record_manual_save_required(job, "MOCK_SAVE_FAILED")
    view = LayerDCoordinator(tmp_path).recover(job.job_id)
    checkpoint = coordinator.checkpoints.load(job.job_id)
    assert view.job.status is StoredJobStatus.MANUAL_SAVE_REQUIRED
    assert view.job.manual_save_required is True
    assert checkpoint.manual_save_required is True


def test_timeout_is_enforced_at_safe_boundary() -> None:
    boundary = SafeBoundaryController.with_timeout(0)
    with pytest.raises(DeadlineExceeded):
        boundary.check()


def test_cancellation_is_deferred_inside_persistence_critical_section() -> None:
    boundary = SafeBoundaryController()
    boundary.request_cancellation()
    with boundary.persistence_critical_section():
        boundary.check()
    with pytest.raises(CancellationRequested):
        boundary.check()


def test_mock_backend_is_deterministic() -> None:
    left = MockCadBackend()
    right = MockCadBackend()
    assert left.list_documents()[0].to_dict() == right.list_documents()[0].to_dict()
    left_session = left.open_document(left.list_documents()[0])
    right_session = right.open_document(right.list_documents()[0])
    left_entity = left.create_entity(left_session.session_id, entity_type="LINE", geometry={"bbox": [2, 2, 3, 3]})
    right_entity = right.create_entity(right_session.session_id, entity_type="LINE", geometry={"bbox": [2, 2, 3, 3]})
    assert left_entity.to_dict() == right_entity.to_dict()
    assert left.inspect_document(left_session.session_id).document_sha256 == right.inspect_document(right_session.session_id).document_sha256


def test_mock_failure_injection_is_deterministic() -> None:
    backend = MockCadBackend(failure_injections=[FailureInjection("create", error_code="INJECTED")])
    session = backend.open_document(backend.list_documents()[0])
    with pytest.raises(BackendError) as caught:
        backend.create_entity(session.session_id, entity_type="LINE", geometry={"bbox": [2, 2, 3, 3]})
    assert caught.value.error_code == "INJECTED"


def test_protected_region_rejects_mock_entity_creation() -> None:
    backend = MockCadBackend(create_default_document=False)
    identity = backend.create_document(
        document_id="protected-doc",
        document_full_path="mock://protected/doc",
        protected_regions=[ProtectedRegion("pump-room", (0, 0, 10, 10))],
    )
    session = backend.open_document(identity)
    with pytest.raises(BackendError) as caught:
        backend.create_entity(session.session_id, entity_type="LINE", geometry={"bbox": [1, 1, 2, 2]})
    assert caught.value.error_code == "PROTECTED_REGION_VIOLATION"


def test_original_file_role_write_is_forbidden() -> None:
    identity = {
        "document_full_path": "D:/safe/reference.dwg",
        "document_sha256": SHA_A,
        "document_role": "REFERENCE",
    }
    with pytest.raises(ApprovalRejected, match="禁止写入"):
        validate_write_document(identity)


def test_arbitrary_code_execution_tools_are_absent() -> None:
    forbidden = {
        "execute_code",
        "send_code_to_autocad",
        "python.exec",
        "csharp.compile",
        "shell.exec",
    }
    assert forbidden.isdisjoint(NEXTGEN_TOOLS)
    assert all("code" not in tool["inputSchema"]["properties"] for tool in NEXTGEN_TOOLS.values())


def test_transport_package_contains_no_socket_listener() -> None:
    root = Path(__file__).parents[2] / "mcp_nextgen" / "transport"
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py")))
    assert "import socket" not in source
    assert ".listen(" not in source
    assert ".bind(" not in source


def test_mock_and_real_capabilities_are_strictly_separated() -> None:
    backend = MockCadBackend()
    capabilities = backend.get_capabilities()
    assert capabilities
    assert all(item.backend_kind is BackendKind.MOCK for item in capabilities)
    assert all(item.production_allowed is False for item in capabilities)
    assert all(item.real_cad_execution is False for item in capabilities)
    assert all(item.real_dwg_modified is False for item in capabilities)


def test_legacy_adapter_is_disabled_and_does_not_call_facade() -> None:
    class Facade:
        called = False

        def probe(self):
            self.called = True
            return {"unsafe": True}

    facade = Facade()
    adapter = LegacyCadBackendAdapter(facade, enabled=True)
    probe = adapter.probe()
    assert probe["enabled"] is False
    assert probe["available"] is False
    assert probe["facade_called"] is False
    assert facade.called is False
    with pytest.raises(BackendUnavailableError):
        adapter.save_document("any-session")


def test_control_dispatcher_rejects_unknown_operation() -> None:
    with pytest.raises(ControlPlaneError) as caught:
        dispatch_tool("shell.exec", {})
    assert caught.value.code == "UNKNOWN_METHOD"


def test_mock_backend_manual_save_required_preserves_session() -> None:
    backend = MockCadBackend(failure_injections=[FailureInjection("save", error_code="SAVE_FAILED")])
    session = backend.open_document(backend.list_documents()[0])
    result = backend.save_document(session.session_id)
    assert result.status == "MANUAL_SAVE_REQUIRED"
    assert backend.inspect_document(session.session_id).document_id == session.document_id
    with pytest.raises(BackendError) as caught:
        backend.close_document(session.session_id)
    assert caught.value.error_code == "MANUAL_SAVE_REQUIRED"


def test_mock_runtime_timeout_does_not_execute_batch() -> None:
    backend = MockCadBackend()
    runtime = MockPluginRuntime(backend)
    runtime.start()
    identity = backend.list_documents()[0]
    context = runtime.open_document(identity)
    plan = _plan([_task("task-timeout", "batch-timeout")], document=identity)
    result = runtime.execute_batch(context.context_id, plan, "batch-timeout", timeout_seconds=0)
    assert result.status == "TIMEOUT"
    assert result.error_code == "DEADLINE_EXCEEDED"
    assert backend.list_entities(context.session_id) == []


def test_mock_runtime_cancellation_does_not_execute_batch() -> None:
    backend = MockCadBackend()
    runtime = MockPluginRuntime(backend)
    runtime.start()
    identity = backend.list_documents()[0]
    context = runtime.open_document(identity)
    plan = _plan([_task("task-cancel", "batch-cancel")], document=identity)
    token = CancellationToken()
    token.cancel()
    result = runtime.execute_batch(context.context_id, plan, "batch-cancel", cancellation_token=token)
    assert result.status == "CANCELLED"
    assert result.error_code == "CANCELLATION_REQUESTED"
    assert backend.list_entities(context.session_id) == []


def test_mock_runtime_progress_is_monotonic() -> None:
    backend = MockCadBackend()
    runtime = MockPluginRuntime(backend)
    runtime.start()
    identity = backend.list_documents()[0]
    context = runtime.open_document(identity)
    plan = _plan(
        [_task("task-progress-1", "batch-progress"), _task("task-progress-2", "batch-progress")],
        document=identity,
    )
    result = runtime.execute_batch(context.context_id, plan, "batch-progress")
    events = runtime.progress_events(plan.job_id)
    assert result.status == "COMPLETED"
    assert [event.sequence for event in events] == [1, 2]
    assert [event.completed_task_count for event in events] == [1, 2]


def test_manual_save_required_blocks_runtime_stop() -> None:
    backend = MockCadBackend(failure_injections=[FailureInjection("save")])
    runtime = MockPluginRuntime(backend)
    runtime.start()
    context = runtime.open_document(backend.list_documents()[0])
    assert runtime.save_document(context.context_id).status == "MANUAL_SAVE_REQUIRED"
    with pytest.raises(RuntimeLifecycleError):
        runtime.stop()


def test_checkpoint_rejects_inconsistent_completed_counts() -> None:
    data = CheckpointRecord(
        job_id="job-counts",
        state="RUNNING",
        plan_hash=SHA_B,
        document_identity_digest=SHA_A,
        journal_sequence=1,
        journal_head_hash=SHA_A,
        last_completed_batch_id="batch-x",
        completed_batch_ids=["batch-x"],
        completed_task_ids=["task-x"],
        pending_task_ids=[],
        auto_dependency_task_ids=[],
    ).to_dict()
    data["completed_task_count"] = 99
    with pytest.raises(ValueError, match="completed_task_count"):
        CheckpointRecord.from_mapping(data)
