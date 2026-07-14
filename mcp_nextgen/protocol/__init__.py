"""NextGen 版本化协议模型。"""

from .enums import ApprovalLevel, BackendKind, DocumentRole, JobStatus
from .models import (
    ApprovalContext,
    CapabilityRecord,
    Checkpoint,
    DocumentIdentity,
    ErrorRecord,
    ExecutionPlan,
    ExecutionResult,
    ExecutionTask,
    JobRecord,
    JournalEntry,
    OperationIntent,
    ProgressEvent,
)
from .version import PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS, negotiate_version

__all__ = [
    "ApprovalContext",
    "ApprovalLevel",
    "BackendKind",
    "CapabilityRecord",
    "Checkpoint",
    "DocumentIdentity",
    "DocumentRole",
    "ErrorRecord",
    "ExecutionPlan",
    "ExecutionResult",
    "ExecutionTask",
    "JobRecord",
    "JobStatus",
    "JournalEntry",
    "OperationIntent",
    "PROTOCOL_VERSION",
    "ProgressEvent",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "negotiate_version",
]
