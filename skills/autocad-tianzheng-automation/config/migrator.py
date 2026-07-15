from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from runtime.errors import (
    ConfigApprovalInheritanceForbidden,
    ManifestMigrationFailed,
    ManifestUnknownField,
)

from .versioning import CURRENT_VERSION, ManifestVersionPolicy

_V1_FIELDS = {
    "schema_version", "project_id", "project_name", "task_type",
    "runtime_mode", "product", "reference_documents", "target_documents",
    "output_root", "artifact_root", "document_identities", "expected_sha256",
    "input_roles", "reference_types", "workflow", "approval_level", "approval",
    "production_allowed", "production_d1_allowed", "protected_regions",
    "excluded_layers", "excluded_objects", "preferred_backend", "fallback_backend",
    "visual_review_required", "engineering_review_required", "checkpoint", "options",
}

_PRODUCT_MAP = {
    "autocad": "generic_autocad",
    "tianzheng_water": "tianzheng_water",
    "tianzheng_hvac": "tianzheng_hvac",
    "offline": "unknown",
    "auto": "unknown",
}

_BACKEND_MAP = {
    "offline": "offline",
    "original-redraw-adapter": "original_redraw_adapter",
    "nextgen-mock": "nextgen_mock",
    "legacy-contract-disabled": "legacy_contract_disabled",
    "legacy-com": "legacy_com",
    "nextgen-real": "nextgen_real",
    "autocad-dotnet-plugin": "autocad_dotnet_plugin",
    "tianzheng-water-real": "tianzheng_water_real",
    "tianzheng-hvac-real": "tianzheng_hvac_real",
}


@dataclass(frozen=True)
class MigrationResult:
    manifest: dict[str, Any]
    from_version: str
    to_version: str
    field_changes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    deprecated_fields: tuple[str, ...] = field(default_factory=tuple)
    unmigrated_fields: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "field_changes": list(self.field_changes),
            "deprecated_fields": list(self.deprecated_fields),
            "unmigrated_fields": list(self.unmigrated_fields),
            "warnings": list(self.warnings),
        }


def _document(item: Mapping[str, Any], index: int, category: str) -> dict[str, Any]:
    media_type = str(item.get("type") or "none").lower()
    expected_product = "unknown"
    return {
        "document_id": str(item.get("id") or f"{category}-{index + 1}"),
        "role": str(item.get("role") or category),
        "media_type": media_type,
        "path": str(item.get("path") or ""),
        "identity_policy": "require_runtime_verification" if media_type in {"dwg", "dxf"} else "declared_only",
        "expected_product": expected_product,
        "readonly": bool(item.get("read_only", True)),
        "required": True,
        "synthetic_test_file": False,
        "expected_filename": None,
        "expected_extension": f".{media_type}" if media_type != "none" else None,
        "expected_sha256": None,
        "expected_size": None,
        "identity_status": "RUNTIME_VERIFICATION_REQUIRED" if media_type in {"dwg", "dxf"} else "DECLARED",
    }


