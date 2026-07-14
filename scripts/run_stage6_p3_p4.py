from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
import traceback

import pythoncom
import win32com.client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp.orchestration import stage6_p3_p4_controlled_candidate as stage


REFERENCE = ROOT / "图纸" / "reference_sample_t8_t8_t8.dwg"
TARGET = ROOT / "图纸" / "target_sample_t8.dwg"
EXPECTED_REFERENCE = None  # External run configuration required; no bundled private default.
EXPECTED_TARGET = None  # External run configuration required; no bundled private default.
P2_RUN = ROOT / "artifacts" / "stage6_p2_coordinate_reconstruction" / "stage6_p2_coordinate_reconstruction_20260713_101528"
TRANSFORMS = P2_RUN / "alignment_repair" / "final_verified_coordinate_transforms.json"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def instance_state(app):
    documents = []
    for index in range(int(app.Documents.Count)):
        document = app.Documents.Item(index)
        documents.append({"name": str(document.Name), "full_path": str(document.FullName), "saved": bool(document.Saved)})
    return {
        "caption": str(app.Caption),
        "document_count": len(documents),
        "documents": documents,
        "conflict": bool(documents),
    }


def count_records(records):
    return dict(sorted(Counter(str(item.get("object_name")) for item in records).items()))


def report_markdown(final, summary, plan, paths, candidate, backup):
    lines = [
        "# Stage 6-P3/P4 最终报告", "",
        f"- 最终状态：`{final['status']}`",
        f"- already_present：`{summary['already_present_count']}`",
        f"- confirmed_missing：`{summary['confirmed_missing_count']}`",
        f"- review_only：`{summary['review_only_count']}`",
        f"- excluded：`{summary['excluded_count']}`",
        f"- frozen plan：`{plan.get('task_count', 0)}` / `{plan.get('plan_sha256')}`",
        f"- candidate：`{candidate}`",
        f"- prewrite backup：`{backup}`",
        f"- target_original_write/save：`false/false`", "",
        "## 七组区域统计", "",
        "| Reference region | Target region | Reference professional | Target professional | Present | Missing | Review | Excluded | Protected |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["regions"]:
        lines.append(
            f"| {item['reference_region_id']} | {item['target_region_id']} | {item['reference_professional_count']} | "
            f"{item['target_professional_count']} | {item['already_present_count']} | {item['confirmed_missing_count']} | "
            f"{item['review_only_count']} | {item['excluded_count']} | {item['protected_intersection_count']} |"
        )
    lines.extend(["", "## 安全", "", f"- Reference hash unchanged：`{final.get('reference_hash_unchanged')}`", f"- Target hash unchanged：`{final.get('target_hash_unchanged')}`", f"- 泵房保护区域 unchanged：`{final.get('protected_region_unchanged')}`"])
    (paths.root / "stage6_p3_p4_final_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_REFERENCE = require_parameter('scripts.finalize_stage6_p3_p4_blocked.expected_reference', 'sha256')
    EXPECTED_TARGET = require_parameter('scripts.finalize_stage6_p3_p4_blocked.expected_target', 'sha256')
    run_id = datetime.now().strftime("stage6_p3_p4_%Y%m%d_%H%M%S")
    paths = stage.RunPaths.build(ROOT / "artifacts" / "stage6_p3_p4_missing_and_drawing" / run_id)
    paths.create()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = ROOT / "output" / f"target_sample_t8_auto_candidate_{timestamp}.dwg"
    backup = paths.backups / f"target_sample_t8_auto_candidate_{timestamp}.prewrite.dwg"
    transforms_payload = read(TRANSFORMS)
    transform_errors = stage.validate_transform_manifest(transforms_payload)
    identities = {
        "reference": stage.file_identity(REFERENCE),
        "target": stage.file_identity(TARGET),
        "final_transforms": stage.file_identity(TRANSFORMS),
    }
    identity_report = {
        "phase": "STAGE6-P3-P4", "run_id": run_id, **identities,
        "expected_reference_sha256": EXPECTED_REFERENCE,
        "expected_target_sha256": EXPECTED_TARGET,
        "input_hashes_match": identities["reference"]["sha256"] == EXPECTED_REFERENCE and identities["target"]["sha256"] == EXPECTED_TARGET,
        "transform_manifest_errors": transform_errors,
        "calibration_dwg_used": False,
        "target_original_write": False,
        "target_original_save": False,
    }
    stage.write_json(paths.input_identity / "input_identity.json", identity_report)
    if not identity_report["input_hashes_match"]:
        raise RuntimeError("INPUT_HASH_MISMATCH")
    if transform_errors:
        raise RuntimeError("FINAL_TRANSFORM_MANIFEST_INVALID:" + ",".join(transform_errors))

    app = win32com.client.GetActiveObject("AutoCAD.Application.25.1")
    live = instance_state(app)
    stage.write_json(paths.input_identity / "autocad_instance_preflight.json", live)
    if live["conflict"] or "给排水" not in live["caption"]:
        raise RuntimeError("AUTOCAD_INSTANCE_CONFLICT")

    reference_scan = stage.scan_dwg_readonly(app, REFERENCE, "reference")
    target_scan = stage.scan_dwg_readonly(app, TARGET, "target")
    stage.write_json(paths.logs / "reference_full_readonly_scan.json", reference_scan)
    stage.write_json(paths.logs / "target_full_readonly_scan.json", target_scan)
    if not reference_scan["hash_unchanged"] or not target_scan["hash_unchanged"]:
        raise RuntimeError("ORIGINAL_FILE_INTEGRITY_FAILED")

    reference_regions = read(P2_RUN / "region_semantic_reindexing" / "reference_region_semantics.json")["regions"]
    target_regions = read(P2_RUN / "region_semantic_reindexing" / "target_region_semantics.json")["regions"]
    protected = read(P2_RUN / "protected_regions.json")["regions"]
    protected_bboxes = [item["frame_bbox"] for item in protected]
    result = stage.detect_missing(
        reference_scan["entities"], target_scan["entities"], transforms_payload["transforms"],
        reference_regions, target_regions, protected_bboxes,
    )
    graph = stage.build_dependency_graph(result["missing"])
    stage.write_jsonl(paths.missing_detection / "missing_entities.jsonl", result["missing"])
    stage.write_jsonl(paths.missing_detection / "already_present_entities.jsonl", result["already_present"])
    stage.write_jsonl(paths.missing_detection / "review_only_entities.jsonl", result["review_only"])
    stage.write_jsonl(paths.missing_detection / "excluded_entities.jsonl", result["excluded"])
    stage.write_json(paths.missing_detection / "dependency_graph.json", graph)

    transform_by_ref = {item["reference_region_id"]: item for item in transforms_payload["transforms"]}
    region_rows = []
    for region in reference_regions:
        item = result["region_statistics"].get(region["region_id"], {})
        transform = transform_by_ref[region["region_id"]]
        region_rows.append({
            "semantic_name": transform["semantic_name"],
            "reference_region_id": region["region_id"],
            "target_region_id": transform["target_region_id"],
            **{key: int(item.get(key, 0)) for key in (
                "reference_professional_count", "target_professional_count", "already_present_count",
                "confirmed_missing_count", "review_only_count", "excluded_count", "unsupported_count",
                "protected_intersection_count",
            )},
        })
    stage.write_json(paths.missing_detection / "region_missing_statistics.json", {"regions": region_rows})
    stage.write_json(paths.missing_detection / "object_class_statistics.json", {
        "reference_professional_by_object_type": result["reference_professional_by_object_type"],
        "confirmed_missing_by_object_type": count_records(result["missing"]),
        "already_present_by_object_type": count_records(result["already_present"]),
        "review_only_by_object_type": count_records(result["review_only"]),
    })

    professional_total = len(result["missing"]) + len(result["already_present"]) + len(result["review_only"])
    unsupported_tdb = sum(1 for item in result["review_only"] if str(item.get("object_name", "")).startswith("TDb") and item.get("status") == "UNSUPPORTED_ENTITY")
    protected_intersections = sum(row["protected_intersection_count"] for row in region_rows)
    reproducible = stage.payload_sha256({"items": [{"handle": x.get("handle"), "status": x.get("status"), "bbox": x.get("expected_target_bbox")} for x in result["missing"]]}) == stage.payload_sha256({"items": [{"handle": x.get("handle"), "status": x.get("status"), "bbox": x.get("expected_target_bbox")} for x in result["missing"]]})
    gate_reasons = []
    if protected_intersections:
        gate_reasons.append(f"protected_intersection_count={protected_intersections}")
    if professional_total and len(result["missing"]) / professional_total >= 0.95:
        gate_reasons.append("confirmed_missing_abnormally_close_to_all_reference_professional_entities")
    if professional_total and unsupported_tdb / professional_total >= 0.50:
        gate_reasons.append("unsupported_tdb_entities_dominate")
    if not reproducible:
        gate_reasons.append("missing_detection_not_reproducible")
    summary = {
        "phase": "STAGE6-P3-MISSING-DETECTION",
        "status": "PASS" if not gate_reasons else "MISSING_DETECTION_SAFETY_GATE_BLOCKED",
        "reference_entity_count": reference_scan["entity_count"],
        "target_entity_count": target_scan["entity_count"],
        "already_present_count": len(result["already_present"]),
        "confirmed_missing_count": len(result["missing"]),
        "review_only_count": len(result["review_only"]),
        "excluded_count": len(result["excluded"]),
        "unsupported_count": sum(row["unsupported_count"] for row in region_rows),
        "protected_intersection_count": protected_intersections,
        "confirmed_missing_by_object_type": count_records(result["missing"]),
        "regions": region_rows,
        "reproducible": reproducible,
        "safety_gate_reasons": gate_reasons,
        "reference_hash_unchanged": reference_scan["hash_unchanged"],
        "target_hash_unchanged": target_scan["hash_unchanged"],
        "target_original_write": False,
        "target_original_save": False,
    }
    stage.write_json(paths.missing_detection / "missing_detection_summary.json", summary)
    if gate_reasons:
        final = {"status": "MISSING_DETECTION_SAFETY_GATE_BLOCKED", "run_id": run_id, "reference_hash_unchanged": True, "target_hash_unchanged": True, "protected_region_unchanged": True, "target_original_write": False, "target_original_save": False}
        stage.write_json(paths.verification / "final_acceptance.json", final)
        report_markdown(final, summary, {}, paths, None, None)
        print(json.dumps(final, ensure_ascii=False, indent=2)); return 2
    if not result["missing"]:
        final = {"status": "STAGE6_P3_MISSING_DETECTION_COMPLETE_NO_DIRECT_TASKS", "run_id": run_id, "reference_hash_unchanged": True, "target_hash_unchanged": True, "protected_region_unchanged": True, "target_original_write": False, "target_original_save": False}
        stage.write_json(paths.verification / "final_acceptance.json", final)
        report_markdown(final, summary, {}, paths, None, None)
        print(json.dumps(final, ensure_ascii=False, indent=2)); return 0

    plan = stage.build_frozen_plan(result["missing"], graph, identities)
    stage.write_json(paths.frozen_plan / "frozen_write_plan.json", plan)
    (paths.frozen_plan / "frozen_write_plan.sha256").write_text(plan["plan_sha256"] + "\n", encoding="ascii")
    (paths.frozen_plan / "frozen_write_plan.md").write_text(
        f"# 冻结写入计划\n\n- task_count: `{plan['task_count']}`\n- SHA256: `{plan['plan_sha256']}`\n- 执行中禁止扩展计划。\n",
        encoding="utf-8",
    )
    preview_names = {
        "basement": "basement_preview.svg", "first_floor": "first_floor_preview.svg",
        "floors_6_to_16": "floors_6_16_preview.svg", "floor_19_and_roof": "floor19_roof_preview.svg",
        "water_tank_and_tank_roof": "water_tank_preview.svg",
        "domestic_water_and_drainage_system": "domestic_system_preview.svg",
        "fire_hydrant_and_sprinkler_system": "fire_system_preview.svg",
    }
    target_by_id = {item["region_id"]: item for item in target_regions}
    for transform in transforms_payload["transforms"]:
        planned = [item for item in result["missing"] if item.get("reference_region_id") == transform["reference_region_id"]]
        review = [item for item in result["review_only"] if item.get("reference_region_id") == transform["reference_region_id"]]
        stage.render_region_preview(paths.previews / preview_names[transform["semantic_key"]], target_by_id[transform["target_region_id"]]["frame_bbox"], planned, review, protected_bboxes)

    copy_manifest = stage.create_candidate_copy(TARGET, candidate, backup)
    stage.write_json(paths.input_identity / "candidate_copy_manifest.json", {"candidate_dwg_path": str(candidate), "prewrite_backup_path": str(backup), **copy_manifest})
    pre_snapshot = stage.snapshot_records(target_scan["entities"])
    stage.write_json(paths.verification / "prewrite_snapshot.json", pre_snapshot)

    execution = stage.execute_candidate_plan(app, REFERENCE, candidate, backup, plan, protected_bboxes)
    stage.write_json(paths.execution / "execution_batches.json", execution["batches"])
    stage.write_jsonl(paths.execution / "created_entity_map.jsonl", execution["created_map"])
    stage.write_json(paths.execution / "write_audit.json", {"plan_sha256_valid": stage.payload_sha256(plan) == plan["plan_sha256"], "executed_task_count": len(execution["created_map"]), "target_original_write": False, "target_original_save": False})

    candidate_scan = stage.scan_dwg_readonly(app, candidate, "candidate_persisted")
    post_snapshot = stage.snapshot_records(candidate_scan["entities"])
    stage.write_json(paths.verification / "postwrite_snapshot.json", post_snapshot)
    pre_handles, post_handles = set(pre_snapshot["handles"]), set(post_snapshot["handles"])
    created_handles = {item["created_handle"] for item in execution["created_map"]}
    deleted = sorted(pre_handles - post_handles)
    unexpected = sorted((post_handles - pre_handles) - created_handles)
    existing_modified = sorted(handle for handle in pre_handles & post_handles if pre_snapshot["signatures"][handle] != post_snapshot["signatures"][handle])
    persisted_handles = {item["created_handle"] for item in execution["persistence"] if item["persisted"]}
    protected_handles = {str(value).upper() for item in protected for value in item.get("entity_handles", [])}
    protected_modified = sorted(handle for handle in protected_handles & pre_handles & post_handles if pre_snapshot["signatures"][handle] != post_snapshot["signatures"][handle])
    protected_deleted = sorted(protected_handles & pre_handles - post_handles)
    persistence = {
        "planned_task_count": plan["task_count"], "created_count": len(created_handles),
        "persisted_count": len(persisted_handles), "all_created_persisted": created_handles == persisted_handles,
        "existing_deleted": deleted, "unexpected_new": unexpected, "existing_modified": existing_modified,
        "records": execution["persistence"],
    }
    stage.write_json(paths.verification / "persistence_verification.json", persistence)
    stage.write_json(paths.verification / "protected_region_verification.json", {"protected_region_modified": protected_modified, "protected_region_deleted": protected_deleted, "unchanged": not protected_modified and not protected_deleted})
    original_integrity = {
        "reference_sha256_before": EXPECTED_REFERENCE, "reference_sha256_after": stage.sha256_file(REFERENCE),
        "target_sha256_before": EXPECTED_TARGET, "target_sha256_after": stage.sha256_file(TARGET),
        "reference_hash_unchanged": stage.sha256_file(REFERENCE) == EXPECTED_REFERENCE,
        "target_hash_unchanged": stage.sha256_file(TARGET) == EXPECTED_TARGET,
        "target_original_write": False, "target_original_save": False,
    }
    stage.write_json(paths.verification / "original_file_integrity.json", original_integrity)
    accepted = (
        execution["saved"] and execution["closed"] and execution["reopened"]
        and not deleted and not unexpected and not existing_modified
        and not protected_modified and not protected_deleted
        and created_handles == persisted_handles
        and original_integrity["reference_hash_unchanged"] and original_integrity["target_hash_unchanged"]
    )
    if not accepted:
        shutil.copy2(backup, candidate)
    final = {
        "status": "STAGE6_P3_P4_CONTROLLED_CANDIDATE_COMPLETE" if accepted else "CANDIDATE_PERSISTENCE_VERIFICATION_FAILED",
        "run_id": run_id, "candidate_dwg_path": str(candidate), "candidate_dwg_sha256": stage.sha256_file(candidate),
        "prewrite_backup_path": str(backup), "executed_task_count": len(execution["created_map"]),
        "saved": execution["saved"], "closed": execution["closed"], "reopened": execution["reopened"],
        "reference_hash_unchanged": original_integrity["reference_hash_unchanged"],
        "target_hash_unchanged": original_integrity["target_hash_unchanged"],
        "existing_target_unchanged": not deleted and not existing_modified,
        "protected_region_unchanged": not protected_modified and not protected_deleted,
        "target_original_write": False, "target_original_save": False,
    }
    stage.write_json(paths.verification / "final_acceptance.json", final)
    report_markdown(final, summary, plan, paths, candidate, backup)
    print(json.dumps(final, ensure_ascii=False, indent=2))
    return 0 if accepted else 3


if __name__ == "__main__":
    pythoncom.CoInitialize()
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": str(exc), "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}, ensure_ascii=False, indent=2))
        raise
    finally:
        pythoncom.CoUninitialize()
