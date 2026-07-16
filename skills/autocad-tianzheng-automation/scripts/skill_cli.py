from __future__ import annotations

import argparse
import json
import ntpath
import sys
from pathlib import Path
from typing import Any, Mapping

from config import (
    DefaultResolver,
    ManifestLoader,
    ManifestMigrator,
    ManifestPathResolver,
    canonical_hash,
)
from runtime.backend_registry import select_backend
from runtime.errors import (
    ConfigConflict,
    ManifestInvalid,
    PathExternalNotAllowed,
    SkillRuntimeError,
)
from runtime.execution_plan import (
    ExecutionPlanBuilder,
    execution_plan_hash,
    verify_execution_plan,
)
from runtime.file_guard import assert_offline_read_allowed
from runtime.planner import build_offline_plan
from runtime.product_profile import ProductRuntimeRouter
from runtime.routing import RuntimeRouter, select_product
from runtime.selector import select_runtime
from runtime.simulation import simulate_plan
from runtime.workflow_registry import WorkflowRegistry, select_workflow

ROOT = Path(__file__).resolve().parents[1]
INSTALL_ROOT = str(Path.home() / ".agents" / "skills" / "autocad-tianzheng-automation")
ORIGINAL_SKILL_ROOT = (
    r"C:\Users\REDACTED_USER\.agents\skills\autocad-dwg-redraw-skill-main"
    r"\autocad-dwg-redraw-skill-main\skills\autocad-dwg-redraw"
)
FORBIDDEN_OUTPUT_ROOTS = (INSTALL_ROOT, ORIGINAL_SKILL_ROOT)
TEMPLATE_FORBIDDEN_OUTPUT_ROOTS = (*FORBIDDEN_OUTPUT_ROOTS, str(ROOT))
CAD_EXTENSIONS = {".dwg", ".dxf"}


class SafeArgumentParser(argparse.ArgumentParser):
    """将参数错误转换为统一、可序列化的 CLI 错误。"""

    def error(self, message: str) -> None:
        raise ManifestInvalid(f"CLI 参数错误: {message}", field="arguments")


def _read_json(path: str | Path) -> dict[str, Any]:
    candidate = assert_offline_read_allowed(str(path))
    if candidate.suffix.lower() != ".json":
        raise ManifestInvalid("只允许读取 JSON 输入", field="path", source=str(candidate))
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestInvalid(
            f"JSON 读取或解析失败: {exc}", field="path", source=str(candidate)
        ) from exc
    if not isinstance(value, dict):
        raise ManifestInvalid("JSON 顶层必须是 object", field="path", source=str(candidate))
    return value


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _wants_json(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False) or getattr(args, "global_json", False))


def _success(result: Any, args: argparse.Namespace, *, legacy: bool = False) -> None:
    if legacy and not _wants_json(args):
        _print(result)
    else:
        _print({"ok": True, "result": result})


def _error_exit_code(exc: SkillRuntimeError) -> int:
    """兼容 WP2 registry 异常未声明 default_exit_code 的情况。"""
    code = str(getattr(exc, "code", ""))
    if code.startswith("MANIFEST_VERSION") or code == "MANIFEST_MIGRATION_FAILED":
        return 7
    if code.startswith("MANIFEST_") or code == "PLAN_HASH_MISMATCH":
        return 2
    if code.startswith("PATH_") or code == "REAL_CAD_ACCESS_FORBIDDEN":
        return 6
    if code.startswith("BACKEND_") or code in {
        "CONFIG_BACKEND_OVERRIDE_FORBIDDEN",
        "REAL_EXECUTION_NOT_AVAILABLE",
    }:
        return 4
    if code.startswith("APPROVAL_") or code in {
        "CONFIG_APPROVAL_INHERITANCE_FORBIDDEN",
        "CONFIG_PRIVILEGE_ESCALATION_BLOCKED",
        "PLAN_NOT_EXECUTABLE",
        "UNSAFE_OPERATION",
    }:
        return 5
    if code == "SAFE_BASELINE_INVALID":
        return 8
    if code.startswith(("CONFIG_", "RUNTIME_", "PRODUCT_", "WORKFLOW_")):
        return 3
    return int(getattr(exc, "exit_code", 9))


