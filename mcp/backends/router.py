from __future__ import annotations

from typing import Any

from .errors import BackendSafetyError
from .models import BackendSelectionResult, RepairTask
from .registry import BackendRegistry
from .safety import BackendSafetyEnforcer


class BackendRouter:
    def __init__(self, registry: BackendRegistry, safety: BackendSafetyEnforcer | None = None) -> None:
        self.registry = registry
        self.safety = safety or BackendSafetyEnforcer()

    def route(
        self,
        task_value: RepairTask | dict[str, Any],
        *,
        source_path: str | None,
        working_copy: str | None,
        requested_backend: str | None = None,
    ) -> BackendSelectionResult:
        task = task_value if isinstance(task_value, RepairTask) else RepairTask.from_dict(task_value)
        candidate_ids = _candidate_ids(task, requested_backend, self.registry.ids())

        if task.classification == "manual_tianzheng":
            return _manual_result(task, candidate_ids, "task is explicitly classified for manual Tianzheng workflow")

        try:
            self.safety.validate_common(task, source_path=source_path, working_copy=working_copy)
        except BackendSafetyError as exc:
            if task.fallback_policy == "manual_tianzheng" and _is_tianzheng_task(task):
                return _manual_result(task, candidate_ids, exc.message)
            return BackendSelectionResult(
                task_id=task.task_id,
                requested_capabilities=task.required_capabilities,
                candidate_backends=[],
                selected_backend=None,
                selection_status="blocked",
                selection_reason=exc.message,
                fallback_used=False,
            )

        evidence: list[dict[str, Any]] = []
        for backend_id in candidate_ids:
            if backend_id == "manual_tianzheng":
                continue
            try:
                backend = self.registry.get(backend_id)
            except Exception:
                evidence.append({"backend_id": backend_id, "available": False, "reason": "not registered"})
                continue
            capabilities = backend.get_capabilities()
            missing = capabilities.missing(task.required_capabilities)
            sandbox_verified = capabilities.sandbox_verified(task.required_capabilities)
            record = {
                "backend_id": backend_id,
                "available": capabilities.available,
                "missing_capabilities": missing,
                "sandbox_verified": sandbox_verified,
                "capability_evidence": capabilities.capability_evidence,
            }
            evidence.append(record)
            if capabilities.available and not missing and sandbox_verified:
                fallback_used = bool(task.preferred_backend and backend_id != task.preferred_backend)
                if fallback_used and not self.safety.policy.allow_automatic_fallback:
                    continue
                return BackendSelectionResult(
                    task_id=task.task_id,
                    requested_capabilities=task.required_capabilities,
                    candidate_backends=evidence,
                    selected_backend=backend_id,
                    selection_status="selected",
                    selection_reason="backend is available, capability-complete, and sandbox-verified",
                    fallback_used=fallback_used,
                    backend_capability_evidence=record,
                )

        if task.fallback_policy == "manual_tianzheng" and _is_tianzheng_task(task):
            return _manual_result(task, evidence, "no verified backend supports all Tianzheng capabilities")
        return BackendSelectionResult(
            task_id=task.task_id,
            requested_capabilities=task.required_capabilities,
            candidate_backends=evidence,
            selected_backend=None,
            selection_status="blocked",
            selection_reason="no available sandbox-verified backend satisfies all required capabilities",
            fallback_used=False,
        )


def _candidate_ids(task: RepairTask, requested_backend: str | None, registered: list[str]) -> list[str]:
    if requested_backend:
        return [requested_backend]
    if task.allowed_backends:
        return list(dict.fromkeys(task.allowed_backends))
    if task.preferred_backend:
        return [task.preferred_backend]
    return registered


def _manual_result(task: RepairTask, candidates: list[Any], reason: str) -> BackendSelectionResult:
    normalized = [item if isinstance(item, dict) else {"backend_id": item} for item in candidates]
    return BackendSelectionResult(
        task_id=task.task_id,
        requested_capabilities=task.required_capabilities,
        candidate_backends=normalized,
        selected_backend=None,
        selection_status="manual_fallback",
        selection_reason=reason,
        fallback_used=True,
    )


def _is_tianzheng_task(task: RepairTask) -> bool:
    object_type = task.object_type.lower()
    return object_type.startswith("tdb") or any(capability.startswith("create_tdb") or capability.startswith("create_tianzheng") for capability in task.required_capabilities)
