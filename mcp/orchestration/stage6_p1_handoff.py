from __future__ import annotations

import json
import shutil
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from mcp.orchestration.stage6_p1 import P1Paths, _bbox2d, _read_json, _sha256, _write_json, validate_frozen_execution_plan
from mcp.orchestration.stage6_p1_override import (
    EXPECTED_PLAN_SHA256,
    EXPECTED_REFERENCE_SHA256,
    EXPECTED_TARGET_SHA256,
    MAIN_RUN_ID,
    ROOT,
    _bbox_intersects,
    _copy_and_move_with_provenance,
    _introduced_duplicates,
    _region_for_bbox,
)


HANDOFF_ROOT = ROOT / "artifacts" / "stage6_p1_handoff"


def _paths(run_id: str) -> dict[str, Path]:
    root = HANDOFF_ROOT / run_id
    return {
        "root": root,
        "inputs": root / "execution_inputs",
        "evidence": root / "evidence",
        "checkpoints": root / "checkpoints",
        "reports": root / "reports",
    }


def prepare_handoff(run_id: str | None = None) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    main = P1Paths.build(MAIN_RUN_ID)
    plan_path = main.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json"
    plan = _read_json(plan_path)
    valid, actual = validate_frozen_execution_plan(plan)
    if not valid or actual != EXPECTED_PLAN_SHA256 or len(plan.get("tasks", [])) != 4343:
        raise RuntimeError("frozen plan validation failed")
    emergency_report = _read_json(ROOT / "reports" / "stage6_p1_emergency_delivery.json")
    work_file = Path(emergency_report["override_dwg_path"])
    if _sha256(work_file) != EXPECTED_TARGET_SHA256:
        raise RuntimeError("working file is not clean target baseline")
    reference = Path(plan["frozen_inputs"]["reference"]["path"])
    if _sha256(reference) != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError("reference hash changed")
    run_id = run_id or datetime.now().strftime("stage6_p1_handoff_%Y%m%d_%H%M%S")
    paths = _paths(run_id)
    if paths["root"].exists():
        raise FileExistsError(paths["root"])
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    reference_copy = paths["inputs"] / "reference_execution_copy.dwg"
    shutil.copy2(reference, reference_copy)
    if _sha256(reference_copy) != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError("reference execution copy hash mismatch")
    manifest = {
        "phase": "STAGE6-P1-EMERGENCY-IN-MEMORY-HANDOFF",
        "status": "PREPARED_NOT_STARTED",
        "run_id": run_id,
        "main_run_id": MAIN_RUN_ID,
        "frozen_plan_path": str(plan_path),
        "frozen_plan_sha256": actual,
        "frozen_task_count": len(plan["tasks"]),
        "reference_path": str(reference),
        "reference_execution_copy": str(reference_copy),
        "work_file": str(work_file),
        "work_file_initial_hash": _sha256(work_file),
        "save_allowed": False,
        "save_as_allowed": False,
        "document_close_allowed": False,
        "production_d1_allowed": False,
    }
    _write_json(paths["root"] / "handoff_manifest.json", manifest)
    return manifest


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _bring_to_foreground(acad: Any) -> bool:
    import ctypes

    try:
        hwnd = int(acad.HWND)
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


