from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid
from typing import Any

from mcp.backends.models import BackendConfig
from mcp.backends.registry import build_default_registry
from mcp.domains.registry import build_default_domain_registry


DEFAULT_DOMAIN = "water_supply_and_drainage"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="天正给排水识别与安全副本补绘 Skill CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("inspect", "diff", "plan", "qa", "run"):
        sub = subparsers.add_parser(command)
        _add_common_arguments(sub)

    backend_list = subparsers.add_parser("backend-list")
    backend_list.add_argument("--json", action="store_true")

    capabilities = subparsers.add_parser("backend-capabilities")
    capabilities.add_argument("--backend", required=True)

    doctor = subparsers.add_parser("backend-doctor")
    doctor.add_argument("--backend", default="mock")
    doctor.add_argument("--connect", action="store_true", help="未来显式连接开关；Stage 2 禁止使用")

    execute = subparsers.add_parser("execute-sandbox")
    _add_common_arguments(execute, working_copy_required=True)
    execute.add_argument("--execute", action="store_true", help="显式执行开关；Stage 2 配置仍会阻止真实连接")

    validate_fixture = subparsers.add_parser("validate-fixture")
    validate_fixture.add_argument("--report", default="reports/stage1_final_acceptance.json")

    stage4 = subparsers.add_parser("full-safe-pipeline")
    stage4.add_argument("--reference", required=True)
    stage4.add_argument("--target", required=True)
    stage4.add_argument("--mode", choices=["stage4-mvp"], required=True)
    stage4.add_argument("--execute-safe-ordinary", action="store_true")
    stage4.add_argument("--alignment-evidence", required=True)
    stage4.add_argument("--resume-run", default=None)
    return parser


def _add_common_arguments(parser: argparse.ArgumentParser, *, working_copy_required: bool = False) -> None:
    parser.add_argument("--backend", default=None)
    parser.add_argument("--config", default="skill/configs/default.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--source", default=None)
    parser.add_argument("--working-copy", default=None, required=working_copy_required)
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--run-id", default=None)


def run_cli(argv: list[str] | None = None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    if args.command == "full-safe-pipeline":
        from mcp.orchestration.stage4_mvp import run_stage4

        return run_stage4(
            Path(args.reference), Path(args.target),
            execute_safe_ordinary=bool(args.execute_safe_ordinary),
            resume_run_id=args.resume_run,
            alignment_evidence=Path(args.alignment_evidence),
        )
    registry = build_default_registry()

    if args.command == "backend-list":
        return {
            "backends": [
                {
                    "backend_id": backend.backend_id,
                    "available": backend.get_capabilities().available,
                    "contract_only": backend.backend_id in {"net_bridge", "tianzheng_api"},
                }
                for backend in registry.list()
            ],
            "autocad_connected": False,
        }
    if args.command == "backend-capabilities":
        return registry.get(args.backend).get_capabilities().to_dict()
    if args.command == "backend-doctor":
        if args.connect:
            raise SystemExit("Stage 2 禁止连接 AutoCAD；请在后续授权阶段启用真实连接。")
        return registry.get(args.backend).probe().to_dict()
    if args.command == "validate-fixture":
        report_path = Path(args.report)
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return {
            "validation_mode": data.get("validation_mode"),
            "status": data.get("status"),
            "real_sample_repair_completed": False,
            "production_d1_allowed": False,
            "autocad_connected": False,
        }

    config = load_config(args.config)
    if args.command == "execute-sandbox" and args.execute:
        raise SystemExit("Stage 2 execution is disabled by safety configuration; no backend connection attempted.")
    return build_dry_run_manifest(args, config, registry.ids())


def build_dry_run_manifest(args: argparse.Namespace, config: dict[str, Any], backend_ids: list[str]) -> dict[str, Any]:
    run_id = args.run_id or f"stage2-{uuid.uuid4().hex[:12]}"
    selected = args.backend or config.get("backend", {}).get("default_backend", "com")
    domains = build_default_domain_registry().status()
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": args.command,
        "mode": "dry_run",
        "professional_domain": DEFAULT_DOMAIN,
        "professional_domain_status": domains,
        "reference_inputs": list(args.reference or []),
        "source_dwg": args.source,
        "working_copy": args.working_copy,
        "backend": {
            "requested_backend": args.backend,
            "selected_backend": selected if selected in backend_ids else None,
            "fallback_used": False,
            "selection_reason": "dry-run configuration only; no backend connected",
        },
        "safety": stage2_safety_flags(),
        "real_sample_repair_completed": False,
        "production_d1_allowed": False,
        "status": "PARTIAL",
    }


def load_config(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml

            return dict(yaml.safe_load(text) or {})
        except ImportError as exc:
            raise RuntimeError("config is not JSON-compatible YAML and PyYAML is unavailable") from exc


def stage2_safety_flags() -> dict[str, bool]:
    return {
        "autocad_connected": False,
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "source_modified": False,
        "save_called_on_source": False,
        "sandbox_dwg_opened": False,
        "sandbox_saved": False,
        "opened_test_drawings_accessed": False,
        "opened_test_drawings_saved": False,
        "drawing_executed": False,
        "sendcommand_used": False,
        "tianzheng_command_executed": False,
        "dangerous_command_executed": False,
        "production_d1_allowed": False,
    }


def main() -> None:
    result = run_cli()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
