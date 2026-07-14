from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from runtime.errors import UnsafeOperation


class SafetyLevel(str, Enum):
    L0_READ_ONLY = "L0_READ_ONLY"
    L1_DRY_RUN = "L1_DRY_RUN"
    L2_SANDBOX_PREP = "L2_SANDBOX_PREP"
    L3_SANDBOX_WRITE = "L3_SANDBOX_WRITE"
    L4_CONTROLLED_PRODUCTION = "L4_CONTROLLED_PRODUCTION"


REQUIRED_APPROVAL_BINDINGS = {
    "job_id", "document_identity", "document_sha256", "plan_hash",
    "allowed_operations", "runtime_mode", "product", "single_use", "expires_at",
}


@dataclass(frozen=True)
class ApprovalContext:
    """当前作业的权威声明；审批票据必须逐项与之相等。"""

    job_id: str
    document_identity: str
    document_sha256: str
    plan_hash: str
    allowed_operations: tuple[str, ...]
    runtime_mode: str
    product: str


def _validate_claim_bindings(approval: Mapping[str, Any], context: ApprovalContext) -> None:
    expected = {
        "job_id": context.job_id,
        "document_identity": context.document_identity,
        "document_sha256": context.document_sha256,
        "plan_hash": context.plan_hash,
        "allowed_operations": list(context.allowed_operations),
        "runtime_mode": context.runtime_mode,
        "product": context.product,
    }
    for claim, expected_value in expected.items():
        observed = approval.get(claim)
        if claim == "allowed_operations":
            observed = list(observed or [])
        if observed != expected_value:
            raise UnsafeOperation(f"审批声明与当前作业不一致: {claim}")


def validate_approval(
    level: str,
    approval: Mapping[str, Any] | None,
    context: ApprovalContext | None = None,
    *,
    production_allowed: bool = False,
) -> None:
    safety_level = SafetyLevel(level)
    if approval is None and safety_level in {SafetyLevel.L0_READ_ONLY, SafetyLevel.L1_DRY_RUN}:
        return
    if approval is None:
        raise UnsafeOperation(f"{level} 缺少审批")
    missing = REQUIRED_APPROVAL_BINDINGS - approval.keys()
    if missing:
        raise UnsafeOperation(f"审批缺少绑定字段: {sorted(missing)}")
    if approval.get("single_use") is not True:
        raise UnsafeOperation("审批必须为 single_use")
    if approval.get("consumed") is True:
        raise UnsafeOperation("审批不得复用")
    if context is None:
        raise UnsafeOperation("缺少当前作业 ApprovalContext，不能验证审批绑定")
    _validate_claim_bindings(approval, context)
    expires_at = datetime.fromisoformat(str(approval["expires_at"]).replace("Z", "+00:00"))
    if expires_at <= datetime.now(timezone.utc):
        raise UnsafeOperation("审批已过期")
    if safety_level is SafetyLevel.L4_CONTROLLED_PRODUCTION:
        if production_allowed is not True or approval.get("production_allowed") is not True:
            raise UnsafeOperation("L4 必须由当前作业和审批票据共同明确授权 production_allowed=true")
    elif production_allowed is True or approval.get("production_allowed") is True:
        raise UnsafeOperation("L0-L3 不得携带生产写入授权")
