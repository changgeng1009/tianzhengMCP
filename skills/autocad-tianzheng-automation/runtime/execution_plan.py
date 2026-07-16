from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from adapters.registry import (
    BackendSelectionResult,
    ProductAdapterSelection,
    ProductCapabilityResolver,
)
from config.canonical import canonical_hash, canonicalize

from .backend_registry import select_backend
from .contracts import RuntimeSelectionResult, WorkflowSelectionResult
from .errors import PlanHashMismatch
from .routing import RuntimeRouter, select_product
from .workflow_registry import WorkflowRegistry, select_workflow


PLAN_SCHEMA_VERSION = "1.0.0"
_NON_SEMANTIC_KEYS = {
    "created_at",
    "generated_at",
    "temporary_run_directory",
    "notes",
    "random_uuid",
    "run_id",
}
_LEVELS = {
    "L0_READ_ONLY": 0,
    "L1_DRY_RUN": 1,
    "L2_SANDBOX_PREP": 2,
    "L3_SANDBOX_WRITE": 3,
    "L4_CONTROLLED_PRODUCTION": 4,
}


def _approval_requirement(
    approval: Mapping[str, Any],
    *,
    requested_level: str,
    minimum_level: str,
) -> dict[str, Any]:
    """生成仅声明性的审批追踪合同。

    Execution Plan 是离线、确定性的计划，不是审批 authority。除非未来由
    独立 authority 在执行时验证，本函数绝不把引用、过期、消费或 scope
    绑定推断为已验证。
    """

    approval_required = bool(approval.get("approval_required", False)) or (
        _LEVELS.get(requested_level, 99) >= _LEVELS["L3_SANDBOX_WRITE"]
    )
    reference_present = bool(approval.get("approval_reference"))
    return {
        "required_level": approval.get("required_level", minimum_level),
        "approval_required": approval_required,
        "approval_declared": approval_required or reference_present,
        "approval_reference_present": reference_present,
        "approval_verified": False,
        "approval_consumed": "UNVERIFIED",
        "approval_expired": "UNVERIFIED",
        "approval_scope_match": "UNVERIFIED",
        "single_use": True,
    }


def _semantic_projection(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _semantic_projection(item)
            for key, item in value.items()
            if str(key) not in _NON_SEMANTIC_KEYS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_semantic_projection(item) for item in value]
    return value


def canonical_manifest_hash(manifest: Mapping[str, Any]) -> str:
    return canonical_hash(canonicalize(_semantic_projection(manifest)))


def _plan_hash_input(plan: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(plan))
    value.pop("plan_id", None)
    value.pop("plan_hash", None)
    return _semantic_projection(value)


def execution_plan_hash(plan: Mapping[str, Any]) -> str:
    return canonical_hash(canonicalize(_plan_hash_input(plan)))


def verify_execution_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    expected = execution_plan_hash(plan)
    actual = str(plan.get("plan_hash") or "")
    expected_id = f"plan-{expected[:16]}"
    if actual != expected or plan.get("plan_id") != expected_id:
        raise PlanHashMismatch(
            "Execution Plan hash 或 plan_id 不匹配",
            field="plan_hash",
            details={
                "expected_plan_hash": expected,
                "actual_plan_hash": actual,
                "expected_plan_id": expected_id,
                "actual_plan_id": plan.get("plan_id"),
            },
        )
    return {"ok": True, "plan_hash": expected, "plan_id": expected_id}


