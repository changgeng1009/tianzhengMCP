"""AutoCadPluginBackend — S6 contracts on top of the in-process AutoCAD plugin.

Layering (never inverted):

    S6 CadOperationPlan  ->  this mapping layer  ->  Plugin Protocol 2.0

The S6 contract is consumed as published. Nothing plugin-specific is pushed back into it:
plugin document tokens, session nonces and wire error codes stay inside this module, and
diagnostics travel in the existing ``details``/``data`` dictionaries rather than in new
S6 DTO fields.

Import-safe: importing this module opens no socket and starts no AutoCAD.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Mapping, Sequence

from mcp_nextgen.protocol.enums import BackendKind, DocumentRole
from mcp_nextgen.protocol.models import DocumentIdentity, ExecutionPlan, ExecutionResult
from mcp_nextgen.s6.contracts import CadOperation, CadOperationPlan, CadOperationResult, EntitySnapshot

from .base import BackendError, BackendUnavailableError, BoundaryCheck, ICadBackend, ProgressCallback
from .models import BackendCapability, BackendSession
from .plugin_transport import (
    PluginCapabilities,
    PluginExecutionOutcomeUnknown,
    PluginTransportClient,
    PluginTransportError,
)

BACKEND_ID = "autocad_plugin_backend"

#: S6 operation -> plugin operation. Anything absent is unsupported by this backend.
S6_TO_PLUGIN_OPERATION: dict[str, str] = {
    "ENSURE_LAYER": "create_layer",
    "CREATE_LINE": "create_line",
    "CREATE_CIRCLE": "create_circle",
    "CREATE_POLYLINE": "create_polyline",
    "QUERY_ENTITIES": "query_entities",
}

#: S6 entity kinds this backend can render through the plugin.
SUPPORTED_ENTITY_TYPES = frozenset({"line", "circle", "polyline"})

#: Lifecycle operations handled outside the entity batch.
LIFECYCLE_OPERATIONS = frozenset({
    "SAVE_SYNTHETIC_DOCUMENT", "CLOSE_SYNTHETIC_DOCUMENT", "REOPEN_SYNTHETIC_DOCUMENT",
})

UNSUPPORTED_OPERATION_ERROR = "UNSUPPORTED_OPERATION_BY_PLUGIN_BACKEND"

# --------------------------------------------------------------------------- errors

#: Plugin wire error -> (retryable, category). Deliberately NOT collapsed into "FAILED":
#: the caller must be able to distinguish transport from ownership from validation.
PLUGIN_ERROR_TAXONOMY: dict[str, tuple[bool, str]] = {
    # protocol / auth
    "AUTH_FAILED": (False, "authentication"),
    "AUTH_REQUIRED": (False, "authentication"),
    "INCOMPATIBLE_PROTOCOL_VERSION": (False, "protocol"),
    "PLUGIN_PROTOCOL_VERSION_MISMATCH": (False, "protocol"),
    "SESSION_NONCE_REQUIRED": (True, "session"),
    "SESSION_NONCE_INVALID": (True, "session"),
    # ownership
    "DOCUMENT_TOKEN_REQUIRED": (False, "ownership"),
    "DOCUMENT_TOKEN_INVALID": (False, "ownership"),
    "DOCUMENT_NOT_JOB_OWNED": (False, "ownership"),
    "DOCUMENT_SESSION_MISMATCH": (False, "ownership"),
    "DOCUMENT_JOB_MISMATCH": (False, "ownership"),
    "DOCUMENT_DATABASE_MISMATCH": (False, "ownership"),
    "DOCUMENT_ALREADY_CLOSED": (False, "ownership"),
    "DOCUMENT_NOT_SAVED": (False, "lifecycle"),
    # execution
    "DOCUMENT_LOCK_FAILED": (True, "execution"),
    "TRANSACTION_START_FAILED": (True, "execution"),
    "TRANSACTION_ABORTED": (False, "execution"),
    "BATCH_ROLLED_BACK": (False, "execution"),
    "ENTITY_CREATE_FAILED": (False, "execution"),
    "ENTITY_QUERY_FAILED": (False, "execution"),
    "SAVE_FAILED": (True, "lifecycle"),
    "CLOSE_FAILED": (True, "lifecycle"),
    "REOPEN_FAILED": (True, "lifecycle"),
    # validation
    "INVALID_GEOMETRY": (False, "validation"),
    "INVALID_LAYER": (False, "validation"),
    "INVALID_SANDBOX_PATH": (False, "validation"),
    "PATH_TRAVERSAL_REJECTED": (False, "validation"),
    "SANDBOX_ESCAPE_REJECTED": (False, "validation"),
    "SANDBOX_NOT_CONFIGURED": (False, "configuration"),
    "UNKNOWN_FIELD": (False, "validation"),
    "MISSING_FIELD": (False, "validation"),
    "INVALID_FIELD_TYPE": (False, "validation"),
    "INVALID_TIMEOUT": (False, "validation"),
    # idempotency
    "IDEMPOTENCY_CONFLICT": (False, "idempotency"),
    "IDEMPOTENCY_KEY_REQUIRED": (False, "idempotency"),
    # unsupported
    "UNKNOWN_OPERATION": (False, "unsupported"),
    "NOT_IMPLEMENTED_IN_STAGE": (False, "unsupported"),
    UNSUPPORTED_OPERATION_ERROR: (False, "unsupported"),
    # transport
    "FRAME_TOO_LARGE": (False, "transport"),
    "MALFORMED_FRAME": (False, "transport"),
    "TIMEOUT": (True, "transport"),
    "CONNECTION_REFUSED": (True, "transport"),
    "CONNECTION_RESET": (True, "transport"),
    "QUEUE_SATURATED": (True, "transport"),
    "OPERATION_TIMEOUT": (True, "transport"),
    "PLUGIN_HOST_NOT_LOOPBACK": (False, "configuration"),
    "PLUGIN_TOKEN_INVALID": (False, "configuration"),
    "PLUGIN_NOT_READY": (True, "availability"),
    "PLUGIN_UNAVAILABLE": (True, "availability"),
    "PLUGIN_EXECUTION_OUTCOME_UNKNOWN": (False, "execution"),
}


def classify_plugin_error(error_code: str) -> tuple[bool, str]:
    """Return ``(retryable, category)``; unknown codes are conservatively non-retryable."""
    return PLUGIN_ERROR_TAXONOMY.get(error_code, (False, "unknown"))


class PluginBackendError(BackendError):
    """Structured backend error carrying the plugin's own code and category."""

    def __init__(self, error_code: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        retryable, category = classify_plugin_error(error_code)
        super().__init__(error_code, message, recoverable=retryable, details=dict(details or {}))
        self.category = category
        self.retryable = retryable


# --------------------------------------------------------------------------- mapping


@dataclass(frozen=True)
class PlanMapping:
    """A validated translation of an S6 plan into plugin batch operations."""

    operations: tuple[dict[str, Any], ...]
    query_operations: tuple[CadOperation, ...] = ()
    lifecycle_operations: tuple[CadOperation, ...] = ()


def _point(value: Mapping[str, Any]) -> list[float]:
    return [float(value.get("x", 0.0)), float(value.get("y", 0.0)), float(value.get("z", 0.0))]


def map_operation(operation: CadOperation) -> dict[str, Any]:
    """Translate ONE S6 operation into a plugin batch operation."""
    plugin_operation = S6_TO_PLUGIN_OPERATION.get(operation.operation)
    if plugin_operation is None:
        raise PluginBackendError(
            UNSUPPORTED_OPERATION_ERROR,
            f"operation {operation.operation} is not supported by the plugin backend",
            details={"s6_operation": operation.operation},
        )

    if operation.operation == "ENSURE_LAYER":
        layer_spec = dict(operation.parameters.get("layer") or {})
        name = str(layer_spec.get("name", ""))
        parameters: dict[str, Any] = {"layer": name}
        color = layer_spec.get("color_index")
        if color is not None:
            parameters["color_index"] = int(color)
        return {
            "operation_type": plugin_operation,
            "operation_id": operation.operation_id,
            "parameters": parameters,
        }

    entity = operation.entity
    if entity is None:
        raise PluginBackendError(
            UNSUPPORTED_OPERATION_ERROR,
            f"operation {operation.operation} carries no entity",
            details={"s6_operation": operation.operation},
        )

    if entity.entity_type not in SUPPORTED_ENTITY_TYPES:
        raise PluginBackendError(
            UNSUPPORTED_OPERATION_ERROR,
            f"entity type {entity.entity_type} is not supported by the plugin backend",
            details={"entity_type": entity.entity_type},
        )

    geometry = dict(entity.geometry)
    parameters = {"layer": entity.layer}

    if entity.entity_type == "line":
        parameters["start"] = _point(geometry["start"])
        parameters["end"] = _point(geometry["end"])
    elif entity.entity_type == "circle":
        parameters["center"] = _point(geometry["center"])
        parameters["radius"] = float(geometry["radius"])
    else:  # polyline
        parameters["vertices"] = [_point(vertex) for vertex in geometry["vertices"]]
        parameters["closed"] = bool(geometry.get("closed", False))

    return {
        "operation_type": plugin_operation,
        "operation_id": operation.operation_id,
        "parameters": parameters,
    }


def map_plan(plan: CadOperationPlan) -> PlanMapping:
    """Translate a whole S6 plan, rejecting it entirely if ANY operation is unsupported.

    Rejecting up front is the point: partially sending a plan would create some entities
    and then fail, which is exactly the partial execution the plugin's all_or_nothing
    transaction is meant to prevent.
    """
    batch: list[dict[str, Any]] = []
    queries: list[CadOperation] = []
    lifecycle: list[CadOperation] = []

    for operation in plan.operations:
        if operation.operation in LIFECYCLE_OPERATIONS:
            lifecycle.append(operation)
            continue
        if operation.operation == "QUERY_ENTITIES":
            queries.append(operation)
            continue
        batch.append(map_operation(operation))  # raises on anything unsupported

    return PlanMapping(tuple(batch), tuple(queries), tuple(lifecycle))


def plan_supported(plan: CadOperationPlan) -> tuple[bool, str | None]:
    """Non-throwing capability probe used by the router."""
    try:
        map_plan(plan)
    except PluginBackendError as exc:
        return False, str(exc.details.get("s6_operation") or exc.details.get("entity_type") or exc.error_code)
    return True, None


# --------------------------------------------------------------------------- backend


@dataclass
class PluginDocumentBinding:
    """Backend-internal link between an S6 identity and the plugin's transport token."""

    document_token: str
    job_id: str
    database_fingerprint: str
    identity: DocumentIdentity
    sandbox_identity: str = ""
    saved: bool = False
    closed: bool = False


class AutoCadPluginBackend(ICadBackend):
    """``ICadBackend`` implementation backed by the in-process AutoCAD plugin.

    Capability is taken from the runtime handshake, never hardcoded: if the plugin does
    not advertise an operation, this backend reports it unsupported even though the code
    to call it exists.
    """

    backend_id = BACKEND_ID
    backend_kind = BackendKind.REAL_PLUGIN

    def __init__(self, client: PluginTransportClient, *, job_id: str = "s7-plugin-backend") -> None:
        self._client = client
        self._job_id = job_id
        self._bindings: dict[str, PluginDocumentBinding] = {}
        self._sessions: dict[str, BackendSession] = {}
        self._last_diagnostics: dict[str, Any] = {}

    # ---------------------------------------------------------------- helpers

    @property
    def client(self) -> PluginTransportClient:
        return self._client

    @property
    def last_diagnostics(self) -> dict[str, Any]:
        return dict(self._last_diagnostics)

    def _ensure_connected(self) -> PluginCapabilities:
        try:
            return self._client.connect()
        except PluginTransportError as exc:
            raise BackendUnavailableError(
                f"AutoCAD plugin backend unavailable ({exc.error_code})") from exc

    def _call(self, operation: str, *, mutating: bool, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.call(operation, mutating=mutating, **kwargs)
        except PluginExecutionOutcomeUnknown as exc:
            # Never converted into a success or a retry.
            raise PluginBackendError(exc.error_code, exc.message) from exc
        except PluginTransportError as exc:
            raise PluginBackendError(exc.error_code, exc.message, details=exc.details) from exc

        self._last_diagnostics = {
            "plugin_error_code": response.get("error_code") or None,
            "plugin_stage": response.get("stage"),
            "plugin_state": response.get("plugin_state"),
            "transaction_status": response.get("transaction_status"),
            "document_status": response.get("document_status"),
            "idempotency_status": response.get("idempotency_status"),
            "duration_ms": response.get("duration_ms"),
            "warnings": response.get("warnings") or [],
        }

        if not response.get("success"):
            code = response.get("error_code") or "PLUGIN_UNKNOWN_ERROR"
            raise PluginBackendError(
                code,
                str(response.get("sanitized_message") or "plugin rejected the request"),
                details=self._last_diagnostics,
            )
        return response

    def _binding(self, session_id: str) -> PluginDocumentBinding:
        binding = self._bindings.get(session_id)
        if binding is None:
            raise PluginBackendError(
                "DOCUMENT_TOKEN_REQUIRED", "no plugin document is bound to this backend session")
        return binding

    # ------------------------------------------------------------ ICadBackend

    def get_capabilities(self) -> list[BackendCapability]:
        """Capabilities derived from the live handshake, not from constants."""
        capabilities = self._ensure_connected()
        available = capabilities.readiness and capabilities.readiness_state.startswith("AVAILABLE")

        entries: list[BackendCapability] = []
        for s6_operation, plugin_operation in sorted(S6_TO_PLUGIN_OPERATION.items()):
            supported = available and capabilities.supports(plugin_operation)
            entries.append(BackendCapability(
                capability_id=f"{BACKEND_ID}.{s6_operation.lower()}",
                operation=s6_operation,
                backend_kind=BackendKind.REAL_PLUGIN,
                available=supported,
                production_allowed=False,
                dry_run=capabilities.dry_run_support,
                real_cad_execution=supported,
                real_dwg_modified=False,
                details={
                    "plugin_operation": plugin_operation,
                    "readiness_state": capabilities.readiness_state,
                    "capability_version": capabilities.capability_version,
                },
            ))

        for s6_operation, plugin_operation in (
            ("SAVE_SYNTHETIC_DOCUMENT", "save"),
            ("CLOSE_SYNTHETIC_DOCUMENT", "close"),
            ("REOPEN_SYNTHETIC_DOCUMENT", "reopen"),
        ):
            supported = available and capabilities.supports(plugin_operation)
            entries.append(BackendCapability(
                capability_id=f"{BACKEND_ID}.{s6_operation.lower()}",
                operation=s6_operation,
                backend_kind=BackendKind.REAL_PLUGIN,
                available=supported,
                production_allowed=False,
                dry_run=False,
                real_cad_execution=supported,
                real_dwg_modified=supported,
                details={"plugin_operation": plugin_operation,
                         "persistence_support": capabilities.persistence_support},
            ))
        return entries

    def list_documents(self) -> list[DocumentIdentity]:
        """Only documents this backend created. A user drawing can never appear here."""
        return [binding.identity for binding in self._bindings.values() if not binding.closed]

    def open_document(self, expected_identity: DocumentIdentity) -> BackendSession:
        """Create a NEW job-owned synthetic document.

        There is deliberately no way to open an arbitrary path: the plugin creates a blank
        drawing and returns a token. ``expected_identity`` is honoured only for a document
        this backend previously created and closed (reopen).
        """
        binding = self._find_binding_by_identity(expected_identity)
        if binding is not None and binding.closed:
            return self.reopen_document(expected_identity)
        return self.create_synthetic_document()

    def create_synthetic_document(self) -> BackendSession:
        self._ensure_connected()
        response = self._call(
            "create_synthetic_document", mutating=True, job_id=self._job_id, document_context={})
        result = response.get("result") or {}

        token = str(result.get("document_token", ""))
        fingerprint = str(result.get("database_fingerprint", ""))
        identity = self._identity_for(token, fingerprint)

        session_id = f"plugin-{token[:16]}"
        self._bindings[session_id] = PluginDocumentBinding(
            document_token=token, job_id=self._job_id,
            database_fingerprint=fingerprint, identity=identity)

        session = BackendSession(
            session_id=session_id, backend_kind=BackendKind.REAL_PLUGIN,
            document_id=identity.document_id, opened_identity=identity,
            connected=True, document_open=True, manual_save_required=True)
        self._sessions[session_id] = session
        return session

    def inspect_document(self, session_id: str) -> DocumentIdentity:
        return self._binding(session_id).identity

    def list_entities(self, session_id: str) -> list[dict[str, Any]]:
        binding = self._binding(session_id)
        response = self._call(
            "query_entities", mutating=False, job_id=binding.job_id,
            document_context={"document_token": binding.document_token}, parameters={})
        return list((response.get("result") or {}).get("entities") or [])

    def execute_batch(
        self,
        session_id: str,
        plan: ExecutionPlan,
        batch_id: str,
        *,
        progress_callback: ProgressCallback | None = None,
        boundary_check: BoundaryCheck | None = None,
    ) -> ExecutionResult:
        """``ICadBackend`` batch entry point. Accepts an S6 plan carried in the plan payload."""
        cad_plan = _extract_cad_plan(plan)
        outcome = self.execute_cad_plan(session_id, cad_plan, batch_id=batch_id,
                                        progress_callback=progress_callback,
                                        boundary_check=boundary_check)
        return outcome

    def execute_cad_plan(
        self,
        session_id: str,
        plan: CadOperationPlan,
        *,
        batch_id: str | None = None,
        idempotency_key: str | None = None,
        progress_callback: ProgressCallback | None = None,
        boundary_check: BoundaryCheck | None = None,
    ) -> ExecutionResult:
        """Execute one S6 plan as ONE plugin batch (one lock, one transaction)."""
        binding = self._binding(session_id)
        if boundary_check is not None:
            boundary_check()

        mapping = map_plan(plan)  # raises UNSUPPORTED_OPERATION_BY_PLUGIN_BACKEND before sending
        key = idempotency_key or plan.plan_hash
        results: list[CadOperationResult] = []
        data: dict[str, Any] = {"actual_backend_used": BACKEND_ID}

        if mapping.operations:
            if progress_callback is not None:
                progress_callback(plan.job_id, "batch", 0, len(mapping.operations))

            response = self._call(
                "batch_execute", mutating=True, job_id=binding.job_id,
                document_context={"document_token": binding.document_token},
                parameters={"transaction_mode": "all_or_nothing",
                            "operations": list(mapping.operations)},
                idempotency_key=key, dry_run=plan.dry_run)

            batch = response.get("result") or {}
            data.update({
                "batch_id": batch.get("batch_id") or batch_id,
                "transaction_mode": batch.get("transaction_mode"),
                "transaction_status": batch.get("transaction_status"),
                "rollback_status": batch.get("rollback_status"),
                "partial_commit_status": batch.get("partial_commit_status"),
                "idempotency_status": batch.get("idempotency_status"),
                "plugin_plan_hash": batch.get("plan_hash"),
                "created_count": batch.get("created_count", 0),
                "handles": response.get("handles") or [],
                "entity_ids": response.get("entity_ids") or [],
            })
            results.extend(_map_batch_results(batch))

            if progress_callback is not None:
                progress_callback(plan.job_id, "batch", len(mapping.operations), len(mapping.operations))

        for query in mapping.query_operations:
            entities = self.list_entities(session_id)
            results.append(CadOperationResult(
                query.operation_id, "QUERY_OK",
                tuple(_to_snapshot(item, query.operation_id) for item in entities)))
            data["query_entity_count"] = len(entities)

        data["operation_results"] = [item.to_dict() for item in results]
        data["plugin_diagnostics"] = self.last_diagnostics

        return ExecutionResult(
            request_id=batch_id or plan.plan_id, job_id=plan.job_id,
            idempotency_key=key, status="COMPLETED",
            batch_id=batch_id, dry_run=plan.dry_run, data=data)

    def save_document(self, session_id: str) -> ExecutionResult:
        binding = self._binding(session_id)
        file_name = _sandbox_file_name(binding.document_token)
        response = self._call(
            "save", mutating=True, job_id=binding.job_id,
            document_context={"document_token": binding.document_token},
            parameters={"file_name": file_name})
        result = response.get("result") or {}
        binding.saved = True
        binding.sandbox_identity = str(result.get("sandbox_identity", file_name))
        return ExecutionResult(
            request_id=f"save-{session_id}", job_id=binding.job_id,
            idempotency_key=binding.document_token[:32], status="COMPLETED", dry_run=False,
            data={"actual_backend_used": BACKEND_ID, "save_status": result.get("save_status"),
                  "sandbox_identity": binding.sandbox_identity,
                  "plugin_diagnostics": self.last_diagnostics})

    def close_document(self, session_id: str, *, save: bool = False) -> ExecutionResult:
        binding = self._binding(session_id)
        if save and not binding.saved:
            self.save_document(session_id)
        response = self._call(
            "close", mutating=True, job_id=binding.job_id,
            document_context={"document_token": binding.document_token})
        binding.closed = True
        session = self._sessions.get(session_id)
        if session is not None:
            session.document_open = False
        return ExecutionResult(
            request_id=f"close-{session_id}", job_id=binding.job_id,
            idempotency_key=binding.document_token[:32], status="COMPLETED", dry_run=False,
            data={"actual_backend_used": BACKEND_ID,
                  "document_status": (response.get("result") or {}).get("document_status"),
                  "plugin_diagnostics": self.last_diagnostics})

    def reopen_document(self, expected_identity: DocumentIdentity) -> BackendSession:
        """Reopen the exact sandbox path the plugin itself saved. No caller path is accepted."""
        binding = self._find_binding_by_identity(expected_identity)
        if binding is None:
            raise PluginBackendError(
                "DOCUMENT_TOKEN_INVALID", "no plugin document matches the expected identity")

        response = self._call(
            "reopen", mutating=True, job_id=binding.job_id,
            document_context={"document_token": binding.document_token})
        result = response.get("result") or {}

        new_token = str(result.get("document_token", ""))
        fingerprint = str(result.get("database_fingerprint", ""))
        identity = self._identity_for(new_token, fingerprint)

        # The old binding dies with the old token; a reopened document is a new binding.
        old_session_id = next(
            (key for key, value in self._bindings.items() if value.document_token == binding.document_token), None)
        if old_session_id is not None:
            self._bindings.pop(old_session_id, None)
            self._sessions.pop(old_session_id, None)

        session_id = f"plugin-{new_token[:16]}"
        self._bindings[session_id] = PluginDocumentBinding(
            document_token=new_token, job_id=binding.job_id,
            database_fingerprint=fingerprint, identity=identity,
            sandbox_identity=str(result.get("sandbox_identity", binding.sandbox_identity)), saved=True)

        session = BackendSession(
            session_id=session_id, backend_kind=BackendKind.REAL_PLUGIN,
            document_id=identity.document_id, opened_identity=identity,
            connected=True, document_open=True, manual_save_required=True)
        self._sessions[session_id] = session
        return session

    # ------------------------------------------------------------- internals

    def _identity_for(self, token: str, fingerprint: str) -> DocumentIdentity:
        """S6 identity for a plugin document.

        The transport token is never exposed as the S6 identity; a stable digest is used,
        so plugin-internal identity does not leak into the published contract.
        """
        digest = sha256(f"{token}|{fingerprint}".encode("utf-8")).hexdigest()
        return DocumentIdentity(
            document_full_path=f"plugin-synthetic://{digest[:16]}",
            document_sha256=digest,
            # SANDBOX_COPY is the S6 role for a controlled, non-user drawing.
            document_role=DocumentRole.SANDBOX_COPY,
            document_id=f"plugin-doc-{digest[:12]}",
            backend_kind=BackendKind.REAL_PLUGIN,
            read_only=False,
        )

    def _find_binding_by_identity(self, identity: DocumentIdentity) -> PluginDocumentBinding | None:
        for binding in self._bindings.values():
            if binding.identity.document_sha256 == identity.document_sha256:
                return binding
        return None


# --------------------------------------------------------------------------- utils


def _sandbox_file_name(token: str) -> str:
    """Backend-generated sandbox file name. Callers never supply a path."""
    return f"s7_synthetic_{token[:16]}.dwg"


def _extract_cad_plan(plan: ExecutionPlan) -> CadOperationPlan:
    candidate = getattr(plan, "cad_plan", None)
    if isinstance(candidate, CadOperationPlan):
        return candidate
    raise PluginBackendError(
        UNSUPPORTED_OPERATION_ERROR,
        "execute_batch requires an S6 CadOperationPlan attached to the execution plan")


def _map_batch_results(batch: Mapping[str, Any]) -> list[CadOperationResult]:
    """Map plugin operation results onto S6 results.

    Critically, a rolled-back operation is NEVER mapped to an S6 success: the plugin
    reports ``success=false`` with ``entity_status=ROLLED_BACK`` and this mapping keeps it
    a failure, so an upper layer cannot mistake a discarded effect for a committed one.
    """
    mapped: list[CadOperationResult] = []
    for item in batch.get("operation_results") or []:
        operation_id = str(item.get("operation_id", ""))
        entity_status = str(item.get("entity_status", ""))
        if item.get("success"):
            status = "CREATED" if entity_status == "CREATED" else "APPLIED"
            entities = tuple(
                _to_snapshot(entity, operation_id) for entity in item.get("entities") or ())
            mapped.append(CadOperationResult(operation_id, status, entities))
        elif entity_status == "ROLLED_BACK":
            mapped.append(CadOperationResult(
                operation_id, "FAILED", (), error_code="BATCH_ROLLED_BACK",
                warning="operation executed but was rolled back with the transaction"))
        else:
            mapped.append(CadOperationResult(
                operation_id, "FAILED", (),
                error_code=str(item.get("error_code") or "ENTITY_CREATE_FAILED"),
                warning=str(item.get("sanitized_message") or "")))
    return mapped


def _to_snapshot(entity: Mapping[str, Any], operation_id: str) -> EntitySnapshot:
    return EntitySnapshot(
        handle=str(entity.get("handle", "")),
        entity_type=str(entity.get("entity_type", "")),
        layer=str(entity.get("layer", "")),
        geometry=dict(entity.get("geometry") or {}),
        operation_id=operation_id,
    )