def _load_migration(path: str | Path) -> tuple[Path, dict[str, Any], Any, dict[str, Any]]:
    manifest_path = Path(path)
    loader = ManifestLoader()
    original = loader.load(manifest_path)
    loader.validate(original)
    migration = ManifestMigrator().preview(original)
    canonical = migration.manifest
    loader.validate(canonical)
    return manifest_path, original, migration, canonical


def _product_or_mode(manifest: Mapping[str, Any]) -> str:
    product_block = manifest.get("product") or {}
    product = str(
        product_block.get("profile")
        or product_block.get("requested_product")
        or "unknown"
    )
    if product != "unknown":
        return product
    return str((manifest.get("runtime") or {}).get("runtime_mode") or "offline_analysis")


def _resolve_pipeline(
    path: str | Path,
    *,
    run_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_path, original, migration, canonical = _load_migration(path)
    resolution = DefaultResolver().resolve(
        canonical,
        product_or_mode=_product_or_mode(canonical),
        workflow_defaults={},
        run_override=run_override,
    )
    resolved = resolution.value
    ManifestLoader().validate(resolved)
    directory = str(manifest_path.parent.absolute())
    paths = ManifestPathResolver(
        project_root=directory,
        workspace_root=directory,
        forbidden_output_roots=FORBIDDEN_OUTPUT_ROOTS,
    ).resolve_manifest(resolved, manifest_directory=directory)
    runtime = RuntimeRouter().select(resolved)
    product_runtime = ProductRuntimeRouter().select_from_manifest(resolved)
    product = select_product(resolved, runtime)
    backend = select_backend(resolved)
    workflow = select_workflow(
        resolved,
        runtime=runtime,
        product=product,
        backend=backend,
    )
    return {
        "manifest_path": manifest_path,
        "original": original,
        "migration": migration,
        "manifest": resolved,
        "resolution": resolution,
        "paths": paths,
        "runtime": runtime,
        "product_runtime": product_runtime,
        "product": product,
        "backend": backend,
        "workflow": workflow,
    }


def _build_plan(context: Mapping[str, Any]) -> dict[str, Any]:
    return ExecutionPlanBuilder().build(
        context["manifest"],
        runtime=context["runtime"],
        product=context["product"],
        backend=context["backend"],
        workflow=context["workflow"],
    )


def _validate_plan_schema(plan: Mapping[str, Any]) -> None:
    schema = _read_json(ROOT / "schemas" / "execution_plan.schema.json")
    try:
        import jsonschema

        jsonschema.validate(dict(plan), schema, format_checker=jsonschema.FormatChecker())
    except ImportError as exc:
        raise ManifestInvalid("需要 jsonschema 才能验证 Execution Plan") from exc
    except jsonschema.ValidationError as exc:
        field = ".".join(str(part) for part in exc.absolute_path) or None
        raise ManifestInvalid(
            f"Execution Plan Schema 校验失败: {exc.message}",
            field=field,
            details={"schema_path": list(exc.absolute_schema_path)},
        ) from exc


def _diff(left: Any, right: Any, path: str = "$") -> list[dict[str, Any]]:
    if type(left) is not type(right):
        return [{"path": path, "left": left, "right": right, "change": "type_changed"}]
    if isinstance(left, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}"
            if key not in left:
                changes.append({"path": child, "right": right[key], "change": "added"})
            elif key not in right:
                changes.append({"path": child, "left": left[key], "change": "removed"})
            else:
                changes.extend(_diff(left[key], right[key], child))
        return changes
    if isinstance(left, list):
        return [] if left == right else [
            {"path": path, "left": left, "right": right, "change": "list_changed"}
        ]
    return [] if left == right else [
        {"path": path, "left": left, "right": right, "change": "value_changed"}
    ]


def _manifest_command(args: argparse.Namespace) -> Any:
    if args.action == "diff":
        _, _, left_migration, left = _load_migration(args.left)
        _, _, right_migration, right = _load_migration(args.right)
        changes = _diff(left, right)
        return {
            "left": {"path": args.left, "version": left_migration.to_version, "hash": canonical_hash(left)},
            "right": {"path": args.right, "version": right_migration.to_version, "hash": canonical_hash(right)},
            "equal": not changes,
            "change_count": len(changes),
            "changes": changes,
        }

    manifest_path, _, migration, canonical = _load_migration(args.manifest)
    if args.action == "validate":
        return {
            "valid": True,
            "source_version": migration.from_version,
            "canonical_version": migration.to_version,
            "migration_required": migration.from_version != migration.to_version,
            "production_allowed": False,
            "production_d1_allowed": False,
        }
    if args.action == "normalize":
        return {"manifest": canonical, "canonical_hash": canonical_hash(canonical)}
    if args.action == "explain":
        context = _resolve_pipeline(manifest_path)
        return {
            "migration": context["migration"].as_dict(),
            "resolution": context["resolution"].as_dict(),
            "paths": context["paths"].as_dict(),
            "runtime": context["runtime"].to_dict(),
            "product_profile": context["product_runtime"].to_dict(),
            "product": context["product"].to_dict(),
            "backend": context["backend"].to_dict(),
            "workflow": context["workflow"].to_dict(),
            "filesystem_accessed_by_path_resolver": False,
        }
    if args.action == "migrate":
        result = migration.as_dict()
        if args.preview:
            result["written"] = False
            return result
        output = Path(args.output) if args.output else manifest_path.with_suffix(".migrated.json")
        if output.absolute() == manifest_path.absolute():
            raise ConfigConflict("迁移禁止原地覆盖 Manifest", field="output")
        if output.exists():
            raise ConfigConflict("迁移输出已存在；拒绝覆盖", field="output", source=str(output))
        if not output.parent.exists():
            raise ConfigConflict("迁移输出父目录不存在", field="output", source=str(output.parent))
        output.write_text(
            json.dumps(canonical, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result.update({"written": True, "output": str(output), "canonical_hash": canonical_hash(canonical)})
        return result
    raise ManifestInvalid(f"未知 manifest 操作: {args.action}")


def _template_output_directory(value: str) -> Path:
    """校验模板写出目录；这是 CLI 输出规则，不复用 Manifest 文档路径策略。"""
    declared = str(value or "").strip()
    if not declared:
        raise ManifestInvalid("模板输出目录不能为空", field="output")
    if "\x00" in declared:
        raise ManifestInvalid("模板输出路径包含 NUL", field="output")
    normalized_parts = declared.replace("\\", "/").split("/")
    if any(part == ".." for part in normalized_parts):
        raise ConfigConflict("模板输出路径不得包含 '..'", field="output")
    if declared.startswith(("\\\\", "//")):
        raise ConfigConflict("模板输出目录不得使用 UNC 路径", field="output")

    canonical = ntpath.normpath(
        declared if ntpath.isabs(declared) else ntpath.join(str(Path.cwd()), declared)
    )
    canonical_slash = canonical.replace("\\", "/")
    if ntpath.splitext(canonical)[1].lower() in CAD_EXTENSIONS:
        raise ConfigConflict("模板输出目录不得使用 CAD 扩展名", field="output")

    def is_inside(candidate: str, root: str) -> bool:
        try:
            return ntpath.commonpath(
                [candidate.casefold(), ntpath.normpath(root).casefold()]
            ) == ntpath.normpath(root).casefold()
        except ValueError:
            return False

    for forbidden in TEMPLATE_FORBIDDEN_OUTPUT_ROOTS:
        if is_inside(canonical, forbidden):
            raise PathExternalNotAllowed(
                "模板输出目录不得位于规范源、安装目录或原始 Skill 内",
                field="output",
                details={"forbidden_root": forbidden},
            )
    return Path(canonical_slash)


def _templates_command(args: argparse.Namespace) -> Any:
    catalog = _read_json(ROOT / "templates" / "template_catalog.json")
    if args.action == "list":
        return catalog
    entry = next(
        (item for item in catalog.get("templates", []) if item.get("template_id") == args.template_id),
        None,
    )
    if entry is None:
        raise ManifestInvalid(
            f"未知模板: {args.template_id}",
            field="template_id",
            details={"available": [item.get("template_id") for item in catalog.get("templates", [])]},
        )
    template = ManifestLoader().load_canonical(ROOT / "templates" / str(entry["path"]))
    output_dir = _template_output_directory(args.output)
    target = output_dir / "project_manifest.json"
    if target.exists():
        raise ConfigConflict("模板目标已存在；拒绝覆盖", field="output", source=str(target))
    output_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "template_id": args.template_id,
        "output": str(target),
        "canonical_hash": canonical_hash(template),
        "cad_connected": False,
        "documents_opened": 0,
    }


def _new_command(args: argparse.Namespace) -> Any:
    if args.group == "manifest":
        return _manifest_command(args)
    if args.group == "templates":
        return _templates_command(args)
    if args.group == "plan" and args.action in {"verify", "hash"}:
        plan = _read_json(args.plan)
        _validate_plan_schema(plan)
        return verify_execution_plan(plan) if args.action == "verify" else {
            "plan_hash": execution_plan_hash(plan),
            "stored_plan_hash": plan.get("plan_hash"),
        }

    run_override = None
    if args.group == "simulate":
        run_override = {
            "backend": {
                "preferred_backend": args.backend,
                "mock_allowed": args.backend == "nextgen_mock",
            }
        }
    context = _resolve_pipeline(args.manifest, run_override=run_override)
    if args.group == "config":
        return {
            "manifest": context["manifest"],
            "resolution": context["resolution"].as_dict(),
            "paths": context["paths"].as_dict(),
        }
    if args.group == "runtime":
        return context["runtime"].to_dict()
    if args.group == "product":
        result = context["product"].to_dict()
        result["product_profile"] = context["product_runtime"].to_dict()
        return result
    if args.group == "backend":
        return context["backend"].to_dict()
    if args.group == "workflow":
        return context["workflow"].to_dict()
    if args.group == "plan" and args.action == "build":
        return _build_plan(context)
    if args.group == "simulate":
        plan = _build_plan(context)
        return {"plan": plan, "simulation": simulate_plan(plan, backend=args.backend)}
    raise ManifestInvalid(f"未知命令组: {args.group}")


def _legacy_command(args: argparse.Namespace) -> Any:
    if args.command == "capabilities":
        mapping = {
            "plain_autocad": "generic_autocad.json",
            "tianzheng_water": "tianzheng_water.json",
            "tianzheng_hvac": "tianzheng_hvac.json",
        }
        return _read_json(ROOT / "capabilities" / mapping[args.mode])
    _, original, _, _ = _load_migration(args.manifest)
    if args.command == "inspect-manifest":
        return {"manifest": original, "cad_connected": False, "dwg_read": False}
    if args.command == "validate-manifest":
        return {"valid": True, "production_allowed": False}
    if args.command == "select-runtime":
        selection = select_runtime(original)
        return selection.__dict__ | {"mode": selection.mode.value}
    if args.command == "build-plan":
        return build_offline_plan(original)
    raise ManifestInvalid(f"未知兼容命令: {args.command}")


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="输出统一 JSON envelope")


def _leaf(parent: argparse._SubParsersAction, name: str, help_text: str) -> argparse.ArgumentParser:
    parser = parent.add_parser(name, help=help_text)
    _add_json(parser)
    return parser


def _manifest_leaf(parent: argparse._SubParsersAction, name: str) -> argparse.ArgumentParser:
    parser = _leaf(parent, name, f"Manifest {name}")
    parser.add_argument("manifest")
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(description="AutoCAD 与天正自动化 Skill 安全离线 CLI")
    parser.add_argument("--json", action="store_true", dest="global_json", help="输出统一 JSON envelope")
    sub = parser.add_subparsers(dest="command", required=True)

    manifest = sub.add_parser("manifest", help="Manifest 操作")
    manifest_sub = manifest.add_subparsers(dest="action", required=True)
    for name in ("validate", "normalize", "explain"):
        _manifest_leaf(manifest_sub, name)
    migrate = _manifest_leaf(manifest_sub, "migrate")
    migrate.add_argument("--to-version", default="1.1.0", choices=["1.1.0"])
    migrate.add_argument("--output")
    migrate.add_argument("--preview", action="store_true")
    diff = _leaf(manifest_sub, "diff", "比较两个 canonical Manifest")
    diff.add_argument("left")
    diff.add_argument("right")

    for group, action in (
        ("config", "resolve"),
        ("runtime", "select"),
        ("product", "select"),
        ("backend", "select"),
        ("workflow", "select"),
    ):
        group_parser = sub.add_parser(group)
        group_sub = group_parser.add_subparsers(dest="action", required=True)
        _manifest_leaf(group_sub, action)

    plan = sub.add_parser("plan", help="Execution Plan 操作")
    plan_sub = plan.add_subparsers(dest="action", required=True)
    _manifest_leaf(plan_sub, "build")
    for name in ("verify", "hash"):
        leaf = _leaf(plan_sub, name, f"Execution Plan {name}")
        leaf.add_argument("plan")

    simulate = _leaf(sub, "simulate", "纯离线或 NextGen Mock 模拟")
    simulate.set_defaults(group="simulate")
    simulate.add_argument("manifest")
    simulate.add_argument("--backend", choices=["offline", "nextgen_mock"], default="offline")

    templates = sub.add_parser("templates", help="模板操作")
    templates_sub = templates.add_subparsers(dest="action", required=True)
    _leaf(templates_sub, "list", "列出模板")
    create = _leaf(templates_sub, "create", "创建 canonical Manifest 模板")
    create.add_argument("template_id")
    create.add_argument("--output", required=True, help="显式模板输出目录（可为安全的外部临时目录）")

    for name in ("inspect-manifest", "validate-manifest", "select-runtime"):
        legacy = _leaf(sub, name, "兼容旧入口")
        legacy.add_argument("manifest")
        legacy.set_defaults(legacy=True)
    legacy_plan = _leaf(sub, "build-plan", "兼容旧离线计划入口")
    legacy_plan.add_argument("manifest")
    legacy_plan.add_argument("--dry-run", action="store_true", required=True)
    legacy_plan.set_defaults(legacy=True)
    caps = _leaf(sub, "capabilities", "兼容旧能力表入口")
    caps.add_argument(
        "--mode",
        required=True,
        choices=["plain_autocad", "tianzheng_water", "tianzheng_hvac"],
    )
    caps.set_defaults(legacy=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if getattr(args, "legacy", False):
            _success(_legacy_command(args), args, legacy=True)
        else:
            if not hasattr(args, "group"):
                args.group = args.command
            _success(_new_command(args), args)
        return 0
    except SkillRuntimeError as exc:
        _print(exc.to_error_payload())
        return _error_exit_code(exc)
    except Exception as exc:
        _print(
            {
                "ok": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "field": None,
                    "source": "skill_cli",
                    "details": {"type": type(exc).__name__},
                    "suggested_action": "检查离线配置与 CLI 参数；不要启用真实后端",
                },
            }
        )
        return 9


if __name__ == "__main__":
    sys.exit(main())
