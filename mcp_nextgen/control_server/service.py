"""S4 Mock-only MCP 控制面作业服务。

本模块仅协调内存模拟/离线计划的作业状态、审批、进度和持久化证据。它不导入
AutoCAD、COM 或任何真实 backend，也不会打开或读取 DWG/DXF。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
import uuid

from mcp_nextgen.journal.checkpoint import FileCheckpointStore
from mcp_nextgen.journal.models import CheckpointRecord, JournalEntry
from mcp_nextgen.journal.store import FileJournalStore, JournalCorrupted
from mcp_nextgen.safety.approval import document_identity_digest
from mcp_nextgen.safety.canonical import canonical_json, sha256_hex
from mcp_nextgen.safety.paths import contained_path, validate_persistence_id


S4_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PRODUCTS = frozenset({"generic_autocad", "tianzheng_water", "tianzheng_hvac", "offline_analysis"})
_RUNTIMES = frozenset({"offline", "mock"})
_BACKENDS = frozenset({"offline", "nextgen_mock"})
_CAD_SUFFIXES = frozenset({".dwg", ".dxf"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ControlPlaneJobError(RuntimeError):
    """可由 dispatcher 映射为稳定 MCP error schema 的失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ControlJobStatus(str, Enum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_TRANSITIONS: dict[ControlJobStatus, frozenset[ControlJobStatus]] = {
    ControlJobStatus.CREATED: frozenset({ControlJobStatus.PLANNED, ControlJobStatus.FAILED, ControlJobStatus.CANCELLED}),
    ControlJobStatus.PLANNED: frozenset({ControlJobStatus.APPROVED, ControlJobStatus.FAILED, ControlJobStatus.CANCELLED}),
    ControlJobStatus.APPROVED: frozenset({ControlJobStatus.RUNNING, ControlJobStatus.FAILED, ControlJobStatus.CANCELLED}),
    ControlJobStatus.RUNNING: frozenset({ControlJobStatus.COMPLETED, ControlJobStatus.FAILED, ControlJobStatus.CANCELLED}),
    ControlJobStatus.COMPLETED: frozenset(),
    ControlJobStatus.FAILED: frozenset(),
    ControlJobStatus.CANCELLED: frozenset(),
}


@dataclass
class ControlProgressEvent:
    job_id: str
    event: str
    progress: int
    completed_count: int
    total_count: int
    status: ControlJobStatus
    sequence: int
    error_code: str | None = None
    timestamp: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value


@dataclass
class ControlJob:
    job_id: str
    request_id: str
    idempotency_key: str
    plan_hash: str
    operation: str
    product: str
    execution_runtime: str
    backend: str
    document_identity: dict[str, Any]
    tasks: list[dict[str, Any]]
    status: ControlJobStatus = ControlJobStatus.CREATED
    approval: dict[str, Any] | None = None
    completed_task_ids: list[str] = field(default_factory=list)
    completed_batch_ids: list[str] = field(default_factory=list)
    last_completed_batch_id: str | None = None
    error_code: str | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    schema_version: str = S4_SCHEMA_VERSION

    @property
    def completed_task_count(self) -> int:
        return len(set(self.completed_task_ids))

    @property
    def completed_batch_count(self) -> int:
        return len(set(self.completed_batch_ids))

    def pending_tasks(self) -> list[dict[str, Any]]:
        done = set(self.completed_task_ids)
        return [item for item in self.tasks if item["task_id"] not in done]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "request_id": self.request_id,
            "idempotency_key": self.idempotency_key,
            "plan_hash": self.plan_hash,
            "operation": self.operation,
            "product": self.product,
            "execution_runtime": self.execution_runtime,
            "backend": self.backend,
            "document_identity": dict(self.document_identity),
            "tasks": [dict(item) for item in self.tasks],
            "status": self.status.value,
            "approval": dict(self.approval) if self.approval else None,
            "completed_task_ids": list(dict.fromkeys(self.completed_task_ids)),
            "completed_task_count": self.completed_task_count,
            "completed_batch_ids": list(dict.fromkeys(self.completed_batch_ids)),
            "completed_batch_count": self.completed_batch_count,
            "last_completed_batch_id": self.last_completed_batch_id,
            "error_code": self.error_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "production_allowed": False,
            "production_d1_allowed": False,
            "real_backend": False,
            "real_cad_access": False,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ControlJob":
        status = ControlJobStatus(str(value["status"]))
        job = cls(
            job_id=str(value["job_id"]),
            request_id=str(value["request_id"]),
            idempotency_key=str(value["idempotency_key"]),
            plan_hash=str(value["plan_hash"]),
            operation=str(value["operation"]),
            product=str(value["product"]),
            execution_runtime=str(value["execution_runtime"]),
            backend=str(value["backend"]),
            document_identity=dict(value["document_identity"]),
            tasks=[dict(item) for item in value["tasks"]],
            status=status,
            approval=dict(value["approval"]) if value.get("approval") else None,
            completed_task_ids=[str(item) for item in value.get("completed_task_ids", [])],
            completed_batch_ids=[str(item) for item in value.get("completed_batch_ids", [])],
            last_completed_batch_id=value.get("last_completed_batch_id"),
            error_code=value.get("error_code"),
            created_at=str(value.get("created_at", _utc_now())),
            updated_at=str(value.get("updated_at", _utc_now())),
            schema_version=str(value.get("schema_version", S4_SCHEMA_VERSION)),
        )
        if int(value.get("completed_task_count", job.completed_task_count)) != job.completed_task_count:
            raise ControlPlaneJobError("CHECKPOINT_COUNT_MISMATCH", "completed_task_count 不一致")
        if int(value.get("completed_batch_count", job.completed_batch_count)) != job.completed_batch_count:
            raise ControlPlaneJobError("CHECKPOINT_COUNT_MISMATCH", "completed_batch_count 不一致")
        return job


class _ControlJobStore:
    """仅保存可由 journal 重建的原子快照，journal 才是恢复事实来源。"""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, job_id: str) -> Path:
        validate_persistence_id(job_id, "job_id")
        return contained_path(self.root, f"{job_id}.json")

    def save(self, job: ControlJob) -> Path:
        path = self.path_for(job.job_id)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical_json(job.to_dict()) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            return path
        finally:
            if temporary.exists():
                temporary.unlink()

    def load(self, job_id: str) -> ControlJob | None:
        path = self.path_for(job_id)
        if not path.exists():
            return None
        return ControlJob.from_mapping(json.loads(path.read_text(encoding="utf-8")))


