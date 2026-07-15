from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "autocad-tianzheng-automation"
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))


def _document(document_id: str, role: str, path: str, product: str = "unknown") -> dict:
    return {
        "document_id": document_id,
        "role": role,
        "media_type": "dwg",
        "path": path,
        "identity_policy": "require_runtime_verification",
        "expected_product": product,
        "readonly": True,
        "required": True,
        "synthetic_test_file": False,
        "expected_filename": None,
        "expected_extension": ".dwg",
        "expected_sha256": None,
        "expected_size": None,
        "identity_status": "RUNTIME_VERIFICATION_REQUIRED",
    }


def canonical_manifest_value() -> dict:
    """只包含虚构路径字符串；任何测试都不得跟随打开这些路径。"""

    return {
        "schema_version": "1.1.0",
        "project": {
            "project_id": "fictional-project",
            "project_name": "虚构配置项目",
            "description": "纯离线配置测试",
            "project_type": "cad_automation",
            "tags": ["synthetic", "offline"],
        },
        "task": {
            "task_id": "fictional-task",
            "task_type": "inspect_drawing",
            "task_description": "仅生成离线计划",
            "requested_operations": ["inspect"],
            "expected_outputs": ["plan"],
        },
        "runtime": {
            "runtime_mode": "plain_autocad",
            "auto_detect_policy": "explicit_metadata_only",
            "conflict_policy": "fail_closed",
            "offline_only": True,
        },
        "documents": {
            "reference_documents": [
                _document("reference-1", "reference", "inputs/fictional-reference.dwg")
            ],
            "target_documents": [
                _document("target-1", "target", "inputs/fictional-target.dwg")
            ],
            "auxiliary_documents": [],
        },
        "paths": {
            "path_policy": "project_relative",
            "allow_external": False,
            "allow_unc": False,
        },
        "product": {
            "requested_product": "generic_autocad",
            "required_capabilities": [],
            "prohibited_products": ["tianzheng_water", "tianzheng_hvac"],
            "product_detection_policy": "explicit_metadata_only",
        },
        "backend": {
            "preferred_backend": "offline",
            "fallback_backends": [],
            "backend_selection_policy": "explicit_only",
            "require_real_execution": False,
            "mock_allowed": False,
        },
        "workflow": {
            "workflow_id": "generic_autocad_redraw_offline",
            "workflow_type": "offline_plan",
            "stages": [],
            "stage_policy": "registry_defined",
            "dry_run": True,
            "simulate_only": True,
        },
        "safety": {
            "requested_level": "L1_DRY_RUN",
            "production_allowed": False,
            "production_d1_allowed": False,
            "sandbox_required": True,
            "source_write_forbidden": True,
            "protected_regions": [],
            "operation_allowlist": [],
            "operation_denylist": [],
            "fail_closed": True,
            "real_cad_access_allowed": False,
        },
        "approval": {
            "required_level": "L1_DRY_RUN",
            "approval_reference": None,
            "approval_required": False,
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
            "checkpoint_enabled": True,
            "journal_enabled": True,
            "resume_enabled": True,
            "manual_save_required": True,
            "idempotency_required": True,
        },
        "output": {
            "output_root": "generated/output",
            "artifact_root": "generated/artifacts",
            "plan_output": "generated/plan.json",
            "evidence_output": "generated/evidence.json",
            "report_output": "generated/report.json",
            "naming_policy": "deterministic",
        },
        "metadata": {
            "created_at": None,
            "created_by": None,
            "source": "synthetic_test",
            "notes": "",
        },
        "extensions": {},
    }


@pytest.fixture
def canonical_manifest() -> dict:
    return deepcopy(canonical_manifest_value())


@pytest.fixture
def legacy_manifest() -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "legacy-fictional",
        "project_name": "虚构旧项目",
        "task_type": "inspect_drawing",
        "runtime_mode": "plain_autocad",
        "product": "autocad",
        "reference_documents": [
            {"id": "reference-1", "type": "DWG", "path": "inputs/old-reference.dwg"}
        ],
        "target_documents": [],
        "output_root": "generated/output",
        "artifact_root": "generated/artifacts",
        "workflow": "generic_autocad_redraw_offline",
        "approval_level": "L1_DRY_RUN",
        "production_allowed": False,
        "production_d1_allowed": False,
        "preferred_backend": "offline",
        "visual_review_required": True,
        "engineering_review_required": True,
    }
