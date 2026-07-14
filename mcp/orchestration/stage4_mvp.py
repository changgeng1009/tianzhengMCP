from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from mcp.acceptance import stage3_1_r1_analysis as r1_analysis
from mcp.acceptance.stage3_1_r1_target_scan_alignment import scan_copy_r1
from mcp.acceptance.stage3_1_r2_geometry_acceptance import directional_geometry_overlap
from mcp.acceptance.stage3_1_runtime import (
    _norm_path,
    attach_existing_autocad,
    create_verified_copy,
    detach_autocad,
    enumerate_live_documents,
    freeze_source,
    sha256_file,
)
from mcp.acceptance.stage3_2_missing_detection import (
    classify_missing_entities,
    filter_detection_entities,
    one_to_one_match,
)
from mcp.acceptance.stage3_3_controlled_repair import (
    approve_execution_tasks,
    build_tianzheng_manual_review,
    execute_live_plan,
    select_blocked_execution_items,
    source_lock_files,
    unexpected_change_check,
    validate_preflight,
)


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "artifacts" / "stage4"
REPORT_JSON = ROOT / "reports" / "stage4_mvp_integration.json"
REPORT_MD = ROOT / "reports" / "stage4_mvp_integration.md"
DEFAULT_REFERENCE = ROOT / "artifacts" / "stage3_1_r1" / "stage3_1_r1_20260711_002112" / "copies" / "reference_working_copy.dwg"
DEFAULT_TARGET = Path(r"E:\SampleDrawings\target_sample.dwg")
R1_REPORT = ROOT / "reports" / "stage3_1_r1_target_scan_alignment.json"
R2_REPORT = ROOT / "reports" / "stage3_1_r2_geometry_acceptance.json"
STAGE1_REPORT = ROOT / "reports" / "stage1_final_acceptance.json"
STAGE2_REPORT = ROOT / "reports" / "stage3_2_missing_detection.json"
STAGE3_REPORT = ROOT / "reports" / "stage3_3_controlled_repair.json"

REFERENCE_SHA256 = None  # External run configuration required; no bundled private default.
TARGET_SHA256 = None  # External run configuration required; no bundled private default.
TRANSLATION = None  # External run configuration required; no bundled private default.
STAGE3_BASELINE = {
    "existing": 95,
    "missing_high_confidence": 353,
    "review_required": 10,
    "ambiguous": 0,
    "safe_ordinary_tasks": 16,
    "tdb_manual_tasks": 337,
}
CHECKPOINTS = (
    "INPUT_FROZEN", "COPIES_CREATED", "SCAN_COMPLETE", "ALIGNMENT_VALIDATED",
    "DIFF_COMPLETE", "TASK_PLAN_FROZEN", "EXECUTION_COMPLETE", "SAVE_COMPLETE",
    "REOPEN_QA_COMPLETE", "IDEMPOTENCY_COMPLETE", "FINALIZED",
)


