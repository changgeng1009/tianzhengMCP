"""审批、文档身份和计划绑定校验。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Mapping

from .canonical import sha256_hex


class ApprovalLevel(IntEnum):
    L0_READ_ONLY = 0
    L1_DRY_RUN = 1
    L2_SANDBOX_PREP = 2
    L3_SANDBOX_WRITE = 3
    L4_CONTROLLED_PRODUCTION = 4


WRITE_FORBIDDEN_ROLES = frozenset({"SOURCE", "REFERENCE", "TARGET_ORIGINAL", "ORIGINAL"})


@dataclass(frozen=True)
class ApprovalPolicy:
    production_d1_allowed: bool = False


class ApprovalRejected(PermissionError):
    pass


def _field(value: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in value:
            return value[name]
    return None


def document_identity_digest(identity: Mapping[str, Any]) -> str:
    path = _field(identity, "document_full_path", "document_path")
    digest = _field(identity, "document_sha256", "document_hash")
    role = _field(identity, "document_role", "role")
    if not path or not digest or not role:
        raise ApprovalRejected("DocumentIdentity 缺少 full_path/sha256/role")
    return sha256_hex({
        "document_full_path": str(Path(str(path)).resolve(strict=False)),
        "document_sha256": str(digest).lower(),
        "document_role": str(role).upper(),
    })


def validate_approval(
    approval: Mapping[str, Any],
    *,
    job_id: str,
    document_identity: Mapping[str, Any],
    plan_hash: str,
    operations: list[str],
    required_level: ApprovalLevel,
    policy: ApprovalPolicy | None = None,
) -> None:
    policy = policy or ApprovalPolicy()
    if str(approval.get("job_id", "")) != job_id:
        raise ApprovalRejected("审批未绑定当前 job_id")
    if str(approval.get("plan_hash", "")) != plan_hash:
        raise ApprovalRejected("审批未绑定当前 plan_hash")
    expected_identity = document_identity_digest(document_identity)
    approval_identity_digest = approval.get("document_identity_digest")
    if not approval_identity_digest and isinstance(approval.get("document"), Mapping):
        approval_identity_digest = document_identity_digest(approval["document"])
    if str(approval_identity_digest or "") != expected_identity:
        raise ApprovalRejected("审批未绑定当前 DocumentIdentity")
    try:
        raw_level = approval.get("approval_level", -1)
        if isinstance(raw_level, str) and raw_level in ApprovalLevel.__members__:
            level = ApprovalLevel[raw_level]
        else:
            level = ApprovalLevel(int(raw_level))
    except (TypeError, ValueError) as exc:
        raise ApprovalRejected("approval_level 非法") from exc
    if level < required_level:
        raise ApprovalRejected("审批等级不足")
    if level is ApprovalLevel.L4_CONTROLLED_PRODUCTION and not policy.production_d1_allowed:
        raise ApprovalRejected("当前 production_d1_allowed=false")
    allowed = {str(item) for item in approval.get("allowed_operations", [])}
    missing = sorted(set(operations) - allowed)
    if missing:
        raise ApprovalRejected(f"审批不允许操作: {missing}")
    consumed = bool(approval.get("consumed", False) or approval.get("used_at"))
    if bool(approval.get("single_use", False)) and consumed:
        raise ApprovalRejected("single-use 审批已消费")
    expires_at = approval.get("expires_at")
    if expires_at:
        try:
            expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ApprovalRejected("审批 expires_at 非法") from exc
        if expires.tzinfo is None:
            raise ApprovalRejected("审批 expires_at 必须带时区")
        if expires <= datetime.now(timezone.utc):
            raise ApprovalRejected("审批已过期")


def validate_write_document(identity: Mapping[str, Any]) -> None:
    role = str(_field(identity, "document_role", "role") or "").upper()
    if role in WRITE_FORBIDDEN_ROLES:
        raise ApprovalRejected(f"文档角色禁止写入: {role}")
    document_identity_digest(identity)
