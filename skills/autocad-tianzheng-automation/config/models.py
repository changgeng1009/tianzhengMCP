from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ManifestVersion(str, Enum):
    V1_0 = "1.0"
    V1_0_0 = "1.0.0"
    V1_1_0 = "1.1.0"


@dataclass(frozen=True)
class ManifestCompatibilityMatrix:
    current_version: str
    minimum_supported_version: str
    maximum_supported_version: str
    migration_path: tuple[str, ...]
    deprecated_fields: tuple[str, ...] = ()
    removed_fields: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "current_version": self.current_version,
            "minimum_supported_version": self.minimum_supported_version,
            "maximum_supported_version": self.maximum_supported_version,
            "migration_path": list(self.migration_path),
            "deprecated_fields": list(self.deprecated_fields),
            "removed_fields": list(self.removed_fields),
        }


@dataclass(frozen=True)
class DefaultSourceTrace:
    field: str
    value: Any
    source: str
    action: str = "APPLIED"
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "source": self.source,
            "action": self.action,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MergeTrace:
    field: str
    previous_value: Any
    incoming_value: Any
    resolved_value: Any
    source: str
    policy: str
    rejected: bool = False
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "previous_value": self.previous_value,
            "incoming_value": self.incoming_value,
            "resolved_value": self.resolved_value,
            "source": self.source,
            "policy": self.policy,
            "rejected": self.rejected,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ResolvedPathRecord:
    field: str
    declared_path: str
    canonical_path: str
    policy: str
    is_output: bool
    is_external: bool
    filesystem_accessed: bool = False
    runtime_boundary_verification_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "declared_path": self.declared_path,
            "canonical_path": self.canonical_path,
            "policy": self.policy,
            "is_output": self.is_output,
            "is_external": self.is_external,
            "filesystem_accessed": self.filesystem_accessed,
            "runtime_boundary_verification_required": self.runtime_boundary_verification_required,
        }


@dataclass
class ResolutionResult:
    value: dict[str, Any]
    source_trace: list[DefaultSourceTrace] = field(default_factory=list)
    merge_trace: list[MergeTrace] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "source_trace": [item.as_dict() for item in self.source_trace],
            "merge_trace": [item.as_dict() for item in self.merge_trace],
        }
