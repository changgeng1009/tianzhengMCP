from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from runtime.errors import SkillRuntimeError
from runtime.file_guard import assert_offline_read_allowed
from runtime.planner import build_offline_plan
from runtime.selector import select_runtime

ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: str) -> dict[str, Any]:
    candidate = assert_offline_read_allowed(path)
    return json.loads(candidate.read_text(encoding="utf-8"))


def _validate(manifest: dict[str, Any]) -> None:
    schema = json.loads((ROOT / "schemas" / "project_manifest.schema.json").read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("需要安装 jsonschema 才能执行完整 Schema 校验") from exc
    jsonschema.validate(manifest, schema, format_checker=jsonschema.FormatChecker())


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AutoCAD 与天正自动化 Skill 离线入口")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect-manifest", "validate-manifest", "select-runtime"):
        p = sub.add_parser(name)
        p.add_argument("manifest")
    plan = sub.add_parser("build-plan")
    plan.add_argument("manifest")
    plan.add_argument("--dry-run", action="store_true", required=True)
    caps = sub.add_parser("capabilities")
    caps.add_argument("--mode", required=True, choices=["plain_autocad", "tianzheng_water", "tianzheng_hvac"])
    args = parser.parse_args(argv)
    try:
        if args.command == "capabilities":
            mapping = {
                "plain_autocad": "generic_autocad.json",
                "tianzheng_water": "tianzheng_water.json",
                "tianzheng_hvac": "tianzheng_hvac.json",
            }
            _print(_read_json(str(ROOT / "capabilities" / mapping[args.mode])))
            return 0
        manifest = _read_json(args.manifest)
        if args.command == "inspect-manifest":
            _print({"manifest": manifest, "cad_connected": False, "dwg_read": False})
        elif args.command == "validate-manifest":
            _validate(manifest)
            _print({"valid": True, "production_allowed": False})
        elif args.command == "select-runtime":
            selection = select_runtime(manifest)
            _print(selection.__dict__ | {"mode": selection.mode.value})
        elif args.command == "build-plan":
            _validate(manifest)
            _print(build_offline_plan(manifest))
        return 0
    except SkillRuntimeError as exc:
        _print({"status": "STOPPED", "error_code": exc.code, "message": str(exc)})
        return 2
    except Exception as exc:
        _print({"status": "ERROR", "error_code": type(exc).__name__, "message": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
