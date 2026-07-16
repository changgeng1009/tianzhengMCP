from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from adapters.registry import BackendSelectionResult, ProductAdapterSelection

from .contracts import (
    RoutingTraceEntry,
    RuntimeSelectionResult,
    WorkflowDefinition,
    WorkflowSelectionResult,
)
from .errors import WorkflowNotAvailable


_LEVELS = {
    "L0_READ_ONLY": 0,
    "L1_DRY_RUN": 1,
    "L2_SANDBOX_PREP": 2,
    "L3_SANDBOX_WRITE": 3,
    "L4_CONTROLLED_PRODUCTION": 4,
}

# S2 的 OfflineAnalysisAdapter 曾用 ``unknown`` 表示“并未选择 CAD
# 产品”。S3 将其提升为明确的产品配置档案 ``offline_analysis``；保留这个
# 规范化边界，避免旧 Manifest/Adapter 选择结果在升级后静默失效。
_PRODUCT_ALIASES = {
    "unknown": "offline_analysis",
    "offline": "offline_analysis",
    "offline_analysis": "offline_analysis",
}


def canonical_product_id(value: object) -> str:
    """将旧 S2 离线产品别名映射到 S3 ProductProfile 标识。"""

    text = str(value)
    return _PRODUCT_ALIASES.get(text, text)


class WorkflowRegistry:
    """机器可读 Workflow 注册表；只读取 Skill 内 JSON 合同。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[1] / "config" / "workflows"
        self._definitions = self._load()

    def _load(self) -> dict[str, WorkflowDefinition]:
        definitions: dict[str, WorkflowDefinition] = {}
        for path in sorted(self.root.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            definition = WorkflowDefinition(
                workflow_id=str(raw["workflow_id"]),
                workflow_type=str(raw["workflow_type"]),
                status=str(raw["status"]),
                supported_runtime_modes=tuple(raw["supported_runtime_modes"]),
                supported_products=tuple(raw["supported_products"]),
                required_capabilities=tuple(raw.get("required_capabilities", ())),
                required_backend_types=tuple(raw["required_backend_types"]),
                minimum_approval_level=str(raw["minimum_approval_level"]),
                real_execution_required=bool(raw["real_execution_required"]),
                stages=tuple(raw["stages"]),
                verification_requirements=tuple(raw.get("verification_requirements", ())),
                recovery_requirements=tuple(raw.get("recovery_requirements", ())),
                expected_artifacts=tuple(raw.get("expected_artifacts", ())),
                unavailable_reason=raw.get("unavailable_reason"),
            )
            if definition.workflow_id in definitions:
                raise ValueError(f"重复 workflow_id: {definition.workflow_id}")
            definitions[definition.workflow_id] = definition
        return definitions

    def list(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def get(self, workflow_id: str) -> WorkflowDefinition:
        try:
            return self._definitions[str(workflow_id)]
        except KeyError as exc:
            raise WorkflowNotAvailable(
                f"未注册 workflow: {workflow_id}",
                field="workflow.workflow_id",
                details={"available_workflows": sorted(self._definitions)},
            ) from exc

    def select(
        self,
        manifest: Mapping[str, Any],
        *,
        runtime: RuntimeSelectionResult,
        product: ProductAdapterSelection,
        backend: BackendSelectionResult,
    ) -> WorkflowSelectionResult:
        raw = manifest.get("workflow") or {}
        workflow_id = str(
            raw.get("workflow_id") if isinstance(raw, Mapping) else raw
        )
        definition = self.get(workflow_id)
        if runtime.mode.value not in definition.supported_runtime_modes:
            raise WorkflowNotAvailable(
                "workflow 不支持所选 runtime mode",
                field="workflow.workflow_id",
                details={"workflow_id": workflow_id, "runtime_mode": runtime.mode.value},
            )
        selected_product = canonical_product_id(product.product)
        workflow_products = tuple(
            canonical_product_id(item) for item in definition.supported_products
        )
        if selected_product not in workflow_products:
            raise WorkflowNotAvailable(
                "workflow 不支持所选产品",
                field="workflow.workflow_id",
                details={
                    "workflow_id": workflow_id,
                    "product": selected_product,
                    "supported_products": list(workflow_products),
                },
            )
        missing = sorted(
            set(definition.required_capabilities) - set(product.supported_capabilities)
        )
        if missing:
            raise WorkflowNotAvailable(
                "Product Adapter 缺少 workflow 必需能力",
                field="workflow.workflow_id",
                details={"workflow_id": workflow_id, "missing_capabilities": missing},
            )
        if backend.backend not in definition.required_backend_types:
            raise WorkflowNotAvailable(
                "workflow 与显式 backend 冲突；不自动替代",
                field="workflow.workflow_id",
                details={
                    "workflow_id": workflow_id,
                    "backend": backend.backend,
                    "required_backend_types": list(definition.required_backend_types),
                },
            )

        requested_level = str((manifest.get("safety") or {}).get("requested_level", "L0_READ_ONLY"))
        blocked: list[str] = []
        if definition.status == "NOT_EXECUTABLE_CURRENTLY":
            blocked.append("WORKFLOW_NOT_EXECUTABLE_CURRENTLY")
        if definition.real_execution_required:
            blocked.append("REAL_EXECUTION_NOT_AVAILABLE")
        if _LEVELS.get(definition.minimum_approval_level, 99) >= _LEVELS["L3_SANDBOX_WRITE"]:
            blocked.append("APPROVAL_REQUIRED")
        if _LEVELS.get(requested_level, 99) >= _LEVELS["L3_SANDBOX_WRITE"]:
            blocked.append("APPROVAL_REQUIRED")

        trace = (
            RoutingTraceEntry(
                "runtime_router",
                "runtime.runtime_mode",
                runtime.mode.value,
                "runtime 证据独立于 ProductProfile 选择",
            ),
            RoutingTraceEntry(
                "product_adapter_registry",
                "product.requested_product",
                selected_product,
                "产品证据已规范化；不从 backend 或 workflow 反推产品",
            ),
            RoutingTraceEntry(
                "project_manifest",
                "workflow.workflow_id",
                workflow_id,
                "显式 workflow，不进行静默替代",
            ),
            RoutingTraceEntry(
                "backend_registry",
                "backend.preferred_backend",
                backend.backend,
                "backend 证据独立于 runtime/product 选择",
            ),
        )
        return WorkflowSelectionResult(
            definition,
            selected=True,
            executable_currently=not blocked,
            blocked_reasons=tuple(sorted(set(blocked))),
            trace=trace,
        )


def select_workflow(
    manifest: Mapping[str, Any],
    *,
    runtime: RuntimeSelectionResult,
    product: ProductAdapterSelection,
    backend: BackendSelectionResult,
    registry: WorkflowRegistry | None = None,
) -> WorkflowSelectionResult:
    return (registry or WorkflowRegistry()).select(
        manifest, runtime=runtime, product=product, backend=backend
    )
