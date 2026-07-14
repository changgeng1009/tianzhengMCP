from __future__ import annotations

import json
from pathlib import Path

from mcp.acceptance.models import AcceptanceRunResult
from mcp.repair_actions.review_cleanup import cleanup_review_actions, write_review_previews


def generate_acceptance_report(
    result: AcceptanceRunResult,
    output_dir: str | None = None,
) -> dict:
    output = Path(output_dir or "artifacts/acceptance_reports")
    json_path = output / f"{result.run_id}.json"
    markdown_path = output / f"{result.run_id}.md"
    output.mkdir(parents=True, exist_ok=True)
    can_claim = _can_claim_real_success(result)
    cleanup = _attach_review_action_cleanup(result)
    payload = result.to_dict()
    payload["can_claim_real_success"] = can_claim
    payload["review_action_cleanup_summary"] = cleanup.get("summary", {})
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(result, can_claim), encoding="utf-8")
    return {
        "status": "success",
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "can_claim_real_success": can_claim,
        "review_action_cleanup_summary": cleanup.get("summary", {}),
        "warnings": [],
        "errors": [],
    }


def _can_claim_real_success(result: AcceptanceRunResult) -> bool:
    return (
        result.writeback_result.get("status") == "committed"
        and result.writeback_result.get("metadata", {}).get("mode") == "real"
        and result.reread_verification.get("status") == "verified"
    )


def _markdown(result: AcceptanceRunResult, can_claim: bool) -> str:
    schema = result.confirmed_schema_status or {}
    repair_plan = result.e2e_result.get("repair_plan_v2", {}) if result.e2e_result else {}
    writeback = result.writeback_result or {}
    reread = result.reread_verification or {}
    input_report = _input_graph_report(result)
    lines = [
        f"# Phase 15 首张真实图纸验收报告 - {result.run_id}",
        "",
        "## 结论",
    ]
    if can_claim:
        lines.append("- 可以声明真实补图成功。")
    elif not writeback:
        lines.append("- 本次未执行真实 CAD 写回。")
    else:
        lines.append("- 不能声明真实补图成功。")
    lines.extend(
        [
            "",
            "## Schema 状态",
            f"- Confirmed: `{schema.get('confirmed_object_types', [])}`",
            f"- Unconfirmed: `{schema.get('unconfirmed_object_types', [])}`",
            "",
            "## 写回状态",
            f"- Writeback status: `{writeback.get('status')}`",
            f"- Writeback mode: `{writeback.get('metadata', {}).get('mode')}`",
            f"- Created entities: `{len(writeback.get('created_entities', []))}`",
            "",
            "## Re-read Verification",
            f"- Status: `{reread.get('status')}`",
            "",
            "## Repair Actions",
            f"- Actions: `{len(repair_plan.get('actions', []))}`",
            f"- Review: `{len(repair_plan.get('review_actions', []))}`",
            f"- Rejected: `{len(repair_plan.get('rejected_actions', []))}`",
            "",
            "## review_action_cleanup_summary",
            f"- cleanup: `{json.dumps(result.e2e_result.get('review_action_cleanup', {}).get('summary', {}), ensure_ascii=False)}`",
            "",
            "## 输入图诊断",
            f"- input_readiness_status: `{input_report.get('input_readiness_status', '')}`",
            f"- target_graph_empty_reason: `{input_report.get('target_graph_empty_reason', '')}`",
            f"- reference_graph_empty_reason: `{input_report.get('reference_graph_empty_reason', '')}`",
            f"- target_graph_diagnostics: `{json.dumps(_compact_diagnostics(input_report.get('target_graph_diagnostics', {})), ensure_ascii=False)}`",
            f"- reference_graph_diagnostics: `{json.dumps(_compact_diagnostics(input_report.get('reference_graph_diagnostics', {})), ensure_ascii=False)}`",
            f"- scope_summary: `{json.dumps(input_report.get('scope_summary', {}), ensure_ascii=False)}`",
            f"- manual_anchor_summary: `{json.dumps(input_report.get('manual_anchor_summary', {}), ensure_ascii=False)}`",
            f"- pdf_line_candidate_summary: `{json.dumps(input_report.get('pdf_line_candidate_summary', {}), ensure_ascii=False)}`",
            f"- dwg_primitive_graph_summary: `{json.dumps(input_report.get('dwg_primitive_graph_summary', {}), ensure_ascii=False)}`",
            f"- readiness_status: `{input_report.get('readiness_status', '')}`",
            f"- review_only_repair_summary: `{json.dumps(input_report.get('review_only_repair_summary', {}), ensure_ascii=False)}`",
            "",
            "## Warnings",
        ]
    )
    lines.extend([f"- {warning}" for warning in result.warnings] or ["- 无"])
    lines.extend(["", "## Errors"])
    lines.extend([f"- {error}" for error in result.errors] or ["- 无"])
    return "\n".join(lines) + "\n"


