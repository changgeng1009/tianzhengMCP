"""TianzhengBackend — minimal engineering wrapper over the native pipe surface.

This is deliberately NOT a rewrite of the S7 plugin backend. It reuses the S7 transport,
job_id / operation_id / idempotency_key, structured results and structured errors, and the
plugin's main-thread scheduling. It adds only what S8.2 asks for: create, query, and
validate a native pipe.

The Tianzheng command name never crosses this boundary. Callers pass a structured
:class:`TianzhengPipeSpec`; the command is an implementation detail of the plugin-side
creation adapter.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from mcp_nextgen.backends.base import BackendError
from mcp_nextgen.s8.persistence import (
    IDEMPOTENCY_CONFLICT,
    NATIVE_IDENTITY_MISMATCH,
    PIPE_NOT_FOUND,
)

#: The only capabilities S8.2 declares. Valves, fittings-as-first-class, equipment,
#: annotation and network editing are deliberately absent rather than declared-and-broken.
TIANZHENG_CAPABILITIES: tuple[str, ...] = (
    "create_native_pipe",
    "query_native_pipe",
    "validate_native_pipe_identity",
)

#: Plugin error code -> (retryable, human summary).
TIANZHENG_ERROR_TAXONOMY: dict[str, tuple[bool, str]] = {
    PIPE_NOT_FOUND: (False, "no such pipe in this drawing"),
    NATIVE_IDENTITY_MISMATCH: (False, "object is not a live native TDbPipe"),
    IDEMPOTENCY_CONFLICT: (False, "idempotency key reused for a different pipe"),
    "TIANZHENG_PIPE_PROPERTY_UNAVAILABLE": (False, "property has no readable route yet"),
    "TIANZHENG_PIPE_SAVE_FAILED": (True, "saving the drawing failed"),
    "TIANZHENG_PIPE_REOPEN_FAILED": (True, "reopening the drawing failed"),
    "TIANZHENG_PIPE_PERSISTENCE_FAILED": (False, "the pipe did not survive the round trip"),
}

TARGET_CLASS = "TDbPipe"


class TianzhengBackendError(BackendError):
    """Structured failure. Never a bare FAILED."""

    def __init__(self, error_code: str, message: str, *, details: Mapping[str, Any] | None = None):
        retryable, _summary = TIANZHENG_ERROR_TAXONOMY.get(error_code, (False, ""))
        super().__init__(error_code, message, recoverable=retryable, details=dict(details or {}))


@dataclass(frozen=True)
class TianzhengPipeSpec:
    """Structured pipe parameters. There is no field here that can carry a command."""

    start: tuple[float, float, float]
    end: tuple[float, float, float]

    def to_parameters(self) -> dict[str, Any]:
        return {"start": list(self.start), "end": list(self.end)}


@dataclass
class TianzhengPipeCreation:
    """Result of one create call, distinguishing the pipe from its related native objects."""

    status: str
    primary_handle: str | None = None
    primary_runtime_class: str | None = None
    related_handles: list[str] = field(default_factory=list)
    related_runtime_classes: list[str] = field(default_factory=list)
    native_object_count: int = 0
    creation_method: str = ""
    database_diff: list[dict[str, Any]] = field(default_factory=list)
    pipe_count_before: int = 0
    pipe_count_after: int = 0
    fitting_count_before: int = 0
    fitting_count_after: int = 0
    native_identity_confirmed: bool = False
    replayed_from_record: bool = False
    duplicate_created: bool = False
    record_persisted: bool = False
    snapshot: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "primary_handle": self.primary_handle,
            "primary_runtime_class": self.primary_runtime_class,
            "related_handles": self.related_handles,
            "related_runtime_classes": self.related_runtime_classes,
            "native_object_count": self.native_object_count,
            "creation_method": self.creation_method,
            "database_diff": self.database_diff,
            "pipe_count_before": self.pipe_count_before,
            "pipe_count_after": self.pipe_count_after,
            "fitting_count_before": self.fitting_count_before,
            "fitting_count_after": self.fitting_count_after,
            "native_identity_confirmed": self.native_identity_confirmed,
            "replayed_from_record": self.replayed_from_record,
            "duplicate_created": self.duplicate_created,
            "record_persisted": self.record_persisted,
            "snapshot": self.snapshot,
            "warnings": self.warnings,
        }


class SupportsCall(Protocol):
    """The slice of the S7 transport this backend needs, so tests can supply a fake."""

    def call(self, operation_type: str, *, mutating: bool, **kwargs: Any) -> dict[str, Any]: ...


class TianzhengBackend:
    """Minimal native-pipe backend over the existing S7 plugin transport."""

    def __init__(self, client: SupportsCall, *, job_id: str = "s8-tianzheng-backend",
                 poll_interval: float = 2.0, poll_timeout: float = 120.0) -> None:
        self._client = client
        self._job_id = job_id
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout

    # ------------------------------------------------------------------ capability

    @property
    def capabilities(self) -> tuple[str, ...]:
        return TIANZHENG_CAPABILITIES

    def supports(self, capability: str) -> bool:
        return capability in TIANZHENG_CAPABILITIES

    # ------------------------------------------------------------------ operations

    def create_pipe(
        self,
        document_token: str,
        spec: TianzhengPipeSpec,
        *,
        idempotency_key: str,
        operation_id: str | None = None,
    ) -> TianzhengPipeCreation:
        """Create one native pipe, or recognise that this key already did.

        The creation runs inside AutoCAD's command context, so this starts it and then polls
        for the outcome; blocking the plugin's main thread would deadlock the very command
        it queued.
        """
        parameters = spec.to_parameters()
        parameters["idempotency_key"] = idempotency_key

        started = self._call(
            "tianzheng_create_pipe",
            mutating=True,
            parameters=parameters,
            document_context={"document_token": document_token},
            operation_id=operation_id or f"create-{uuid.uuid4().hex[:8]}",
            idempotency_key=idempotency_key,
        )
        if not started.get("started"):
            raise TianzhengBackendError(
                "TIANZHENG_PIPE_PERSISTENCE_FAILED", "the plugin did not queue the creation",
                details=dict(started))

        payload = self._poll_creation()
        return self._to_creation(payload)

    def query_pipe(self, document_token: str, handle: str,
                   related_handles: Sequence[str] = ()) -> dict[str, Any]:
        """Snapshot of one pipe. Never a DBObject and never a native pointer."""
        return self._call(
            "tianzheng_query_pipe",
            mutating=False,
            parameters={"handle": handle, "related_handles": list(related_handles)},
            document_context={"document_token": document_token},
        )

    def validate_identity(self, document_token: str, handle: str) -> dict[str, Any]:
        """Re-read the object and confirm it is still a live native TDbPipe."""
        snapshot = self._call(
            "tianzheng_validate_pipe_identity",
            mutating=False,
            parameters={"handle": handle},
            document_context={"document_token": document_token},
        )
        if not snapshot.get("native_identity_confirmed"):
            raise TianzhengBackendError(
                NATIVE_IDENTITY_MISMATCH,
                f"handle {handle} is not a live native {TARGET_CLASS}",
                details=dict(snapshot))
        return snapshot

    def inventory(self, document_token: str) -> dict[str, Any]:
        """Counts of native pipes and their related fittings, for duplicate detection."""
        return self._call(
            "tianzheng_pipe_inventory",
            mutating=False,
            parameters={},
            document_context={"document_token": document_token},
        )

    # ------------------------------------------------------------------ internals

    def _call(self, operation_type: str, *, mutating: bool, **kwargs: Any) -> dict[str, Any]:
        response = self._client.call(
            operation_type, mutating=mutating, job_id=self._job_id, **kwargs)
        if not response.get("success"):
            code = response.get("error_code") or "TIANZHENG_PIPE_PERSISTENCE_FAILED"
            raise TianzhengBackendError(
                code, response.get("sanitized_message") or f"{operation_type} failed",
                details={"operation_type": operation_type})
        return response.get("result") or {}

    def _poll_creation(self) -> dict[str, Any]:
        deadline = time.monotonic() + self._poll_timeout
        while time.monotonic() < deadline:
            time.sleep(self._poll_interval)
            payload = self._call("diagnostic_native_pipe_result", mutating=False, parameters={})
            if payload.get("available") and not payload.get("running"):
                return payload.get("result") or {}
        raise TianzhengBackendError(
            "TIANZHENG_PIPE_PERSISTENCE_FAILED",
            "timed out waiting for the creation command to finish")

    @staticmethod
    def _to_creation(payload: Mapping[str, Any]) -> TianzhengPipeCreation:
        status = str(payload.get("status") or "failed")
        if status == "failed":
            raise TianzhengBackendError(
                str(payload.get("error_code") or "TIANZHENG_PIPE_PERSISTENCE_FAILED"),
                str(payload.get("error") or "creation failed"),
                details={"status": status})

        creation = TianzhengPipeCreation(
            status=status,
            primary_handle=payload.get("primary_handle"),
            primary_runtime_class=payload.get("primary_runtime_class"),
            related_handles=list(payload.get("related_handles") or []),
            related_runtime_classes=list(payload.get("related_runtime_classes") or []),
            native_object_count=int(payload.get("native_object_count") or 0),
            creation_method=str(payload.get("creation_method") or ""),
            database_diff=list(payload.get("new_objects") or []),
            pipe_count_before=int(payload.get("pipe_count_before") or 0),
            pipe_count_after=int(payload.get("pipe_count_after") or 0),
            fitting_count_before=int(payload.get("fitting_count_before") or 0),
            fitting_count_after=int(payload.get("fitting_count_after") or 0),
            native_identity_confirmed=bool(payload.get("native_identity_confirmed")),
            replayed_from_record=bool(payload.get("replayed_from_record")),
            duplicate_created=bool(payload.get("duplicate_created")),
            record_persisted=bool(payload.get("record_persisted")),
            snapshot=payload.get("snapshot"),
            warnings=list(payload.get("warnings") or []),
        )

        if status == "no_native_pipe_in_diff":
            raise TianzhengBackendError(
                NATIVE_IDENTITY_MISMATCH,
                "the command ran but produced no native TDbPipe",
                details=creation.to_dict())
        return creation
