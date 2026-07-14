from __future__ import annotations

import json
from pathlib import Path

from mcp.e2e.models import E2ERunResult, E2EScenario


def generate_e2e_report(
    scenario: E2EScenario,
    result: E2ERunResult,
    output_dir: str | None = None,
) -> dict:
    warnings: list[str] = []
    errors: list[str] = []
    root = Path(output_dir or "artifacts/e2e_reports")
    json_path = root / f"{result.run_id}.json"
    markdown_path = root / f"{result.run_id}.md"
    try:
        root.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps({"scenario": scenario.to_dict(), "result": result.to_dict()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        markdown_path.write_text(_markdown_report(scenario, result), encoding="utf-8")
    except Exception as exc:
        warnings.append(f"report write failed: {exc}")
    return {
        "status": "success" if not errors else "failed",
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "warnings": warnings,
        "errors": errors,
    }


def _markdown_report(scenario: E2EScenario, result: E2ERunResult) -> str:
    metrics = result.metrics or {}
    lines = [
        f"# Phase 14 E2E 验证报告 - {scenario.name}",
        "",
        "## 场景摘要",
        f"- Scenario ID: `{scenario.scenario_id}`",
        f"- Run ID: `{result.run_id}`",
        f"- Target DWG: `{scenario.target_dwg_path}`",
        f"- Status: `{result.status}`",
        "",
        "## 输入文件",
    ]
    for source in scenario.reference_sources:
        lines.append(f"- {source.get('type')}: `{source.get('path')}`")
    lines.extend(
        [
            "",
            "## Pipeline",
            f"- Stage: `{result.pipeline_result.get('stage')}`",
            f"- Status: `{result.pipeline_result.get('status')}`",
            "",
            "## 补图动作",
            f"- Auto actions: `{len(result.repair_plan_v2.get('actions', []))}`",
            f"- Review actions: `{len(result.repair_plan_v2.get('review_actions', []))}`",
            f"- Rejected actions: `{len(result.repair_plan_v2.get('rejected_actions', []))}`",
            "",
            "## 写回与重读验证",
            f"- Writeback: `{result.writeback_result.get('status')}`",
            f"- Reread: `{result.reread_verification.get('status')}`",
            "",
            "## 指标",
        ]
    )
    for key, value in metrics.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {warning}" for warning in result.warnings] or ["- 无"])
    lines.extend(["", "## Errors"])
    lines.extend([f"- {error}" for error in result.errors] or ["- 无"])
    return "\n".join(lines) + "\n"

