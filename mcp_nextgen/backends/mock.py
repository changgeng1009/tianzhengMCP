"""确定性、纯内存、永不访问 CAD/DWG 的 Mock backend。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable

from mcp_nextgen.protocol.enums import BackendKind, DocumentRole
from mcp_nextgen.protocol.models import DocumentIdentity, ExecutionPlan, ExecutionResult

from .base import BackendError, BoundaryCheck, ICadBackend, ProgressCallback
from .models import (
    BackendCapability,
    BackendExecutionContext,
    BackendSession,
    FailureInjection,
    MockEntity,
    ProtectedRegion,
    mock_document_identity,
)


DEFAULT_MOCK_CREATED_AT = "2000-01-01T00:00:00+00:00"


@dataclass
class _MockDocument:
    document_id: str
    path: str
    read_only: bool
    created_at: str
    entities: dict[str, MockEntity] = field(default_factory=dict)
    protected_regions: list[ProtectedRegion] = field(default_factory=list)
    saved_entities: dict[str, MockEntity] = field(default_factory=dict)
    version: int = 0
    saved_version: int = 0

    def state_hash(self, *, saved: bool = False) -> str:
        entities = self.saved_entities if saved else self.entities
        payload = {
            "document_id": self.document_id,
            "path": self.path,
            "read_only": self.read_only,
            "entities": [entities[key].to_dict() for key in sorted(entities)],
            "protected_regions": [
                {"region_id": item.region_id, "bbox": list(item.bbox)}
                for item in sorted(self.protected_regions, key=lambda item: item.region_id)
            ],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def identity(self, *, saved: bool = False) -> DocumentIdentity:
        return mock_document_identity(
            document_id=self.document_id,
            document_full_path=self.path,
            document_sha256=self.state_hash(saved=saved),
            read_only=self.read_only,
            created_at=self.created_at,
        )

    def save(self) -> None:
        self.saved_entities = deepcopy(self.entities)
        self.saved_version = self.version

    def discard_unsaved(self) -> None:
        self.entities = deepcopy(self.saved_entities)
        self.version = self.saved_version


class MockCadBackend(ICadBackend):
    """确定性 Mock：ID 单调递增，故障按明确调用序号触发。"""

    backend_kind = BackendKind.MOCK
    production_allowed = False
    real_cad_execution = False
    real_dwg_modified = False

    def __init__(
        self,
        *,
        failure_injections: Sequence[FailureInjection] = (),
        create_default_document: bool = True,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._documents: dict[str, _MockDocument] = {}
        self._sessions: dict[str, BackendSession] = {}
        self._entity_counter = 0
        self._document_counter = 0
        self._session_counter = 0
        self._operation_counts: dict[str, int] = {}
        self._failure_injections = list(failure_injections)
        self._consumed_failures: set[int] = set()
        self._clock = clock or (lambda: DEFAULT_MOCK_CREATED_AT)
        if create_default_document:
            self.create_document(
                document_id="mock-document-0001",
                document_full_path="mock://document/0001",
            )

    def get_capabilities(self) -> list[BackendCapability]:
        operations = (
            "document.open", "document.close", "document.inspect", "entity.create",
            "entity.copy", "entity.transform", "batch.execute", "document.save",
            "document.reopen", "failure.inject", "progress.publish",
        )
        return [
            BackendCapability(
                capability_id=f"mock.{operation}",
                operation=operation,
                backend_kind=BackendKind.MOCK,
                available=True,
                production_allowed=False,
                dry_run=True,
                details={"implementation_kind": "MOCK", "file_access_performed": False},
            )
            for operation in operations
        ]

    def create_document(
        self,
        *,
        document_id: str | None = None,
        document_full_path: str | None = None,
        read_only: bool = False,
        entities: Sequence[MockEntity | Mapping[str, Any]] = (),
        protected_regions: Sequence[ProtectedRegion] = (),
    ) -> DocumentIdentity:
        self._document_counter += 1
        doc_id = document_id or f"mock-document-{self._document_counter:04d}"
        if doc_id in self._documents:
            raise BackendError("DOCUMENT_ALREADY_EXISTS", f"Mock 文档已存在: {doc_id}")
        path = document_full_path or f"mock://document/{self._document_counter:04d}"
        created_at = str(self._clock())
        if not created_at:
            raise ValueError("Mock clock 必须返回非空 ISO-8601 字符串")
        doc = _MockDocument(
            doc_id,
            path,
            bool(read_only),
            created_at,
            protected_regions=list(protected_regions),
        )
        for raw in entities:
            entity = deepcopy(raw) if isinstance(raw, MockEntity) else self._entity_from_mapping(raw)
            if entity.entity_id in doc.entities:
                raise BackendError("DUPLICATE_ENTITY_ID", entity.entity_id)
            doc.entities[entity.entity_id] = entity
        doc.save()
        self._documents[doc_id] = doc
        return doc.identity()

    def list_documents(self) -> list[DocumentIdentity]:
        return [self._documents[key].identity() for key in sorted(self._documents)]

    def open_document(self, expected_identity: DocumentIdentity) -> BackendSession:
        self._require_mock_identity(expected_identity)
        doc = self._documents.get(expected_identity.document_id)
        self._maybe_fail("open", document_id=expected_identity.document_id)
        if doc is None:
            raise BackendError("DOCUMENT_NOT_FOUND", expected_identity.document_id)
        self._assert_identity(expected_identity, doc.identity())
        self._session_counter += 1
        session = BackendSession(
            session_id=f"mock-session-{self._session_counter:04d}",
            backend_kind=BackendKind.MOCK,
            document_id=doc.document_id,
            opened_identity=expected_identity,
        )
        self._sessions[session.session_id] = session
        return session

    def inspect_document(self, session_id: str) -> DocumentIdentity:
        return self._document_for_session(session_id).identity()

    def close_document(self, session_id: str, *, save: bool = False) -> ExecutionResult:
        session = self._session(session_id)
        if save:
            raise BackendError("IMPLICIT_SAVE_FORBIDDEN", "close 不得隐式保存")
        if session.manual_save_required:
            raise BackendError("MANUAL_SAVE_REQUIRED", "保存失败后必须保持 Mock 文档上下文打开")
        doc = self._document_for_session(session_id)
        self._maybe_fail("close", document_id=doc.document_id)
        doc.discard_unsaved()
        session.document_open = False
        session.connected = False
        return self._result("CLOSED", data={"closed": True, "saved": False})

    def reopen_document(self, expected_identity: DocumentIdentity) -> BackendSession:
        self._maybe_fail("reopen", document_id=expected_identity.document_id)
        return self.open_document(expected_identity)

    def list_entities(self, session_id: str) -> list[dict[str, Any]]:
        doc = self._document_for_session(session_id)
        return [deepcopy(doc.entities[key].to_dict()) for key in sorted(doc.entities)]

    def create_entity(
        self,
        session_id: str,
        *,
        entity_type: str,
        geometry: Mapping[str, Any],
        properties: Mapping[str, Any] | None = None,
        automatic_dependency: bool = False,
        task_id: str | None = None,
    ) -> MockEntity:
        doc = self._writable_document(session_id)
        self._maybe_fail("create", document_id=doc.document_id, task_id=task_id)
        self._entity_counter += 1
        entity = MockEntity(
            entity_id=f"mock-entity-{self._entity_counter:08d}",
            entity_type=str(entity_type),
            geometry=deepcopy(dict(geometry)),
            properties=deepcopy(dict(properties or {})),
            automatic_dependency=bool(automatic_dependency),
        )
        self._assert_not_protected(doc, entity)
        doc.entities[entity.entity_id] = entity
        doc.version += 1
        return deepcopy(entity)

    def copy_entity(
        self,
        session_id: str,
        source_entity_id: str,
        *,
        target_session_id: str | None = None,
        transform: Mapping[str, Any] | None = None,
        task_id: str | None = None,
    ) -> MockEntity:
        source_doc = self._document_for_session(session_id)
        target_doc = self._writable_document(target_session_id or session_id)
        self._maybe_fail("copy", document_id=target_doc.document_id, task_id=task_id)
        source = source_doc.entities.get(source_entity_id)
        if source is None:
            raise BackendError("ENTITY_NOT_FOUND", source_entity_id)
        if self._entity_is_protected(source_doc, source):
            raise BackendError("PROTECTED_REGION_VIOLATION", source_entity_id)
        self._entity_counter += 1
        entity = source.clone(f"mock-entity-{self._entity_counter:08d}")
        if transform:
            entity.geometry = self._translated_geometry(entity.geometry, transform)
        self._assert_not_protected(target_doc, entity)
        target_doc.entities[entity.entity_id] = entity
        target_doc.version += 1
        return deepcopy(entity)

    def transform_entity(
        self,
        session_id: str,
        entity_id: str,
        transform: Mapping[str, Any],
        *,
        task_id: str | None = None,
    ) -> MockEntity:
        doc = self._writable_document(session_id)
        self._maybe_fail("transform", document_id=doc.document_id, task_id=task_id)
        entity = doc.entities.get(entity_id)
        if entity is None:
            raise BackendError("ENTITY_NOT_FOUND", entity_id)
        if self._entity_is_protected(doc, entity):
            raise BackendError("PROTECTED_REGION_VIOLATION", entity_id)
        updated = deepcopy(entity)
        updated.geometry = self._translated_geometry(updated.geometry, transform)
        updated.revision += 1
        self._assert_not_protected(doc, updated)
        doc.entities[entity_id] = updated
        doc.version += 1
        return deepcopy(updated)

    def execute_batch(
        self,
        session_id: str,
        plan: ExecutionPlan,
        batch_id: str,
        *,
        progress_callback: ProgressCallback | None = None,
        boundary_check: BoundaryCheck | None = None,
    ) -> ExecutionResult:
        doc = self._writable_document(session_id)
        self._assert_identity(plan.document, self._session(session_id).opened_identity)
        if plan.production_allowed:
            raise BackendError("PRODUCTION_FORBIDDEN", "Mock backend 禁止生产执行")
        tasks = [task for task in plan.tasks if task.batch_id == batch_id]
        if not tasks:
            raise BackendError("BATCH_NOT_FOUND", batch_id)
        self._maybe_fail("batch", document_id=doc.document_id, batch_id=batch_id)
        completed: list[str] = []
        failed: list[dict[str, str]] = []
        records: list[dict[str, Any]] = []
        for task in tasks:
            if boundary_check:
                boundary_check()
            try:
                record = self._execute_task(session_id, task)
                completed.append(task.task_id)
                records.append(record)
                status = "COMPLETED"
            except BackendError as exc:
                failed.append({"task_id": task.task_id, "error_code": exc.error_code, "message": str(exc)})
                status = "FAILED"
            if progress_callback:
                progress_callback(task.task_id, status, len(completed), len(tasks))
        status = "COMPLETED" if not failed else ("PARTIAL_FAILED" if completed else "FAILED")
        return ExecutionResult(
            request_id=plan.request_id,
            job_id=plan.job_id,
            idempotency_key=plan.idempotency_key,
            batch_id=batch_id,
            status=status,
            production_allowed=False,
            dry_run=plan.dry_run,
            error_code=None if not failed else "MOCK_BATCH_PARTIAL_FAILURE",
            data={
                "backend_kind": BackendKind.MOCK.value,
                "real_cad_execution": False,
                "real_dwg_modified": False,
                "completed_task_ids": completed,
                "failed_tasks": failed,
                "records": records,
            },
        )

    def save_document(self, session_id: str) -> ExecutionResult:
        session = self._session(session_id)
        doc = self._writable_document(session_id)
        try:
            self._maybe_fail("save", document_id=doc.document_id)
        except BackendError as exc:
            session.manual_save_required = True
            return self._result(
                "MANUAL_SAVE_REQUIRED",
                error_code=exc.error_code,
                data={"simulated_save": False, "document_must_remain_open": True},
            )
        doc.save()
        session.manual_save_required = False
        return self._result(
            "SAVED",
            data={
                "simulated_save": True,
                "file_access_performed": False,
                "document": doc.identity(saved=True).to_dict(),
            },
        )

    def replace_failure_injections(self, values: Sequence[FailureInjection]) -> None:
        self._failure_injections = list(values)
        self._consumed_failures.clear()
        self._operation_counts.clear()

    def _execute_task(self, session_id: str, task: Any) -> dict[str, Any]:
        payload = dict(task.payload)
        operation = task.operation.lower()
        if operation in {"create", "entity.create", "cad.entity.create"}:
            entity = self.create_entity(
                session_id,
                entity_type=str(payload.get("entity_type") or payload.get("object_type") or "MockEntity"),
                geometry=payload.get("geometry") or {},
                properties=payload.get("properties") or {},
                automatic_dependency=task.automatic_dependency,
                task_id=task.task_id,
            )
        elif operation in {"copy", "clone", "entity.copy", "cad.batch.clone"}:
            entity = self.copy_entity(
                session_id,
                str(payload["source_entity_id"]),
                transform=payload.get("transform"),
                task_id=task.task_id,
            )
        elif operation in {"transform", "entity.transform", "cad.batch.transform"}:
            entity = self.transform_entity(
                session_id,
                str(payload["entity_id"]),
                payload.get("transform") or payload,
                task_id=task.task_id,
            )
        else:
            raise BackendError("UNKNOWN_OPERATION", task.operation)
        return {
            "task_id": task.task_id,
            "entity": entity.to_dict(),
            "automatic_dependency": task.automatic_dependency,
        }

    def _entity_from_mapping(self, value: Mapping[str, Any]) -> MockEntity:
        entity_id = str(value.get("entity_id") or "")
        if not entity_id:
            self._entity_counter += 1
            entity_id = f"mock-entity-{self._entity_counter:08d}"
        return MockEntity(
            entity_id=entity_id,
            entity_type=str(value.get("entity_type") or value.get("object_type") or "MockEntity"),
            geometry=deepcopy(dict(value.get("geometry") or {})),
            properties=deepcopy(dict(value.get("properties") or {})),
            protected_region_ids=[str(item) for item in value.get("protected_region_ids", [])],
            automatic_dependency=bool(value.get("automatic_dependency", False)),
            revision=int(value.get("revision", 0)),
        )

    def _session(self, session_id: str) -> BackendSession:
        session = self._sessions.get(session_id)
        if session is None or not session.connected or not session.document_open:
            raise BackendError("SESSION_NOT_OPEN", session_id)
        return session

    def _document_for_session(self, session_id: str) -> _MockDocument:
        return self._documents[self._session(session_id).document_id]

    def _writable_document(self, session_id: str) -> _MockDocument:
        doc = self._document_for_session(session_id)
        if doc.read_only:
            raise BackendError("DOCUMENT_READ_ONLY", doc.document_id)
        return doc

    @staticmethod
    def _require_mock_identity(identity: DocumentIdentity) -> None:
        if identity.backend_kind is not BackendKind.MOCK or identity.document_role is not DocumentRole.MOCK_DOCUMENT:
            raise BackendError("MOCK_REAL_IDENTITY_CONFLICT", "Mock backend 只接受 MOCK_DOCUMENT")

    @staticmethod
    def _assert_identity(expected: DocumentIdentity, actual: DocumentIdentity) -> None:
        fields = ("document_id", "document_full_path", "document_sha256", "document_role", "backend_kind")
        mismatches = [name for name in fields if getattr(expected, name) != getattr(actual, name)]
        if mismatches:
            raise BackendError("DOCUMENT_IDENTITY_CONFLICT", f"文档身份不匹配: {mismatches}")

    def _maybe_fail(self, operation: str, **context: Any) -> None:
        count = self._operation_counts.get(operation, 0) + 1
        self._operation_counts[operation] = count
        for index, item in enumerate(self._failure_injections):
            if index in self._consumed_failures or item.operation != operation or item.occurrence != count:
                continue
            if any(
                expected is not None and expected != context.get(name)
                for name, expected in (
                    ("document_id", item.document_id), ("batch_id", item.batch_id), ("task_id", item.task_id)
                )
            ):
                continue
            self._consumed_failures.add(index)
            raise BackendError(item.error_code, item.message, recoverable=True, details=context)

    def _assert_not_protected(self, doc: _MockDocument, entity: MockEntity) -> None:
        hits = [region.region_id for region in doc.protected_regions if _bbox_intersects(_entity_bbox(entity), region.bbox)]
        if entity.protected_region_ids or hits:
            raise BackendError(
                "PROTECTED_REGION_VIOLATION",
                entity.entity_id,
                details={"protected_region_ids": sorted(set(entity.protected_region_ids + hits))},
            )

    def _entity_is_protected(self, doc: _MockDocument, entity: MockEntity) -> bool:
        return bool(entity.protected_region_ids) or any(
            _bbox_intersects(_entity_bbox(entity), region.bbox) for region in doc.protected_regions
        )

    @staticmethod
    def _translated_geometry(geometry: Mapping[str, Any], transform: Mapping[str, Any]) -> dict[str, Any]:
        kind = str(transform.get("type") or transform.get("transform_type") or "translate").lower()
        if kind not in {"translate", "translation", "move"}:
            raise BackendError("UNSUPPORTED_TRANSFORM", kind)
        dx = float(transform.get("dx", transform.get("translation_x", 0.0)))
        dy = float(transform.get("dy", transform.get("translation_y", 0.0)))
        dz = float(transform.get("dz", transform.get("translation_z", 0.0)))
        result = deepcopy(dict(geometry))
        for name in ("start_point", "end_point", "insert_point", "position", "center"):
            if name in result:
                result[name] = _translate_point(result[name], dx, dy, dz)
        for name in ("vertices", "points"):
            if name in result:
                result[name] = [_translate_point(point, dx, dy, dz) for point in result[name]]
        if "bbox" in result:
            bbox = result["bbox"]
            if len(bbox) == 4:
                result["bbox"] = [bbox[0] + dx, bbox[1] + dy, bbox[2] + dx, bbox[3] + dy]
        return result

    @staticmethod
    def _result(status: str, *, error_code: str | None = None, data: dict[str, Any] | None = None) -> ExecutionResult:
        return ExecutionResult(
            request_id="mock-backend-request",
            job_id="mock-backend-job",
            idempotency_key="mock-backend-idempotency",
            status=status,
            production_allowed=False,
            dry_run=True,
            error_code=error_code,
            data={
                "backend_kind": BackendKind.MOCK.value,
                "real_cad_execution": False,
                "real_dwg_modified": False,
                **(data or {}),
            },
        )


def _translate_point(value: Sequence[Any], dx: float, dy: float, dz: float) -> list[float]:
    coords = [float(item) for item in value]
    if len(coords) < 2:
        raise BackendError("INVALID_GEOMETRY", "点坐标至少包含 x/y")
    result = [coords[0] + dx, coords[1] + dy]
    if len(coords) >= 3:
        result.append(coords[2] + dz)
    return result


def _entity_bbox(entity: MockEntity) -> tuple[float, float, float, float]:
    geometry = entity.geometry
    if "bbox" in geometry and len(geometry["bbox"]) == 4:
        return tuple(float(value) for value in geometry["bbox"])  # type: ignore[return-value]
    points: list[Sequence[Any]] = []
    for name in ("start_point", "end_point", "insert_point", "position", "center"):
        if name in geometry:
            points.append(geometry[name])
    for name in ("vertices", "points"):
        points.extend(geometry.get(name, []))
    if not points:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_intersects(left: Sequence[float], right: Sequence[float]) -> bool:
    return not (left[2] < right[0] or left[0] > right[2] or left[3] < right[1] or left[1] > right[3])