def execute_handoff(run_id: str) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_2_native_clone_poc import _retry
    from mcp.orchestration.stage5_1_r3 import _existing_record_unchanged, _scan_modelspace, _snapshot

    paths = _paths(run_id)
    manifest = _read_json(paths["root"] / "handoff_manifest.json")
    plan = _read_json(Path(manifest["frozen_plan_path"]))
    valid, actual = validate_frozen_execution_plan(plan)
    if not valid or actual != EXPECTED_PLAN_SHA256:
        raise RuntimeError("frozen plan changed before execution")
    work_file = Path(manifest["work_file"])
    reference = Path(manifest["reference_path"])
    reference_copy = Path(manifest["reference_execution_copy"])
    if _sha256(work_file) != EXPECTED_TARGET_SHA256:
        raise RuntimeError("work file is no longer clean baseline")
    if _sha256(reference) != EXPECTED_REFERENCE_SHA256 or _sha256(reference_copy) != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError("reference integrity failed")

    main = P1Paths.build(MAIN_RUN_ID)
    region_manifest = _read_json(main.root / "region_manifest.json")
    target_regions = region_manifest["target_regions"]
    protected_bbox = plan["protected_region"]["bbox"]
    task_by_id = {str(task["task_id"]): task for task in plan["tasks"]}
    task_by_source = {str(task["source_entity_id"]).upper(): task for task in plan["tasks"]}
    task_source_handles = set(task_by_source)
    transforms = {item["alignment_id"]: item["transform"] for item in plan["alignment_evidence"]}
    component_plan = _read_json(Path(plan["core_component_dependency_plan"]["path"]))
    ordinary_by_transform: dict[str, list[str]] = defaultdict(list)
    for task in plan["tasks"]:
        if task["task_group"] == "ordinary":
            ordinary_by_transform[str(task["transform_id"])].append(str(task["source_entity_id"]).upper())

    acad = source_doc = target_doc = None
    provenance = []
    source_to_target: dict[str, str] = {}
    created_handles: list[str] = []
    initial_records = []
    after_records = []
    initial_snapshot = {}
    after_snapshot = {}
    existing_modified = []
    unexpected_new = []
    existing_deleted = []
    protected_modified = []
    protected_intersections = []
    duplicate_candidates = []
    wrong_region = []
    call_count = 0
    target_open = False
    target_unsaved = False
    foreground_requested = False
    active_document_name = None
    error = None
    automation_stopped = False
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (reference, work_file, reference_copy))
        if live.get("documents"):
            raise RuntimeError(f"AutoCAD has open documents; handoff requires a clean document set: {live['documents']}")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, work_file, _open_document_with_retry(acad, work_file))
        target_open = True
        initial_records = _retry(lambda: _scan_modelspace(target_doc, "stage6_handoff_before"), "handoff initial scan", attempts=60, delay=0.5)
        initial_snapshot = _snapshot(initial_records)
        _write_json(paths["checkpoints"] / "checkpoint_01_initial_scan.json", {
            "modelspace_count": len(initial_records), "work_file_hash": _sha256(work_file),
            "save_called": False, "close_called": False,
        })

        for transform_id, handles in sorted(ordinary_by_transform.items()):
            for batch_index, batch in enumerate(_chunks(sorted(handles), 200), 1):
                call_count += 1
                call = _copy_and_move_with_provenance(
                    source_doc, target_doc, batch, transforms[transform_id]["translation"],
                    call_id=f"copyobjects_{call_count:04d}",
                    label=f"ordinary {transform_id} batch {batch_index}",
                    task_ids=[task_by_source[handle]["task_id"] for handle in batch],
                    component_id=None,
                )
                provenance.append(call); created_handles.extend(call["primary_target_handles"])
                source_to_target.update({
                    str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper()
                    for pair in call["primary_pairs"]
                })
                _write_json(paths["checkpoints"] / "execution_progress.json", {
                    "copyobjects_call_count": call_count,
                    "mapped_task_count": len(task_source_handles & set(source_to_target)),
                    "save_called": False, "close_called": False,
                })

        valve_calls = []
        for component in component_plan["components"]:
            if component.get("status") != "READY":
                raise RuntimeError(f"component not ready: {component['component_id']}")
            for dependency in component.get("existing_source_to_target_dependencies", []):
                source_to_target[str(dependency["source_handle"]).upper()] = str(dependency["target_handle"]).upper()
            non_valves, valves = [], []
            for task_id in component["execution_order"]:
                task = task_by_id[task_id]
                (valves if task["object_name"] == "TDbPipeValve" else non_valves).append(str(task["source_entity_id"]).upper())
            if non_valves:
                call_count += 1
                transform_id = str(task_by_source[non_valves[0]]["transform_id"])
                call = _copy_and_move_with_provenance(
                    source_doc, target_doc, non_valves, transforms[transform_id]["translation"],
                    call_id=f"copyobjects_{call_count:04d}", label=component["component_id"],
                    task_ids=[task_by_source[handle]["task_id"] for handle in non_valves],
                    component_id=component["component_id"],
                )
                provenance.append(call); created_handles.extend(call["primary_target_handles"])
                source_to_target.update({
                    str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper()
                    for pair in call["primary_pairs"]
                })
            if valves:
                valve_calls.append((component, valves))
            _write_json(paths["checkpoints"] / "execution_progress.json", {
                "copyobjects_call_count": call_count,
                "mapped_task_count": len(task_source_handles & set(source_to_target)),
                "save_called": False, "close_called": False,
            })

        for component, valves in valve_calls:
            for source_handle in valves:
                call_count += 1
                task = task_by_source[source_handle]
                call = _copy_and_move_with_provenance(
                    source_doc, target_doc, [source_handle], transforms[str(task["transform_id"])]["translation"],
                    call_id=f"copyobjects_{call_count:04d}", label=f"Valve {source_handle}",
                    task_ids=[task["task_id"]], component_id=component["component_id"],
                )
                provenance.append(call); created_handles.extend(call["primary_target_handles"])
                source_to_target[source_handle] = call["primary_target_handles"][0]
                _write_json(paths["checkpoints"] / "execution_progress.json", {
                    "copyobjects_call_count": call_count,
                    "mapped_task_count": len(task_source_handles & set(source_to_target)),
                    "save_called": False, "close_called": False,
                })

        after_records = _retry(lambda: _scan_modelspace(target_doc, "stage6_handoff_after"), "handoff final scan", attempts=60, delay=0.5)
        after_snapshot = _snapshot(after_records)
        created_set = set(created_handles)
        existing_deleted = sorted(set(initial_snapshot) - set(after_snapshot))
        existing_modified = sorted(
            handle for handle, record in initial_snapshot.items()
            if handle in after_snapshot and not _existing_record_unchanged(record, after_snapshot[handle])
        )
        unexpected_new = sorted(set(after_snapshot) - set(initial_snapshot) - created_set)
        protected_initial = {
            handle for handle, record in initial_snapshot.items()
            if _bbox_intersects(_bbox2d(record), protected_bbox)
        }
        protected_modified = sorted(
            handle for handle in protected_initial
            if handle not in after_snapshot or not _existing_record_unchanged(initial_snapshot[handle], after_snapshot[handle])
        )
        protected_intersections = sorted(
            handle for handle in created_set | set(unexpected_new)
            if handle in after_snapshot and _bbox_intersects(_bbox2d(after_snapshot[handle]), protected_bbox)
        )
        duplicate_candidates = _introduced_duplicates(initial_snapshot, after_snapshot, created_set | set(unexpected_new))
        for source_handle, task in task_by_source.items():
            target_handle = source_to_target.get(source_handle)
            record = after_snapshot.get(target_handle or "")
            if record and _region_for_bbox(_bbox2d(record), target_regions) != task["target_region_id"]:
                wrong_region.append(task["task_id"])
        mapped_count = len(task_source_handles & set(source_to_target))
        if mapped_count != 4343:
            raise RuntimeError(f"mapped task count {mapped_count} != 4343")
        if existing_deleted:
            raise RuntimeError(f"existing_deleted={len(existing_deleted)}")
        if protected_modified:
            raise RuntimeError(f"protected_region_modified={len(protected_modified)}")
        if protected_intersections:
            raise RuntimeError(f"protected_region_intersection={len(protected_intersections)}")
        _write_json(paths["evidence"] / "copyobjects_provenance.json", {"calls": provenance})
        _write_json(paths["evidence"] / "in_memory_snapshot.json", {"records": after_records})
        target_doc.Activate()
        target_unsaved = bool(not target_doc.Saved)
        active_document_name = str(acad.ActiveDocument.Name)
        foreground_requested = _bring_to_foreground(acad)
        result = {
            "phase": "STAGE6-P1-EMERGENCY-IN-MEMORY-HANDOFF",
            "status": "EMERGENCY_IN_MEMORY_HANDOFF_READY",
            "run_id": run_id,
            "active_document_name": active_document_name,
            "work_file": str(work_file),
            "frozen_plan_sha256": actual,
            "executed_task_count": mapped_count,
            "document_open_in_autocad": True,
            "document_unsaved": target_unsaved,
            "existing_modified": len(existing_modified),
            "unexpected_new": len(unexpected_new),
            "duplicate_candidate_count": len(duplicate_candidates),
            "wrong_region_write": len(wrong_region),
            "existing_deleted": len(existing_deleted),
            "protected_region_modified": len(protected_modified),
            "protected_region_intersection": len(protected_intersections),
            "pump_room_unchanged": not protected_modified and not protected_intersections,
            "save_called": False,
            "save_as_called": False,
            "close_called": False,
            "foreground_requested": foreground_requested,
            "disk_work_file_hash_unchanged": _sha256(work_file) == EXPECTED_TARGET_SHA256,
            "reference_hash_unchanged": _sha256(reference) == EXPECTED_REFERENCE_SHA256,
            "automatic_operations_stopped": True,
            "production_d1_allowed": False,
        }
        _write_json(paths["reports"] / "handoff_result.json", result)
        _write_json(ROOT / "reports" / "stage6_p1_emergency_in_memory_handoff.json", result)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if target_doc is not None:
            try:
                target_doc.Activate()
                active_document_name = str(acad.ActiveDocument.Name)
                target_open = True
                target_unsaved = bool(not target_doc.Saved)
                foreground_requested = _bring_to_foreground(acad)
            except Exception:
                pass
        result = {
            "phase": "STAGE6-P1-EMERGENCY-IN-MEMORY-HANDOFF",
            "status": "FAILED_IN_MEMORY_HANDOFF",
            "run_id": run_id,
            "active_document_name": active_document_name,
            "executed_task_count": len(task_source_handles & set(source_to_target)),
            "document_open_in_autocad": target_open,
            "document_unsaved": target_unsaved,
            "existing_deleted": len(existing_deleted),
            "protected_region_modified": len(protected_modified),
            "save_called": False,
            "save_as_called": False,
            "close_called": False,
            "error": error,
            "automatic_operations_stopped": True,
            "production_d1_allowed": False,
        }
        _write_json(paths["reports"] / "handoff_result.json", result)
    finally:
        if acad is not None:
            detach_autocad()
        automation_stopped = True
    result["automatic_operations_stopped"] = automation_stopped
    return result

