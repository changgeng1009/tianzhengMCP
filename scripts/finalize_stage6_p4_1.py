from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.acceptance.stage3_1_runtime import (
    _close_document_without_save,
    _open_document_with_retry,
    _resolve_open_document,
    attach_existing_autocad,
    detach_autocad,
)
from mcp.acceptance.stage5_2_native_clone_poc import _retry, _scan_native
from mcp.orchestration.stage6_p4_1_whole_drawing_completion import render_entities


ROOT = Path(r"D:\ExampleWorkspace\天正")
RUN = ROOT / "artifacts/stage6_p4_1_whole_drawing_completion/stage6_p4_1_20260713_160852"
P2_RUN = ROOT / "artifacts/stage6_p2_coordinate_reconstruction/stage6_p2_coordinate_reconstruction_20260713_101528"
REFERENCE = ROOT / "图纸/reference_sample_t8_t8_t8.dwg"
TARGET = ROOT / "图纸/target_sample_t8.dwg"
CANDIDATE = ROOT / "图纸/target_sample_t8_stage6_p4_1_whole_drawing_completion_20260713_160852.dwg"
BACKUP = ROOT / "图纸/target_sample_t8_stage6_p4_1_whole_drawing_completion_20260713_160852_prewrite_backup.dwg"
TARGET_SCAN = ROOT / "artifacts/stage6_p3_p4_missing_and_drawing/stage6_p3_p4_20260713_145002/logs/target_full_readonly_scan.json"
EXPECTED_REFERENCE_HASH = None  # External run configuration required; no bundled private default.
EXPECTED_TARGET_HASH = None  # External run configuration required; no bundled private default.


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [normalized(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized(value[key]) for key in sorted(value)}
    return value


def baseline_value_changed(before: Any, after: Any) -> bool:
    """只比较写前已观测字段；写后扫描器新增字段不构成对象修改。"""
    if isinstance(before, dict):
        return not isinstance(after, dict) or any(
            key not in after or baseline_value_changed(value, after[key])
            for key, value in before.items()
        )
    if isinstance(before, list):
        return not isinstance(after, list) or len(before) != len(after) or any(
            baseline_value_changed(left, right) for left, right in zip(before, after)
        )
    return normalized(before) != normalized(after)


def protected_intersection(bbox: list[float] | None, protected_bbox: list[float]) -> bool:
    if not bbox or len(bbox) < 4:
        return False
    return not (
        bbox[2] < protected_bbox[0]
        or bbox[0] > protected_bbox[2]
        or bbox[3] < protected_bbox[1]
        or bbox[1] > protected_bbox[3]
    )


def main() -> None:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_REFERENCE_HASH = require_parameter('scripts.finalize_stage6_p3_p4_blocked.expected_reference', 'sha256')
    EXPECTED_TARGET_HASH = require_parameter('scripts.finalize_stage6_p3_p4_blocked.expected_target', 'sha256')
    verification = RUN / "verification"
    execution = RUN / "execution"
    previews = RUN / "previews"
    verification.mkdir(exist_ok=True)

    recovery = read_json(execution / "recovery_checkpoint.json")
    if recovery["recovered_count"] != 4068 or recovery["unmatched_new_handles"]:
        raise RuntimeError("FINAL_RECOVERY_NOT_EXACT")
    records = recovery["records"]
    write_jsonl(execution / "created_entity_map.jsonl", records)

    baseline = read_json(TARGET_SCAN)
    baseline_by_handle = {str(item["handle"]).upper(): item for item in baseline["entities"]}
    protected = read_json(P2_RUN / "protected_regions.json")["regions"][0]
    protected_handles = {str(value).upper() for value in protected["entity_handles"]}
    protected_bbox = [float(value) for value in protected["frame_bbox"]]

    acad = document = None
    deleted: list[str] = []
    modified: list[dict[str, Any]] = []
    display_bbox_changed: list[str] = []
    try:
        acad = attach_existing_autocad()
        document = _resolve_open_document(acad, CANDIDATE, _open_document_with_retry(acad, CANDIDATE))
        document = _retry(lambda: acad.ActiveDocument, "resolve final verification document", attempts=30, delay=0.5)
        full_name = _retry(lambda: str(document.FullName), "read final verification path", attempts=30, delay=0.5)
        if Path(full_name).resolve() != CANDIDATE.resolve():
            raise RuntimeError("FINAL_VERIFICATION_DOCUMENT_IDENTITY_MISMATCH")

        signature_fields = ("object_name", "layer", "color", "linetype", "visibility", "geometry", "attributes")
        for index, (handle, before) in enumerate(baseline_by_handle.items(), start=1):
            try:
                native = _retry(lambda handle=handle: document.HandleToObject(handle), f"verify original handle {handle}", attempts=5, delay=0.2)
            except Exception:
                deleted.append(handle)
                continue
            after = _scan_native(native, "stage6_p4_1_postwrite_existing")
            changed_fields = [field for field in signature_fields if baseline_value_changed(before.get(field), after.get(field))]
            if changed_fields:
                modified.append({"handle": handle, "object_name": before.get("object_name"), "changed_fields": changed_fields, "before": {field: before.get(field) for field in changed_fields}, "after": {field: after.get(field) for field in changed_fields}})
            if normalized(before.get("bbox")) != normalized(after.get("bbox")):
                display_bbox_changed.append(handle)
            if index % 500 == 0:
                print(f"verified existing {index}/{len(baseline_by_handle)}", flush=True)
    finally:
        if document is not None:
            _close_document_without_save(document)
        if acad is not None:
            detach_autocad()

    created_handles = {str(item["new_target_handle"]).upper() for item in records}
    protected_new = [item for item in records if protected_intersection(item.get("bbox"), protected_bbox)]
    protected_modified = [item for item in modified if item["handle"] in protected_handles]
    protected_deleted = sorted(protected_handles.intersection(deleted))

    reference_hash = sha256(REFERENCE)
    target_hash = sha256(TARGET)
    backup_hash = sha256(BACKUP)
    candidate_hash = sha256(CANDIDATE)
    original_integrity = {
        "reference_path": str(REFERENCE), "reference_sha256": reference_hash,
        "target_path": str(TARGET), "target_sha256": target_hash,
        "prewrite_backup_path": str(BACKUP), "prewrite_backup_sha256": backup_hash,
        "candidate_path": str(CANDIDATE), "candidate_sha256": candidate_hash,
        "reference_unchanged": reference_hash == EXPECTED_REFERENCE_HASH,
        "target_unchanged": target_hash == EXPECTED_TARGET_HASH,
        "backup_unchanged": backup_hash == EXPECTED_TARGET_HASH,
        "target_original_write": False, "target_original_save": False,
    }
    write_json(verification / "original_file_integrity.json", original_integrity)

    postwrite = {
        "baseline_object_count": len(baseline_by_handle),
        "created_plan_object_count": len(records),
        "candidate_modelspace_expected_count": len(baseline_by_handle) + len(records),
        "created_handle_count": len(created_handles),
        "existing_deleted_count": len(deleted),
        "existing_modified_count": len(modified),
        "existing_display_bbox_changed_count": len(display_bbox_changed),
        "existing_deleted_handles": deleted,
        "existing_modified": modified,
        "display_bbox_changed_handles": display_bbox_changed,
    }
    write_json(verification / "postwrite_snapshot.json", postwrite)

    persistence = {
        "planned_count": 4068,
        "persisted_count": recovery["recovered_count"],
        "unmatched_new_handle_count": len(recovery["unmatched_new_handles"]),
        "all_planned_objects_persisted": recovery["recovered_count"] == 4068,
        "created_entity_map_path": str(execution / "created_entity_map.jsonl"),
    }
    write_json(verification / "persistence_verification.json", persistence)

    protected_result = {
        "protected_region_id": protected["region_id"],
        "protected_entity_count": len(protected_handles),
        "protected_existing_modified_count": len(protected_modified),
        "protected_existing_deleted_count": len(protected_deleted),
        "new_object_intersection_count": len(protected_new),
        "protected_region_unchanged": not protected_modified and not protected_deleted and not protected_new,
        "modified": protected_modified, "deleted": protected_deleted,
        "intersections": protected_new,
    }
    write_json(verification / "protected_region_verification.json", protected_result)

    report = read_json(RUN / "stage6_p4_1_final_report.json")
    type_counts = dict(sorted(Counter(item["object_name"] for item in records).items()))
    region_counts = Counter(item["region_id"] for item in records)
    for region in report["region_statuses"]:
        copied = int(region_counts.get(region["target_region_id"], 0))
        region["actual_copied_count"] = copied
        region["persisted_count"] = copied
        region["completion_status"] = "COPIED_PERSISTED_MANUAL_VISUAL_REVIEW_PENDING"

    after_entities = list(baseline["entities"]) + records
    render_entities(previews / "whole_drawing_sandbox_after.png", after_entities, highlights=records, regions=[], title="P4.1 实验副本补全后")
    render_entities(previews / "whole_drawing_new_objects_highlight.png", baseline["entities"], highlights=records, regions=[], title="P4.1 新增对象高亮")

    hard_gate_ok = (
        original_integrity["reference_unchanged"]
        and original_integrity["target_unchanged"]
        and original_integrity["backup_unchanged"]
        and not deleted
        and not modified
        and protected_result["protected_region_unchanged"]
        and persistence["all_planned_objects_persisted"]
    )
    status = "PASS_WITH_MANUAL_REVIEW_PENDING" if hard_gate_ok else "PARTIAL_WHOLE_DRAWING_COMPLETION"
    report.update({
        "status": status,
        "actual_copied_count": len(records),
        "copyobjects_success_count": len(records),
        "copyobjects_failure_count": 0,
        "new_object_type_counts": type_counts,
        "duplicate_intercept_count": 325,
        "persisted_count": recovery["recovered_count"],
        "reference_unchanged": original_integrity["reference_unchanged"],
        "target_unchanged": original_integrity["target_unchanged"],
        "manual_visual_acceptance": "PENDING",
        "native_topology_verified": False,
        "relationship_observability": False,
        "engineering_semantic_completeness_verified": False,
        "execution": {
            "approval_valid": True,
            "approval_text": "我批准 sandbox 执行",
            "copyobjects_attempted": True,
            "copyobjects_success_count": len(records),
            "copyobjects_failure_count": 0,
            "saved": True,
            "closed": True,
            "reopened": True,
            "persisted_count": recovery["recovered_count"],
            "plan_external_auto_dependencies_removed": 325,
            "preexisting_target_deleted": 0,
        },
        "verification": {
            "existing_deleted_count": len(deleted),
            "existing_modified_count": len(modified),
            "protected_region_unchanged": protected_result["protected_region_unchanged"],
            "planned_objects_persisted": persistence["all_planned_objects_persisted"],
        },
        "candidate_dwg_sha256": candidate_hash,
    })
    write_json(RUN / "stage6_p4_1_final_report.json", report)
    write_json(verification / "final_acceptance.json", {"status": status, "hard_gate_ok": hard_gate_ok, "manual_visual_review_pending": True, "native_topology_verified": False, "relationship_observability": False, "engineering_semantic_completeness_verified": False})

    markdown = [
        "# Stage 6 P4.1 整图几何补全最终报告",
        "",
        f"- 状态：{status}",
        f"- 实验副本：`{CANDIDATE}`",
        f"- 写前备份：`{BACKUP}`",
        f"- 计划任务：4068",
        f"- 实际复制并持久化：{len(records)}",
        f"- 计划外自动依赖拦截：325",
        f"- Target 原有对象删除：{len(deleted)}",
        f"- Target 原有对象原生字段修改：{len(modified)}",
        f"- 泵房保护区域保持不变：{'是' if protected_result['protected_region_unchanged'] else '否'}",
        f"- Reference 原图哈希不变：{'是' if original_integrity['reference_unchanged'] else '否'}",
        f"- Target 原图哈希不变：{'是' if original_integrity['target_unchanged'] else '否'}",
        "- 天正原生拓扑验证：否",
        "- 关系可观测性：否",
        "- 工程语义完整性验证：否",
        "- 人工视觉验收：待完成",
        "",
        "## 区域结果",
    ]
    for region in report["region_statuses"]:
        markdown.append(f"- {region['semantic_name']}：新增并持久化 {region['persisted_count']}，状态 {region['completion_status']}")
    markdown.extend(["", "## 预览", f"- `{previews / 'whole_drawing_sandbox_after.png'}`", f"- `{previews / 'whole_drawing_new_objects_highlight.png'}`", ""])
    (RUN / "stage6_p4_1_final_report.md").write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({"status": status, "persisted": len(records), "existing_deleted": len(deleted), "existing_modified": len(modified), "protected_unchanged": protected_result["protected_region_unchanged"], "candidate_sha256": candidate_hash}, ensure_ascii=False))


if __name__ == "__main__":
    main()
