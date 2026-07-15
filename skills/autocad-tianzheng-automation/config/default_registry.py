from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .merge import ConfigMerger
from .models import DefaultSourceTrace, ResolutionResult

_PRODUCT_FILES = {
    "plain_autocad": "plain_autocad_defaults.json",
    "generic_autocad": "plain_autocad_defaults.json",
    "tianzheng_water": "tianzheng_water_defaults.json",
    "tianzheng_hvac": "tianzheng_hvac_defaults.json",
    "offline_analysis": "offline_analysis_defaults.json",
    "unknown": "offline_analysis_defaults.json",
}


class DefaultRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parent / "defaults"

    def _read(self, name: str) -> dict[str, Any]:
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def system_defaults(self) -> dict[str, Any]:
        return self._read("system_defaults.json")

    def skill_defaults(self) -> dict[str, Any]:
        return self._read("skill_defaults.json")

    def product_defaults(self, product_or_mode: str | None) -> dict[str, Any]:
        if not product_or_mode:
            return {}
        filename = _PRODUCT_FILES.get(product_or_mode)
        return self._read(filename) if filename else {}

    def describe(self) -> dict[str, Any]:
        return {
            "precedence_high_to_low": [
                "run_override", "project_manifest", "workflow_default",
                "product_default", "skill_default", "system_default",
            ],
            "files": {
                "system_default": "system_defaults.json",
                "skill_default": "skill_defaults.json",
                "product_defaults": sorted(set(_PRODUCT_FILES.values())),
            },
            "approval_inherited": False,
        }


def _walk_sources(value: Any, source: str, prefix: str = "") -> list[DefaultSourceTrace]:
    if isinstance(value, Mapping):
        items: list[DefaultSourceTrace] = []
        for key in sorted(value):
            field = f"{prefix}.{key}" if prefix else key
            items.extend(_walk_sources(value[key], source, field))
        return items
    return [DefaultSourceTrace(prefix, deepcopy(value), source)]


class DefaultResolver:
    """按六层优先级解析，并为每个叶子字段保留来源与安全合并轨迹。"""

    def __init__(
        self,
        registry: DefaultRegistry | None = None,
        merger: ConfigMerger | None = None,
    ) -> None:
        self.registry = registry or DefaultRegistry()
        self.merger = merger or ConfigMerger()

    def resolve(
        self,
        project_manifest: Mapping[str, Any],
        *,
        product_or_mode: str | None = None,
        workflow_defaults: Mapping[str, Any] | None = None,
        run_override: Mapping[str, Any] | None = None,
    ) -> ResolutionResult:
        layers = [
            ("system_default", self.registry.system_defaults()),
            ("skill_default", self.registry.skill_defaults()),
            ("product_default", self.registry.product_defaults(product_or_mode)),
            ("workflow_default", dict(workflow_defaults or {})),
            ("project_manifest", dict(project_manifest)),
            ("run_override", dict(run_override or {})),
        ]
        resolved, merge_trace = self.merger.merge_layers(layers)
        latest_sources: dict[str, DefaultSourceTrace] = {}
        for source, layer in layers:
            for item in _walk_sources(layer, source):
                latest_sources[item.field] = item
        for item in merge_trace:
            if item.policy in {
                "permission_boolean_and", "required_boolean_or", "restrictive_union",
                "allowlist_intersection", "non_executing_level_declaration",
            }:
                latest_sources[item.field] = DefaultSourceTrace(
                    item.field,
                    item.resolved_value,
                    "security_forced",
                    reason=item.policy,
                )
        return ResolutionResult(
            resolved,
            source_trace=[latest_sources[key] for key in sorted(latest_sources)],
            merge_trace=merge_trace,
        )