MockTaskExecutor = Callable[[ControlJob, Mapping[str, Any]], Mapping[str, Any] | None]
ProgressSubscriber = Callable[[ControlProgressEvent], None]


class ControlPlaneService:
    """S4 的可持久化 Mock-only 控制面；显式 root 由调用方提供。"""

    def __init__(self, root: str | Path) -> None:
        root_path = Path(root).resolve(strict=False)
        root_path.mkdir(parents=True, exist_ok=True)
        self._jobs = _ControlJobStore(root_path / "jobs")
        self._journal = FileJournalStore(root_path / "journal")
        self._checkpoints = FileCheckpointStore(root_path / "checkpoints")
        self._subscribers: list[ProgressSubscriber] = []
        self._events: dict[str, list[ControlProgressEvent]] = {}

    def subscribe_progress(self, callback: ProgressSubscriber) -> None:
        self._subscribers.append(callback)

    def create_job(
        self,
        *,
        job_id: str,
        request_id: str,
        idempotency_key: str,
        plan_hash: str,
        operation: str,
        product: str,
        execution_runtime: str,
        backend: str,
        document_identity: Mapping[str, Any],
        tasks: Iterable[Mapping[str, Any]],
        production_allowed: bool = False,
        production_d1_allowed: bool = False,
    ) -> ControlJob:
        """创建并自动完成 CREATED→PLANNED；审批从不在这里自动授予。"""
        self._validate_request(
            job_id=job_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            plan_hash=plan_hash,
            operation=operation,
            product=product,
            execution_runtime=execution_runtime,
            backend=backend,
            document_identity=document_identity,
            production_allowed=production_allowed,
            production_d1_allowed=production_d1_allowed,
        )
        existing = self._jobs.load(job_id)
        normalized_tasks = self._normalize_tasks(tasks, required_operation=operation)
        if existing is not None:
            incoming = {
                "request_id": request_id, "idempotency_key": idempotency_key,
                "plan_hash": plan_hash, "operation": operation, "product": product,
                "execution_runtime": execution_runtime, "backend": backend,
                "document_identity": dict(document_identity), "tasks": normalized_tasks,
            }
            expected = {key: existing.to_dict()[key] for key in incoming}
            if canonical_json(incoming) != canonical_json(expected):
                raise ControlPlaneJobError("IDEMPOTENCY_CONFLICT", "同一 job_id 的计划内容不一致")
            return existing
        job = ControlJob(
            job_id=job_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            plan_hash=plan_hash,
            operation=operation,
            product=product,
            execution_runtime=execution_runtime,
            backend=backend,
            document_identity=dict(document_identity),
            tasks=normalized_tasks,
        )
        self._journal.append(job.job_id, "JOB_CREATED", {"job": job.to_dict()})
        self._persist(job)
        self._transition(job, ControlJobStatus.PLANNED, event="PLAN_CREATED")
        return job

    def approve(self, job_id: str, approval: Mapping[str, Any]) -> ControlJob:
        job = self.get_job(job_id)
        if job.status is not ControlJobStatus.PLANNED:
            raise ControlPlaneJobError("INVALID_JOB_TRANSITION", "只有 PLANNED 作业可以审批")
        self._validate_approval(job, approval)
        job.approval = dict(approval)
        self._journal.append(job.job_id, "APPROVAL_CONTEXT_BOUND", {"approval": dict(job.approval)})
        self._transition(job, ControlJobStatus.APPROVED, event="APPROVAL_BOUND")
        return job

    def run(self, job_id: str, *, executor: MockTaskExecutor | None = None) -> ControlJob:
        """执行纯 Mock/offline 模拟；executor 只收到任务 mapping，永不获得 CAD 句柄。"""
        job = self.get_job(job_id)
        if job.status is not ControlJobStatus.APPROVED:
            raise ControlPlaneJobError("INVALID_JOB_TRANSITION", "只有 APPROVED 作业可以运行")
        if job.approval is None:
            raise ControlPlaneJobError("APPROVAL_REQUIRED", "作业没有已绑定审批")
        self._validate_approval(job, job.approval)
        self._consume_approval(job)
        self._transition(job, ControlJobStatus.RUNNING, event="JOB_STARTED")
        try:
            for task in job.pending_tasks():
                if executor is not None:
                    outcome = executor(job, task) or {}
                    if outcome.get("real_backend") or outcome.get("real_cad_access"):
                        raise ControlPlaneJobError("REAL_BACKEND_BLOCKED", "Mock 控制面拒绝真实 backend/CAD 结果")
                    if outcome.get("status") == "FAILED":
                        raise ControlPlaneJobError(str(outcome.get("error_code") or "MOCK_EXECUTION_FAILED"), "Mock 任务执行失败")
                self._complete_task(job, task)
            self._transition(job, ControlJobStatus.COMPLETED, event="JOB_COMPLETED")
        except ControlPlaneJobError as exc:
            self._fail(job, exc.code)
            raise
        except Exception as exc:
            self._fail(job, "MOCK_EXECUTION_FAILED")
            raise ControlPlaneJobError("MOCK_EXECUTION_FAILED", "Mock 执行器异常") from exc
        return job

    def cancel(self, job_id: str, *, reason: str = "CANCELLED_BY_REQUEST") -> ControlJob:
        job = self.get_job(job_id)
        if job.status in {ControlJobStatus.COMPLETED, ControlJobStatus.FAILED, ControlJobStatus.CANCELLED}:
            raise ControlPlaneJobError("INVALID_JOB_TRANSITION", "终态作业不能取消")
        job.error_code = reason
        self._transition(job, ControlJobStatus.CANCELLED, event="JOB_CANCELLED")
        return job

    def get_job(self, job_id: str) -> ControlJob:
        job = self._jobs.load(job_id)
        if job is None:
            raise ControlPlaneJobError("JOB_NOT_FOUND", f"job 不存在: {job_id}")
        return job

    def status(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        return {
            **job.to_dict(),
            "progress": self._progress(job),
            "events": [event.to_dict() for event in self._events.get(job_id, [])],
        }

    def progress_events(self, job_id: str) -> list[ControlProgressEvent]:
        self.get_job(job_id)
        return list(self._events.get(job_id, []))

    def recover(self, job_id: str) -> ControlJob:
        """只由 hash-chain journal 重放；checkpoint 只作为锚点互校验。"""
        entries = self._journal.validate(job_id)
        if not entries:
            raise ControlPlaneJobError("JOB_NOT_FOUND", f"job 不存在: {job_id}")
        job = self._replay(entries)
        checkpoint = self._checkpoints.load(job_id)
        if checkpoint is not None:
            self._checkpoints.validate_against_journal(checkpoint, self._journal)
            if checkpoint.plan_hash != job.plan_hash:
                raise JournalCorrupted("checkpoint plan_hash 与 journal 不一致")
            if checkpoint.document_identity_digest != document_identity_digest(job.document_identity):
                raise JournalCorrupted("checkpoint DocumentIdentity 与 journal 不一致")
            if checkpoint.completed_task_ids != job.completed_task_ids:
                raise JournalCorrupted("checkpoint completed_task_ids 与 journal 不一致")
        self._jobs.save(job)
        return job

    def _validate_request(self, **values: Any) -> None:
        for name in ("job_id", "request_id", "idempotency_key", "operation"):
            if not isinstance(values[name], str) or not values[name].strip():
                raise ControlPlaneJobError("INVALID_REQUEST", f"{name} 不能为空")
        validate_persistence_id(values["job_id"], "job_id")
        if not _SHA256.fullmatch(str(values["plan_hash"])):
            raise ControlPlaneJobError("INVALID_PLAN_HASH", "plan_hash 必须是小写 64 位 SHA-256")
        if values["product"] not in _PRODUCTS:
            raise ControlPlaneJobError("PRODUCT_UNSUPPORTED", "product 不在 S3 已注册产品中")
        if values["execution_runtime"] not in _RUNTIMES:
            raise ControlPlaneJobError("RUNTIME_UNAVAILABLE", "S4 仅允许 offline 或 mock runtime")
        expected_backend = "offline" if values["execution_runtime"] == "offline" else "nextgen_mock"
        if values["backend"] not in _BACKENDS or values["backend"] != expected_backend:
            raise ControlPlaneJobError("BACKEND_UNAVAILABLE", "runtime/backend 组合不可用或非 Mock-only")
        if values["production_allowed"] or values["production_d1_allowed"]:
            raise ControlPlaneJobError("PRODUCTION_D1_BLOCKED", "S4 production_allowed=false 且 production_d1_allowed=false")
        identity = dict(values["document_identity"])
        path = str(identity.get("document_full_path") or identity.get("document_path") or "")
        if not path:
            raise ControlPlaneJobError("DOCUMENT_IDENTITY_REQUIRED", "需要 document_full_path")
        if Path(path).suffix.lower() in _CAD_SUFFIXES:
            raise ControlPlaneJobError("REAL_CAD_PATH_BLOCKED", "S4 不接受 DWG/DXF 文档路径")
        if not (path.startswith("mock://") or path.startswith("offline://")):
            raise ControlPlaneJobError("DOCUMENT_IDENTITY_UNSAFE", "仅允许 mock:// 或 offline:// synthetic 文档身份")
        try:
            document_identity_digest(identity)
        except Exception as exc:
            raise ControlPlaneJobError("DOCUMENT_IDENTITY_INVALID", "DocumentIdentity 不完整或不安全") from exc

    @staticmethod
    def _normalize_tasks(
        tasks: Iterable[Mapping[str, Any]], *, required_operation: str
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw in enumerate(tasks):
            task_id = str(raw.get("task_id", ""))
            batch_id = str(raw.get("batch_id", ""))
            if not task_id or not batch_id:
                raise ControlPlaneJobError("INVALID_PLAN", "每个任务需要 task_id 和 batch_id")
            if task_id in seen:
                raise ControlPlaneJobError("DUPLICATE_TASK", f"重复 task_id: {task_id}")
            validate_persistence_id(task_id, "task_id")
            validate_persistence_id(batch_id, "batch_id")
            seen.add(task_id)
            task_operation = str(raw.get("operation", ""))
            if task_operation != required_operation:
                raise ControlPlaneJobError("INVALID_PLAN", "任务 operation 必须与计划 operation 一致")
            normalized.append({"task_id": task_id, "batch_id": batch_id, "operation": task_operation, "index": index})
        if not normalized:
            raise ControlPlaneJobError("INVALID_PLAN", "tasks 不能为空")
        return normalized

    def _validate_approval(self, job: ControlJob, approval: Mapping[str, Any]) -> None:
        try:
            expiry = datetime.fromisoformat(str(approval["expires_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError) as exc:
            raise ControlPlaneJobError("APPROVAL_EXPIRY_INVALID", "审批 expires_at 必须带时区") from exc
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ControlPlaneJobError("APPROVAL_EXPIRED", "审批已过期")
        bindings = {
            "job_id": job.job_id,
            "plan_hash": job.plan_hash,
            "operation": job.operation,
            "product": job.product,
            "runtime": job.execution_runtime,
        }
        for name, expected in bindings.items():
            if str(approval.get(name, "")) != expected:
                raise ControlPlaneJobError("APPROVAL_BINDING_MISMATCH", f"审批未绑定当前 {name}")
        allowed = {str(item) for item in approval.get("allowed_operations", [])}
        if job.operation not in allowed:
            raise ControlPlaneJobError("APPROVAL_OPERATION_REJECTED", "审批未允许当前 operation")
        if approval.get("single_use") is not True or approval.get("used_at"):
            raise ControlPlaneJobError("APPROVAL_SINGLE_USE_REQUIRED", "审批必须是未消费的 single_use")
        if approval.get("production_allowed") or approval.get("production_d1_allowed"):
            raise ControlPlaneJobError("PRODUCTION_D1_BLOCKED", "S4 不允许生产审批")

    def _consume_approval(self, job: ControlJob) -> None:
        assert job.approval is not None
        job.approval = {**job.approval, "used_at": _utc_now()}
        self._journal.append(job.job_id, "APPROVAL_CONSUMED", {"approval_digest": sha256_hex(job.approval)})
        self._persist(job)

    def _transition(self, job: ControlJob, status: ControlJobStatus, *, event: str) -> None:
        if status not in _TRANSITIONS[job.status]:
            raise ControlPlaneJobError("INVALID_JOB_TRANSITION", f"非法状态转换: {job.status.value} -> {status.value}")
        job.status = status
        job.updated_at = _utc_now()
        self._journal.append(job.job_id, "STATUS_CHANGED", {"status": status.value, "event": event, "error_code": job.error_code})
        self._persist(job)
        self._publish(job, event)

    def _complete_task(self, job: ControlJob, task: Mapping[str, Any]) -> None:
        task_id = str(task["task_id"])
        batch_id = str(task["batch_id"])
        if task_id in job.completed_task_ids:
            return
        job.completed_task_ids.append(task_id)
        batch_tasks = [item for item in job.tasks if item["batch_id"] == batch_id]
        if all(str(item["task_id"]) in set(job.completed_task_ids) for item in batch_tasks):
            job.completed_batch_ids.append(batch_id)
            job.last_completed_batch_id = batch_id
        job.updated_at = _utc_now()
        self._journal.append(job.job_id, "TASK_COMPLETED", {"task": dict(task)}, batch_id=batch_id, task_id=task_id)
        self._persist(job)
        self._publish(job, "TASK_COMPLETED")

    def _fail(self, job: ControlJob, error_code: str) -> None:
        if job.status in {ControlJobStatus.COMPLETED, ControlJobStatus.FAILED, ControlJobStatus.CANCELLED}:
            return
        job.error_code = error_code
        self._transition(job, ControlJobStatus.FAILED, event="JOB_FAILED")

    def _persist(self, job: ControlJob) -> None:
        self._jobs.save(job)
        anchor = self._journal.append(job.job_id, "CHECKPOINT_ANCHOR", {})
        checkpoint = CheckpointRecord(
            job_id=job.job_id,
            state=job.status.value,
            plan_hash=job.plan_hash,
            document_identity_digest=document_identity_digest(job.document_identity),
            journal_sequence=anchor.sequence,
            journal_head_hash=anchor.entry_hash,
            last_completed_batch_id=job.last_completed_batch_id,
            completed_batch_ids=list(dict.fromkeys(job.completed_batch_ids)),
            completed_task_ids=list(dict.fromkeys(job.completed_task_ids)),
            pending_task_ids=[str(item["task_id"]) for item in job.pending_tasks()],
            auto_dependency_task_ids=[],
            manual_save_required=False,
        )
        self._checkpoints.save(checkpoint)

    def _publish(self, job: ControlJob, event: str) -> None:
        records = self._events.setdefault(job.job_id, [])
        progress = self._progress(job)
        item = ControlProgressEvent(
            job_id=job.job_id,
            event=event,
            progress=progress,
            completed_count=job.completed_task_count,
            total_count=len(job.tasks),
            status=job.status,
            sequence=len(records) + 1,
            error_code=job.error_code,
        )
        records.append(item)
        for subscriber in tuple(self._subscribers):
            try:
                subscriber(item)
            except Exception:
                continue

    @staticmethod
    def _progress(job: ControlJob) -> int:
        return (100 * job.completed_task_count // len(job.tasks)) if job.tasks else 0

    @staticmethod
    def _replay(entries: list[JournalEntry]) -> ControlJob:
        created = next((entry for entry in entries if entry.event_type == "JOB_CREATED"), None)
        if created is None or not isinstance(created.payload.get("job"), Mapping):
            raise JournalCorrupted("缺少 JOB_CREATED 作业快照")
        job = ControlJob.from_mapping(created.payload["job"])
        for entry in entries[entries.index(created) + 1:]:
            if entry.event_type == "STATUS_CHANGED":
                job.status = ControlJobStatus(str(entry.payload["status"]))
                job.error_code = entry.payload.get("error_code")
            elif entry.event_type == "APPROVAL_CONTEXT_BOUND":
                approval = entry.payload.get("approval")
                if not isinstance(approval, Mapping):
                    raise JournalCorrupted("审批绑定事件缺少审批上下文")
                job.approval = dict(approval)
            elif entry.event_type == "APPROVAL_CONSUMED":
                if job.approval is None:
                    raise JournalCorrupted("审批消费事件没有审批上下文")
                # 消费时刻不影响绑定内容；恢复时只保持 single-use 已消费。
                job.approval = {**job.approval, "used_at": "recovered"}
            elif entry.event_type == "TASK_COMPLETED":
                if entry.task_id is None or entry.batch_id is None:
                    raise JournalCorrupted("TASK_COMPLETED 缺少 task/batch")
                if entry.task_id not in {item["task_id"] for item in job.tasks}:
                    raise JournalCorrupted("journal 引用了计划外 task")
                if entry.task_id not in job.completed_task_ids:
                    job.completed_task_ids.append(entry.task_id)
                batch_tasks = [item for item in job.tasks if item["batch_id"] == entry.batch_id]
                if batch_tasks and all(item["task_id"] in set(job.completed_task_ids) for item in batch_tasks):
                    if entry.batch_id not in job.completed_batch_ids:
                        job.completed_batch_ids.append(entry.batch_id)
                    job.last_completed_batch_id = entry.batch_id
        return job
