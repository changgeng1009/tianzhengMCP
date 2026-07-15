from __future__ import annotations

import pytest

from config import ManifestMigrator, ManifestVersionPolicy
from runtime.errors import (
    ConfigApprovalInheritanceForbidden,
    ManifestMigrationFailed,
    ManifestUnknownField,
    ManifestVersionTooNew,
    ManifestVersionTooOld,
)


def test_supported_version_aliases_share_path():
    assert ManifestVersionPolicy.normalize("1.0") == "1.0.0"
    assert ManifestVersionPolicy.migration_path("1.0")[-1] == "1.1.0"


@pytest.mark.parametrize(
    ("version", "error"),
    [("0.9.9", ManifestVersionTooOld), ("9.0.0", ManifestVersionTooNew)],
)
def test_version_boundaries_fail_closed(version, error):
    with pytest.raises(error):
        ManifestVersionPolicy.normalize(version)


def test_migration_preview_reports_changes(legacy_manifest):
    result = ManifestMigrator().preview(legacy_manifest)
    assert result.from_version == "1.0.0"
    assert result.to_version == "1.1.0"
    assert result.field_changes
    assert result.unmigrated_fields == ()


def test_migration_rejects_unknown_field(legacy_manifest):
    legacy_manifest["mystery"] = 1
    with pytest.raises(ManifestUnknownField):
        ManifestMigrator().migrate(legacy_manifest)


def test_migration_rejects_approval_inheritance(legacy_manifest):
    legacy_manifest["approval"] = {"token": "not-valid"}
    with pytest.raises(ConfigApprovalInheritanceForbidden):
        ManifestMigrator().migrate(legacy_manifest)


def test_migration_never_enables_production(legacy_manifest):
    legacy_manifest["production_allowed"] = True
    with pytest.raises(ManifestMigrationFailed):
        ManifestMigrator().migrate(legacy_manifest)
