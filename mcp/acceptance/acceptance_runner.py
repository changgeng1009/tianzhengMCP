from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcp.acceptance.acceptance_report import generate_acceptance_report
from mcp.acceptance.models import AcceptanceRunConfig, AcceptanceRunResult
from mcp.acceptance.real_writeback_checklist import generate_real_writeback_checklist
from mcp.acceptance.schema_confirmation import (
    build_confirmed_schema_set,
    load_and_validate_manual_confirmation,
)
from mcp.e2e.dataset import E2EDatasetRegistry
from mcp.e2e.models import E2ERunConfig
from mcp.e2e.probe_loader import load_manual_probe_result
from mcp.e2e.scenario_runner import E2EScenarioRunner


class Phase15AcceptanceRunner:
    def run_acceptance(self, config: AcceptanceRunConfig) -> AcceptanceRunResult:
        warnings: list[str] = []
        errors: list[str] = []
        scenarios = E2EDatasetRegistry().load_scenarios_from_json(config.scenario_path)
        probe_result = load_manual_probe_result(config.probe_result_path) if config.probe_result_path else {"status": "skipped", "capabilities": []}
        manual_loaded = (
            load_and_validate_manual_confirmation(config.manual_confirmation_path)
            if config.manual_confirmation_path
            else {"status": "skipped", "manual_confirmation": {}, "warnings": [], "errors": []}
        )
        warnings.extend(probe_result.get("warnings", []))
        warnings.extend(manual_loaded.get("warnings", []))
        errors.extend(probe_result.get("errors", []))
        errors.extend(manual_loaded.get("errors", []))
        schema_set = build_confirmed_schema_set(
            probe_result,
            manual_loaded.get("manual_confirmation", {}),
        )
        checklist = generate_real_writeback_checklist(config, schema_set.to_dict())

        allow_writeback = (
            config.enable_real_writeback
            and not config.dry_run_only
            and (checklist["ready"] or not config.real_com_mode)
        )
        if not checklist["ready"] and config.real_com_mode:
            warnings.extend([f"real writeback gate blocked: {item}" for item in checklist["blocking_items"]])

        e2e_result = E2EScenarioRunner().run_scenario(
            scenarios[0],
            E2ERunConfig(
                run_id=config.run_id,
                scenario_id=scenarios[0].scenario_id,
                real_com_mode=config.real_com_mode if checklist["ready"] else False,
                dry_run_only=config.dry_run_only,
                sandbox_dir=config.sandbox_dir,
                enable_t30_writeback=allow_writeback,
                verification_mode=config.verification_mode,
            ),
        )
        warnings.extend(e2e_result.warnings)
        errors.extend(e2e_result.errors)
        result = AcceptanceRunResult(
            run_id=config.run_id,
            status="failed" if errors else ("warning" if warnings else "success"),
            confirmed_schema_status=schema_set.to_dict(),
            e2e_result=e2e_result.to_dict(),
            writeback_result=dict(e2e_result.writeback_result or {}),
            reread_verification=dict(e2e_result.reread_verification or {}),
            warnings=warnings,
            errors=errors,
            metadata={"checklist": checklist, "config": config.to_dict()},
        )
        report = generate_acceptance_report(result, config.output_dir)
        result.acceptance_report_path = report.get("markdown_path")
        return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 15 T30 real acceptance runner")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--probe-result", required=True)
    parser.add_argument("--manual-confirmation", required=True)
    parser.add_argument("--sandbox-dir", default="artifacts/acceptance_sandbox")
    parser.add_argument("--output-dir", default="artifacts/acceptance_reports")
    parser.add_argument("--enable-real-writeback", default="false", choices=["true", "false"])
    parser.add_argument("--real-com-mode", default="false", choices=["true", "false"])
    parser.add_argument("--dry-run-only", default="true", choices=["true", "false"])
    parser.add_argument("--verification-mode", default="manual_review", choices=["fake", "reread_dwg", "manual_review"])
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_arg_parser().parse_args(argv)
    config = AcceptanceRunConfig(
        scenario_path=args.scenario,
        probe_result_path=args.probe_result,
        manual_confirmation_path=args.manual_confirmation,
        sandbox_dir=args.sandbox_dir,
        output_dir=args.output_dir,
        enable_real_writeback=_bool(args.enable_real_writeback),
        real_com_mode=_bool(args.real_com_mode),
        dry_run_only=_bool(args.dry_run_only),
        verification_mode=args.verification_mode,
    )
    result = Phase15AcceptanceRunner().run_acceptance(config)
    payload = result.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def _bool(value: str) -> bool:
    return str(value).lower() == "true"


if __name__ == "__main__":
    main()
