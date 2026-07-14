from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcp.e2e.dataset import E2EDatasetRegistry
from mcp.e2e.models import E2ERunConfig
from mcp.e2e.probe_loader import load_manual_probe_result
from mcp.e2e.report import generate_e2e_report
from mcp.e2e.scenario_runner import E2EScenarioRunner
from mcp.e2e.schema_promoter import promote_probe_to_confirmed_schema


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 14 real drawing E2E validation runner")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--probe-result", default="")
    parser.add_argument("--manual-confirmation", default="")
    parser.add_argument("--sandbox-dir", default="artifacts/e2e_sandbox")
    parser.add_argument("--dry-run-only", default="true", choices=["true", "false"])
    parser.add_argument("--enable-real-writeback", default="false", choices=["true", "false"])
    parser.add_argument("--real-com-mode", default="false", choices=["true", "false"])
    parser.add_argument("--verification-mode", default="fake", choices=["fake", "reread_dwg", "manual_review"])
    parser.add_argument("--output-dir", default="artifacts/e2e_reports")
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_arg_parser().parse_args(argv)
    registry = E2EDatasetRegistry()
    scenarios = registry.load_scenarios_from_json(args.scenario)
    probe_result = load_manual_probe_result(args.probe_result) if args.probe_result else {"status": "skipped"}
    manual_confirmation = _load_json(args.manual_confirmation) if args.manual_confirmation else None
    schema_result = (
        promote_probe_to_confirmed_schema(probe_result, manual_confirmation)
        if probe_result.get("status") == "success"
        else {"status": "skipped", "schemas": [], "warnings": []}
    )
    results = []
    for scenario in scenarios:
        config = E2ERunConfig(
            scenario_id=scenario.scenario_id,
            real_com_mode=_bool_arg(args.real_com_mode),
            dry_run_only=_bool_arg(args.dry_run_only),
            sandbox_dir=args.sandbox_dir,
            enable_t30_writeback=_bool_arg(args.enable_real_writeback),
            verification_mode=args.verification_mode,
        )
        result = E2EScenarioRunner().run_scenario(scenario, config)
        report = generate_e2e_report(scenario, result, args.output_dir)
        result.report_path = report.get("markdown_path")
        results.append(result.to_dict())
    output = {"status": "success", "probe_result": probe_result, "schema_result": schema_result, "results": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


def _bool_arg(value: str) -> bool:
    return str(value).lower() == "true"


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

