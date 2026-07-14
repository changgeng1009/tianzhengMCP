"""Mock Plugin Runtime：生命周期、DocumentContext、调度、取消和进度模拟。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp_nextgen.backends import BackendError, ICadBackend
from mcp_nextgen.jobs.boundaries import CancellationRequested, DeadlineExceeded, SafeBoundaryController
from mcp_nextgen.protocol.enums import BackendKind
from mcp_nextgen.protocol.models import DocumentIdentity, ExecutionPlan, ExecutionResult, ProgressEvent

from .models import CancellationToken, DocumentContext, RuntimeState
from .scheduler import MockMainThreadScheduler


ProgressSubscriber = Callable[[ProgressEvent], None]


class RuntimeLifecycleError(RuntimeError):
    pass


class MockPluginRuntime:
    backend_kind = BackendKind.MOCK
    production_allowed = False
    real_plugin_available = False

    def __init__(self, backend: ICadBackend) -> None:
        self.backend = backend
        self.state = RuntimeState.CREATED
        self.scheduler: MockMainThreadScheduler | None = None
        self._contexts: dict[str, DocumentContext] = {}
        self._context_counter = 0
        self._progress_sequence: dict[str, int] = {}
        self._completed_task_ids: dict[str, set[str]] = {}
        self._events: list[ProgressEvent] = []
        self._subscribers: list[ProgressSubscriber] = []

    def initialize(self) -> None:
        if self.state is RuntimeState.DISPOSED:
            raise RuntimeLifecycleError("runtime 已释放")
        if self.state in {RuntimeState.INITIALIZED, RuntimeState.RUNNING}:
            return
        self.scheduler = MockMainThreadScheduler()
        self.state = RuntimeState.INITIALIZED

    def start(self) -> None:
        if self.state in {RuntimeState.CREATED, RuntimeState.STOPPED}:
            self.initialize()
        if self.state is RuntimeState.DISPOSED:
            raise RuntimeLifecycleError("runtime 已释放")
        self.state = RuntimeState.RUNNING

    def stop(self) -> None:
        if self.state is RuntimeState.DISPOSED:
            return
        for context in self._contexts.values():
            if context.manual_save_required:
                raise RuntimeLifecycleError("存在 MANUAL_SAVE_REQUIRED 文档，禁止停止 runtime")
        self.state = RuntimeState.STOPPED

    def dispose(self) -> None:
        if any(context.manual_save_required for context in self._contexts.values()):
            raise RuntimeLifecycleError("存在 MANUAL_SAVE_REQUIRED 文档，禁止释放 runtime")
        self._contexts.clear()
        self.state = RuntimeState.DISPOSED

    def subscribe_progress(self, callback: ProgressSubscriber) -> None:
        self._subscribers.append(callback)

    def progress_events(self, job_id: str | None = None) -> list[ProgressEvent]:
        return [event for event in self._events if job_id is None or event.job_id == job_id]

    def open_document(self, identity: DocumentIdentity) -> DocumentContext:
        self._require_running()
        session = self._invoke(self.backend.open_document, identity)
        self._context_counter += 1
        context = DocumentContext(
            context_id=f"mock-context-{self._context_counter:04d}",
            session_id=session.session_id,
            bound_identity=identity,
            current_identity=identity,
        )
        self._contexts[context.context_id] = context
        return context

    def inspect_document(self, context_id: str) -> DocumentIdentity:
        context = self._context(context_id)
        context.current_identity = self._invoke(self.backend.inspect_document, context.session_id)
        return context.current_identity

    def execute_batch(
        self,
        context_id: str,
        plan: ExecutionPlan,
        batch_id: str,
        *,
        timeout_seconds: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> ExecutionResult:
        context = self._context(context_id)
        self._assert_plan_binding(context, plan)
        boundary = SafeBoundaryController.with_timeout(timeout_seconds)
        token = cancellation_token or CancellationToken()

        def check_boundary() -> None:
            if token.cancelled:
                boundary.request_cancellation()
            boundary.check()

        def on_progress(task_id: str, status: str, _completed: int, _total: int) -> None:
            if status == "COMPLETED":
                self._completed_task_ids.setdefault(plan.job_id, set()).add(task_id)
            self._publish_progress(plan, batch_id, task_id, status)

        try:
            check_boundary()
            result = self._invoke(
                self.backend.execute_batch,
                context.session_id,
                plan,
                batch_id,
                progress_callback=on_progress,
                boundary_check=check_boundary,
            )
            context.current_identity = self._invoke(self.backend.inspect_document, context.session_id)
            return result
        except CancellationRequested:
            return self._runtime_result(plan, batch_id, "CANCELLED", "CANCELLATION_REQUESTED")
        except DeadlineExceeded:
            return self._runtime_result(plan, batch_id, "TIMEOUT", "DEADLINE_EXCEEDED")
        except BackendError as exc:
            return self._runtime_result(plan, batch_id, "FAILED", exc.error_code, {"message": str(exc)})

    def save_document(
        self,
        context_id: str,
        *,
        timeout_seconds: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> ExecutionResult:
        context = self._context(context_id)
        boundary = SafeBoundaryController.with_timeout(timeout_seconds)
        if cancellation_token and cancellation_token.cancelled:
            boundary.request_cancellation()
        boundary.check()
        with boundary.persistence_critical_section():
            result = self._invoke(self.backend.save_document, context.session_id)
        context.manual_save_required = result.status == "MANUAL_SAVE_REQUIRED"
        context.current_identity = self._invoke(self.backend.inspect_document, context.session_id)
        return result

    def close_document(self, context_id: str) -> ExecutionResult:
        context = self._context(context_id)
        if context.manual_save_required:
            raise RuntimeLifecycleError("MANUAL_SAVE_REQUIRED 文档不得自动关闭")
        result = self._invoke(self.backend.close_document, context.session_id, save=False)
        context.active = False
        return result

    def request_cancellation(self, token: CancellationToken) -> None:
        token.cancel()

    def _publish_progress(
        self, plan: ExecutionPlan, batch_id: str, task_id: str, status: str
    ) -> None:
        sequence = self._progress_sequence.get(plan.job_id, 0) + 1
        self._progress_sequence[plan.job_id] = sequence
        event = ProgressEvent(
            request_id=plan.request_id,
            job_id=plan.job_id,
            sequence=sequence,
            status=status,
            completed_batch_count=0,
            completed_task_count=len(self._completed_task_ids.get(plan.job_id, set())),
            total_task_count=len(plan.tasks),
            batch_id=batch_id,
            task_id=task_id,
        )
        self._events.append(event)
        for subscriber in tuple(self._subscribers):
            try:
                subscriber(event)
            except Exception:
                continue

    def _invoke(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if self.scheduler is None:
            raise RuntimeLifecycleError("runtime 尚未初始化")
        return self.scheduler.invoke(callback, *args, **kwargs)

    def _context(self, context_id: str) -> DocumentContext:
        self._require_running()
        context = self._contexts.get(context_id)
        if context is None or not context.active:
            raise RuntimeLifecycleError(f"DocumentContext 不可用: {context_id}")
        return context

    def _require_running(self) -> None:
        if self.state is not RuntimeState.RUNNING:
            raise RuntimeLifecycleError(f"runtime 未运行: {self.state.value}")

    @staticmethod
    def _assert_plan_binding(context: DocumentContext, plan: ExecutionPlan) -> None:
        left = context.bound_identity
        right = plan.document
        if (
            left.document_id != right.document_id
            or left.document_full_path != right.document_full_path
            or left.document_sha256 != right.document_sha256
            or right.backend_kind is not BackendKind.MOCK
            or plan.production_allowed
        ):
            raise RuntimeLifecycleError("ExecutionPlan 与 Mock DocumentContext 身份不匹配")

    @staticmethod
    def _runtime_result(
        plan: ExecutionPlan,
        batch_id: str,
        status: str,
        error_code: str,
        data: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            request_id=plan.request_id,
            job_id=plan.job_id,
            idempotency_key=plan.idempotency_key,
            status=status,
            batch_id=batch_id,
            production_allowed=False,
            dry_run=plan.dry_run,
            error_code=error_code,
            data={
                "backend_kind": BackendKind.MOCK.value,
                "real_plugin_available": False,
                "real_cad_execution": False,
                "real_dwg_modified": False,
                **(data or {}),
            },
        )
