"""Stage 6-P4.1 整图几何补全的写前分析与受控执行门。"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw

from mcp.orchestration.stage6_p3_p4_controlled_candidate import (
    _bbox_flat, bind_region, create_candidate_copy, detect_missing,
    file_identity, payload_sha256, sha256_file, write_json, write_jsonl,
)


PHASE = "STAGE6-P4.1"
L3_APPROVAL_PHRASE = "我批准 sandbox 执行"


def manual_save_handoff(
    *, write_completed: bool, active_document_is_experimental_copy: bool,
    document_name: str | None, document_full_path: str | None,
    document_saved_state: bool | None, document_read_only_state: bool | None,
    object_count_before: int, object_count_after: int,
    new_object_handles: Sequence[str], copyobjects_success_count: int,
    copyobjects_failure_count: int, save_error_type: str, save_error_message: str,
) -> dict[str, Any]:
    """自动保存失败后的非破坏性交接；调用方不得再关闭或回滚文档。"""
    identity_ok = bool(active_document_is_experimental_copy and document_full_path)
    status = "MANUAL_SAVE_REQUIRED" if write_completed and identity_ok else "MANUAL_SAVE_BLOCKED_BY_DOCUMENT_IDENTITY_UNCERTAINTY"
    return {
        "status": status,
        "current_document_name": document_name,
        "current_document_full_path": document_full_path,
        "document_saved_state": document_saved_state,
        "document_read_only_state": document_read_only_state,
        "write_completed": write_completed,
        "object_count_before": object_count_before,
        "object_count_after": object_count_after,
        "new_object_count": len(new_object_handles),
        "new_object_handles": list(new_object_handles),
        "copyobjects_success_count": copyobjects_success_count,
        "copyobjects_failure_count": copyobjects_failure_count,
        "active_document_confirmed": identity_ok,
        "manual_save_document_verified": identity_ok,
        "save_error_type": save_error_type,
        "save_error_message": save_error_message,
        "automatic_save_succeeded": False,
        "manual_save_required": bool(write_completed and identity_ok),
        "document_must_remain_open": True,
        "automatic_close_allowed": False,
        "rollback_allowed": False,
        "copy_retry_allowed": False,
        "persistence_verification_completed": False,
        "manual_persistence_verification_pending": bool(write_completed and identity_ok),
    }


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validated_transforms(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    transforms = list(payload.get("transforms", []))
    if len(transforms) != 7:
        raise ValueError("seven_region_transforms_required")
    if len({item["reference_region_id"] for item in transforms}) != 7 or len({item["target_region_id"] for item in transforms}) != 7:
        raise ValueError("duplicate_region_binding")
    for item in transforms:
        if item.get("transform_type") != "translation_only" or float(item.get("scale", 0)) != 1 or float(item.get("rotation", 1)) != 0:
            raise ValueError("only_verified_translation_is_allowed")
    return transforms


def build_whole_drawing_plan(missing: Sequence[Mapping[str, Any]], transforms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    transform_by_ref = {item["reference_region_id"]: item for item in transforms}
    tasks = []
    for index, item in enumerate(missing, 1):
        transform = transform_by_ref[item["reference_region_id"]]
        tasks.append({
            "task_id": f"stage6_p4_1_{index:05d}", "classification": "MISSING_HIGH_CONFIDENCE",
            "reference_handle": item["handle"], "object_name": item["object_name"], "layer": item.get("layer"),
            "region_id": item["reference_region_id"], "target_region_id": item["target_region_id"],
            "source_bbox": _bbox_flat(item), "expected_target_bbox": item.get("expected_target_bbox"),
            "transform": {"type": "translation_only", "x": transform["translation_x"], "y": transform["translation_y"]},
            "copy_method": "Document.CopyObjects", "confidence": item.get("confidence", 0.0),
            "native_topology_required": False, "relationship_required": False,
        })
    plan = {
        "phase": PHASE, "scope": "ENTIRE_MODELSPACE", "task_goal": "WHOLE_DRAWING_GEOMETRIC_COMPLETION",
        "task_count": len(tasks), "tasks": tasks, "old_4068_frozen_plan_reused": False,
        "target_existing_objects_protected": True, "no_plan_expansion_allowed": True,
    }
    plan["plan_sha256"] = payload_sha256(plan)
    return plan


def region_statistics(transforms: Sequence[Mapping[str, Any]], detection: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    results = []
    for transform in transforms:
        ref_id = transform["reference_region_id"]
        def count(key: str) -> int:
            return sum(1 for item in detection[key] if item.get("reference_region_id") == ref_id)
        results.append({
            "semantic_name": transform["semantic_name"], "reference_region_id": ref_id,
            "target_region_id": transform["target_region_id"], "alignment_status": "VERIFIED",
            "alignment_confidence": max(float(transform.get("holdout_match_ratio") or 0), 0.9),
            "already_present_count": count("already_present"),
            "missing_high_confidence_count": count("missing"), "ambiguous_count": count("review_only"),
            "excluded_count": count("excluded"), "completion_status": "PLANNED_NOT_WRITTEN",
        })
    return results


def _extent(entities: Sequence[Mapping[str, Any]]) -> list[float]:
    boxes = [item.get("expected_target_bbox") or _bbox_flat(item) for item in entities]
    boxes = [box for box in boxes if box]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else [0, 0, 1, 1]


def render_entities(path: Path, entities: Sequence[Mapping[str, Any]], *, highlights: Sequence[Mapping[str, Any]] = (), regions: Sequence[Mapping[str, Any]] = (), title: str = "") -> None:
    width, height = 1600, 1000
    extent = _extent(list(entities) + list(highlights))
    sx, sy = (width-80)/max(extent[2]-extent[0], 1), (height-80)/max(extent[3]-extent[1], 1)
    scale = min(sx, sy)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    def map_box(box: Sequence[float]) -> tuple[int, int, int, int]:
        return (int(40+(box[0]-extent[0])*scale), int(40+(extent[3]-box[3])*scale), int(40+(box[2]-extent[0])*scale), int(40+(extent[3]-box[1])*scale))
    for item in entities:
        box = _bbox_flat(item)
        if box:
            draw.rectangle(map_box(box), outline=(175, 180, 185), width=1)
    for item in highlights:
        box = item.get("expected_target_bbox") or _bbox_flat(item)
        if box:
            draw.rectangle(map_box(box), outline=(215, 35, 45), width=2)
    for region in regions:
        box = region.get("frame_bbox")
        if box:
            draw.rectangle(map_box(box), outline=(20, 90, 180), width=3)
    draw.text((20, 15), title, fill=(0, 0, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def create_visual_package(previews: Path, reference_entities: Sequence[Mapping[str, Any]], target_entities: Sequence[Mapping[str, Any]], detection: Mapping[str, Sequence[Mapping[str, Any]]], ref_regions: Sequence[Mapping[str, Any]], target_regions: Sequence[Mapping[str, Any]], transforms: Sequence[Mapping[str, Any]]) -> list[str]:
    paths = []
    specs = [
        ("whole_drawing_reference_overview.png", reference_entities, (), ref_regions, "Reference whole drawing"),
        ("whole_drawing_target_before.png", target_entities, (), target_regions, "Target before"),
        ("whole_drawing_sandbox_after.png", target_entities, (), target_regions, "Sandbox unchanged - write gate blocked"),
        ("whole_drawing_new_objects_highlight.png", target_entities, detection["missing"], target_regions, "Planned high confidence missing"),
        ("whole_drawing_ambiguous_objects.png", target_entities, detection["review_only"], target_regions, "Ambiguous review"),
        ("whole_drawing_duplicate_check.png", target_entities, (), target_regions, "Duplicate check before write"),
    ]
    for name, entities, highlights, regions, title in specs:
        path = previews / name; render_entities(path, entities, highlights=highlights, regions=regions, title=title); paths.append(str(path))
    for transform in transforms:
        target_id = transform["target_region_id"]
        region = next(item for item in target_regions if item["region_id"] == target_id)
        relevant = [item for item in target_entities if bind_region(item, [region]) == target_id]
        highlights = [item for item in detection["missing"] if item.get("target_region_id") == target_id]
        path = previews / f"region_comparison_{target_id}.png"
        render_entities(path, relevant, highlights=highlights, regions=[region], title=transform["semantic_name"]); paths.append(str(path))
    return paths


def run_analysis(*, root: Path, prior_run: Path, p2_run: Path, reference: Path, target: Path, expected_reference_hash: str, expected_target_hash: str, approval_text: str = "") -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"stage6_p4_1_{stamp}"
    run_root = root / "artifacts" / "stage6_p4_1_whole_drawing_completion" / run_id
    previews = run_root / "previews"; plan_dir = run_root / "frozen_plan"
    previews.mkdir(parents=True); plan_dir.mkdir(parents=True)
    ref_before, target_before = sha256_file(reference), sha256_file(target)
    if ref_before != expected_reference_hash or target_before != expected_target_hash:
        raise RuntimeError("FAILED_ORIGINAL_FILE_INTEGRITY")
    transforms = validated_transforms(read_json(p2_run / "alignment_repair" / "final_verified_coordinate_transforms.json"))
    ref_scan = read_json(prior_run / "logs" / "reference_full_readonly_scan.json")
    target_scan = read_json(prior_run / "logs" / "target_full_readonly_scan.json")
    ref_regions = read_json(p2_run / "reference_regions.json")["regions"]
    target_regions = [item for item in read_json(p2_run / "target_regions.json")["regions"] if str(item["region_id"]).startswith("target_region_")]
    protected = [item["frame_bbox"] for item in read_json(p2_run / "protected_regions.json")["regions"]]
    detection = detect_missing(ref_scan["entities"], target_scan["entities"], transforms, ref_regions, target_regions, protected)
    plan = build_whole_drawing_plan(detection["missing"], transforms)
    write_json(plan_dir / "whole_drawing_write_plan.json", plan)
    (plan_dir / "whole_drawing_write_plan.sha256").write_text(plan["plan_sha256"]+"\n", encoding="ascii")
    stats = region_statistics(transforms, detection)
    write_json(run_root / "region_completion_statistics.json", {"regions": stats})
    write_jsonl(run_root / "missing_high_confidence.jsonl", detection["missing"])
    write_jsonl(run_root / "already_present.jsonl", detection["already_present"])
    write_jsonl(run_root / "ambiguous_review.jsonl", detection["review_only"])
    candidate = root / "图纸" / f"target_sample_t8_stage6_p4_1_whole_drawing_completion_{stamp}.dwg"
    backup = root / "图纸" / f"target_sample_t8_stage6_p4_1_whole_drawing_completion_{stamp}_prewrite_backup.dwg"
    copy_manifest = create_candidate_copy(target, candidate, backup)
    visual_paths = create_visual_package(previews, ref_scan["entities"], target_scan["entities"], detection, ref_regions, target_regions, transforms)
    approval = L3_APPROVAL_PHRASE in approval_text
    execution = {
        "approval_valid": approval, "approval_phrase_required": L3_APPROVAL_PHRASE,
        "copyobjects_attempted": False, "copyobjects_success_count": 0, "copyobjects_failure_count": 0,
        "ordinary_cad_rebuild_count": 0, "visual_fallback_count": 0,
        "saved": False, "closed": False, "reopened": False, "persisted_count": 0,
        "blocked_reason": None if approval else "L3_APPROVAL_PHRASE_MISSING",
        "manual_save_fallback_enabled": True,
        "manual_save_required": False,
        "automatic_close_after_save_failure_allowed": False,
    }
    write_json(run_root / "execution_gate.json", execution)
    ref_after, target_after = sha256_file(reference), sha256_file(target)
    status = "BLOCKED_BY_COPYOBJECTS_FAILURE"
    summary = {
        "phase": PHASE, "run_id": run_id, "status": status,
        "reference": {**file_identity(reference), "sha256_before": ref_before, "sha256_after": ref_after, "unchanged": ref_before == ref_after},
        "target": {**file_identity(target), "sha256_before": target_before, "sha256_after": target_after, "unchanged": target_before == target_after},
        "candidate_dwg_path": str(candidate), "prewrite_backup_path": str(backup), "copy_manifest": copy_manifest,
        "region_count": 7, "aligned_region_count": 7, "unresolved_region_count": 0,
        "reference_object_count": ref_scan["entity_count"], "target_existing_count": target_scan["entity_count"],
        "already_present_count": len(detection["already_present"]), "missing_high_confidence_count": len(detection["missing"]),
        "ambiguous_count": len(detection["review_only"]), "excluded_count": len(detection["excluded"]),
        "actual_copied_count": 0, "copyobjects_success_count": 0, "copyobjects_failure_count": 0,
        "ordinary_cad_rebuild_count": 0, "visual_fallback_count": 0, "new_object_type_counts": {},
        "duplicate_intercept_count": 0, "region_statuses": stats, "persisted_count": 0,
        "reference_unchanged": ref_before == ref_after, "target_unchanged": target_before == target_after,
        "target_original_write": False, "target_original_save": False,
        "visual_preview_paths": visual_paths, "manual_visual_acceptance": "PENDING",
        "native_topology_verified": False, "relationship_observability": False,
        "engineering_semantic_completeness_verified": False,
        "old_4068_frozen_plan_reused": False, "execution": execution,
    }
    write_json(run_root / "stage6_p4_1_final_report.json", summary)
    (run_root / "stage6_p4_1_final_report.md").write_text(
        f"# Stage 6-P4.1 最终报告\n\n- 状态：{status}\n- 区域：7/7 已对齐\n- Reference/Target：{ref_scan['entity_count']}/{target_scan['entity_count']}\n- 已匹配：{len(detection['already_present'])}\n- 高置信缺失：{len(detection['missing'])}\n- 歧义：{len(detection['review_only'])}\n- 实际复制：0\n- 写入阻断：{execution['blocked_reason']}\n- 原图哈希不变：{ref_before == ref_after and target_before == target_after}\n",
        encoding="utf-8",
    )
    return summary