class ManifestMigrator:
    """将 1.0/1.0.0 扁平 Manifest 无权限提升地迁移到 1.1.0。"""

    def preview(self, manifest: Mapping[str, Any], *, to_version: str = CURRENT_VERSION) -> MigrationResult:
        source = deepcopy(dict(manifest))
        from_version = ManifestVersionPolicy.normalize(source.get("schema_version"))
        target = ManifestVersionPolicy.normalize(to_version)
        if target != CURRENT_VERSION:
            raise ManifestMigrationFailed(
                f"当前仅支持迁移到 {CURRENT_VERSION}", field="schema_version"
            )
        if from_version == CURRENT_VERSION:
            return MigrationResult(source, from_version, target)
        unknown = sorted(set(source) - _V1_FIELDS)
        if unknown:
            raise ManifestUnknownField(
                f"1.0 Manifest 包含未知顶层字段: {unknown}",
                details={"unknown_fields": unknown, "allowed_extension_target": "extensions"},
            )
        if source.get("approval"):
            raise ConfigApprovalInheritanceForbidden(
                "旧 Manifest 中的审批票据不得跨版本继承；请移除票据并仅保留新的 approval_reference 声明",
                field="approval",
            )
        if source.get("production_allowed") is not False:
            raise ManifestMigrationFailed("迁移拒绝 production_allowed=true", field="production_allowed")
        if source.get("production_d1_allowed", False) is not False:
            raise ManifestMigrationFailed("迁移拒绝 production_d1_allowed=true", field="production_d1_allowed")

        project_id = str(source.get("project_id") or "")
        task_type = str(source.get("task_type") or "")
        level = str(source.get("approval_level") or "L0_READ_ONLY")
        checkpoint = deepcopy(source.get("checkpoint") or {})
        extensions: dict[str, Any] = {}
        for old_key, extension_key in (
            ("options", "legacy_options"),
            ("checkpoint", "legacy_checkpoint"),
            ("document_identities", "legacy_document_identities"),
            ("expected_sha256", "legacy_expected_sha256"),
            ("input_roles", "legacy_input_roles"),
            ("reference_types", "legacy_reference_types"),
            ("excluded_layers", "legacy_excluded_layers"),
        ):
            if source.get(old_key):
                extensions[extension_key] = deepcopy(source[old_key])

        preferred = _BACKEND_MAP.get(str(source.get("preferred_backend") or "offline"))
        if preferred is None:
            raise ManifestMigrationFailed(
                "旧 Manifest backend 无确定映射",
                field="preferred_backend",
                details={"value": source.get("preferred_backend")},
            )
        fallback_raw = source.get("fallback_backend")
        fallback = _BACKEND_MAP.get(str(fallback_raw)) if fallback_raw else None
        if fallback_raw and fallback is None:
            raise ManifestMigrationFailed(
                "旧 Manifest fallback backend 无确定映射",
                field="fallback_backend",
                details={"value": fallback_raw},
            )

        migrated = {
            "schema_version": CURRENT_VERSION,
            "project": {
                "project_id": project_id,
                "project_name": str(source.get("project_name") or ""),
                "description": "",
                "project_type": "cad_automation",
                "tags": [],
            },
            "task": {
                "task_id": f"{project_id}-{task_type}".strip("-"),
                "task_type": task_type,
                "task_description": "",
                "requested_operations": [],
                "expected_outputs": [],
            },
            "runtime": {
                "runtime_mode": str(source.get("runtime_mode") or "auto_detect"),
                "auto_detect_policy": "explicit_metadata_only",
                "conflict_policy": "fail_closed",
                "offline_only": True,
            },
            "documents": {
                "reference_documents": [
                    _document(item, index, "reference")
                    for index, item in enumerate(source.get("reference_documents") or [])
                ],
                "target_documents": [
                    _document(item, index, "target")
                    for index, item in enumerate(source.get("target_documents") or [])
                ],
                "auxiliary_documents": [],
            },
            "paths": {
                "path_policy": "project_relative",
                "allow_external": False,
                "allow_unc": False,
            },
            "product": {
                "requested_product": _PRODUCT_MAP.get(str(source.get("product") or "auto"), "unknown"),
                "required_capabilities": [],
                "prohibited_products": [],
                "product_detection_policy": "explicit_metadata_only",
            },
            "backend": {
                "preferred_backend": preferred,
                "fallback_backends": [fallback] if fallback else [],
                "backend_selection_policy": "explicit_only",
                "require_real_execution": False,
                "mock_allowed": preferred == "nextgen_mock",
            },
            "workflow": {
                "workflow_id": str(source.get("workflow") or "00_select_runtime"),
                "workflow_type": task_type or "offline_plan",
                "stages": [],
                "stage_policy": "registry_defined",
                "dry_run": True,
                "simulate_only": True,
            },
            "safety": {
                "requested_level": level,
                "production_allowed": False,
                "production_d1_allowed": False,
                "sandbox_required": True,
                "source_write_forbidden": True,
                "protected_regions": deepcopy(source.get("protected_regions") or []),
                "operation_allowlist": [],
                "operation_denylist": sorted(set(source.get("excluded_objects") or [])),
                "fail_closed": True,
                "real_cad_access_allowed": False,
            },
            "approval": {
                "required_level": level,
                "approval_reference": None,
                "approval_required": level not in {"L0_READ_ONLY", "L1_DRY_RUN"},
                "single_use": True,
                "expires_at": None,
            },
            "verification": {
                "entity_verification_required": True,
                "visual_review_required": True,
                "topology_verification_required": False,
                "engineering_review_required": True,
                "reopen_verification_required": False,
            },
            "recovery": {
                "checkpoint_enabled": bool(checkpoint),
                "journal_enabled": bool(checkpoint),
                "resume_enabled": bool(checkpoint),
                "manual_save_required": True,
                "idempotency_required": True,
            },
            "output": {
                "output_root": str(source.get("output_root") or "outputs"),
                "artifact_root": str(source.get("artifact_root") or "artifacts"),
                "plan_output": "artifacts/plan.json",
                "evidence_output": "artifacts/evidence.json",
                "report_output": "artifacts/report.json",
                "naming_policy": "deterministic",
            },
            "metadata": {
                "created_at": None,
                "created_by": None,
                "source": "migrated_from_1_0",
                "notes": "",
            },
            "extensions": extensions,
        }
        deprecated = tuple(
            field for field in ManifestVersionPolicy.compatibility_matrix.deprecated_fields
            if field in source
        )
        changes = (
            {"field": "schema_version", "from": source.get("schema_version"), "to": CURRENT_VERSION},
            {"field": "top_level", "from": "flat_v1", "to": "canonical_nested_v1_1"},
            {"field": "safety", "action": "forced_restrictive_defaults"},
            {"field": "approval", "action": "not_inherited"},
        )
        return MigrationResult(
            migrated,
            from_version,
            target,
            field_changes=changes,
            deprecated_fields=deprecated,
            warnings=("文档身份仅迁移为声明；真实运行仍须独立验证。",),
        )

    def migrate(self, manifest: Mapping[str, Any], *, to_version: str = CURRENT_VERSION) -> dict[str, Any]:
        return self.preview(manifest, to_version=to_version).manifest
