from __future__ import annotations

from pathlib import Path

import pytest

from config import ManifestPathResolver
from runtime.errors import (
    PathExternalNotAllowed,
    PathSourceOutputCollision,
    PathTraversalBlocked,
    PathUncNotAllowed,
)


def _resolver() -> ManifestPathResolver:
    return ManifestPathResolver(
        project_root="C:/fictional/project",
        workspace_root="C:/fictional",
        forbidden_output_roots=(
            "C:/fictional/project/skills/autocad-tianzheng-automation",
            "C:/fictional/original-redraw-skill",
        ),
    )


def test_req_025_manifest_relative_path():
    record = _resolver().resolve_one(
        "inputs/reference.dwg",
        field="documents.reference_documents[0].path",
        manifest_directory="C:/fictional/project/config",
    )
    assert record.canonical_path == "C:/fictional/project/config/inputs/reference.dwg"


def test_req_026_resolution_does_not_depend_on_cwd(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parent)
    first = _resolver().resolve_one(
        "inputs/reference.dwg", field="document.path", manifest_directory="C:/fictional/project/config"
    )
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    second = _resolver().resolve_one(
        "inputs/reference.dwg", field="document.path", manifest_directory="C:/fictional/project/config"
    )
    assert first.canonical_path == second.canonical_path


def test_req_027_parent_traversal_is_blocked():
    with pytest.raises(PathTraversalBlocked):
        _resolver().resolve_one(
            "../outside/reference.dwg", field="document.path", manifest_directory="C:/fictional/project"
        )


def test_req_028_source_output_collision(canonical_manifest):
    canonical_manifest["documents"]["reference_documents"][0]["path"] = "generated/output"
    with pytest.raises(PathSourceOutputCollision):
        _resolver().resolve_manifest(canonical_manifest, manifest_directory="C:/fictional/project")


def test_req_029_unc_is_blocked():
    with pytest.raises(PathUncNotAllowed):
        _resolver().resolve_one(
            r"\\fictional-server\share\reference.dwg",
            field="document.path",
            manifest_directory="C:/fictional/project",
        )


def test_req_030_external_absolute_requires_explicit_policy():
    with pytest.raises(PathExternalNotAllowed):
        _resolver().resolve_one(
            "D:/external/reference.dwg",
            field="document.path",
            manifest_directory="C:/fictional/project",
        )
    record = _resolver().resolve_one(
        "D:/external/reference.dwg",
        field="document.path",
        manifest_directory="C:/fictional/project",
        policy="external_readonly",
        allow_external=True,
    )
    assert record.is_external is True


def test_req_031_windows_case_is_normalized_for_collision(canonical_manifest):
    canonical_manifest["documents"]["reference_documents"][0]["path"] = "GENERATED/OUTPUT"
    with pytest.raises(PathSourceOutputCollision):
        _resolver().resolve_manifest(canonical_manifest, manifest_directory="C:/fictional/project")


def test_req_032_slashes_are_normalized():
    record = _resolver().resolve_one(
        r"inputs\nested/reference.dwg",
        field="document.path",
        manifest_directory="C:/fictional/project",
    )
    assert "\\" not in record.canonical_path
    assert record.canonical_path.endswith("inputs/nested/reference.dwg")


def test_req_033_path_resolution_never_opens_cad(cad_access_guard):
    record = _resolver().resolve_one(
        "inputs/reference.dwg",
        field="document.path",
        manifest_directory="C:/fictional/project",
    )
    assert record.filesystem_accessed is False
    assert cad_access_guard._installed is True


def test_req_034_output_cannot_enter_skill_installation():
    with pytest.raises(PathExternalNotAllowed):
        _resolver().resolve_one(
            "skills/autocad-tianzheng-automation/generated",
            field="output.output_root",
            manifest_directory="C:/fictional/project",
            is_output=True,
            readonly=False,
        )
