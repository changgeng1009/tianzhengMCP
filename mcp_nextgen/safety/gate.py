"""Layer D 入口安全门。"""

from __future__ import annotations

from typing import Any, Mapping

from .approval import ApprovalLevel, ApprovalPolicy, validate_approval, validate_write_document


def validate_execution_binding(
    *,
    job_id: str,
    document_identity: Mapping[str, Any],
    plan_hash: str,
    approval_context: Mapping[str, Any],
    operations: list[str],
    dry_run: bool,
    production_allowed: bool = False,
    policy: ApprovalPolicy | None = None,
) -> None:
    policy = policy or ApprovalPolicy()
    if not plan_hash or len(plan_hash) != 64:
        raise ValueError("plan_hash 必须是完整 SHA-256")
    if production_allowed and not policy.production_d1_allowed:
        raise PermissionError("production_d1_allowed=false")
    if not dry_run:
        validate_write_document(document_identity)
    required = ApprovalLevel.L1_DRY_RUN if dry_run else ApprovalLevel.L3_SANDBOX_WRITE
    validate_approval(
        approval_context,
        job_id=job_id,
        document_identity=document_identity,
        plan_hash=plan_hash,
        operations=operations,
        required_level=required,
        policy=policy,
    )

