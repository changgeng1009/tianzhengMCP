"""配置驱动运行时的离线、确定性基础组件。"""

from .canonical import canonical_dumps, canonical_hash, canonicalize
from .default_registry import DefaultRegistry, DefaultResolver
from .manifest_loader import ManifestLoader
from .merge import ConfigMerger, SecurityAwareMergePolicy
from .migrator import ManifestMigrator, MigrationResult
from .models import (
    DefaultSourceTrace,
    ManifestCompatibilityMatrix,
    ManifestVersion,
    MergeTrace,
    ResolvedPathRecord,
)
from .path_resolver import ManifestPathResolver, PathPolicy
from .versioning import CURRENT_VERSION, ManifestVersionPolicy

__all__ = [
    "CURRENT_VERSION",
    "ConfigMerger",
    "DefaultRegistry",
    "DefaultResolver",
    "DefaultSourceTrace",
    "ManifestCompatibilityMatrix",
    "ManifestLoader",
    "ManifestMigrator",
    "ManifestPathResolver",
    "ManifestVersion",
    "ManifestVersionPolicy",
    "MergeTrace",
    "MigrationResult",
    "PathPolicy",
    "ResolvedPathRecord",
    "SecurityAwareMergePolicy",
    "canonical_dumps",
    "canonical_hash",
    "canonicalize",
]
