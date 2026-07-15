from __future__ import annotations

from typing import Any, Mapping


class SkillRuntimeError(RuntimeError):
    """可稳定序列化的 Skill 运行时错误基类。"""

    code = "SKILL_RUNTIME_ERROR"
    default_exit_code = 9

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        source: str | None = None,
        details: Mapping[str, Any] | None = None,
        suggested_action: str | None = None,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.source = source
        self.details = dict(details or {})
        self.suggested_action = suggested_action
        self.exit_code = exit_code if exit_code is not None else self.default_exit_code

    def to_error_payload(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": str(self),
                "field": self.field,
                "source": self.source,
                "details": self.details,
                "suggested_action": self.suggested_action,
            },
        }


class ManifestInvalid(SkillRuntimeError):
    code = "MANIFEST_INVALID"
    default_exit_code = 2


class ManifestVersionUnsupported(SkillRuntimeError):
    code = "MANIFEST_VERSION_UNSUPPORTED"
    default_exit_code = 7


class ManifestVersionTooOld(ManifestVersionUnsupported):
    code = "MANIFEST_VERSION_TOO_OLD"


class ManifestVersionTooNew(ManifestVersionUnsupported):
    code = "MANIFEST_VERSION_TOO_NEW"


class ManifestMigrationFailed(SkillRuntimeError):
    code = "MANIFEST_MIGRATION_FAILED"
    default_exit_code = 7


class ManifestDeprecatedField(SkillRuntimeError):
    code = "MANIFEST_DEPRECATED_FIELD"
    default_exit_code = 2


class ManifestUnknownField(SkillRuntimeError):
    code = "MANIFEST_UNKNOWN_FIELD"
    default_exit_code = 2


class ConfigConflict(SkillRuntimeError):
    code = "CONFIG_CONFLICT"
    default_exit_code = 3


class ConfigSecurityDowngradeBlocked(SkillRuntimeError):
    code = "CONFIG_SECURITY_DOWNGRADE_BLOCKED"
    default_exit_code = 3


class ConfigPrivilegeEscalationBlocked(SkillRuntimeError):
    code = "CONFIG_PRIVILEGE_ESCALATION_BLOCKED"
    default_exit_code = 5


class ConfigBackendOverrideForbidden(SkillRuntimeError):
    code = "CONFIG_BACKEND_OVERRIDE_FORBIDDEN"
    default_exit_code = 4


class ConfigApprovalInheritanceForbidden(SkillRuntimeError):
    code = "CONFIG_APPROVAL_INHERITANCE_FORBIDDEN"
    default_exit_code = 5


class ConfigMergeFailed(SkillRuntimeError):
    code = "CONFIG_MERGE_FAILED"
    default_exit_code = 3


class PathInvalid(SkillRuntimeError):
    code = "PATH_INVALID"
    default_exit_code = 6


class PathTraversalBlocked(PathInvalid):
    code = "PATH_TRAVERSAL_BLOCKED"


class PathOutsideProject(PathInvalid):
    code = "PATH_OUTSIDE_PROJECT"


class PathSourceOutputCollision(PathInvalid):
    code = "PATH_SOURCE_OUTPUT_COLLISION"


class PathExternalNotAllowed(PathInvalid):
    code = "PATH_EXTERNAL_NOT_ALLOWED"


class PathUncNotAllowed(PathInvalid):
    code = "PATH_UNC_NOT_ALLOWED"


class PathSymlinkBoundaryViolation(PathInvalid):
    code = "PATH_SYMLINK_BOUNDARY_VIOLATION"


class PathRequiredValueMissing(PathInvalid):
    code = "PATH_REQUIRED_VALUE_MISSING"


class RuntimeModeConflict(SkillRuntimeError):
    code = "RUNTIME_MODE_CONFLICT"
    default_exit_code = 3


class ProductInstanceConflict(SkillRuntimeError):
    code = "PRODUCT_INSTANCE_CONFLICT"
    default_exit_code = 3


class ProductModeConflict(ProductInstanceConflict):
    code = "PRODUCT_MODE_CONFLICT"


class ProductCapabilityUnavailable(SkillRuntimeError):
    code = "PRODUCT_CAPABILITY_UNAVAILABLE"
    default_exit_code = 3


class BackendNotAvailable(SkillRuntimeError):
    code = "BACKEND_NOT_AVAILABLE"
    default_exit_code = 4


class BackendConflict(BackendNotAvailable):
    code = "BACKEND_CONFLICT"


class WorkflowNotAvailable(SkillRuntimeError):
    code = "WORKFLOW_NOT_AVAILABLE"
    default_exit_code = 3


class ApprovalRequired(SkillRuntimeError):
    code = "APPROVAL_REQUIRED"
    default_exit_code = 5


class ApprovalScopeMismatch(ApprovalRequired):
    code = "APPROVAL_SCOPE_MISMATCH"


class RealCadAccessForbidden(SkillRuntimeError):
    code = "REAL_CAD_ACCESS_FORBIDDEN"
    default_exit_code = 6


class RealExecutionNotAvailable(SkillRuntimeError):
    code = "REAL_EXECUTION_NOT_AVAILABLE"
    default_exit_code = 4


class PlanNotExecutable(SkillRuntimeError):
    code = "PLAN_NOT_EXECUTABLE"
    default_exit_code = 5


class PlanHashMismatch(SkillRuntimeError):
    code = "PLAN_HASH_MISMATCH"
    default_exit_code = 2


class SafeBaselineInvalid(SkillRuntimeError):
    code = "SAFE_BASELINE_INVALID"
    default_exit_code = 8


class DocumentIdentityAmbiguous(SkillRuntimeError):
    code = "DOCUMENT_IDENTITY_AMBIGUOUS"
    default_exit_code = 3


class UnsafeOperation(SkillRuntimeError):
    code = "UNSAFE_OPERATION"
    default_exit_code = 5
