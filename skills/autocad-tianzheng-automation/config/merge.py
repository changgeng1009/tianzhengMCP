from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from runtime.errors import (
    ConfigApprovalInheritanceForbidden,
    ConfigBackendOverrideForbidden,
    ConfigPrivilegeEscalationBlocked,
    ConfigSecurityDowngradeBlocked,
)

from .canonical import canonical_dumps
from .models import MergeTrace

_PERMISSION_BOOLEANS = {
    "paths.allow_external",
    "paths.allow_unc",
    "safety.production_allowed",
    "safety.production_d1_allowed",
    "safety.real_cad_access_allowed",
}
_REQUIRED_BOOLEANS = {
    "runtime.offline_only",
    "workflow.dry_run",
    "workflow.simulate_only",
    "safety.source_write_forbidden",
    "safety.sandbox_required",
    "safety.fail_closed",
    "verification.visual_review_required",
    "verification.engineering_review_required",
    "recovery.manual_save_required",
}
_UNION_ARRAYS = {
    "safety.operation_denylist",
    "safety.protected_regions",
    "product.prohibited_products",
    "product.required_capabilities",
}
_INTERSECTION_ARRAYS = {"safety.operation_allowlist"}
_FORBIDDEN_BACKEND_FIELDS = {
    "backend.available",
    "backend.execution_allowed",
    "backend.support_level",
    "backend.real_cad_capability",
}
_LEVELS = {
    "L0_READ_ONLY": 0,
    "L1_DRY_RUN": 1,
    "L2_SANDBOX_PREP": 2,
    "L3_SANDBOX_WRITE": 3,
    "L4_CONTROLLED_PRODUCTION": 4,
}


def _unique_union(left: list[Any], right: list[Any]) -> list[Any]:
    seen: dict[str, Any] = {}
    for item in [*left, *right]:
        seen.setdefault(canonical_dumps(item), deepcopy(item))
    return [seen[key] for key in sorted(seen)]


def _safe_intersection(left: list[Any], right: list[Any]) -> list[Any]:
    left_items = {canonical_dumps(item): item for item in left}
    right_keys = {canonical_dumps(item) for item in right}
    return [deepcopy(left_items[key]) for key in sorted(left_items.keys() & right_keys)]


class SecurityAwareMergePolicy:
    """普通值按层覆盖，安全值只能保持或收紧。"""

    def resolve(
        self,
        field: str,
        previous: Any,
        incoming: Any,
        *,
        source: str,
    ) -> tuple[Any, str]:
        if field in _FORBIDDEN_BACKEND_FIELDS:
            raise ConfigBackendOverrideForbidden(
                f"配置不得改变 backend capability registry: {field}", field=field, source=source
            )
        if field in _PERMISSION_BOOLEANS:
            if previous is False and incoming is True:
                raise ConfigSecurityDowngradeBlocked(
                    f"安全权限不得由 false 提升为 true: {field}", field=field, source=source
                )
            return bool(previous) and bool(incoming), "permission_boolean_and"
        if field in _REQUIRED_BOOLEANS:
            if previous is True and incoming is False:
                raise ConfigSecurityDowngradeBlocked(
                    f"强制安全要求不得关闭: {field}", field=field, source=source
                )
            return bool(previous) or bool(incoming), "required_boolean_or"
        if field == "safety.requested_level":
            if incoming not in _LEVELS:
                raise ConfigPrivilegeEscalationBlocked(
                    f"未知安全等级: {incoming}", field=field, source=source
                )
            if _LEVELS[incoming] >= _LEVELS["L3_SANDBOX_WRITE"]:
                raise ConfigPrivilegeEscalationBlocked(
                    "配置不能授予 L3/L4；只能生成 blocked plan",
                    field=field,
                    source=source,
                    details={"requested_level": incoming},
                )
            return incoming, "non_executing_level_declaration"
        if field in _UNION_ARRAYS:
            return _unique_union(list(previous or []), list(incoming or [])), "restrictive_union"
        if field in _INTERSECTION_ARRAYS:
            return _safe_intersection(list(previous or []), list(incoming or [])), "allowlist_intersection"
        return deepcopy(incoming), "priority_override"


class ConfigMerger:
    def __init__(self, policy: SecurityAwareMergePolicy | None = None) -> None:
        self.policy = policy or SecurityAwareMergePolicy()

    def merge_layers(
        self, layers: list[tuple[str, Mapping[str, Any]]]
    ) -> tuple[dict[str, Any], list[MergeTrace]]:
        resolved: dict[str, Any] = {}
        trace: list[MergeTrace] = []
        for source, layer in layers:
            if source != "project_manifest" and layer.get("approval"):
                raise ConfigApprovalInheritanceForbidden(
                    "approval 不得来自默认值、workflow 或 run override",
                    field="approval",
                    source=source,
                )
            self._merge_mapping(resolved, layer, source=source, prefix="", trace=trace)
        return resolved, trace

    def _merge_mapping(
        self,
        destination: dict[str, Any],
        incoming: Mapping[str, Any],
        *,
        source: str,
        prefix: str,
        trace: list[MergeTrace],
    ) -> None:
        for key in sorted(incoming):
            field = f"{prefix}.{key}" if prefix else key
            value = incoming[key]
            if key not in destination:
                if isinstance(value, Mapping):
                    destination[key] = {}
                    self._merge_mapping(
                        destination[key], value, source=source, prefix=field, trace=trace
                    )
                    continue
                security_default: Any | None = None
                policy_name = "initial_value"
                if field in _PERMISSION_BOOLEANS:
                    security_default = False
                elif field in _REQUIRED_BOOLEANS:
                    security_default = True
                elif field == "safety.requested_level":
                    security_default = "L0_READ_ONLY"
                elif field in _UNION_ARRAYS or field in _INTERSECTION_ARRAYS:
                    security_default = []
                elif field in _FORBIDDEN_BACKEND_FIELDS:
                    security_default = None
                if security_default is not None or field in _FORBIDDEN_BACKEND_FIELDS:
                    destination[key], policy_name = self.policy.resolve(
                        field, security_default, value, source=source
                    )
                else:
                    destination[key] = deepcopy(value)
                trace.append(MergeTrace(field, None, value, destination[key], source, policy_name))
                continue
            previous = destination[key]
            if isinstance(previous, dict) and isinstance(value, Mapping):
                self._merge_mapping(previous, value, source=source, prefix=field, trace=trace)
                continue
            resolved, policy_name = self.policy.resolve(field, previous, value, source=source)
            destination[key] = resolved
            trace.append(MergeTrace(field, previous, value, resolved, source, policy_name))