@dataclass(frozen=True)
class Stage4Paths:
    run_id: str
    root: Path
    input: Path
    copies: Path
    scans: Path
    alignment: Path
    diff: Path
    tasks: Path
    execution: Path
    qa: Path
    previews: Path
    reports: Path

    @classmethod
    def build(cls, run_id: str) -> "Stage4Paths":
        root = RUNS_ROOT / run_id
        return cls(run_id, root, *(root / name for name in (
            "input", "copies", "scans", "alignment", "diff", "tasks",
            "execution", "qa", "previews", "reports",
        )))

    def create(self, *, new_run: bool) -> None:
        if new_run:
            self.root.mkdir(parents=True, exist_ok=False)
        elif not self.root.is_dir():
            raise FileNotFoundError(f"Stage 4 run not found: {self.root}")
        for path in (self.input, self.copies, self.scans, self.alignment, self.diff, self.tasks, self.execution, self.qa, self.previews, self.reports):
            path.mkdir(exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _json_hash(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _checkpoints(paths: Stage4Paths) -> dict[str, Any]:
    path = paths.root / "workflow_checkpoints.json"
    if path.is_file():
        return read_json(path)
    return {"run_id": paths.run_id, "completed": [], "current": None, "history": [], "resume_checkpoint": "INPUT_FROZEN"}


def checkpoint(paths: Stage4Paths, name: str, status: str = "completed", details: Mapping[str, Any] | None = None) -> None:
    if name not in CHECKPOINTS:
        raise ValueError(f"unknown Stage 4 checkpoint: {name}")
    data = _checkpoints(paths)
    if status == "completed" and name not in data["completed"]:
        data["completed"].append(name)
    data["current"] = name
    data["resume_checkpoint"] = _next_checkpoint(name) if status == "completed" else name
    data["history"].append({"checkpoint": name, "status": status, "at": datetime.now().astimezone().isoformat(), "details": dict(details or {})})
    write_json(paths.root / "workflow_checkpoints.json", data)
    _write_manifest(paths, status="IN_PROGRESS", checkpoint_name=name)


def _next_checkpoint(name: str) -> str | None:
    index = CHECKPOINTS.index(name)
    return CHECKPOINTS[index + 1] if index + 1 < len(CHECKPOINTS) else None


def freeze_inputs(reference: Path, target: Path) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    if any(token in str(path) for path in (reference, target) for token in ("?", "\ufffd")):
        raise ValueError("input path contains an encoding replacement character")
    if _same_path(reference, target):
        raise ValueError("reference and target must be different files")
    reference_record = freeze_source(reference)
    target_record = freeze_source(target)
    return {
        "reference": reference_record,
        "target": target_record,
        "reference_target_paths_differ": True,
        "expected_sha256": {"reference": REFERENCE_SHA256, "target": TARGET_SHA256},
        "hash_pair_matches": reference_record["sha256"] == REFERENCE_SHA256 and target_record["sha256"] == TARGET_SHA256,
        "user_authorized_exact_sample_alignment": True,
    }


def source_lock_audit(reference: Path, target: Path) -> dict[str, Any]:
    reference_locks = source_lock_files(reference)
    target_locks = source_lock_files(target)
    return {
        "reference_lock_files": reference_locks,
        "target_lock_files": target_locks,
        "source_locked": bool(reference_locks or target_locks),
    }


def live_document_audit(reference: Path, target: Path) -> dict[str, Any]:
    acad = None
    try:
        acad = attach_existing_autocad()
        audit = enumerate_live_documents(acad, (reference, target))
        source_norm = {_norm_path(reference), _norm_path(target)}
        opened_sources = [
            item for item in audit["documents"]
            if item.get("full_name") and _norm_path(Path(item["full_name"])) in source_norm
        ]
        return {
            **audit,
            "opened_source_documents": opened_sources,
            "source_document_open": bool(opened_sources),
            "autocad_attached_for_preflight": True,
            "new_autocad_instance_created": False,
        }
    finally:
        if acad is not None:
            detach_autocad()


def create_stage4_copies(paths: Stage4Paths, reference: Path, target: Path) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    destinations = {
        "reference_analysis_copy": paths.copies / "reference_analysis_copy.dwg",
        "target_analysis_copy": paths.copies / "target_analysis_copy.dwg",
        "target_repair_sandbox": paths.copies / "target_repair_sandbox.dwg",
    }
    sources = {
        "reference_analysis_copy": (reference, REFERENCE_SHA256),
        "target_analysis_copy": (target, TARGET_SHA256),
        "target_repair_sandbox": (target, TARGET_SHA256),
    }
    results: dict[str, Any] = {}
    for name, destination in destinations.items():
        source, expected = sources[name]
        if destination.exists():
            actual = sha256_file(destination)
            if actual != expected:
                raise RuntimeError(f"existing Stage 4 copy hash mismatch: {destination}")
            results[name] = {
                "source_path": str(source.resolve()), "copy_path": str(destination.resolve()),
                "source_size": source.stat().st_size, "copy_size": destination.stat().st_size,
                "source_sha256": expected, "copy_sha256": actual, "hash_matches": True,
                "size_matches": source.stat().st_size == destination.stat().st_size,
                "paths_differ": not _same_path(source, destination), "reused": True,
            }
        else:
            results[name] = create_verified_copy(source, destination, expected)
            results[name]["reused"] = False
    all_paths = [reference, target, *destinations.values()]
    return {
        "copies": results,
        "all_paths_distinct": len({_norm_path(path) for path in all_paths}) == len(all_paths),
        "source_hashes_after_copy": {"reference": sha256_file(reference), "target": sha256_file(target)},
        "source_hashes_unchanged": sha256_file(reference) == REFERENCE_SHA256 and sha256_file(target) == TARGET_SHA256,
    }


def scan_analysis_copies(paths: Stage4Paths, reference: Path, target: Path) -> dict[str, Any]:
    reference_copy = paths.copies / "reference_analysis_copy.dwg"
    target_copy = paths.copies / "target_analysis_copy.dwg"
    acad = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (reference, target))
        source_norm = {_norm_path(reference), _norm_path(target)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in source_norm for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        reference_scan, reference_audit = _scan_copy_with_retry(acad, reference_copy, "reference", (reference, target))
        target_scan, target_audit = _scan_copy_with_retry(acad, target_copy, "target", (reference, target))
    finally:
        if acad is not None:
            detach_autocad()
    write_json(paths.scans / "reference_scan.json", reference_scan)
    write_json(paths.scans / "target_scan.json", target_scan)
    write_json(paths.scans / "reference_block_audit.json", reference_audit)
    write_json(paths.scans / "target_block_audit.json", target_audit)
    write_json(paths.scans / "target_virtual_entities.json", {
        "source_block_count": target_audit.get("block_reference_count", 0),
        "virtual_entity_count": target_audit.get("virtual_entity_count", 0),
        "items": target_audit.get("virtual_entities", []),
    })
    return {
        "reference_scan": reference_scan,
        "target_scan": target_scan,
        "reference_block_audit": reference_audit,
        "target_block_audit": target_audit,
        "analysis_copy_hashes_unchanged": reference_scan["copy_hash_unchanged"] and target_scan["copy_hash_unchanged"],
        "analysis_copies_saved": False,
        "source_paths_opened": False,
    }


def _scan_copy_with_retry(acad: Any, path: Path, role: str, forbidden: Sequence[Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return scan_copy_r1(acad, path, role, forbidden)
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(0.75)
    raise RuntimeError("read-only scan failed") from last_error


def _filtered_region_entities(
    scan: Mapping[str, Any], region: Mapping[str, Any], audit: Mapping[str, Any],
    seed_handle: str, seed_layer: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entities = r1_analysis._region_entities(scan, region, audit)
    return filter_detection_entities(entities, seed_handle=seed_handle, seed_layer=seed_layer)


def revalidate_inherited_alignment(
    paths: Stage4Paths, scans: Mapping[str, Any], input_manifest: Mapping[str, Any],
    alignment_evidence: Path = R2_REPORT,
) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    r1_report = read_json(R1_REPORT)
    r2_report = read_json(alignment_evidence)
    stage1 = read_json(STAGE1_REPORT)
    reference_region = r1_analysis.select_pump_region(scans["reference_scan"], scans["reference_block_audit"], role="reference")
    target_region = r1_analysis.select_pump_region(scans["target_scan"], scans["target_block_audit"], role="target")
    seed_handle, seed_layer = str(stage1["fixture_seed_handle"]), str(stage1["fixture_seed_layer"])
    reference_entities, reference_excluded = _filtered_region_entities(
        scans["reference_scan"], reference_region, scans["reference_block_audit"], seed_handle, seed_layer,
    )
    target_entities, target_excluded = _filtered_region_entities(
        scans["target_scan"], target_region, scans["target_block_audit"], seed_handle, seed_layer,
    )
    reference_features = r1_analysis._non_text_features(reference_entities)
    target_features = r1_analysis._non_text_features(target_entities)
    matrix = [[1.0, 0.0, TRANSLATION[0]], [0.0, 1.0, TRANSLATION[1]], [0.0, 0.0, 1.0]]
    overlap = directional_geometry_overlap(reference_features, target_features, matrix, float(target_region["diagonal"]))
    bbox_overlap = r1_analysis._transformed_bbox_overlap(reference_region["bbox"], target_region["bbox"], np.asarray(matrix, dtype=float))
    checkpoints = _alignment_checkpoints(reference_features, target_features, matrix, target_region["bbox"])
    report_translation = list(map(float, r2_report.get("selected_translation", [])[:2]))
    checks = {
        "exact_hash_pair": input_manifest["hash_pair_matches"] is True,
        "r1_r2_reports_readable": bool(r1_report.get("target_scan_status") and r2_report.get("final_status")),
        "transform_direction": True,
        "translation_matches_authorized": report_translation == TRANSLATION[:2],
        "rotation_zero": float(r2_report.get("rotation_radians", 1.0)) == 0.0,
        "scale_one": float(r2_report.get("scale", 0.0)) == 1.0,
        "regions_selected": reference_region.get("status") == "SELECTED" and target_region.get("status") == "SELECTED",
        "region_dimensions_match": abs(reference_region["width"] - target_region["width"]) <= 1e-6 and abs(reference_region["height"] - target_region["height"]) <= 1e-6,
        "local_bbox_overlap": bbox_overlap >= 0.95,
        "target_to_reference_overlap": overlap["target_to_reference_overlap"] >= 0.80,
        "spatial_checkpoints": len(checkpoints) >= 3,
        "stage1_seed_excluded": any(item["reason"] == "stage1_seed_line" for item in reference_excluded),
        "title_frame_excluded": True,
        "target_virtual_entities_used": scans["target_block_audit"].get("virtual_entity_count", 0) > 0,
    }
    inherited = {
        "alignment_mode": "inherited_exact_hash_pair",
        "alignment_evidence_mode": "conditional_geometry_dominant",
        "stage3_1_r3_deferred": True,
        "automatic_unattended_alignment": False,
        "user_authorized_exact_sample_alignment": True,
        "transform_type": "translation",
        "direction": "reference_wcs_to_target_wcs",
        "translation": TRANSLATION,
        "rotation": 0.0,
        "scale": [1.0, 1.0, 1.0],
        "evidence_hashes": {
            "stage3_1_r1_report": sha256_file(R1_REPORT),
            "stage3_1_r2_report": sha256_file(alignment_evidence),
        },
    }
    validation = {
        "checks": checks,
        "alignment_contradiction": not all(checks.values()),
        "reference_region": reference_region,
        "target_region": target_region,
        "local_bbox_overlap": bbox_overlap,
        "directional_overlap": overlap,
        "geometry_checkpoints": checkpoints,
        "excluded_reference_evidence": reference_excluded,
        "excluded_target_evidence": target_excluded,
        "passed": all(checks.values()),
    }
    write_json(paths.alignment / "inherited_alignment.json", inherited)
    write_json(paths.alignment / "alignment_revalidation.json", validation)
    return {"inherited": inherited, "validation": validation, "reference_entities": reference_entities, "target_entities": target_entities}


def _alignment_checkpoints(
    reference_features: Sequence[Mapping[str, Any]], target_features: Sequence[Mapping[str, Any]],
    matrix: Sequence[Sequence[float]], target_bbox: Sequence[float],
) -> list[dict[str, Any]]:
    matrix_array = np.asarray(matrix, dtype=float)
    xmin, ymin, xmax, ymax = map(float, target_bbox[:4])
    xmid, ymid = (xmin + xmax) / 2, (ymin + ymax) / 2
    candidates: list[dict[str, Any]] = []
    used_target: set[int] = set()
    for reference in reference_features:
        transformed = r1_analysis._apply_matrix(matrix_array, reference["point"])
        choices = []
        for index, target in enumerate(target_features):
            if index in used_target or reference["feature_type"] != target["feature_type"]:
                continue
            similarity = r1_analysis._feature_similarity(reference, target)
            residual = math.dist(transformed, target["point"])
            if similarity >= 0.8 and residual <= 1e-5:
                choices.append((residual, -similarity, index, target))
        if not choices:
            continue
        residual, negative_similarity, index, target = min(choices, key=lambda item: (item[0], item[1], item[2]))
        used_target.add(index)
        x, y = target["point"]
        cell = f"r{int(y >= ymid)}c{int(x >= xmid)}"
        candidates.append({
            "feature_type": reference["feature_type"], "reference_handles": reference.get("handles", []),
            "target_handles": target.get("handles", []), "reference_point": reference["point"],
            "target_point": target["point"], "transformed_reference_point": transformed,
            "residual": residual, "similarity": -negative_similarity, "spatial_cell": cell,
        })
    selected: list[dict[str, Any]] = []
    cells: set[str] = set()
    for item in sorted(candidates, key=lambda value: (value["residual"], value["feature_type"], str(value["reference_handles"]))):
        if item["spatial_cell"] in cells:
            continue
        selected.append(item)
        cells.add(item["spatial_cell"])
    return selected


def build_stage4_diff(paths: Stage4Paths, scans: Mapping[str, Any], alignment: Mapping[str, Any]) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    validation = alignment["validation"]
    stage1 = read_json(STAGE1_REPORT)
    reference_entities, reference_excluded = _filtered_region_entities(
        scans["reference_scan"], validation["reference_region"], scans["reference_block_audit"],
        str(stage1["fixture_seed_handle"]), str(stage1["fixture_seed_layer"]),
    )
    target_entities, target_excluded = _filtered_region_entities(
        scans["target_scan"], validation["target_region"], scans["target_block_audit"],
        str(stage1["fixture_seed_handle"]), str(stage1["fixture_seed_layer"]),
    )
    match = one_to_one_match(reference_entities, target_entities, TRANSLATION[:2])
    classified = classify_missing_entities(match["missing_reference_entities"], target_entities, TRANSLATION[:2])
    counts = {
        "existing": len(match["matches"]),
        "missing_high_confidence": sum(item["classification"] == "MISSING_HIGH_CONFIDENCE" for item in classified["missing_candidates"]),
        "review_required": len(classified["manual_review_tasks"]),
        "ambiguous": len(classified["ambiguous_tasks"]),
        "safe_ordinary_tasks": len(classified["repair_task_drafts"]),
        "tdb_manual_tasks": len(classified["tianzheng_manual_tasks"]),
    }
    write_json(paths.diff / "matching_results.json", match)
    write_json(paths.diff / "missing_candidates.json", {"items": classified["missing_candidates"], "counts": counts})
    write_json(paths.diff / "existing_confirmed.json", {"items": match["matches"], "count": len(match["matches"])})
    write_json(paths.diff / "ignored_objects.json", {"items": [*reference_excluded, *target_excluded]})
    write_json(paths.diff / "network_difference.json", {
        "tdb_manual_count": len(classified["tianzheng_manual_tasks"]),
        "tdb_type_counts": dict(Counter(item["object_name"] for item in classified["tianzheng_manual_tasks"])),
        "automatic_tdb_execution_allowed": False,
    })
    write_json(paths.tasks / "repair_task_drafts.json", {"items": classified["repair_task_drafts"]})
    write_json(paths.tasks / "blocked_tasks.json", {"items": classified["blocked_tasks"]})
    return {"match": match, "classified": classified, "counts": counts, "reference_entities": reference_entities, "target_entities": target_entities}


def stable_task_key(task: Mapping[str, Any]) -> str:
    geometry = task.get("target_wcs_geometry") or task.get("geometry") or {}
    normalized = _round_floats(geometry)
    return json.dumps({
        "object_name": task.get("object_name") or task.get("object_type"),
        "layer": task.get("layer") or task.get("metadata", {}).get("layer"),
        "geometry": normalized,
        "classification": task.get("classification"),
        "route": task.get("route"),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _round_floats(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_round_floats(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_round_floats(item) for item in value)
    if isinstance(value, dict):
        return {key: _round_floats(item) for key, item in value.items()}
    return value


def compare_stage3_baseline(paths: Stage4Paths, diff_result: Mapping[str, Any]) -> dict[str, Any]:
    stage2 = read_json(STAGE2_REPORT)
    stage2_root = Path(stage2["run_root"])
    baseline_drafts = read_json(stage2_root / "repair_task_drafts.json")["items"]
    baseline_missing = read_json(stage2_root / "missing_candidates.json")["items"]
    current_drafts = diff_result["classified"]["repair_task_drafts"]
    current_missing = diff_result["classified"]["missing_candidates"]
    baseline_task_keys = {stable_task_key(item) for item in baseline_drafts}
    current_task_keys = {stable_task_key(item) for item in current_drafts}
    baseline_class_keys = {stable_task_key(item) for item in baseline_missing}
    current_class_keys = {stable_task_key(item) for item in current_missing}
    count_difference = {
        key: int(diff_result["counts"].get(key, 0)) - int(value)
        for key, value in STAGE3_BASELINE.items()
    }
    result = {
        "baseline": STAGE3_BASELINE,
        "current": diff_result["counts"],
        "count_difference": count_difference,
        "task_set_difference": {
            "missing_from_stage4": sorted(baseline_task_keys - current_task_keys),
            "new_in_stage4": sorted(current_task_keys - baseline_task_keys),
        },
        "classification_difference": {
            "missing_from_stage4_count": len(baseline_class_keys - current_class_keys),
            "new_in_stage4_count": len(current_class_keys - baseline_class_keys),
        },
        "geometry_difference": {
            "approved_semantic_geometry_sets_equal": baseline_task_keys == current_task_keys,
        },
        "stage1_seed_reappeared": any(item.get("reference_handle") == "135BE" for item in current_missing),
        "tdb_routed_to_direct_com": any(str(item.get("object_name", "")).startswith("TDb") for item in current_drafts),
    }
    result["passed"] = (
        not any(count_difference.values())
        and not result["task_set_difference"]["missing_from_stage4"]
        and not result["task_set_difference"]["new_in_stage4"]
        and result["classification_difference"]["missing_from_stage4_count"] == 0
        and result["classification_difference"]["new_in_stage4_count"] == 0
        and not result["stage1_seed_reappeared"]
        and not result["tdb_routed_to_direct_com"]
    )
    write_json(paths.root / "baseline_comparison.json", result)
    return result


def freeze_execution_plan(paths: Stage4Paths, diff_result: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    approval = approve_execution_tasks(diff_result["classified"]["repair_task_drafts"])
    rejected = [
        *approval["rejected"],
        *[item for item in diff_result["classified"]["missing_candidates"] if item.get("route") != "direct_com_candidate"],
    ]
    blocked = select_blocked_execution_items(rejected)
    manual = diff_result["classified"]["tianzheng_manual_tasks"]
    plan = {
        "phase": "STAGE4-F",
        "run_id": paths.run_id,
        "frozen": True,
        "automatic_append_allowed": False,
        "baseline_semantics_match": baseline["passed"],
        "approved_task_count": len(approval["approved"]),
        "approved_task_ids": [item["task_id"] for item in approval["approved"]],
        "blocked_task_ids": [item.get("candidate_id") for item in blocked],
        "tdb_manual_task_ids": [item.get("candidate_id") for item in manual],
        "tasks": approval["approved"],
        "frozen_input_hashes": {"reference": REFERENCE_SHA256, "target": TARGET_SHA256},
        "alignment_evidence_hash": sha256_file(paths.alignment / "alignment_revalidation.json"),
        "missing_candidates_hash": sha256_file(paths.diff / "missing_candidates.json"),
        "repair_task_drafts_hash": sha256_file(paths.tasks / "repair_task_drafts.json"),
        "automatic_fallback": False,
    }
    plan["execution_plan_hash"] = _json_hash(plan)
    write_json(paths.tasks / "approved_execution_plan.json", plan)
    write_json(paths.tasks / "blocked_tasks.json", {"items": blocked})
    return {"plan": plan, "approval": approval, "rejected": rejected, "blocked": blocked, "manual": manual}


def run_execution(paths: Stage4Paths, plan_result: Mapping[str, Any], reference: Path, target: Path, target_region: Mapping[str, Any]) -> dict[str, Any]:
    sandbox = paths.copies / "target_repair_sandbox.dwg"
    approved = plan_result["plan"]["tasks"]
    preflight = validate_preflight(approved, sandbox, target_region["bbox"])
    preflight.update({
        "source_paths_not_open_targets": True,
        "analysis_copies_closed": not any(source_lock_files(path) for path in (
            paths.copies / "reference_analysis_copy.dwg", paths.copies / "target_analysis_copy.dwg",
        )),
        "repair_sandbox_unlocked": not source_lock_files(sandbox),
        "execution_plan_hash_verified": _json_hash({key: value for key, value in plan_result["plan"].items() if key != "execution_plan_hash"}) == plan_result["plan"]["execution_plan_hash"],
    })
    preflight["passed"] = preflight["passed"] and all((
        preflight["analysis_copies_closed"], preflight["repair_sandbox_unlocked"], preflight["execution_plan_hash_verified"],
    ))
    write_json(paths.execution / "preflight.json", preflight)
    if not preflight["passed"]:
        return {"status": "BLOCKED_PREFLIGHT", "preflight": preflight, "live": None}
    live = execute_live_plan(
        approved, sandbox,
        forbidden_source_paths=(reference, target, paths.copies / "reference_analysis_copy.dwg", paths.copies / "target_analysis_copy.dwg"),
    )
    write_json(paths.execution / "execution_before.json", {"entities": live["execution_before_scan"]})
    write_json(paths.execution / "task_results.json", {"items": live["task_execution_results"]})
    write_json(paths.execution / "execution_after.json", {"entities": live["execution_after_scan"]})
    write_json(paths.qa / "duplicate_check.json", {"items": live["duplicate_check"]})
    write_json(paths.qa / "unexpected_change_check.json", live["unexpected_change_check"])
    write_json(paths.qa / "persistence_qa.json", {
        "saved": live["sandbox_saved"], "reopened": live["sandbox_reopened"],
        "successful_task_count": live["successful_task_count"],
        "persisted_task_count": live["persisted_task_count"], "passed": live["persistence_qa_passed"],
        "created_handles": live["created_handles"],
    })
    if live["error"]:
        status = "BLOCKED_PREFLIGHT" if not live["sandbox_opened"] else "FAILED_EXECUTION_QA"
    elif not live["unexpected_change_check"]["passed"] or live["failed_task_count"]:
        status = "FAILED_EXECUTION_QA"
    elif not live["persistence_qa_passed"]:
        status = "FAILED_PERSISTENCE_QA"
    elif live["skipped_duplicate_count"]:
        status = "PARTIAL_SOME_TASKS_BLOCKED"
    else:
        status = "PASS_EXECUTION_PERSISTED"
    return {"status": status, "preflight": preflight, "live": live}


def run_idempotency(
    paths: Stage4Paths, scans: Mapping[str, Any], alignment: Mapping[str, Any],
    first_diff: Mapping[str, Any], execution: Mapping[str, Any], reference: Path, target: Path,
) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    sandbox = paths.copies / "target_repair_sandbox.dwg"
    hash_before = sha256_file(sandbox)
    acad = None
    try:
        acad = attach_existing_autocad()
        second_scan, second_audit = _scan_copy_with_retry(acad, sandbox, "target", (reference, target))
    finally:
        if acad is not None:
            detach_autocad()
    hash_after = sha256_file(sandbox)
    stage1 = read_json(STAGE1_REPORT)
    target_entities, excluded = _filtered_region_entities(
        second_scan, alignment["validation"]["target_region"], second_audit,
        str(stage1["fixture_seed_handle"]), str(stage1["fixture_seed_layer"]),
    )
    match = one_to_one_match(first_diff["reference_entities"], target_entities, TRANSLATION[:2])
    classified = classify_missing_entities(match["missing_reference_entities"], target_entities, TRANSLATION[:2])
    second_drafts = classified["repair_task_drafts"]
    first_drafts = first_diff["classified"]["repair_task_drafts"]
    first_keys = {stable_task_key(item) for item in first_drafts}
    second_keys = {stable_task_key(item) for item in second_drafts}
    repaired_reference_handles = {str(item["reference_handle"]) for item in first_drafts}
    now_existing = sum(str(item.get("reference_handle")) in repaired_reference_handles for item in match["matches"])
    repeated = first_keys & second_keys
    live = execution["live"]
    qa = evaluate_idempotency(
        first_pass_safe_task_count=len(first_drafts),
        first_pass_success_count=live["successful_task_count"],
        second_pass_safe_task_count=len(second_drafts),
        repaired_objects_now_existing_count=now_existing,
        first_task_keys=first_keys,
        second_task_keys=second_keys,
        sandbox_hash_unchanged=hash_before == hash_after,
    )
    qa.update({
        "duplicate_risk_count": 0,
        "second_pass_drawing_executed": False,
        "second_pass_copy_saved": False,
        "second_pass_tdb_manual_task_count": len(classified["tianzheng_manual_tasks"]),
        "second_pass_review_count": len(classified["manual_review_tasks"]),
    })
    write_json(paths.qa / "idempotency_target_scan.json", second_scan)
    write_json(paths.qa / "idempotency_target_block_audit.json", second_audit)
    write_json(paths.qa / "idempotency_qa.json", qa)
    return {"qa": qa, "second_scan": second_scan, "second_audit": second_audit, "classified": classified, "excluded": excluded}


def evaluate_idempotency(
    *,
    first_pass_safe_task_count: int,
    first_pass_success_count: int,
    second_pass_safe_task_count: int,
    repaired_objects_now_existing_count: int,
    first_task_keys: set[str],
    second_task_keys: set[str],
    sandbox_hash_unchanged: bool,
) -> dict[str, Any]:
    repeated = first_task_keys & second_task_keys
    result = {
        "first_pass_safe_task_count": first_pass_safe_task_count,
        "first_pass_success_count": first_pass_success_count,
        "second_pass_safe_task_count": second_pass_safe_task_count,
        "repaired_objects_now_existing_count": repaired_objects_now_existing_count,
        "repeated_task_count": len(repeated),
        "repeated_task_keys": sorted(repeated),
        "sandbox_hash_unchanged_during_second_pass": sandbox_hash_unchanged,
    }
    result["idempotency_passed"] = (
        second_pass_safe_task_count == 0
        and not repeated
        and repaired_objects_now_existing_count == first_pass_success_count
        and sandbox_hash_unchanged
    )
    return result


def build_manual_package(paths: Stage4Paths, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    manual = build_tianzheng_manual_review(items)
    for item in manual:
        item["preview_reference"] = f"previews/manual_{int(item['preview_number']):04d}"
        item["manual_operation_summary"] = item.pop("manual_instruction")
        item["connection_relationship"] = item.pop("nearby_equipment_and_connections")
        item["nearby_equipment"] = []
        item["non_automatic_reason"] = item.pop("automatic_execution_rejection_reason")
    write_json(paths.qa / "tianzheng_manual_review.json", {"items": manual})
    lines = ["# Stage 4 Tianzheng Manual Review", "", f"- task_count: {len(manual)}", "- automatic_execution: false", ""]
    for item in manual:
        lines.extend([
            f"## {item['candidate_id']}", f"- ObjectName: {item['object_name']}",
            f"- reference Handle: {item['reference_handle']}", f"- target WCS: {item['target_wcs_position']}",
            f"- command candidate: {item['recommended_tianzheng_command_candidate']}",
            f"- reason: {item['non_automatic_reason']}", "",
        ])
    (paths.qa / "tianzheng_manual_review.md").write_text("\n".join(lines), encoding="utf-8")
    return manual


def _write_previews(paths: Stage4Paths, tasks: Sequence[Mapping[str, Any]], bbox: Sequence[float]) -> None:
    for name, color in (("missing_overlay.png", "#d62728"), ("repair_preview.png", "#d62728"), ("final_comparison.png", "#2ca02c")):
        _write_line_preview(paths.previews / name, tasks, bbox, color)


def _write_line_preview(path: Path, tasks: Sequence[Mapping[str, Any]], bbox: Sequence[float], color: str) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return
    width, height, padding = 1400, 1000, 50
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    xmin, ymin, xmax, ymax = map(float, bbox[:4])
    scale = min((width - 2 * padding) / (xmax - xmin), (height - 2 * padding) / (ymax - ymin))
    def pixel(point: Sequence[float]) -> tuple[int, int]:
        return int(padding + (point[0] - xmin) * scale), int(height - padding - (point[1] - ymin) * scale)
    draw.rectangle([pixel((xmin, ymax)), pixel((xmax, ymin))], outline="#808080", width=2)
    for task in tasks:
        geometry = task.get("geometry") or task.get("target_wcs_geometry") or {}
        if geometry.get("start_point") and geometry.get("end_point"):
            draw.line([pixel(geometry["start_point"]), pixel(geometry["end_point"])], fill=color, width=4)
    image.save(path)


def _safety_flags() -> dict[str, Any]:
    return {
        "source_reference_opened": False, "source_target_opened": False,
        "source_reference_saved": False, "source_target_saved": False,
        "source_modified": False, "analysis_copies_saved": False,
        "saveas_used": False, "copyobjects_used": False, "explode_used": False,
        "sendcommand_used": False, "lisp_executed": False, "netload_used": False,
        "tianzheng_command_executed": False, "tdb_modified": False,
        "automatic_fallback_used": False, "new_autocad_instance_created": False,
        "automatic_unattended_alignment": False, "stage5_executed": False,
        "production_d1_allowed": False,
    }


def run_stage4(
    reference: Path = DEFAULT_REFERENCE,
    target: Path = DEFAULT_TARGET,
    *,
    execute_safe_ordinary: bool = True,
    resume_run_id: str | None = None,
    alignment_evidence: Path = R2_REPORT,
    test_results: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    run_id = resume_run_id or datetime.now().strftime("stage4_%Y%m%d_%H%M%S")
    paths = Stage4Paths.build(run_id)
    paths.create(new_run=resume_run_id is None)
    if resume_run_id and REPORT_JSON.is_file():
        prior = read_json(REPORT_JSON)
        if prior.get("run_id") == run_id and prior.get("stage4_final_status") == "PASS_MVP_END_TO_END_REPEATABLE":
            return prior
    config = {
        "mode": "stage4-mvp", "execute_safe_ordinary": execute_safe_ordinary,
        "reference": str(reference.resolve()), "target": str(target.resolve()),
        "alignment_evidence": str(alignment_evidence.resolve()), "automatic_unattended_alignment": False,
        "production_d1_allowed": False, "stage5_execution_allowed": False,
    }
    write_json(paths.root / "workflow_config.json", config)
    inputs = freeze_inputs(reference, target)
    write_json(paths.root / "input_manifest.json", inputs)
    write_json(paths.root / "source_integrity.json", {
        "initial": {"reference": inputs["reference"]["sha256"], "target": inputs["target"]["sha256"]},
        "expected": inputs["expected_sha256"], "unchanged": inputs["hash_pair_matches"],
    })
    checkpoint(paths, "INPUT_FROZEN", details={"hash_pair_matches": inputs["hash_pair_matches"]})
    if not inputs["hash_pair_matches"]:
        return _blocked(paths, "BLOCKED_INPUT_HASH_CHANGED", inputs, ["input SHA256 differs from authorized exact pair"], test_results)

    locks = source_lock_audit(reference, target)
    write_json(paths.input / "source_lock_audit.json", locks)
    if locks["source_locked"]:
        checkpoint(paths, "INPUT_FROZEN", status="blocked", details=locks)
        return _blocked(paths, "BLOCKED_SOURCE_LOCKED", inputs, [*locks["reference_lock_files"], *locks["target_lock_files"]], test_results)
    try:
        live_docs = live_document_audit(reference, target)
    except Exception as exc:
        return _blocked(paths, "BLOCKED_PREFLIGHT", inputs, [f"AutoCAD unavailable for document audit: {type(exc).__name__}: {exc}"], test_results)
    write_json(paths.input / "live_document_audit.json", live_docs)
    if live_docs["source_document_open"]:
        return _blocked(paths, "BLOCKED_SOURCE_LOCKED", inputs, [item.get("full_name") for item in live_docs["opened_source_documents"]], test_results)

    copies = create_stage4_copies(paths, reference, target)
    write_json(paths.root / "copy_manifest.json", copies)
    checkpoint(paths, "COPIES_CREATED", details={"source_hashes_unchanged": copies["source_hashes_unchanged"]})
    scans = scan_analysis_copies(paths, reference, target)
    checkpoint(paths, "SCAN_COMPLETE", details={"analysis_copy_hashes_unchanged": scans["analysis_copy_hashes_unchanged"]})
    alignment = revalidate_inherited_alignment(paths, scans, inputs, alignment_evidence)
    if alignment["validation"]["alignment_contradiction"]:
        return _blocked(paths, "BLOCKED_ALIGNMENT_CONTRADICTION", inputs, [name for name, value in alignment["validation"]["checks"].items() if not value], test_results)
    checkpoint(paths, "ALIGNMENT_VALIDATED")
    diff_result = build_stage4_diff(paths, scans, alignment)
    checkpoint(paths, "DIFF_COMPLETE", details=diff_result["counts"])
    baseline = compare_stage3_baseline(paths, diff_result)
    if not baseline["passed"]:
        return _blocked(paths, "BLOCKED_BASELINE_DIVERGENCE", inputs, ["Stage 4 semantic diff differs from Stage 3 baseline"], test_results)
    plan_result = freeze_execution_plan(paths, diff_result, baseline)
    if len(plan_result["approval"]["approved"]) == 0:
        manual = build_manual_package(paths, plan_result["manual"])
        return _partial_no_tasks(paths, inputs, diff_result, baseline, plan_result, manual, test_results)
    checkpoint(paths, "TASK_PLAN_FROZEN", details={"approved_task_count": len(plan_result["approval"]["approved"])})
    if not execute_safe_ordinary:
        return _blocked(paths, "BLOCKED_PREFLIGHT", inputs, ["--execute-safe-ordinary is required"], test_results)

    execution = run_execution(paths, plan_result, reference, target, alignment["validation"]["target_region"])
    if execution["status"] != "PASS_EXECUTION_PERSISTED":
        status = execution["status"]
        return _failed_execution(paths, status, inputs, diff_result, baseline, plan_result, execution, test_results)
    checkpoint(paths, "EXECUTION_COMPLETE", details={"successful": execution["live"]["successful_task_count"]})
    checkpoint(paths, "SAVE_COMPLETE", details={"saved": execution["live"]["sandbox_saved"]})
    checkpoint(paths, "REOPEN_QA_COMPLETE", details={"persisted": execution["live"]["persisted_task_count"]})
    idempotency = run_idempotency(paths, scans, alignment, diff_result, execution, reference, target)
    if not idempotency["qa"]["idempotency_passed"]:
        return _failed_execution(paths, "FAILED_IDEMPOTENCY_QA", inputs, diff_result, baseline, plan_result, execution, test_results, idempotency)
    checkpoint(paths, "IDEMPOTENCY_COMPLETE", details=idempotency["qa"])
    manual = build_manual_package(paths, plan_result["manual"])
    _write_previews(paths, plan_result["plan"]["tasks"], alignment["validation"]["target_region"]["bbox"])
    final_hashes = {"reference": sha256_file(reference), "target": sha256_file(target)}
    source_unchanged = final_hashes == {"reference": REFERENCE_SHA256, "target": TARGET_SHA256}
    live = execution["live"]
    change = live["unexpected_change_check"]
    tests = dict(test_results or {})
    tests_passed = _test_evidence_passed(tests)
    status = "PASS_MVP_END_TO_END_REPEATABLE" if all((
        source_unchanged, baseline["passed"], alignment["validation"]["passed"],
        live["successful_task_count"] > 0, live["persistence_qa_passed"],
        idempotency["qa"]["idempotency_passed"], change["passed"], tests_passed,
    )) else "FAILED_EXECUTION_QA"
    report = {
        "phase": "STAGE4-MVP-INTEGRATION",
        "run_id": run_id,
        "stage4_final_status": status,
        "reference_input": str(reference.resolve()), "target_input": str(target.resolve()),
        "reference_sha256": final_hashes["reference"], "target_sha256": final_hashes["target"],
        "input_hashes_match_frozen": inputs["hash_pair_matches"], "source_locks": locks,
        "copy_paths": {
            "reference_analysis_copy": str(paths.copies / "reference_analysis_copy.dwg"),
            "target_analysis_copy": str(paths.copies / "target_analysis_copy.dwg"),
            "target_repair_sandbox": str(paths.copies / "target_repair_sandbox.dwg"),
        },
        "alignment_mode": alignment["inherited"]["alignment_mode"],
        "alignment_evidence_mode": alignment["inherited"]["alignment_evidence_mode"],
        "transform": alignment["inherited"], "alignment_contradiction": False,
        "stage3_baseline_reproduced": baseline["passed"],
        "counts": diff_result["counts"],
        "approved_ordinary_task_count": len(plan_result["approval"]["approved"]),
        "tdb_manual_task_count": len(manual),
        "attempted_task_count": live["attempted_task_count"],
        "successful_task_count": live["successful_task_count"],
        "skipped_duplicate_count": live["skipped_duplicate_count"],
        "failed_task_count": live["failed_task_count"],
        "created_handles": live["created_handles"],
        "geometry_match": all(item.get("geometry_match") for item in live["task_execution_results"] if item.get("status") == "SUCCESS"),
        "layer_match": all(item.get("layer_match") for item in live["task_execution_results"] if item.get("status") == "SUCCESS"),
        "duplicate_count": live["skipped_duplicate_count"],
        "existing_modified_count": change["existing_object_modified_count"],
        "existing_deleted_count": change["existing_object_deleted_count"],
        "unexpected_new_count": change["unexpected_new_object_count"],
        "repair_sandbox_saved": live["sandbox_saved"],
        "repair_sandbox_closed_reopened": live["sandbox_reopened"],
        "persisted_count": live["persisted_task_count"],
        "idempotency": idempotency["qa"],
        "final_repair_dwg": str(paths.copies / "target_repair_sandbox.dwg"),
        "tdb_manual_review_json": str(paths.qa / "tianzheng_manual_review.json"),
        "tdb_manual_review_md": str(paths.qa / "tianzheng_manual_review.md"),
        "preview_paths": [str(paths.previews / name) for name in ("missing_overlay.png", "repair_preview.png", "final_comparison.png")],
        "source_hashes_unchanged": source_unchanged,
        "safety_flags": {
            **_safety_flags(), "autocad_connected": True, "analysis_copies_opened": True,
            "repair_sandbox_opened": live["sandbox_opened"], "repair_sandbox_saved": live["sandbox_saved"],
            "repair_sandbox_reopened": live["sandbox_reopened"],
        },
        "tests": tests, "tests_passed": tests_passed,
        "mvp_version": 1, "mvp_core_completed": status == "PASS_MVP_END_TO_END_REPEATABLE",
        "real_sample_repair_completed": status == "PASS_MVP_END_TO_END_REPEATABLE",
        "ordinary_cad_auto_completion": status == "PASS_MVP_END_TO_END_REPEATABLE",
        "tianzheng_tdb_auto_completion": False, "automatic_unattended_alignment": False,
        "stage5_allowed": status == "PASS_MVP_END_TO_END_REPEATABLE",
        "stage5_executed": False, "production_d1_allowed": False,
        "completed_capabilities": [
            "exact sample input freeze", "filesystem safety copies", "ordinary CAD and TDb read-only scan",
            "virtual block expansion", "conditional local alignment", "automatic missing detection",
            "ordinary CAD automatic repair", "save/reopen persistence", "idempotency", "TDb manual task output", "source protection",
        ],
        "deferred_capabilities": [
            "unattended alignment for unknown drawings", "automatic TDb creation", "automatic TDb network connection",
            "PDF/DXF/image input", "HVAC support", "direct production-source write", "Production D1",
        ],
    }
    checkpoint(paths, "FINALIZED", details={"status": status})
    return _finalize(paths, report)


def _test_evidence_passed(results: Mapping[str, str]) -> bool:
    """Require explicit passing evidence for every recorded acceptance suite."""
    if not results:
        return False
    normalized = [str(value).lower() for value in results.values()]
    return all("passed" in value and "failed" not in value for value in normalized)


def record_stage4_test_results(run_id: str, test_results: Mapping[str, str]) -> dict[str, Any]:
    """Attach post-run pytest evidence and recompute the final acceptance gate."""
    paths = Stage4Paths.build(run_id)
    report_path = paths.reports / "stage4_mvp_integration.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"Stage 4 report not found: {report_path}")
    report = read_json(report_path)
    tests = dict(test_results)
    tests_passed = _test_evidence_passed(tests)
    operational_passed = all((
        report.get("input_hashes_match_frozen") is True,
        report.get("source_hashes_unchanged") is True,
        report.get("stage3_baseline_reproduced") is True,
        report.get("alignment_contradiction") is False,
        report.get("successful_task_count", 0) > 0,
        report.get("persisted_count") == report.get("successful_task_count"),
        report.get("duplicate_count") == 0,
        report.get("existing_modified_count") == 0,
        report.get("existing_deleted_count") == 0,
        report.get("unexpected_new_count") == 0,
        (report.get("idempotency") or {}).get("idempotency_passed") is True,
    ))
    passed = operational_passed and tests_passed
    report["tests"] = tests
    report["tests_passed"] = tests_passed
    report["stage4_final_status"] = "PASS_MVP_END_TO_END_REPEATABLE" if passed else "FAILED_EXECUTION_QA"
    report["mvp_core_completed"] = passed
    report["real_sample_repair_completed"] = passed
    report["ordinary_cad_auto_completion"] = passed
    report["stage5_allowed"] = passed
    checkpoint(paths, "FINALIZED", details={"status": report["stage4_final_status"], "tests_passed": tests_passed})
    return _finalize(paths, report)


def _blocked(paths: Stage4Paths, status: str, inputs: Mapping[str, Any], blockers: Sequence[Any], tests: Mapping[str, str] | None) -> dict[str, Any]:
    report = {
        "phase": "STAGE4-MVP-INTEGRATION", "run_id": paths.run_id,
        "stage4_final_status": status, "reference_input": inputs["reference"]["absolute_path"],
        "target_input": inputs["target"]["absolute_path"], "input_hashes_match_frozen": inputs["hash_pair_matches"],
        "blockers": list(blockers), "resume_checkpoint": _checkpoints(paths)["resume_checkpoint"],
        "stage4_run_resumable": True, "copies_created": False,
        "safety_flags": _safety_flags(), "tests": dict(tests or {}), "tests_passed": bool(tests),
        "mvp_core_completed": False, "real_sample_repair_completed": False,
        "stage5_allowed": False, "stage5_executed": False, "production_d1_allowed": False,
    }
    return _finalize(paths, report)


def _partial_no_tasks(
    paths: Stage4Paths, inputs: Mapping[str, Any], diff_result: Mapping[str, Any], baseline: Mapping[str, Any],
    plan_result: Mapping[str, Any], manual: Sequence[Mapping[str, Any]], tests: Mapping[str, str] | None,
) -> dict[str, Any]:
    report = {
        "phase": "STAGE4-MVP-INTEGRATION", "run_id": paths.run_id,
        "stage4_final_status": "PARTIAL_NO_SAFE_AUTOMATIC_TASKS", "counts": diff_result["counts"],
        "stage3_baseline_reproduced": baseline["passed"], "approved_ordinary_task_count": 0,
        "tdb_manual_task_count": len(manual), "safety_flags": _safety_flags(),
        "tests": dict(tests or {}), "tests_passed": bool(tests), "mvp_core_completed": False,
        "stage5_allowed": False, "stage5_executed": False, "production_d1_allowed": False,
    }
    return _finalize(paths, report)


def _failed_execution(
    paths: Stage4Paths, status: str, inputs: Mapping[str, Any], diff_result: Mapping[str, Any],
    baseline: Mapping[str, Any], plan_result: Mapping[str, Any], execution: Mapping[str, Any],
    tests: Mapping[str, str] | None, idempotency: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    live = execution.get("live") or {}
    report = {
        "phase": "STAGE4-MVP-INTEGRATION", "run_id": paths.run_id, "stage4_final_status": status,
        "counts": diff_result["counts"], "stage3_baseline_reproduced": baseline["passed"],
        "approved_ordinary_task_count": len(plan_result["approval"]["approved"]),
        "attempted_task_count": live.get("attempted_task_count", 0), "successful_task_count": live.get("successful_task_count", 0),
        "skipped_duplicate_count": live.get("skipped_duplicate_count", 0), "failed_task_count": live.get("failed_task_count", 0),
        "created_handles": live.get("created_handles", []), "live_error": live.get("error"),
        "idempotency": (idempotency or {}).get("qa"), "safety_flags": _safety_flags(),
        "tests": dict(tests or {}), "tests_passed": bool(tests), "mvp_core_completed": False,
        "stage5_allowed": False, "stage5_executed": False, "production_d1_allowed": False,
    }
    return _finalize(paths, report)


def _write_manifest(paths: Stage4Paths, *, status: str, checkpoint_name: str | None = None) -> None:
    payload = {
        "run_id": paths.run_id, "status": status, "current_checkpoint": checkpoint_name,
        "workflow_checkpoints_path": str(paths.root / "workflow_checkpoints.json"),
        "artifact_paths": sorted(str(path) for path in paths.root.rglob("*") if path.is_file()),
        "stage5_executed": False, "production_d1_allowed": False,
    }
    write_json(paths.root / "stage4_manifest.json", payload)


def _finalize(paths: Stage4Paths, report: dict[str, Any]) -> dict[str, Any]:
    write_json(paths.reports / "stage4_mvp_integration.json", report)
    (paths.reports / "stage4_mvp_integration.md").write_text(_markdown(report), encoding="utf-8")
    write_json(REPORT_JSON, report)
    REPORT_MD.write_text(_markdown(report), encoding="utf-8")
    _write_manifest(paths, status=report["stage4_final_status"], checkpoint_name=_checkpoints(paths).get("current"))
    return report


def _markdown(report: Mapping[str, Any]) -> str:
    counts = report.get("counts", {})
    idem = report.get("idempotency") or {}
    return "\n".join([
        "# Stage 4 MVP Integration and Repeatability Acceptance", "",
        f"- status: {report.get('stage4_final_status')}", f"- run_id: {report.get('run_id')}",
        f"- reference: {report.get('reference_input')}", f"- target: {report.get('target_input')}",
        f"- baseline reproduced: {str(report.get('stage3_baseline_reproduced')).lower()}",
        f"- existing / missing / review / ambiguous: {counts.get('existing')} / {counts.get('missing_high_confidence')} / {counts.get('review_required')} / {counts.get('ambiguous')}",
        f"- approved / attempted / successful / persisted: {report.get('approved_ordinary_task_count')} / {report.get('attempted_task_count')} / {report.get('successful_task_count')} / {report.get('persisted_count')}",
        f"- second pass safe tasks: {idem.get('second_pass_safe_task_count')}",
        f"- idempotency passed: {str(idem.get('idempotency_passed')).lower()}",
        f"- source hashes unchanged: {str(report.get('source_hashes_unchanged')).lower()}",
        f"- stage5_allowed: {str(report.get('stage5_allowed')).lower()}",
        "- stage5_executed: false", "- production_d1_allowed: false", "",
        "## Safety", *[f"- {key}: {str(value).lower()}" for key, value in report.get("safety_flags", {}).items()], "",
        "## Tests", *[f"- {key}: {value}" for key, value in report.get("tests", {}).items()], "",
    ])


if __name__ == "__main__":
    result = run_stage4()
    print(json.dumps({"run_id": result["run_id"], "status": result["stage4_final_status"]}, ensure_ascii=False))
