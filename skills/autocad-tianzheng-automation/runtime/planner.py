from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from config.migrator import ManifestMigrator

from .execution_plan import ExecutionPlanBuilder
from .selector import select_runtime


def build_offline_plan(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """旧兼容入口；canonical Manifest 委托新确定性 PlanBuilder。"""
    version = str(manifest.get("schema_version") or "")
    if version in {"1.0", "1.0.0", "1.1.0"}:
        canonical = (
            dict(manifest)
            if version == "1.1.0"
            else ManifestMigrator().migrate(manifest)
        )
        return ExecutionPlanBuilder().build(canonical)

    # 保留无 schema_version 的早期调用行为，供旧 Adapter/测试兼容。
    selection = select_runtime(manifest)
    backend = str(manifest.get("preferred_backend") or "offline")
    if backend not in {"offline", "nextgen-mock", "original-redraw-adapter"}:
        return {
            "status": "DRY_RUN_ONLY",
            "backend": backend,
            "execution_allowed": False,
            "reason": "离线入口不执行真实 CAD 后端",
            "runtime_mode": selection.mode.value,
        }
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "status": "PLAN_READY",
        "execution_allowed": False,
        "runtime_mode": selection.mode.value,
        "product": selection.product,
        "backend": backend,
        "workflow": manifest.get("workflow"),
        "approval_level": manifest.get("approval_level", "L0_READ_ONLY"),
        "production_allowed": False,
        "plan_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "verification_dimensions": [
            "geometry_verified",
            "object_type_verified",
            "properties_verified",
            "display_environment_verified",
            "native_topology_verified",
            "engineering_semantic_completeness_verified",
            "visual_review_verified",
        ],
    }