class ExecutionPlanBuilder:
    """构建纯离线、可重复、无随机值的 Execution Plan。"""

    def __init__(
        self,
        *,
        runtime_router: RuntimeRouter | None = None,
        product_resolver: ProductCapabilityResolver | None = None,
        workflow_registry: WorkflowRegistry | None = None,
    ) -> None:
        self.runtime_router = runtime_router or RuntimeRouter()
        self.product_resolver = product_resolver or ProductCapabilityResolver()
        self.workflow_registry = workflow_registry or WorkflowRegistry()

    def build(
        self,
        manifest: Mapping[str, Any],
        *,
        runtime: RuntimeSelectionResult | None = None,
        product: ProductAdapterSelection | None = None,
        backend: BackendSelectionResult | None = None,
        workflow: WorkflowSelectionResult | None = None,
    ) -> dict[str, Any]:
        runtime = runtime or self.runtime_router.select(manifest)
        product = product or select_product(
            manifest, runtime, resolver=self.product_resolver
        )
        backend = backend or select_backend(manifest)
        workflow = workflow or select_workflow(
            manifest,
            runtime=runtime,
            product=product,
            backend=backend,
            registry=self.workflow_registry,
        )

        safety = dict(manifest.get("safety") or {})
        approval = dict(manifest.get("approval") or {})
        requested_level = str(safety.get("requested_level") or "L0_READ_ONLY")
        approval_requirement = _approval_requirement(
            approval,
            requested_level=requested_level,
            minimum_level=workflow.definition.minimum_approval_level,
        )
        blocked = list(workflow.blocked_reasons)
        if _LEVELS.get(requested_level, 99) >= _LEVELS["L3_SANDBOX_WRITE"]:
            blocked.extend(
                (
                    "APPROVAL_REQUIRED",
                    "REAL_EXECUTION_NOT_AVAILABLE",
                    "REAL_BACKEND_NOT_AVAILABLE",
                )
            )
        if approval_requirement["approval_required"]:
            blocked.append("APPROVAL_REQUIRED")
        if bool((manifest.get("backend") or {}).get("require_real_execution")):
            blocked.extend(("REAL_EXECUTION_NOT_AVAILABLE", "REAL_BACKEND_NOT_AVAILABLE"))
        if bool(safety.get("production_allowed")) or bool(safety.get("production_d1_allowed")):
            blocked.append("CONFIG_SECURITY_DOWNGRADE_BLOCKED")
        if bool(safety.get("real_cad_access_allowed")):
            blocked.append("REAL_CAD_ACCESS_FORBIDDEN")
        blocked = sorted(set(blocked))

        document_requirements: list[dict[str, Any]] = []
        documents = manifest.get("documents") or {}
        for category in ("reference_documents", "target_documents", "auxiliary_documents"):
            for item in documents.get(category, ()):
                record = deepcopy(dict(item))
                record["category"] = category
                record["identity_verified"] = False
                document_requirements.append(record)
        document_requirements.sort(key=lambda item: (str(item.get("category")), str(item.get("document_id"))))

        stages = [
            {
                "index": index,
                "stage_id": stage,
                "status": "PLANNED",
                "execution_mode": "MOCK" if backend.backend == "nextgen_mock" else "OFFLINE",
            }
            for index, stage in enumerate(workflow.definition.stages, start=1)
        ]
        task = dict(manifest.get("task") or {})
        verification = deepcopy(dict(manifest.get("verification") or {}))
        recovery = deepcopy(dict(manifest.get("recovery") or {}))
        limitations = sorted(
            set(product.limitations)
            | set(backend.limitations)
            | ({workflow.definition.unavailable_reason} if workflow.definition.unavailable_reason else set())
        )
        expected_artifacts = sorted(
            set(task.get("expected_outputs") or ()) | set(workflow.definition.expected_artifacts)
        )
        plan: dict[str, Any] = {
            "plan_schema_version": PLAN_SCHEMA_VERSION,
            "plan_id": "",
            "project_id": str((manifest.get("project") or {}).get("project_id") or "unknown-project"),
            "task_id": str(task.get("task_id") or "unknown-task"),
            "runtime_mode": runtime.mode.value,
            "product_mode": product.product,
            "backend": backend.backend,
            "workflow_id": workflow.definition.workflow_id,
            "approval_requirement": approval_requirement,
            "document_requirements": document_requirements,
            "protected_regions": deepcopy(safety.get("protected_regions") or []),
            "operation_allowlist": sorted(set(safety.get("operation_allowlist") or [])),
            "operation_denylist": sorted(set(safety.get("operation_denylist") or [])),
            "stages": stages,
            "expected_artifacts": expected_artifacts,
            "verification_requirements": verification,
            "recovery_policy": recovery,
            "limitations": limitations,
            "executable": not blocked and workflow.executable_currently,
            "blocked_reasons": blocked,
            "canonical_manifest_hash": canonical_manifest_hash(manifest),
            "plan_hash": "",
        }
        plan["plan_hash"] = execution_plan_hash(plan)
        plan["plan_id"] = f"plan-{plan['plan_hash'][:16]}"
        return canonicalize(plan)


class ExecutionPlanCanonicalizer:
    @staticmethod
    def canonicalize(plan: Mapping[str, Any]) -> dict[str, Any]:
        return canonicalize(_semantic_projection(plan))


class ExecutionPlanHasher:
    @staticmethod
    def hash(plan: Mapping[str, Any]) -> str:
        return execution_plan_hash(plan)


class ExecutionPlanValidator:
    @staticmethod
    def verify(plan: Mapping[str, Any]) -> dict[str, Any]:
        return verify_execution_plan(plan)
