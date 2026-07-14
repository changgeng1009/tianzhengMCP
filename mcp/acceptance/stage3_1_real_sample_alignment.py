from __future__ import annotations

import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from mcp.acceptance.stage3_1_runtime import (
    align_selected_regions,
    attach_existing_autocad,
    correspondence_summary,
    create_verified_copy,
    detect_pump_room_regions,
    detach_autocad,
    enumerate_live_documents,
    freeze_source,
    scan_working_copy,
    sha256_file,
    write_json,
)


PHASE = "STAGE3.1-REAL-SAMPLE-ALIGNMENT"
ROOT = Path(__file__).parents[2]
REPORT_JSON = ROOT / "reports" / "stage3_1_real_sample_alignment.json"
REPORT_MD = ROOT / "reports" / "stage3_1_real_sample_alignment.md"

REFERENCE_SOURCE_PATH = (
    ROOT / "artifacts" / "validation" / "s1_reference_fixture_20260710_134249.dwg"
)
TARGET_SOURCE_PATH = Path(r"E:\SampleDrawings\target_sample.dwg")
RUNS_ROOT = ROOT / "artifacts" / "stage3_1"


def amended_precondition_status(environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Stage 3.1 修订门：DeepSeek 闭环延期，但不再阻断只读样本验证。"""
    return {
        "stage2_previous_status": "PARTIAL",
        "stage2_closure_status": "PARTIAL_DEEPSEEK_DEFERRED",
        "deepseek_external_environment_reported_available": True,
        "deepseek_codex_subprocess_available": deepseek_available(environment),
        "deepseek_closure_deferred": True,
        "deepseek_call_succeeded": False,
        "deepseek_result_fabricated": False,
        "stage3_1_precondition_ready": True,
    }


def deepseek_available(environment: Mapping[str, str] | None = None) -> bool:
    """只判断环境变量是否存在，不返回或记录其内容。"""
    active_environment = os.environ if environment is None else environment
    return bool(active_environment.get("DEEPSEEK_API_KEY", "").strip())


def build_blocked_precondition_report(
    *,
    stage2_previous_status: str = "PARTIAL",
    tests: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """构造前置门阻断报告；不得在此函数中访问 DWG 或 AutoCAD。"""
    safety_flags = {
        "autocad_connected": False,
        "new_autocad_instance_created": False,
        "source_reference_opened": False,
        "source_target_opened": False,
        "source_reference_saved": False,
        "source_target_saved": False,
        "source_modified": False,
        "reference_copy_opened": False,
        "target_copy_opened": False,
        "reference_copy_saved": False,
        "target_copy_saved": False,
        "current_live_drawings_modified": False,
        "entities_created": False,
        "entities_modified": False,
        "entities_deleted": False,
        "copyobjects_used": False,
        "saveas_used": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "tdb_modified": False,
        "automatic_fallback_used": False,
        "real_sample_repair_completed": False,
        "production_d1_allowed": False,
    }
    return {
        "phase": PHASE,
        "run_id": None,
        "stage2_previous_status": stage2_previous_status,
        "stage2_closure_status": "PARTIAL",
        "deepseek_available": False,
        "deepseek_call_succeeded": False,
        "delegated_task_id": "ds_stage2_backend_architecture_static_review_final",
        "reference_source_path": str(REFERENCE_SOURCE_PATH),
        "target_source_path": str(TARGET_SOURCE_PATH),
        "reference_source_exists": None,
        "target_source_exists": None,
        "reference_source_sha256_before": None,
        "target_source_sha256_before": None,
        "reference_source_sha256_after": None,
        "target_source_sha256_after": None,
        "source_hashes_unchanged": None,
        "live_document_diverges_from_disk": None,
        "reference_copy_path": None,
        "target_copy_path": None,
        "copy_hashes_match_sources": None,
        "autocad_version": None,
        "tianzheng_water_detected": None,
        "source_documents_opened": False,
        "source_documents_saved": False,
        "copies_opened": False,
        "copies_saved": False,
        "reference_entity_count": None,
        "target_entity_count": None,
        "reference_tdb_count": None,
        "target_tdb_count": None,
        "reference_region_count": None,
        "target_region_count": None,
        "selected_reference_region": None,
        "selected_target_region": None,
        "correspondence_status": "NOT_EVALUATED_PRECONDITION",
        "alignment_type": "NOT_EVALUATED",
        "anchor_count": 0,
        "inlier_count": 0,
        "outlier_count": 0,
        "residual_statistics": None,
        "normalized_residual_statistics": None,
        "alignment_confidence": None,
        "alignment_status": "BLOCKED_PRECONDITION",
        "stage3_1_final_status": "BLOCKED_PRECONDITION",
        "stage3_2_allowed": False,
        "real_sample_repair_completed": False,
        "production_d1_allowed": False,
        "blocked_reason": (
            "DEEPSEEK_API_KEY is unavailable in the current Codex process; "
            "Stage 2 Closure cannot reach PASS."
        ),
        "not_evaluated_due_to_precondition": [
            "source filesystem baselines",
            "live AutoCAD document state",
            "safe copies",
            "entity scans",
            "pump-room region detection",
            "correspondence",
            "alignment",
        ],
        "safety_flags": safety_flags,
        "tests": dict(tests or {}),
    }


def write_report(report: Mapping[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(dict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT_MD.write_text(_render_markdown(report), encoding="utf-8")


def run_precondition_gate(
    *,
    environment: Mapping[str, str] | None = None,
    tests: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """兼容入口：修订后密钥传播问题不再阻断 Stage 3.1。"""
    result = amended_precondition_status(environment)
    result.update({"stage3_1_final_status": "PRECONDITION_READY", "report_written": False})
    if tests:
        result["tests"] = dict(tests)
    return result


def run_stage3_1(
    *,
    reference_source: Path = REFERENCE_SOURCE_PATH,
    target_source: Path = TARGET_SOURCE_PATH,
    environment: Mapping[str, str] | None = None,
    tests: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """执行真实样本冻结、只读副本扫描和泵房局部对齐。"""
    precondition = amended_precondition_status(environment)
    run_id = datetime.now().strftime("stage3_1_%Y%m%d_%H%M%S")
    run_root = RUNS_ROOT / run_id
    for name in ("copies", "scans", "regions", "alignment", "reports"):
        (run_root / name).mkdir(parents=True, exist_ok=True)
    safety = _safety_flags()
    report: dict[str, Any] = {
        "phase": PHASE,
        "run_id": run_id,
        **precondition,
        "deepseek_available": precondition["deepseek_codex_subprocess_available"],
        "delegated_task_id": "ds_stage2_backend_architecture_static_review_final",
        "reference_source_path": str(reference_source),
        "target_source_path": str(target_source),
        "reference_source_exists": False,
        "target_source_exists": False,
        "reference_source_sha256_before": None,
        "target_source_sha256_before": None,
        "reference_source_sha256_after": None,
        "target_source_sha256_after": None,
        "source_hashes_unchanged": False,
        "live_document_diverges_from_disk": None,
        "reference_copy_path": None,
        "target_copy_path": None,
        "copy_hashes_match_sources": False,
        "autocad_version": None,
        "tianzheng_water_detected": False,
        "source_documents_opened": False,
        "source_documents_saved": False,
        "copies_opened": False,
        "copies_saved": False,
        "reference_entity_count": None,
        "target_entity_count": None,
        "reference_tdb_count": None,
        "target_tdb_count": None,
        "reference_region_count": None,
        "target_region_count": None,
        "selected_reference_region": None,
        "selected_target_region": None,
        "correspondence_status": "NOT_EVALUATED",
        "alignment_type": "NOT_EVALUATED",
        "anchor_count": 0,
        "inlier_count": 0,
        "outlier_count": 0,
        "residual_statistics": None,
        "normalized_residual_statistics": None,
        "alignment_confidence": None,
        "alignment_status": "NOT_EVALUATED",
        "stage3_1_final_status": "FAIL",
        "stage3_2_allowed": False,
        "real_sample_repair_completed": False,
        "production_d1_allowed": False,
        "safety_flags": safety,
        "tests": dict(tests or {}),
        "errors": [],
    }
    acad = None
    try:
        reference_baseline = freeze_source(reference_source)
        target_baseline = freeze_source(target_source)
        report["reference_source_exists"] = True
        report["target_source_exists"] = True
        report["reference_source_sha256_before"] = reference_baseline["sha256"]
        report["target_source_sha256_before"] = target_baseline["sha256"]
        if Path(reference_baseline["absolute_path"]) == Path(target_baseline["absolute_path"]):
            raise ValueError("reference and target resolve to the same file")
        write_json(run_root / "input_manifest.json", {
            "run_id": run_id,
            "reference": reference_baseline,
            "target": target_baseline,
            "stage2_closure_status": precondition["stage2_closure_status"],
        })
        (run_root / "input_manifest.md").write_text(_manifest_markdown(run_id, reference_baseline, target_baseline), encoding="utf-8")

        try:
            acad = attach_existing_autocad()
            safety["autocad_connected"] = True
            report["autocad_version"] = str(getattr(acad, "Version", None) or getattr(acad, "Name", "unknown"))
        except Exception as exc:
            report["stage3_1_final_status"] = "BLOCKED_AUTOCAD_UNAVAILABLE"
            report["alignment_status"] = "BLOCKED_AUTOCAD_UNAVAILABLE"
            report["errors"].append(f"existing AutoCAD 25.1 instance unavailable: {type(exc).__name__}: {exc}")
            raise _ControlledStop()

        live_state = enumerate_live_documents(acad, (reference_source, target_source))
        report["live_document_diverges_from_disk"] = live_state["live_document_diverges_from_disk"]
        write_json(run_root / "source_integrity.json", {
            "reference_baseline": reference_baseline,
            "target_baseline": target_baseline,
            "live_document_state": live_state,
        })
        if live_state["live_document_diverges_from_disk"]:
            report["stage3_1_final_status"] = "BLOCKED_INPUT_STATE"
            report["alignment_status"] = "BLOCKED_INPUT_STATE"
            report["errors"].append("a source DWG is open in AutoCAD with unsaved changes")
            raise _ControlledStop()

        reference_copy = run_root / "copies" / "reference_working_copy.dwg"
        target_copy = run_root / "copies" / "target_analysis_sandbox.dwg"
        reference_copy_info = create_verified_copy(reference_source, reference_copy, reference_baseline["sha256"])
        target_copy_info = create_verified_copy(target_source, target_copy, target_baseline["sha256"])
        report["reference_copy_path"] = str(reference_copy)
        report["target_copy_path"] = str(target_copy)
        report["copy_hashes_match_sources"] = reference_copy_info["hash_matches"] and target_copy_info["hash_matches"]

        forbidden_sources = (reference_source, target_source)
        reference_scan = scan_working_copy(acad, reference_copy, "reference", forbidden_sources)
        safety["reference_copy_opened"] = True
        target_scan = scan_working_copy(acad, target_copy, "target", forbidden_sources)
        safety["target_copy_opened"] = True
        report["copies_opened"] = True
        report["reference_entity_count"] = reference_scan["entity_count"]
        report["target_entity_count"] = target_scan["entity_count"]
        report["reference_tdb_count"] = reference_scan["tdb_object_count"]
        report["target_tdb_count"] = target_scan["tdb_object_count"]
        report["tianzheng_water_detected"] = bool(reference_scan["tdb_object_count"] or target_scan["tdb_object_count"])
        write_json(run_root / "scans" / "reference_scan.json", reference_scan)
        write_json(run_root / "scans" / "target_scan.json", target_scan)
        write_json(run_root / "scans" / "object_type_comparison.json", _object_type_comparison(reference_scan, target_scan))
        (run_root / "scans" / "reference_scan_summary.md").write_text(_scan_markdown(reference_scan), encoding="utf-8")
        (run_root / "scans" / "target_scan_summary.md").write_text(_scan_markdown(target_scan), encoding="utf-8")

        reference_regions = detect_pump_room_regions(reference_scan)
        target_regions = detect_pump_room_regions(target_scan)
        report["reference_region_count"] = reference_regions["candidate_count"]
        report["target_region_count"] = target_regions["candidate_count"]
        report["selected_reference_region"] = reference_regions["selected_region"]
        report["selected_target_region"] = target_regions["selected_region"]
        write_json(run_root / "regions" / "reference_region_candidates.json", reference_regions)
        write_json(run_root / "regions" / "target_region_candidates.json", target_regions)
        write_json(run_root / "regions" / "selected_regions.json", {
            "reference": reference_regions["selected_region"],
            "target": target_regions["selected_region"],
        })
        (run_root / "regions" / "region_selection_report.md").write_text(
            _region_markdown(reference_regions, target_regions), encoding="utf-8"
        )

        alignment = align_selected_regions(
            reference_scan, target_scan,
            reference_regions["selected_region"], target_regions["selected_region"],
        )
        correspondence = correspondence_summary(reference_scan, target_scan, reference_regions, target_regions, alignment)
        report.update({
            "correspondence_status": correspondence["correspondence_status"],
            "same_project_likelihood": correspondence["same_project_likelihood"],
            "same_detail_region_likelihood": correspondence["same_detail_region_likelihood"],
            "reference_more_complete": correspondence["reference_more_complete"],
            "target_incomplete_evidence": correspondence["target_incomplete_evidence"],
            "correspondence_blockers": correspondence["correspondence_blockers"],
            "alignment_type": alignment["alignment_type"],
            "anchor_count": alignment["anchor_count"],
            "inlier_count": alignment["inlier_count"],
            "outlier_count": alignment["outlier_count"],
            "residual_statistics": alignment["residual_statistics"],
            "normalized_residual_statistics": alignment["normalized_residual_statistics"],
            "alignment_confidence": alignment["alignment_confidence"],
            "alignment_status": alignment["alignment_status"],
        })
        write_json(run_root / "alignment" / "anchor_candidates.json", {"anchors": alignment["anchor_candidates"]})
        write_json(run_root / "alignment" / "matched_anchors.json", {"anchors": alignment["matched_anchors"]})
        write_json(run_root / "alignment" / "transform_candidates.json", {"transforms": alignment["transform_candidates"]})
        write_json(run_root / "alignment" / "selected_transform.json", {
            "selected_transform": alignment["selected_transform"],
            "alignment_status": alignment["alignment_status"],
        })
        (run_root / "alignment" / "alignment_report.md").write_text(_alignment_markdown(alignment, correspondence), encoding="utf-8")

        if alignment["alignment_status"].startswith("PASS_") and correspondence["correspondence_status"] == "CONFIRMED":
            report["stage3_1_final_status"] = alignment["alignment_status"]
        else:
            report["stage3_1_final_status"] = alignment["alignment_status"]
    except _ControlledStop:
        pass
    except Exception as exc:
        report["stage3_1_final_status"] = "FAIL"
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["traceback"] = traceback.format_exc()
    finally:
        if acad is not None:
            detach_autocad()
        if report["reference_source_exists"]:
            report["reference_source_sha256_after"] = sha256_file(reference_source)
        if report["target_source_exists"]:
            report["target_source_sha256_after"] = sha256_file(target_source)
        report["source_hashes_unchanged"] = bool(
            report["reference_source_sha256_before"]
            and report["target_source_sha256_before"]
            and report["reference_source_sha256_before"] == report["reference_source_sha256_after"]
            and report["target_source_sha256_before"] == report["target_source_sha256_after"]
        )
        if report["reference_copy_path"] and Path(report["reference_copy_path"]).exists():
            safety["reference_copy_saved"] = False
        if report["target_copy_path"] and Path(report["target_copy_path"]).exists():
            safety["target_copy_saved"] = False
        report["copies_saved"] = False
        report["stage3_2_allowed"] = False
        report["production_d1_allowed"] = False
        report["real_sample_repair_completed"] = False
        write_json(run_root / "stage3_1_manifest.json", _manifest_from_report(report))
        write_report(report)
    return report


def _render_markdown(report: Mapping[str, Any]) -> str:
    if report.get("run_id"):
        return _render_runtime_markdown(report)
    safety = report["safety_flags"]
    lines = [
        "# Stage 3.1 — Real Sample Freeze, Read-Only Scan and Local Alignment",
        "",
        "## 结论",
        "",
        "- Stage 2 Closure: PARTIAL",
        "- Stage 3.1: BLOCKED_PRECONDITION",
        "- deepseek_available: false",
        "- deepseek_call_succeeded: false",
        "- stage3_2_allowed: false",
        "",
        "当前 Codex 进程没有可用的 `DEEPSEEK_API_KEY`。按前置门规则，本轮未连接 AutoCAD，"
        "未访问两个源 DWG，未创建副本，未执行扫描、区域识别或对齐。",
        "",
        "## 输入（未访问）",
        "",
        f"- reference: `{report['reference_source_path']}`",
        f"- target: `{report['target_source_path']}`",
        "- exists/hash: 未评估（前置门阻断）",
        "",
        "## 安全标志",
        "",
    ]
    lines.extend(f"- {name}={str(value).lower()}" for name, value in safety.items())
    lines.extend(
        [
            "",
            "## 后续条件",
            "",
            "在启动 Codex 的同一进程环境中提供 `DEEPSEEK_API_KEY` 后，重新执行 Stage 2 Closure。"
            "不得在聊天、代码、日志或报告中粘贴或记录密钥。",
            "",
        ]
    )
    return "\n".join(lines)


class _ControlledStop(Exception):
    pass


def _safety_flags() -> dict[str, bool]:
    return {
        "autocad_connected": False,
        "new_autocad_instance_created": False,
        "source_reference_opened": False,
        "source_target_opened": False,
        "source_reference_saved": False,
        "source_target_saved": False,
        "source_modified": False,
        "reference_copy_opened": False,
        "target_copy_opened": False,
        "reference_copy_saved": False,
        "target_copy_saved": False,
        "current_live_drawings_modified": False,
        "entities_created": False,
        "entities_modified": False,
        "entities_deleted": False,
        "copyobjects_used": False,
        "saveas_used": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "tdb_modified": False,
        "automatic_fallback_used": False,
        "real_sample_repair_completed": False,
        "production_d1_allowed": False,
    }


def _manifest_markdown(run_id: str, reference: Mapping[str, Any], target: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Stage 3.1 输入冻结清单", "", f"- run_id: `{run_id}`",
        f"- reference: `{reference['absolute_path']}`", f"- reference SHA256: `{reference['sha256']}`",
        f"- target: `{target['absolute_path']}`", f"- target SHA256: `{target['sha256']}`", "",
    ])


def _object_type_comparison(reference: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
    keys = sorted(set(reference["object_type_counts"]) | set(target["object_type_counts"]))
    return {
        "schema_version": "stage3.1-object-comparison-v1",
        "types": [
            {
                "object_name": key,
                "reference_count": reference["object_type_counts"].get(key, 0),
                "target_count": target["object_type_counts"].get(key, 0),
            }
            for key in keys
        ],
    }


def _scan_markdown(scan: Mapping[str, Any]) -> str:
    return "\n".join([
        f"# {scan['document_role']} 只读扫描摘要", "",
        f"- entity_count: {scan['entity_count']}",
        f"- tdb_object_count: {scan['tdb_object_count']}",
        f"- copy_hash_unchanged: {str(scan['copy_hash_unchanged']).lower()}",
        f"- copy_saved: false", "",
        "## TDb 对象类型", "",
        *[f"- {name}: {count}" for name, count in scan["tdb_object_types"].items()], "",
    ])


def _region_markdown(reference: Mapping[str, Any], target: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Stage 3.1 泵房区域选择", "",
        f"- reference candidates: {reference['candidate_count']}",
        f"- reference pump room identified: {str(reference['pump_room_identified']).lower()}",
        f"- target candidates: {target['candidate_count']}",
        f"- target pump room identified: {str(target['pump_room_identified']).lower()}",
        "- whole drawing extents used: false", "",
    ])


def _alignment_markdown(alignment: Mapping[str, Any], correspondence: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Stage 3.1 泵房局部对齐", "",
        f"- correspondence_status: {correspondence['correspondence_status']}",
        f"- alignment_status: {alignment['alignment_status']}",
        f"- alignment_type: {alignment['alignment_type']}",
        f"- anchor_count: {alignment['anchor_count']}",
        f"- inlier_count: {alignment['inlier_count']}",
        f"- alignment_confidence: {alignment['alignment_confidence']}",
        f"- residual_statistics: `{json.dumps(alignment['residual_statistics'], ensure_ascii=False)}`", "",
    ])


def _manifest_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": report["phase"],
        "run_id": report["run_id"],
        "stage2_closure_status": report["stage2_closure_status"],
        "reference_source_path": report["reference_source_path"],
        "target_source_path": report["target_source_path"],
        "reference_source_sha256": report["reference_source_sha256_before"],
        "target_source_sha256": report["target_source_sha256_before"],
        "reference_copy_path": report["reference_copy_path"],
        "target_copy_path": report["target_copy_path"],
        "stage3_1_final_status": report["stage3_1_final_status"],
        "stage3_2_allowed": False,
        "safety_flags": report["safety_flags"],
    }


def _render_runtime_markdown(report: Mapping[str, Any]) -> str:
    safety = report["safety_flags"]
    lines = [
        "# Stage 3.1 — 真实样本冻结、只读扫描与泵房局部对齐", "",
        "## 前置规则修订", "",
        f"- Stage 2 Closure: {report['stage2_closure_status']}",
        f"- deepseek_external_environment_reported_available: {str(report['deepseek_external_environment_reported_available']).lower()}",
        f"- deepseek_codex_subprocess_available: {str(report['deepseek_codex_subprocess_available']).lower()}",
        "- deepseek_closure_deferred: true",
        "- deepseek_call_succeeded: false",
        "- deepseek_result_fabricated: false", "",
        "## 结果", "",
        f"- run_id: `{report['run_id']}`",
        f"- Stage 3.1: {report['stage3_1_final_status']}",
        f"- reference SHA256: `{report['reference_source_sha256_before']}`",
        f"- target SHA256: `{report['target_source_sha256_before']}`",
        f"- source_hashes_unchanged: {str(report['source_hashes_unchanged']).lower()}",
        f"- live_document_diverges_from_disk: {str(report['live_document_diverges_from_disk']).lower()}",
        f"- reference entity/TDb: {report['reference_entity_count']} / {report['reference_tdb_count']}",
        f"- target entity/TDb: {report['target_entity_count']} / {report['target_tdb_count']}",
        f"- correspondence_status: {report['correspondence_status']}",
        f"- alignment_status: {report['alignment_status']}",
        f"- alignment_type: {report['alignment_type']}",
        f"- anchors/inliers: {report['anchor_count']} / {report['inlier_count']}",
        f"- residual_statistics: `{json.dumps(report['residual_statistics'], ensure_ascii=False)}`",
        f"- normalized_residual_statistics: `{json.dumps(report['normalized_residual_statistics'], ensure_ascii=False)}`",
        f"- inlier_residual_statistics: `{json.dumps(report.get('inlier_residual_statistics'), ensure_ascii=False)}`",
        f"- inlier_normalized_residual_statistics: `{json.dumps(report.get('inlier_normalized_residual_statistics'), ensure_ascii=False)}`",
        f"- alignment_confidence: {report['alignment_confidence']}",
        f"- stage3_2_allowed: false", "",
        "## 安全标志", "",
    ]
    lines.extend(f"- {name}={str(value).lower()}" for name, value in safety.items())
    if report.get("errors"):
        lines.extend(["", "## 错误", "", *[f"- {error}" for error in report["errors"]]])
    lines.append("")
    return "\n".join(lines)
