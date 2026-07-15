from __future__ import annotations

from copy import deepcopy
import json

import pytest

from config import ManifestLoader, canonical_dumps, canonical_hash
from runtime.errors import ManifestInvalid, ManifestVersionTooNew


def test_req_001_minimal_legal_manifest(canonical_manifest):
    ManifestLoader().validate(canonical_manifest)


def test_req_002_complete_legal_manifest(canonical_manifest):
    canonical_manifest["extensions"] = {"vendor": {"safe_flag": True}}
    ManifestLoader().validate(canonical_manifest)


def test_req_003_required_field_missing(canonical_manifest):
    canonical_manifest.pop("safety")
    with pytest.raises(ManifestInvalid):
        ManifestLoader().validate(canonical_manifest)


def test_req_004_unknown_version_is_rejected(canonical_manifest):
    canonical_manifest["schema_version"] = "banana"
    with pytest.raises(Exception) as caught:
        ManifestLoader().validate(canonical_manifest)
    assert getattr(caught.value, "code", "").startswith("MANIFEST_VERSION")


def test_req_005_old_version_migrates(legacy_manifest):
    from config import ManifestMigrator

    migrated = ManifestMigrator().migrate(legacy_manifest)
    assert migrated["schema_version"] == "1.1.0"
    ManifestLoader().validate(migrated)


def test_req_006_newer_version_is_rejected(canonical_manifest):
    canonical_manifest["schema_version"] = "1.2.0"
    with pytest.raises(ManifestVersionTooNew):
        ManifestLoader().validate(canonical_manifest)


def test_req_007_unknown_top_level_field_is_rejected(canonical_manifest):
    canonical_manifest["unexpected"] = True
    with pytest.raises(ManifestInvalid):
        ManifestLoader().validate(canonical_manifest)


def test_req_008_utf8_manifest_round_trip(tmp_path, canonical_manifest):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(canonical_manifest, ensure_ascii=False), encoding="utf-8")
    loaded = ManifestLoader().load(path)
    assert loaded["project"]["project_name"] == "虚构配置项目"


def test_req_009_canonical_json_is_stable(canonical_manifest):
    reordered = {key: canonical_manifest[key] for key in reversed(canonical_manifest)}
    assert canonical_dumps(reordered) == canonical_dumps(canonical_manifest)
    assert canonical_hash(reordered) == canonical_hash(canonical_manifest)


def test_req_010_schema_round_trip(canonical_manifest):
    round_tripped = json.loads(canonical_dumps(canonical_manifest))
    ManifestLoader().validate(round_tripped)
    assert round_tripped == canonical_manifest
