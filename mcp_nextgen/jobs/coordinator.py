"""最小 Layer D 协调器：只管理状态和持久化，不执行任何 CAD 操作。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from mcp_nextgen.journal.checkpoint import FileCheckpointStore
from mcp_nextgen.journal.models import CheckpointRecord, JournalEntry
from mcp_nextgen.journal.store import FileJournalStore, JournalCorrupted
from mcp_nextgen.safety.approval import ApprovalPolicy, document_identity_digest
from mcp_nextgen.safety.canonical import to_json_value
from mcp_nextgen.safety.gate import validate_execution_binding

from .boundaries import SafeBoundaryController
from .idempotency import FileIdempotencyStore
from .models import JobRecord, JobStatus, TaskOrigin, TaskRecord, TaskStatus, utc_now
from .state_machine import transition
from .store import FileJobStore


def _mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    converted = to_json_value(value)
    if not isinstance(converted, Mapping):
        raise TypeError("预期协议对象或 mapping")
    return dict(converted)


def task_records(tasks: Iterable[Any]) -> dict[str, TaskRecord]:
    """将协议任务明确分类为计划任务或自动依赖任务。"""
    result: dict[str, TaskRecord] = {}
    for raw in tasks:
        item = _mapping(raw)
        task_id = str(item["task_id"])
        if task_id in result:
            raise ValueError(f"重复 task_id: {task_id}")
        automatic = bool(item.get("automatic_dependency", False))
        result[task_id] = TaskRecord(
            task_id=task_id,
            batch_id=str(item["batch_id"]),
            operation=str(item["operation"]),
            origin=TaskOrigin.AUTO_DEPENDENCY if automatic else TaskOrigin.PLANNED,
            dependency_task_ids=[str(value) for value in item.get("dependency_task_ids", [])],
            evidence_paths=[str(value) for value in item.get("evidence_paths", [])],
        )
    return result


@dataclass(frozen=True)
class ResumeView:
    job: JobRecord
    planned_task_ids: list[str]
    auto_dependency_task_ids: list[str]


class LayerDCoordinator:
    """文件型最小协调器；所有目录均受 ID allowlist 和 path containment 保护。"""

    def __init__(self, root: str | Path, *, policy: ApprovalPolicy | None = None):
        root_path = Path(root).resolve(strict=False)
        root_path.mkdir(parents=True, exist_ok=True)
        self.journal = FileJournalStore(root_path / "journal")
        self.checkpoints = FileCheckpointStore(root_path / "checkpoints")
        self.jobs = FileJobStore(root_path / "jobs")
        self.idempotency = FileIdempotencyStore(root_path / "idempotency")
        self.policy = policy or ApprovalPolicy(production_d1_allowed=False)

    def create_job(
        self,
        execution_plan: Any,
        approval_context: Any,
        *,
        boundary: SafeBoundaryController | None = None,
    ) -> tuple[JobRecord, bool]:
        plan = _mapping(execution_plan)
        approval = _mapping(approval_context)
        document = _mapping(plan["document"])
        tasks = task_records(plan.get("tasks", []))
        operations = sorted({task.operation for task in tasks.values()} or {str(plan["operation"])})
        validate_execution_binding(
            job_id=str(plan["job_id"]),
            document_identity=document,
            plan_hash=str(plan["plan_hash"]),
            approval_context=approval,
            operations=operations,
            dry_run=bool(plan.get("dry_run", True)),
            production_allowed=bool(plan.get("production_allowed", False)),
            policy=self.policy,
        )
        complete_request = {"execution_plan": plan, "approval_context": approval}
        idem, is_new = self.idempotency.begin(
            str(plan["idempotency_key"]), complete_request, str(plan["job_id"])
        )
        if not is_new:
            existing = self.jobs.load(idem.job_id)
            if existing is None:
                existing = self.recover(idem.job_id).job
            return existing, False

        job = JobRecord(
            request_id=str(plan["request_id"]),
            job_id=str(plan["job_id"]),
            idempotency_key=str(plan["idempotency_key"]),
            document_identity=document,
            plan_hash=str(plan["plan_hash"]),
            approval_context=approval,
            tasks=tasks,
        )
        guard = boundary or SafeBoundaryController()
        guard.check()
        with guard.persistence_critical_section():
            self.journal.append(job.job_id, "JOB_CREATED", {"job": job.to_dict()})
            self.jobs.save(job)
            self._set_status(job, JobStatus.VALIDATING)
            self._set_status(job, JobStatus.READY)
            self._write_checkpoint(job)
        return job, True

    def start(self, job: JobRecord, *, boundary: SafeBoundaryController | None = None) -> None:
        self._mutate_status(job, JobStatus.RUNNING, boundary)

    def mark_task_completed(
        self,
        job: JobRecord,
        task_id: str,
        *,
        evidence_paths: Iterable[str] = (),
        boundary: SafeBoundaryController | None = None,
    ) -> bool:
        if task_id not in job.tasks:
            raise KeyError(f"计划中不存在 task_id: {task_id}")
        if task_id in job.completed_task_ids:
            return False
        guard = boundary or SafeBoundaryController()
        guard.check()
        task = job.tasks[task_id]
        with guard.persistence_critical_section():
            self.journal.append(
                job.job_id,
                "TASK_COMPLETED",
                {"origin": task.origin.value, "evidence_paths": list(evidence_paths)},
                batch_id=task.batch_id,
                task_id=task_id,
            )
            task.status = TaskStatus.COMPLETED
            task.evidence_paths.extend(str(value) for value in evidence_paths)
            job.completed_task_ids.append(task_id)
            job.updated_at = utc_now()
            self.jobs.save(job)
        return True

    def commit_batch(
        self,
        job: JobRecord,
        batch_id: str,
        *,
        boundary: SafeBoundaryController | None = None,
    ) -> bool:
        """调用方仅可在对应保存/提交成功后调用；本方法不执行保存。"""
        if batch_id in job.completed_batch_ids:
            return False
        batch_tasks = [task for task in job.tasks.values() if task.batch_id == batch_id]
        if not batch_tasks:
            raise KeyError(f"计划中不存在 batch_id: {batch_id}")
        incomplete = [task.task_id for task in batch_tasks if task.task_id not in job.completed_task_ids]
        if incomplete:
            raise ValueError(f"批次仍有未完成任务: {incomplete}")
        guard = boundary or SafeBoundaryController()
        guard.check()
        with guard.persistence_critical_section():
            self.journal.append(job.job_id, "BATCH_COMMITTED", {}, batch_id=batch_id)
            job.completed_batch_ids.append(batch_id)
            job.last_completed_batch_id = batch_id
            job.updated_at = utc_now()
            self.jobs.save(job)
            self._write_checkpoint(job)
        return True

    def record_manual_save_required(
        self,
        job: JobRecord,
        error_code: str,
        *,
        boundary: SafeBoundaryController | None = None,
    ) -> None:
        guard = boundary or SafeBoundaryController()
        guard.check()
        with guard.persistence_critical_section():
            transition(job, JobStatus.MANUAL_SAVE_REQUIRED)
            job.error_code = str(error_code)
            self.journal.append(
                job.job_id,
                "STATUS_CHANGED",
                {"status": job.status.value, "error_code": job.error_code},
            )
            self.jobs.save(job)
            self._write_checkpoint(job)

    def complete(self, job: JobRecord, *, boundary: SafeBoundaryController | None = None) -> None:
        if job.pending_task_ids():
            raise ValueError("仍有未完成任务，不能完成作业")
        self._mutate_status(job, JobStatus.COMPLETED, boundary)
        self.idempotency.finish(job.idempotency_key, status="SUCCEEDED", result=job.to_dict())

    def recover(self, job_id: str) -> ResumeView:
        entries = self.journal.validate(job_id)
        if not entries:
            raise KeyError(f"job 不存在: {job_id}")
        job = self._replay(entries)
        checkpoint = self.checkpoints.load(job_id)
        if checkpoint is not None:
            self.checkpoints.validate_against_journal(checkpoint, self.journal)
            at_anchor = self._replay(entries[: checkpoint.journal_sequence])
            self._validate_checkpoint(checkpoint, at_anchor)
        completed = set(job.completed_task_ids)
        planned = [
            task.task_id for task in job.tasks.values()
            if task.task_id not in completed and task.origin is TaskOrigin.PLANNED
        ]
        automatic = [
            task.task_id for task in job.tasks.values()
            if task.task_id not in completed and task.origin is TaskOrigin.AUTO_DEPENDENCY
        ]
        return ResumeView(job, planned, automatic)

    def rollback(self, job: JobRecord) -> None:
        raise NotImplementedError("Layer D 本阶段不实现任何 CAD/DWG rollback 写入")

    def _mutate_status(
        self,
        job: JobRecord,
        target: JobStatus,
        boundary: SafeBoundaryController | None,
    ) -> None:
        guard = boundary or SafeBoundaryController()
        guard.check()
        with guard.persistence_critical_section():
            self._set_status(job, target)
            self._write_checkpoint(job)

    def _set_status(self, job: JobRecord, target: JobStatus) -> None:
        transition(job, target)
        self.journal.append(job.job_id, "STATUS_CHANGED", {"status": target.value})
        self.jobs.save(job)

    def _write_checkpoint(self, job: JobRecord) -> CheckpointRecord:
        anchor = self.journal.append(job.job_id, "CHECKPOINT_ANCHOR", {})
        checkpoint = CheckpointRecord(
            job_id=job.job_id,
            state=job.status.value,
            plan_hash=job.plan_hash,
            document_identity_digest=document_identity_digest(job.document_identity),
            journal_sequence=anchor.sequence,
            journal_head_hash=anchor.entry_hash,
            last_completed_batch_id=job.last_completed_batch_id,
            completed_batch_ids=list(job.completed_batch_ids),
            completed_task_ids=list(job.completed_task_ids),
            pending_task_ids=job.pending_task_ids(),
            auto_dependency_task_ids=[
                task.task_id for task in job.tasks.values()
                if task.origin is TaskOrigin.AUTO_DEPENDENCY
            ],
            manual_save_required=job.manual_save_required,
        )
        self.checkpoints.save(checkpoint)
        return checkpoint

    @staticmethod
    def _replay(entries: list[JournalEntry]) -> JobRecord:
        created = next((entry for entry in entries if entry.event_type == "JOB_CREATED"), None)
        if created is None or not isinstance(created.payload.get("job"), Mapping):
            raise JournalCorrupted("缺少 JOB_CREATED 作业快照")
        job = JobRecord.from_mapping(created.payload["job"])
        for entry in entries[entries.index(created) + 1 :]:
            if entry.event_type == "STATUS_CHANGED":
                job.status = JobStatus(str(entry.payload["status"]))
                job.manual_save_required = job.status is JobStatus.MANUAL_SAVE_REQUIRED
                job.error_code = entry.payload.get("error_code", job.error_code)
            elif entry.event_type == "TASK_COMPLETED" and entry.task_id:
                if entry.task_id not in job.tasks:
                    raise JournalCorrupted("journal 引用了计划外 task_id")
                if entry.task_id not in job.completed_task_ids:
                    job.completed_task_ids.append(entry.task_id)
                    job.tasks[entry.task_id].status = TaskStatus.COMPLETED
            elif entry.event_type == "BATCH_COMMITTED" and entry.batch_id:
                if entry.batch_id not in {task.batch_id for task in job.tasks.values()}:
                    raise JournalCorrupted("journal 引用了计划外 batch_id")
                if entry.batch_id not in job.completed_batch_ids:
                    job.completed_batch_ids.append(entry.batch_id)
                job.last_completed_batch_id = entry.batch_id
        return job

    @staticmethod
    def _validate_checkpoint(checkpoint: CheckpointRecord, job: JobRecord) -> None:
        if checkpoint.plan_hash != job.plan_hash:
            raise JournalCorrupted("checkpoint plan_hash 与 journal 不一致")
        if checkpoint.document_identity_digest != document_identity_digest(job.document_identity):
            raise JournalCorrupted("checkpoint DocumentIdentity 与 journal 不一致")
        if checkpoint.completed_batch_ids != job.completed_batch_ids:
            raise JournalCorrupted("checkpoint completed_batch_ids 与 journal 不一致")
        if checkpoint.completed_task_ids != job.completed_task_ids:
            raise JournalCorrupted("checkpoint completed_task_ids 与 journal 不一致")
        if checkpoint.last_completed_batch_id != job.last_completed_batch_id:
            raise JournalCorrupted("checkpoint last_completed_batch_id 与 journal 不一致")
        if checkpoint.manual_save_required != job.manual_save_required:
            raise JournalCorrupted("checkpoint manual_save_required 与 journal 不一致")