def _input_graph_report(result: AcceptanceRunResult) -> dict:
    if not result.e2e_result:
        return {}
    pipeline_result = result.e2e_result.get("pipeline_result", {})
    report = pipeline_result.get("data", {}).get("report", {})
    return {
        "target_graph_diagnostics": report.get("target_graph_diagnostics", {}),
        "reference_graph_diagnostics": report.get("reference_graph_diagnostics", {}),
        "target_graph_empty_reason": report.get("target_graph_empty_reason", ""),
        "reference_graph_empty_reason": report.get("reference_graph_empty_reason", ""),
        "input_readiness_status": report.get("input_readiness_status", ""),
        "scope_summary": report.get("scope_summary", {}),
        "manual_anchor_summary": report.get("manual_anchor_summary", {}),
        "pdf_line_candidate_summary": report.get("pdf_line_candidate_summary", {}),
        "dwg_primitive_graph_summary": report.get("dwg_primitive_graph_summary", {}),
        "readiness_status": report.get("readiness_status", ""),
        "review_only_repair_summary": report.get("review_only_repair_summary", {}),
        "review_action_cleanup_summary": report.get("review_action_cleanup_summary", {}),
    }


def _compact_diagnostics(value: dict) -> dict:
    compact = dict(value or {})
    if "line_candidates" in compact:
        compact["line_candidates_sample_count"] = min(len(compact.get("line_candidates", [])), 5)
        compact["line_candidates_total"] = len(compact.get("line_candidates", []))
        compact.pop("line_candidates", None)
    return compact


def _attach_review_action_cleanup(result: AcceptanceRunResult) -> dict:
    if not result.e2e_result:
        return {"summary": _empty_cleanup_summary(), "filtered_actions": [], "merged_actions": [], "groups": []}
    repair_plan = result.e2e_result.get("repair_plan_v2", {}) or {}
    cleanup = cleanup_review_actions(repair_plan, _cleanup_options_from_result(result))
    preview_files = write_review_previews(cleanup, "artifacts/review_previews")
    cleanup["summary"]["preview_files"] = preview_files
    result.e2e_result["review_action_cleanup"] = cleanup
    pipeline_report = result.e2e_result.get("pipeline_result", {}).get("data", {}).get("report")
    if isinstance(pipeline_report, dict):
        pipeline_report["review_action_cleanup_summary"] = cleanup["summary"]
    return cleanup


def _cleanup_options_from_result(result: AcceptanceRunResult) -> dict:
    report = result.e2e_result.get("pipeline_result", {}).get("data", {}).get("report", {}) if result.e2e_result else {}
    scope_target = (report.get("scope_summary") or {}).get("target", {})
    options: dict = {}
    bbox = scope_target.get("target_bbox") or scope_target.get("bbox")
    if bbox:
        options["target_bbox"] = bbox
    return options


def _empty_cleanup_summary() -> dict:
    return {
        "input_review_actions": 0,
        "filtered_actions": 0,
        "merged_actions": 0,
        "groups": 0,
        "actions_with_dn": 0,
        "actions_without_dn": 0,
        "auto_executable_after_cleanup": 0,
        "preview_files": [],
    }
