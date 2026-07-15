from __future__ import annotations

import re

from runtime.errors import (
    ManifestVersionTooNew,
    ManifestVersionTooOld,
    ManifestVersionUnsupported,
)

from .models import ManifestCompatibilityMatrix

CURRENT_VERSION = "1.1.0"
MINIMUM_SUPPORTED_VERSION = "1.0"
MAXIMUM_SUPPORTED_VERSION = CURRENT_VERSION
SUPPORTED_VERSIONS = frozenset({"1.0", "1.0.0", CURRENT_VERSION})
_SEMVER = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")


def _tuple(value: str) -> tuple[int, int, int]:
    match = _SEMVER.fullmatch(value)
    if not match:
        raise ManifestVersionUnsupported(
            f"无法解析 Manifest 版本: {value}", field="schema_version"
        )
    return tuple(int(part or 0) for part in match.groups())


class ManifestVersionPolicy:
    compatibility_matrix = ManifestCompatibilityMatrix(
        current_version=CURRENT_VERSION,
        minimum_supported_version=MINIMUM_SUPPORTED_VERSION,
        maximum_supported_version=MAXIMUM_SUPPORTED_VERSION,
        migration_path=("1.0", "1.0.0", CURRENT_VERSION),
        deprecated_fields=(
            "project_id",
            "project_name",
            "task_type",
            "runtime_mode",
            "product",
            "workflow",
            "approval_level",
            "preferred_backend",
        ),
    )

    @classmethod
    def normalize(cls, value: object) -> str:
        text = str(value or "").strip()
        version = _tuple(text)
        if version < _tuple(MINIMUM_SUPPORTED_VERSION):
            raise ManifestVersionTooOld(
                f"Manifest 版本过旧: {text}",
                field="schema_version",
                details={"minimum_supported_version": MINIMUM_SUPPORTED_VERSION},
            )
        if version > _tuple(MAXIMUM_SUPPORTED_VERSION):
            raise ManifestVersionTooNew(
                f"Manifest 版本过新: {text}",
                field="schema_version",
                details={"maximum_supported_version": MAXIMUM_SUPPORTED_VERSION},
            )
        if text not in SUPPORTED_VERSIONS:
            raise ManifestVersionUnsupported(
                f"Manifest 版本没有已验证迁移路径: {text}",
                field="schema_version",
                details={"supported_versions": sorted(SUPPORTED_VERSIONS)},
            )
        return "1.0.0" if text == "1.0" else text

    @classmethod
    def migration_path(cls, value: object) -> tuple[str, ...]:
        normalized = cls.normalize(value)
        if normalized == CURRENT_VERSION:
            return (CURRENT_VERSION,)
        return (normalized, CURRENT_VERSION)
