"""合法作业状态转换。"""

from __future__ import annotations

from .models import JobRecord, JobStatus, utc_now


class InvalidJobTransition(ValueError):
    pass


TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.CREATED: frozenset({JobStatus.VALIDATING, JobStatus.FAILED}),
    JobStatus.VALIDATING: frozenset({JobStatus.READY, JobStatus.FAILED}),
    JobStatus.READY: frozenset({JobStatus.RUNNING, JobStatus.CANCELLATION_REQUESTED, JobStatus.FAILED}),
    JobStatus.RUNNING: frozenset({
        JobStatus.PAUSE_REQUESTED,
        JobStatus.CANCELLATION_REQUESTED,
        JobStatus.MANUAL_SAVE_REQUIRED,
        JobStatus.RECOVERY_REQUIRED,
        JobStatus.COMPLETED,
        JobStatus.FAILED,
    }),
    JobStatus.PAUSE_REQUESTED: frozenset({JobStatus.PAUSED_SAFE_BOUNDARY, JobStatus.FAILED}),
    JobStatus.PAUSED_SAFE_BOUNDARY: frozenset({JobStatus.RUNNING, JobStatus.CANCELLATION_REQUESTED, JobStatus.FAILED}),
    JobStatus.CANCELLATION_REQUESTED: frozenset({JobStatus.CANCELLED_SAFE_BOUNDARY, JobStatus.RECOVERY_REQUIRED, JobStatus.FAILED}),
    JobStatus.MANUAL_SAVE_REQUIRED: frozenset({JobStatus.RUNNING, JobStatus.RECOVERY_REQUIRED, JobStatus.FAILED}),
    JobStatus.RECOVERY_REQUIRED: frozenset({JobStatus.RUNNING, JobStatus.MANUAL_SAVE_REQUIRED, JobStatus.FAILED}),
    JobStatus.CANCELLED_SAFE_BOUNDARY: frozenset(),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset({JobStatus.RECOVERY_REQUIRED}),
}


def transition(job: JobRecord, target: JobStatus) -> None:
    if target not in TRANSITIONS[job.status]:
        raise InvalidJobTransition(f"非法状态转换: {job.status.value} -> {target.value}")
    job.status = target
    job.updated_at = utc_now()
    job.manual_save_required = target is JobStatus.MANUAL_SAVE_REQUIRED

