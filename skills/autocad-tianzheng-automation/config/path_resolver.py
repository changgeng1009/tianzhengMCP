from __future__ import annotations

import ntpath
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from runtime.errors import (
    PathExternalNotAllowed,
    PathInvalid,
    PathOutsideProject,
    PathRequiredValueMissing,
    PathSourceOutputCollision,
    PathSymlinkBoundaryViolation,
    PathTraversalBlocked,
    PathUncNotAllowed,
)

from .models import ResolvedPathRecord


class PathPolicy(str, Enum):
    PROJECT_RELATIVE = "project_relative"
    WORKSPACE_RELATIVE = "workspace_relative"
    ABSOLUTE_EXPLICIT = "absolute_explicit"
    EXTERNAL_READONLY = "external_readonly"


def _slash(value: str) -> str:
    return ntpath.normpath(value).replace("\\", "/")


def _case(value: str) -> str:
    return _slash(value).casefold()


def _is_unc(value: str) -> bool:
    return value.startswith("\\\\") or value.startswith("//")


def _has_parent_segment(value: str) -> bool:
    return any(part == ".." for part in value.replace("\\", "/").split("/"))


def _inside(path: str, root: str) -> bool:
    try:
        return _case(ntpath.commonpath([_case(path), _case(root)])) == _case(root)
    except ValueError:
        return False


@dataclass(frozen=True)
class ResolvedManifestPaths:
    records: tuple[ResolvedPathRecord, ...]
    source_output_collision: bool = False
    filesystem_accessed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "records": [record.as_dict() for record in self.records],
            "source_output_collision": self.source_output_collision,
            "filesystem_accessed": self.filesystem_accessed,
        }


class ManifestPathResolver:
    """只做 Windows 词法路径解析；从不调用 exists/stat/open/hash/resolve。"""

    def __init__(
        self,
        *,
        project_root: str,
        workspace_root: str | None = None,
        forbidden_output_roots: Sequence[str] = (),
    ) -> None:
        if not project_root:
            raise PathRequiredValueMissing("project_root 不能为空", field="project_root")
        self.project_root = _slash(project_root)
        self.workspace_root = _slash(workspace_root or project_root)
        self.forbidden_output_roots = tuple(_slash(item) for item in forbidden_output_roots)

    def resolve_one(
        self,
        value: str,
        *,
        field: str,
        manifest_directory: str,
        policy: str = PathPolicy.PROJECT_RELATIVE.value,
        is_output: bool = False,
        readonly: bool = True,
        allow_external: bool = False,
        allow_unc: bool = False,
    ) -> ResolvedPathRecord:
        declared = str(value or "").strip()
        if not declared:
            raise PathRequiredValueMissing("路径不能为空", field=field)
        if "\x00" in declared:
            raise PathInvalid("路径包含 NUL", field=field)
        if _has_parent_segment(declared):
            raise PathTraversalBlocked("路径包含 '..'，词法边界检查拒绝", field=field)
        if _is_unc(declared) and not allow_unc:
            raise PathUncNotAllowed("UNC 路径默认禁止", field=field)
        try:
            selected = PathPolicy(policy)
        except ValueError as exc:
            raise PathInvalid(f"未知路径策略: {policy}", field=field) from exc

        absolute = ntpath.isabs(declared) or _is_unc(declared)
        external = False
        if selected is PathPolicy.PROJECT_RELATIVE:
            if absolute:
                raise PathExternalNotAllowed("project_relative 不接受绝对路径", field=field)
            anchor = _slash(manifest_directory)
            canonical = _slash(ntpath.join(anchor, declared))
            if not _inside(canonical, self.project_root):
                raise PathOutsideProject("路径解析结果位于项目外", field=field)
        elif selected is PathPolicy.WORKSPACE_RELATIVE:
            if absolute:
                raise PathExternalNotAllowed("workspace_relative 不接受绝对路径", field=field)
            canonical = _slash(ntpath.join(self.workspace_root, declared))
            if not _inside(canonical, self.workspace_root):
                raise PathOutsideProject("路径解析结果位于 workspace 外", field=field)
        elif selected is PathPolicy.ABSOLUTE_EXPLICIT:
            if not absolute:
                raise PathInvalid("absolute_explicit 必须提供绝对路径", field=field)
            if not allow_external:
                raise PathExternalNotAllowed("未显式允许外部绝对路径", field=field)
            canonical = _slash(declared)
            external = not _inside(canonical, self.project_root)
        else:
            if is_output or not readonly:
                raise PathExternalNotAllowed("external_readonly 仅允许只读输入", field=field)
            if not absolute:
                raise PathInvalid("external_readonly 必须提供绝对路径", field=field)
            if not allow_external:
                raise PathExternalNotAllowed("未显式允许 external_readonly", field=field)
            canonical = _slash(declared)
            external = True

        if is_output:
            for forbidden in self.forbidden_output_roots:
                if _inside(canonical, forbidden):
                    raise PathExternalNotAllowed(
                        "输出目录不得位于 Skill 安装目录或原始 GitHub Skill 内",
                        field=field,
                        details={"forbidden_root": forbidden},
                    )
        return ResolvedPathRecord(
            field=field,
            declared_path=declared,
            canonical_path=canonical,
            policy=selected.value,
            is_output=is_output,
            is_external=external,
            filesystem_accessed=False,
            runtime_boundary_verification_required=True,
        )

    def resolve_manifest(
        self,
        manifest: Mapping[str, Any],
        *,
        manifest_directory: str,
    ) -> ResolvedManifestPaths:
        path_config = manifest.get("paths") or {}
        policy = str(path_config.get("path_policy") or PathPolicy.PROJECT_RELATIVE.value)
        allow_external = bool(path_config.get("allow_external", False))
        allow_unc = bool(path_config.get("allow_unc", False))
        records: list[ResolvedPathRecord] = []
        source_paths: set[str] = set()

        documents = manifest.get("documents") or {}
        for category in ("reference_documents", "target_documents", "auxiliary_documents"):
            for index, document in enumerate(documents.get(category) or []):
                record = self.resolve_one(
                    str(document.get("path") or ""),
                    field=f"documents.{category}[{index}].path",
                    manifest_directory=manifest_directory,
                    policy=policy,
                    is_output=False,
                    readonly=bool(document.get("readonly", True)),
                    allow_external=allow_external,
                    allow_unc=allow_unc,
                )
                records.append(record)
                source_paths.add(_case(record.canonical_path))

        output = manifest.get("output") or {}
        for field in ("output_root", "artifact_root", "plan_output", "evidence_output", "report_output"):
            record = self.resolve_one(
                str(output.get(field) or ""),
                field=f"output.{field}",
                manifest_directory=manifest_directory,
                policy=policy,
                is_output=True,
                readonly=False,
                allow_external=allow_external,
                allow_unc=allow_unc,
            )
            if _case(record.canonical_path) in source_paths:
                raise PathSourceOutputCollision(
                    "source 与 output 解析为同一路径", field=f"output.{field}"
                )
            records.append(record)
        return ResolvedManifestPaths(tuple(records))

    @staticmethod
    def validate_runtime_boundary_observation(
        record: ResolvedPathRecord, *, crosses_symlink_or_junction: bool
    ) -> None:
        """消费外部安全层的边界观察；本解析器自身绝不探测文件系统。"""
        if crosses_symlink_or_junction:
            raise PathSymlinkBoundaryViolation(
                "运行时观察到符号链接或 junction 越界",
                field=record.field,
                details={"canonical_path": record.canonical_path},
            )
