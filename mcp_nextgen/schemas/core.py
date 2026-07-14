"""核心协议结构的 JSON Schema（Draft 2020-12 兼容子集）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..protocol.enums import ApprovalLevel, BackendKind, DocumentRole, JobStatus
from ..protocol.version import PROTOCOL_VERSION

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


def strict_object(
    properties: dict[str, Any],
    required: list[str],
    *,
    schema_id: str | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "$schema": SCHEMA_DIALECT,
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    if schema_id:
        schema["$id"] = schema_id
    return schema


def version_property() -> dict[str, Any]:
    return {"type": "string", "const": PROTOCOL_VERSION, "pattern": SEMVER_PATTERN}


def id_property() -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "maxLength": 128, "pattern": ID_PATTERN}


def sha_property() -> dict[str, Any]:
    return {"type": "string", "pattern": SHA256_PATTERN}


EVIDENCE_PATHS = {
    "type": "array",
    "items": {"type": "string", "minLength": 1, "maxLength": 1024},
    "uniqueItems": True,
}

DOCUMENT_IDENTITY_SCHEMA = strict_object(
    {
        "schema_version": version_property(),
        "document_id": id_property(),
        "document_full_path": {"type": "string", "minLength": 1, "maxLength": 1024},
        "document_sha256": sha_property(),
        "document_role": {"type": "string", "enum": [item.value for item in DocumentRole]},
        "backend_kind": {"type": "string", "const": BackendKind.MOCK.value},
        "read_only": {"type": "boolean"},
        "created_at": {"type": "string", "format": "date-time"},
        "evidence_paths": deepcopy(EVIDENCE_PATHS),
    },
    [
        "schema_version",
        "document_id",
        "document_full_path",
        "document_sha256",
        "document_role",
        "backend_kind",
        "read_only",
        "created_at",
        "evidence_paths",
    ],
    schema_id="urn:tianzheng:mcp-nextgen:DocumentIdentity:1.0.0",
)

APPROVAL_CONTEXT_SCHEMA = strict_object(
    {
        "schema_version": version_property(),
        "request_id": id_property(),
        "job_id": id_property(),
        "idempotency_key": id_property(),
        "document": deepcopy(DOCUMENT_IDENTITY_SCHEMA),
        "plan_hash": sha_property(),
        "approval_level": {"type": "string", "enum": [item.value for item in ApprovalLevel]},
        "allowed_operations": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 128},
            "minItems": 1,
            "uniqueItems": True,
        },
        "expires_at": {"type": "string", "format": "date-time"},
        "single_use": {"type": "boolean", "const": True},
        "production_allowed": {"type": "boolean", "const": False},
        "production_d1_allowed": {"type": "boolean", "const": False},
        "dry_run": {"type": "boolean"},
        "used_at": {"type": ["string", "null"], "format": "date-time"},
        "created_at": {"type": "string", "format": "date-time"},
        "evidence_paths": deepcopy(EVIDENCE_PATHS),
    },
    [
        "schema_version",
        "request_id",
        "job_id",
        "idempotency_key",
        "document",
        "plan_hash",
        "approval_level",
        "allowed_operations",
        "expires_at",
        "single_use",
        "production_allowed",
        "production_d1_allowed",
        "dry_run",
        "created_at",
        "evidence_paths",
    ],
    schema_id="urn:tianzheng:mcp-nextgen:ApprovalContext:1.0.0",
)


def _base_record_properties() -> dict[str, Any]:
    return {
        "schema_version": version_property(),
        "request_id": id_property(),
        "job_id": id_property(),
        "idempotency_key": id_property(),
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
        "evidence_paths": deepcopy(EVIDENCE_PATHS),
    }


def _record_schema(name: str, extra: dict[str, Any], required_extra: list[str]) -> dict[str, Any]:
    properties = _base_record_properties()
    properties.update(extra)
    return strict_object(
        properties,
        [
            "schema_version", "request_id", "job_id", "idempotency_key",
            "created_at", "updated_at", "evidence_paths", *required_extra,
        ],
        schema_id=f"urn:tianzheng:mcp-nextgen:{name}:{PROTOCOL_VERSION}",
    )


CORE_SCHEMAS: dict[str, dict[str, Any]] = {
    "DocumentIdentity": DOCUMENT_IDENTITY_SCHEMA,
    "OperationIntent": _record_schema(
        "OperationIntent",
        {
            "document": deepcopy(DOCUMENT_IDENTITY_SCHEMA),
            "operation": {"type": "string", "minLength": 1},
            "dry_run": {"type": "boolean"},
            "production_allowed": {"type": "boolean", "const": False},
            "parameters": {"type": "object"},
        },
        ["document", "operation", "dry_run", "production_allowed", "parameters"],
    ),
    "ExecutionTask": _record_schema(
        "ExecutionTask",
        {
            "batch_id": id_property(),
            "task_id": id_property(),
            "operation": {"type": "string", "minLength": 1},
            "status": {"type": "string", "minLength": 1},
            "automatic_dependency": {"type": "boolean"},
            "payload": {"type": "object"},
        },
        ["batch_id", "task_id", "operation", "status", "automatic_dependency", "payload"],
    ),
    "ExecutionPlan": _record_schema(
        "ExecutionPlan",
        {
            "document": deepcopy(DOCUMENT_IDENTITY_SCHEMA),
            "operation": {"type": "string", "minLength": 1},
            "plan_hash": sha_property(),
            "tasks": {"type": "array", "items": {"type": "object"}},
            "dry_run": {"type": "boolean"},
            "production_allowed": {"type": "boolean", "const": False},
        },
        ["document", "operation", "plan_hash", "tasks", "dry_run", "production_allowed"],
    ),
    "ApprovalContext": APPROVAL_CONTEXT_SCHEMA,
    "JobRecord": _record_schema(
        "JobRecord",
        {
            "document": deepcopy(DOCUMENT_IDENTITY_SCHEMA),
            "operation": {"type": "string", "minLength": 1},
            "plan_hash": sha_property(),
            "status": {"type": "string", "enum": [item.value for item in JobStatus]},
            "approval_level": {"type": "string", "enum": [item.value for item in ApprovalLevel]},
            "production_allowed": {"type": "boolean", "const": False},
            "dry_run": {"type": "boolean"},
            "last_completed_batch_id": {"type": ["string", "null"]},
            "completed_batch_count": {"type": "integer", "minimum": 0},
            "completed_task_count": {"type": "integer", "minimum": 0},
            "error_code": {"type": ["string", "null"]},
        },
        ["document", "operation", "plan_hash", "status", "approval_level", "production_allowed", "dry_run"],
    ),
    "Checkpoint": strict_object(
        {
            "schema_version": version_property(),
            "job_id": id_property(),
            "plan_hash": sha_property(),
            "status": {"type": "string", "enum": [item.value for item in JobStatus]},
            "last_completed_batch_id": {"type": ["string", "null"]},
            "completed_batch_count": {"type": "integer", "minimum": 0},
            "completed_task_count": {"type": "integer", "minimum": 0},
            "completed_task_ids": {"type": "array", "items": id_property(), "uniqueItems": True},
            "journal_sequence": {"type": "integer", "minimum": 0},
            "journal_head_hash": sha_property(),
            "updated_at": {"type": "string", "format": "date-time"},
            "evidence_paths": deepcopy(EVIDENCE_PATHS),
        },
        [
            "schema_version", "job_id", "plan_hash", "status", "last_completed_batch_id",
            "completed_batch_count", "completed_task_count", "completed_task_ids",
            "journal_sequence", "journal_head_hash", "updated_at", "evidence_paths",
        ],
        schema_id="urn:tianzheng:mcp-nextgen:Checkpoint:1.0.0",
    ),
    "JournalEntry": strict_object(
        {
            "schema_version": version_property(),
            "job_id": id_property(),
            "batch_id": id_property(),
            "task_id": id_property(),
            "sequence": {"type": "integer", "minimum": 1},
            "status": {"type": "string", "minLength": 1},
            "previous_hash": sha_property(),
            "entry_hash": sha_property(),
            "timestamp": {"type": "string", "format": "date-time"},
            "automatic_dependency": {"type": "boolean"},
            "payload": {"type": "object"},
            "evidence_paths": deepcopy(EVIDENCE_PATHS),
        },
        [
            "schema_version", "job_id", "batch_id", "task_id", "sequence", "status",
            "previous_hash", "entry_hash", "timestamp", "automatic_dependency", "payload", "evidence_paths",
        ],
        schema_id="urn:tianzheng:mcp-nextgen:JournalEntry:1.0.0",
    ),
    "CapabilityRecord": strict_object(
        {
            "schema_version": version_property(),
            "capability_id": id_property(),
            "operation": {"type": "string", "minLength": 1},
            "backend_kind": {"type": "string", "const": BackendKind.MOCK.value},
            "available": {"type": "boolean"},
            "production_allowed": {"type": "boolean", "const": False},
            "dry_run": {"type": "boolean"},
            "evidence_paths": deepcopy(EVIDENCE_PATHS),
            "created_at": {"type": "string", "format": "date-time"},
            "updated_at": {"type": "string", "format": "date-time"},
        },
        [
            "schema_version", "capability_id", "operation", "backend_kind", "available",
            "production_allowed", "dry_run", "evidence_paths", "created_at", "updated_at",
        ],
        schema_id="urn:tianzheng:mcp-nextgen:CapabilityRecord:1.0.0",
    ),
    "ExecutionResult": _record_schema(
        "ExecutionResult",
        {
            "status": {"type": "string", "minLength": 1},
            "batch_id": {"type": ["string", "null"]},
            "task_id": {"type": ["string", "null"]},
            "production_allowed": {"type": "boolean", "const": False},
            "dry_run": {"type": "boolean"},
            "error_code": {"type": ["string", "null"]},
            "data": {"type": "object"},
        },
        ["status", "production_allowed", "dry_run", "data"],
    ),
    "ProgressEvent": strict_object(
        {
            "schema_version": version_property(),
            "request_id": id_property(),
            "job_id": id_property(),
            "sequence": {"type": "integer", "minimum": 1},
            "status": {"type": "string", "minLength": 1},
            "completed_batch_count": {"type": "integer", "minimum": 0},
            "completed_task_count": {"type": "integer", "minimum": 0},
            "total_task_count": {"type": "integer", "minimum": 0},
            "batch_id": {"type": ["string", "null"]},
            "task_id": {"type": ["string", "null"]},
            "error_code": {"type": ["string", "null"]},
            "timestamp": {"type": "string", "format": "date-time"},
            "evidence_paths": deepcopy(EVIDENCE_PATHS),
        },
        [
            "schema_version", "request_id", "job_id", "sequence", "status",
            "completed_batch_count", "completed_task_count", "total_task_count", "timestamp", "evidence_paths",
        ],
        schema_id="urn:tianzheng:mcp-nextgen:ProgressEvent:1.0.0",
    ),
    "ErrorRecord": strict_object(
        {
            "schema_version": version_property(),
            "request_id": id_property(),
            "job_id": {"type": ["string", "null"]},
            "error_code": {"type": "string", "minLength": 1},
            "message": {"type": "string", "minLength": 1},
            "status": {"type": "string", "const": "ERROR"},
            "recoverable": {"type": "boolean"},
            "details": {"type": "object"},
            "evidence_paths": deepcopy(EVIDENCE_PATHS),
            "created_at": {"type": "string", "format": "date-time"},
        },
        [
            "schema_version", "request_id", "error_code", "message", "status",
            "recoverable", "details", "evidence_paths", "created_at",
        ],
        schema_id="urn:tianzheng:mcp-nextgen:ErrorRecord:1.0.0",
    ),
}

# ExecutionPlan 中的 task 必须完整符合版本化 ExecutionTask，而非自由对象。
CORE_SCHEMAS["ExecutionPlan"]["properties"]["tasks"]["items"] = deepcopy(
    CORE_SCHEMAS["ExecutionTask"]
)
