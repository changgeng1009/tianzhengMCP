"""S6 的受限 RealAutoCadComBackend 计划执行适配。

本模块不导入 pywin32，也不激活 AutoCAD；调用方必须已经通过 S5 COM_ACTIVATION、
job-owned PID、DocumentOwnershipRegistry 与 L3 approval 创建并验证 synthetic document。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from mcp_nextgen.backends.real_autocad_com import L3SyntheticSandboxApproval, RealAutoCadComBackend, SyntheticAutoCadDocumentIdentity

from .contracts import CadOperation, CadOperationPlan, CadOperationResult, EntitySelector, EntitySnapshot


class S6RealComGateway(Protocol):
    def ensure_s6_resource(self, identity: SyntheticAutoCadDocumentIdentity, operation: str, parameters: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def create_s6_entity(self, identity: SyntheticAutoCadDocumentIdentity, spec: Any, operation_id: str) -> Mapping[str, Any]: ...
    def transform_s6_entity(self, identity: SyntheticAutoCadDocumentIdentity, selector: EntitySelector, operation: str, parameters: Mapping[str, Any], operation_id: str) -> Mapping[str, Any]: ...
    def query_s6_entities(self, identity: SyntheticAutoCadDocumentIdentity, selector: EntitySelector | None = None) -> list[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class S6RealExecutionResult:
    plan_hash: str
    results: tuple[CadOperationResult, ...]
    backend: str = "real_autocad_com"
    execution_mode: str = "com_activation"
    synthetic: bool = True
    limitations: tuple[str, ...] = (
        "仅当前 job 的 synthetic sandbox", "不支持用户 DWG/DXF、天正、L4 或生产写入", "COM 不提供事务性回滚",
        "跨进程 XData/扩展字典幂等尚未验证",
    )


class S6RealComPlanExecutor:
    """在 S5 已验证会话上逐项执行 S6 计划；默认路径完全不会实例化它。"""

    def __init__(self, backend: RealAutoCadComBackend, gateway: S6RealComGateway,
                 *, persisted_results: Mapping[str, CadOperationResult] | None = None) -> None:
        self._backend = backend
        self._gateway = gateway
        # 正常重放由 append-only synthetic job journal 恢复；不以进程内字典
        # 作为 Save/Close/Reopen 之后的唯一幂等依据。
        self._applied: dict[str, CadOperationResult] = dict(persisted_results or {})

    def execute(self, identity: SyntheticAutoCadDocumentIdentity, approval: L3SyntheticSandboxApproval, plan: CadOperationPlan) -> S6RealExecutionResult:
        if plan.job_id != identity.job_id or plan.document_token != identity.ownership_token:
            raise ValueError("S6 plan 未绑定当前 synthetic document")
        if plan.plan_hash != identity.plan_hash:
            raise ValueError("S6 plan_hash 与 document identity 不一致")
        if plan.batch_policy == "all_or_nothing":
            # AutoCAD COM 没有数据库级事务。Mock 完整模拟 all-or-nothing；真实
            # backend 显式拒绝该策略而非虚报 atomic/rollback 成功。
            raise ValueError("S6_REAL_COM_TRUE_ATOMIC_BATCH_NOT_AVAILABLE")
        # 使用 S5 的 registry snapshot 验证，绝不接受 ActiveDocument。
        self._backend._verify(identity)  # noqa: SLF001 - same synthetic trust boundary
        results: list[CadOperationResult] = []
        for operation in plan.operations:
            previous = self._applied.get(operation.operation_id)
            if previous is not None:
                results.append(CadOperationResult(operation.operation_id, "ALREADY_APPLIED", previous.entities)); continue
            result = self._execute_operation(identity, approval, operation)
            self._applied[operation.operation_id] = result
            results.append(result)
        return S6RealExecutionResult(plan.plan_hash, tuple(results))

    def _execute_operation(self, identity: SyntheticAutoCadDocumentIdentity, approval: L3SyntheticSandboxApproval, operation: CadOperation) -> CadOperationResult:
        approval_operation = operation.operation
        self._backend._authorize(identity, approval, approval_operation)  # noqa: SLF001 - preserve L3 binding
        self._backend._verify(identity)  # noqa: SLF001
        if operation.operation in {"ENSURE_LAYER", "ENSURE_TEXT_STYLE", "ENSURE_DIMENSION_STYLE"}:
            raw = self._gateway.ensure_s6_resource(identity, operation.operation, operation.parameters)
            return CadOperationResult(operation.operation_id, str(raw.get("status", "CREATED")), warning=raw.get("font"))
        if operation.operation.startswith("CREATE_") or operation.operation == "INSERT_BLOCK_REFERENCE":
            existing = self._gateway.query_s6_entities(identity, EntitySelector(operation_id=operation.operation_id))
            if existing:
                return CadOperationResult(operation.operation_id, "ALREADY_APPLIED", tuple(_snapshot(item) for item in existing))
            raw = self._gateway.create_s6_entity(identity, operation.entity, operation.operation_id)
            return CadOperationResult(operation.operation_id, "CREATED", (_snapshot(raw),))
        if operation.operation == "QUERY_ENTITIES":
            return CadOperationResult(operation.operation_id, "QUERY_OK", tuple(_snapshot(item) for item in self._gateway.query_s6_entities(identity, operation.selector)))
        if operation.operation in {"MOVE_ENTITY", "COPY_ENTITY", "ROTATE_ENTITY", "SCALE_ENTITY", "DELETE_ENTITY"}:
            raw = self._gateway.transform_s6_entity(identity, operation.selector, operation.operation, operation.parameters, operation.operation_id)
            return CadOperationResult(operation.operation_id, "DELETED" if operation.operation == "DELETE_ENTITY" else ("CREATED" if operation.operation == "COPY_ENTITY" else "UPDATED"), (_snapshot(raw),))
        # Save/close/reopen are deliberately retained in S5 backend facade; a real
        # runner executes them at explicit lifecycle checkpoints, never as implicit plan side effects.
        raise ValueError(f"S6 Real executor 不接受隐式生命周期操作: {operation.operation}")


def _snapshot(raw: Mapping[str, Any]) -> EntitySnapshot:
    return EntitySnapshot(str(raw.get("handle", "")), str(raw.get("entity_type", "")), str(raw.get("layer", "")), dict(raw.get("geometry", {})), str(raw.get("operation_key") or raw.get("operation_id") or "unknown"), bool(raw.get("deleted", False)))
