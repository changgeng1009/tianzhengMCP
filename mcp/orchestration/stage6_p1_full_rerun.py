from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.orchestration.stage6_p1 import (
    P1Paths,
    _bbox2d,
    _read_json,
    _sha256,
    validate_frozen_execution_plan,
)
from mcp.orchestration.stage6_p1_override import (
    EXPECTED_PLAN_SHA256,
    EXPECTED_REFERENCE_SHA256,
    EXPECTED_TARGET_SHA256,
    MAIN_RUN_ID,
    ROOT,
    _bbox_intersects,
    _introduced_duplicates,
    _region_for_bbox,
)


RUN_ROOT = ROOT / "artifacts" / "stage6_p1_full_rerun"
WORK_FILE_NAME = "target_sample-应急提交版-R2.dwg"
KNOWN_IDPAIR_SOURCES = {"B04C6", "B04C7", "B04C8"}


class HardStop(RuntimeError):
    pass


def _paths(run_id: str) -> dict[str, Path]:
    root = RUN_ROOT / run_id
    return {
        "root": root,
        "inputs": root / "execution_inputs",
        "checkpoints": root / "checkpoints",
        "calls": root / "copyobjects_calls",
        "reports": root / "reports",
        "evidence": root / "evidence",
    }


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _modelspace_handles(document: Any) -> set[str]:
    return {
        str(document.ModelSpace.Item(index).Handle).upper()
        for index in range(int(document.ModelSpace.Count))
    }


def _owner_record(document: Any, native: Any) -> dict[str, Any]:
    try:
        owner = document.ObjectIDToObject(int(native.OwnerID))
        return {
            "handle": str(getattr(owner, "Handle", "")).upper(),
            "object_name": str(getattr(owner, "ObjectName", "")),
            "name": str(getattr(owner, "Name", "")),
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _native_record(document: Any, handle: str, role: str) -> dict[str, Any]:
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _scan_native

    native = _retry(lambda: document.HandleToObject(handle), f"{role} {handle} lookup")
    record = _scan_native(native, role)
    record["handle"] = str(record.get("handle") or handle).upper()
    record["owner"] = _owner_record(document, native)
    return record


def _close_without_save(document: Any | None) -> bool:
    if document is None:
        return False
    try:
        document.Close(False)
        return True
    except Exception:
        return False


def _bring_to_foreground(acad: Any) -> bool:
    import ctypes

    try:
        hwnd = int(acad.HWND)
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


def _bbox_close(left: Sequence[float] | None, right: Sequence[float] | None, tolerance: float = 1e-5) -> bool:
    if left is None or right is None or len(left) != len(right):
        return False
    return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))


def _candidate_matches(source: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    if source.get("object_name") != candidate.get("object_name"):
        return False
    if source.get("owner", {}).get("object_name") != candidate.get("owner", {}).get("object_name"):
        return False
    if not _bbox_close(_bbox2d(source), _bbox2d(candidate)):
        return False
    source_geometry = source.get("geometry") or {}
    candidate_geometry = candidate.get("geometry") or {}
    return not source_geometry or source_geometry == candidate_geometry


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _build_state(
    *,
    all_task_ids: set[str],
    completed_task_ids: set[str],
    skipped_task_ids: set[str],
    manual_tasks: list[dict[str, Any]],
    source_to_target: Mapping[str, str],
    created_handles: set[str],
    call_count: int,
    current_task_index: int,
    current_component_index: int,
) -> dict[str, Any]:
    pending = sorted(all_task_ids - completed_task_ids - skipped_task_ids)
    return {
        "completed_task_count": len(completed_task_ids),
        "pending_task_count": len(pending),
        "skipped_task_count": len(skipped_task_ids),
        "completed_task_ids": sorted(completed_task_ids),
        "pending_task_ids": pending,
        "skipped_task_ids": sorted(skipped_task_ids),
        "manual_completion_required": manual_tasks,
        "source_to_target_handle_map": dict(sorted(source_to_target.items())),
        "created_handles": sorted(created_handles),
        "copyobjects_call_count": call_count,
        "current_task_index": current_task_index,
        "current_component_index": current_component_index,
        "save_called": False,
        "save_as_called": False,
        "close_called": False,
    }


def _write_state(paths: Mapping[str, Path], state: Mapping[str, Any], checkpoint_name: str | None = None) -> None:
    _atomic_json(paths["checkpoints"] / "execution_state.json", state)
    if checkpoint_name:
        _atomic_json(paths["checkpoints"] / checkpoint_name, state)


def prepare_full_rerun(run_id: str | None = None) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    main = P1Paths.build(MAIN_RUN_ID)
    plan_path = main.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json"
    plan = _read_json(plan_path)
    valid, plan_sha256 = validate_frozen_execution_plan(plan)
    if not valid or plan_sha256 != EXPECTED_PLAN_SHA256 or len(plan.get("tasks", [])) != 4343:
        raise RuntimeError("frozen plan validation failed")
    frozen = plan["frozen_inputs"]
    reference = Path(frozen["reference"]["path"])
    target = Path(frozen["target"]["path"])
    backup = Path(frozen["prewrite_backup"]["path"])
    actual_hashes = {
        "reference": _sha256(reference),
        "target": _sha256(target),
        "prewrite_backup": _sha256(backup),
    }
    expected_hashes = {
        "reference": EXPECTED_REFERENCE_SHA256,
        "target": EXPECTED_TARGET_SHA256,
        "prewrite_backup": EXPECTED_TARGET_SHA256,
    }
    if actual_hashes != expected_hashes:
        raise RuntimeError(f"input hash mismatch: {actual_hashes}")
    run_id = run_id or datetime.now().strftime("stage6_p1_full_rerun_%Y%m%d_%H%M%S")
    paths = _paths(run_id)
    if paths["root"].exists():
        raise FileExistsError(paths["root"])
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    work_file = target.parent / WORK_FILE_NAME
    if work_file.exists():
        raise FileExistsError(work_file)
    reference_copy = paths["inputs"] / "reference_execution_copy.dwg"
    shutil.copy2(reference, reference_copy)
    shutil.copy2(backup, work_file)
    if _sha256(reference_copy) != EXPECTED_REFERENCE_SHA256 or _sha256(work_file) != EXPECTED_TARGET_SHA256:
        raise RuntimeError("execution copy hash mismatch")
    manifest = {
        "phase": "STAGE6-P1-EMERGENCY-FULL-CLEAN-RERUN",
        "status": "PREPARED_NOT_STARTED",
        "run_id": run_id,
        "frozen_plan_path": str(plan_path),
        "frozen_plan_sha256": plan_sha256,
        "total_tasks": len(plan["tasks"]),
        "reference_original": str(reference),
        "target_original": str(target),
        "prewrite_backup": str(backup),
        "reference_execution_copy": str(reference_copy),
        "work_file": str(work_file),
        "new_work_copy_initial_hash": _sha256(work_file),
        "input_hashes": actual_hashes,
        "save_allowed": False,
        "save_as_allowed": False,
        "success_close_allowed": False,
        "production_d1_allowed": False,
    }
    _atomic_json(paths["root"] / "manifest.json", manifest)
    return manifest


def execute_full_rerun(run_id: str) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_1_valve_component_diagnostics import (
        _copyobjects_with_explicit_idpairs,
        _parse_copyobjects_return,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _scan_native, _variant
    from mcp.orchestration.stage5_1_r3 import _existing_record_unchanged, _scan_modelspace, _snapshot

    paths = _paths(run_id)
    manifest = _read_json(paths["root"] / "manifest.json")
    plan = _read_json(Path(manifest["frozen_plan_path"]))
    valid, actual_plan_sha256 = validate_frozen_execution_plan(plan)
    if not valid or actual_plan_sha256 != EXPECTED_PLAN_SHA256:
        raise RuntimeError("frozen plan changed before execution")
    reference_original = Path(manifest["reference_original"])
    target_original = Path(manifest["target_original"])
    backup = Path(manifest["prewrite_backup"])
    reference_copy = Path(manifest["reference_execution_copy"])
    work_file = Path(manifest["work_file"])
    expected_inputs = {
        reference_original: EXPECTED_REFERENCE_SHA256,
        target_original: EXPECTED_TARGET_SHA256,
        backup: EXPECTED_TARGET_SHA256,
        reference_copy: EXPECTED_REFERENCE_SHA256,
        work_file: EXPECTED_TARGET_SHA256,
    }
    if any(_sha256(path) != expected for path, expected in expected_inputs.items()):
        raise RuntimeError("pre-execution input integrity failed")

    main = P1Paths.build(MAIN_RUN_ID)
    region_manifest = _read_json(main.root / "region_manifest.json")
    target_regions = region_manifest["target_regions"]
    protected_bbox = plan["protected_region"]["bbox"]
    tasks = list(plan["tasks"])
    task_by_id = {str(task["task_id"]): task for task in tasks}
    task_by_source = {str(task["source_entity_id"]).upper(): task for task in tasks}
    all_task_ids = set(task_by_id)
    transforms = {item["alignment_id"]: item["transform"] for item in plan["alignment_evidence"]}
    component_plan = _read_json(Path(plan["core_component_dependency_plan"]["path"]))
    ordinary_by_transform: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        if task["task_group"] == "ordinary":
            ordinary_by_transform[str(task["transform_id"])].append(str(task["source_entity_id"]).upper())

    acad = source_doc = target_doc = None
    completed_task_ids: set[str] = set()
    skipped_task_ids: set[str] = set()
    manual_tasks: list[dict[str, Any]] = []
    source_to_target: dict[str, str] = {}
    created_handles: set[str] = set()
    call_count = 0
    current_component_index = 0
    current_task_index = 0
    initial_records: list[dict[str, Any]] = []
    hard_stop = False
    hard_stop_close_called = False
    foreground_requested = False

    def persist(checkpoint_name: str | None = None) -> None:
        state = _build_state(
            all_task_ids=all_task_ids,
            completed_task_ids=completed_task_ids,
            skipped_task_ids=skipped_task_ids,
            manual_tasks=manual_tasks,
            source_to_target=source_to_target,
            created_handles=created_handles,
            call_count=call_count,
            current_task_index=current_task_index,
            current_component_index=current_component_index,
        )
        _write_state(paths, state, checkpoint_name)

    def mark_manual(source_handle: str, reason: str, call_id: str, component_id: str | None) -> None:
        task = task_by_source[source_handle]
        skipped_task_ids.add(str(task["task_id"]))
        manual_tasks.append({
            "task_id": task["task_id"],
            "source_handle": source_handle,
            "object_name": task["object_name"],
            "component_id": component_id,
            "region_id": task["target_region_id"],
            "transform_id": task["transform_id"],
            "status": "MANUAL_COMPLETION_REQUIRED",
            "reason": reason,
            "copyobjects_call_id": call_id,
        })

    def clone_call(source_handles: list[str], *, label: str, component_id: str | None) -> dict[str, Any]:
        nonlocal call_count, current_task_index
        call_count += 1
        call_id = f"copyobjects_{call_count:04d}"
        before_handles = _modelspace_handles(target_doc)
        source_records = {handle: _native_record(source_doc, handle, f"{call_id}_source") for handle in source_handles}
        objects = [_retry(lambda value=handle: source_doc.HandleToObject(value), f"{label} source {handle}") for handle in source_handles]
        returned = _retry(
            lambda: _copyobjects_with_explicit_idpairs(source_doc, objects, target_doc.ModelSpace),
            f"{label} CopyObjects", attempts=30, delay=0.5,
        )
        parsed = _parse_copyobjects_return(returned, source_doc, target_doc)
        after_handles = _modelspace_handles(target_doc)
        new_handles = sorted(after_handles - before_handles)
        all_pairs = [dict(pair) for pair in parsed.get("idpairs", [])]
        expected = set(source_handles)
        primary_pairs = [
            pair for pair in all_pairs
            if str(pair.get("source_handle") or "").upper() in expected
            and pair.get("target_handle") and pair.get("IsCloned") is not False
        ]
        by_source = {str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper() for pair in primary_pairs}
        candidate_records = {
            handle: _native_record(target_doc, handle, f"{call_id}_candidate")
            for handle in new_handles
        }
        claimed = {
            str(pair["target_handle"]).upper()
            for pair in all_pairs if pair.get("target_handle")
        }
        recovery: list[dict[str, Any]] = []
        for source_handle in sorted(expected - set(by_source)):
            candidates = [
                handle for handle, record in candidate_records.items()
                if handle not in claimed and _candidate_matches(source_records[source_handle], record)
            ]
            if len(candidates) == 1:
                target_handle = candidates[0]
                by_source[source_handle] = target_handle
                claimed.add(target_handle)
                recovery.append({
                    "source_handle": source_handle,
                    "target_handle": target_handle,
                    "mapping_role": "PRIMARY_RECOVERED_EXACT_CALL_DIFF",
                    "candidate_count": 1,
                })
            else:
                recovery.append({
                    "source_handle": source_handle,
                    "target_handle": None,
                    "mapping_role": "MANUAL_COMPLETION_REQUIRED",
                    "candidate_count": len(candidates),
                    "candidate_handles": candidates,
                })
                mark_manual(source_handle, f"primary IDPair missing; exact call diff candidates={len(candidates)}", call_id, component_id)
        vector = [
            float(transforms[str(task_by_source[source_handles[0]]["transform_id"])]["translation"][0]),
            float(transforms[str(task_by_source[source_handles[0]]["transform_id"])]["translation"][1]),
            0.0,
        ]
        completed_in_call = []
        for source_handle in sorted(by_source):
            target_handle = by_source[source_handle]
            native = _retry(lambda value=target_handle: target_doc.HandleToObject(value), f"{label} target {target_handle}")
            _retry(lambda value=native: value.Move(_variant([0.0, 0.0, 0.0]), _variant(vector)), f"{label} target {target_handle} move", attempts=30, delay=0.5)
            moved_record = _scan_native(native, f"{call_id}_moved")
            if _bbox_intersects(_bbox2d(moved_record), protected_bbox):
                raise HardStop(f"protected_region_intersection in {call_id} target {target_handle}")
            source_to_target[source_handle] = target_handle
            created_handles.add(target_handle)
            task_id = str(task_by_source[source_handle]["task_id"])
            completed_task_ids.add(task_id)
            completed_in_call.append(task_id)
        current_task_index = len(completed_task_ids) + len(skipped_task_ids)
        trace = {
            "call_id": call_id,
            "label": label,
            "component_id": component_id,
            "region_id": task_by_source[source_handles[0]]["target_region_id"],
            "transform_id": task_by_source[source_handles[0]]["transform_id"],
            "task_ids": [task_by_source[handle]["task_id"] for handle in source_handles],
            "expected_source_handles": source_handles,
            "before_handle_count": len(before_handles),
            "after_handle_count": len(after_handles),
            "new_handles": new_handles,
            "primary_return_records": parsed.get("primary_return_records", []),
            "returned_idpairs": all_pairs,
            "primary_pairs": primary_pairs,
            "recovery": recovery,
            "completed_task_ids": completed_in_call,
            "translation": vector,
        }
        _atomic_json(paths["calls"] / f"{call_id}.json", trace)
        persist()
        if current_task_index // 100 > (current_task_index - len(source_handles)) // 100:
            persist(f"progress_{current_task_index:04d}.json")
        return trace

    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (reference_original, target_original, reference_copy, work_file))
        if live.get("documents"):
            raise HardStop(f"AutoCAD document set not empty: {live['documents']}")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, work_file, _open_document_with_retry(acad, work_file))
        initial_records = _retry(lambda: _scan_modelspace(target_doc, "stage6_r2_before"), "R2 initial scan", attempts=60, delay=0.5)
        initial_snapshot = _snapshot(initial_records)
        persist("checkpoint_0000_initial.json")

        for transform_id, handles in sorted(ordinary_by_transform.items()):
            for batch_index, batch in enumerate(_chunks(sorted(handles), 200), 1):
                clone_call(batch, label=f"ordinary {transform_id} batch {batch_index}", component_id=None)

        valve_queue: list[tuple[dict[str, Any], list[str]]] = []
        for component_index, component in enumerate(component_plan["components"], 1):
            current_component_index = component_index
            if component.get("status") != "READY":
                for task_id in component.get("execution_order", []):
                    task = task_by_id[task_id]
                    mark_manual(str(task["source_entity_id"]).upper(), "component is not READY", "not_called", component["component_id"])
                persist(f"component_{component_index:04d}.json")
                continue
            for dependency in component.get("existing_source_to_target_dependencies", []):
                source_to_target[str(dependency["source_handle"]).upper()] = str(dependency["target_handle"]).upper()
            non_valves, valves = [], []
            for task_id in component["execution_order"]:
                task = task_by_id[task_id]
                handle = str(task["source_entity_id"]).upper()
                (valves if task["object_name"] == "TDbPipeValve" else non_valves).append(handle)
            if non_valves:
                trace = clone_call(non_valves, label=component["component_id"], component_id=component["component_id"])
                if any(item["mapping_role"] == "MANUAL_COMPLETION_REQUIRED" for item in trace["recovery"]):
                    for handle in valves:
                        mark_manual(handle, "component dependency closure incomplete", "not_called", component["component_id"])
                else:
                    valve_queue.append((component, valves))
            else:
                valve_queue.append((component, valves))
            persist(f"component_{component_index:04d}.json")

        for component, valves in valve_queue:
            for source_handle in valves:
                clone_call([source_handle], label=f"Valve {source_handle}", component_id=component["component_id"])

        after_records = _retry(lambda: _scan_modelspace(target_doc, "stage6_r2_after"), "R2 final scan", attempts=60, delay=0.5)
        after_snapshot = _snapshot(after_records)
        existing_deleted = sorted(set(initial_snapshot) - set(after_snapshot))
        existing_modified = sorted(
            handle for handle, record in initial_snapshot.items()
            if handle in after_snapshot and not _existing_record_unchanged(record, after_snapshot[handle])
        )
        unexpected_new = sorted(set(after_snapshot) - set(initial_snapshot) - created_handles)
        protected_initial = {
            handle for handle, record in initial_snapshot.items()
            if _bbox_intersects(_bbox2d(record), protected_bbox)
        }
        protected_modified = sorted(
            handle for handle in protected_initial
            if handle not in after_snapshot or not _existing_record_unchanged(initial_snapshot[handle], after_snapshot[handle])
        )
        protected_intersections = sorted(
            handle for handle in created_handles | set(unexpected_new)
            if handle in after_snapshot and _bbox_intersects(_bbox2d(after_snapshot[handle]), protected_bbox)
        )
        if existing_deleted:
            raise HardStop(f"existing_deleted={len(existing_deleted)}")
        if protected_modified:
            raise HardStop(f"protected_region_modified={len(protected_modified)}")
        if protected_intersections:
            raise HardStop(f"protected_region_intersection={len(protected_intersections)}")
        duplicate_candidates = _introduced_duplicates(initial_snapshot, after_snapshot, created_handles | set(unexpected_new))
        wrong_region = []
        for source_handle, target_handle in source_to_target.items():
            task = task_by_source.get(source_handle)
            record = after_snapshot.get(target_handle)
            if task and record and _region_for_bbox(_bbox2d(record), target_regions) != task["target_region_id"]:
                wrong_region.append(task["task_id"])
        persist("checkpoint_final.json")
        _atomic_json(paths["evidence"] / "final_object_lists.json", {
            "existing_modified": existing_modified,
            "unexpected_new": unexpected_new,
            "duplicate_candidates": duplicate_candidates,
            "wrong_region_write": wrong_region,
            "existing_deleted": existing_deleted,
            "protected_region_modified": protected_modified,
            "protected_region_intersection": protected_intersections,
        })
        target_doc.Activate()
        document_modified = bool(not target_doc.Saved)
        foreground_requested = _bring_to_foreground(acad)
        status = "EMERGENCY_FULL_RERUN_HANDOFF_READY_WITH_MANUAL_TASKS" if manual_tasks else "EMERGENCY_FULL_RERUN_HANDOFF_READY"
        result = {
            "phase": "STAGE6-P1-EMERGENCY-FULL-CLEAN-RERUN",
            "status": status,
            "run_id": run_id,
            "work_file": str(work_file),
            "new_work_copy_initial_hash": manifest["new_work_copy_initial_hash"],
            "total_tasks": len(tasks),
            "completed_task_count": len(completed_task_ids),
            "uncompleted_task_count": len(all_task_ids - completed_task_ids),
            "manual_completion_required": manual_tasks,
            "known_idpair_results": [item for item in manual_tasks if item["source_handle"] in KNOWN_IDPAIR_SOURCES] + [
                {"task_id": task_by_source[handle]["task_id"], "source_handle": handle, "status": "COMPLETED", "target_handle": source_to_target[handle]}
                for handle in sorted(KNOWN_IDPAIR_SOURCES & set(source_to_target))
            ],
            "complete_checkpoint_generated": True,
            "existing_modified": len(existing_modified),
            "unexpected_new": len(unexpected_new),
            "duplicate_candidates": len(duplicate_candidates),
            "wrong_region_write": len(wrong_region),
            "existing_deleted": 0,
            "protected_region_modified": 0,
            "protected_region_intersection": 0,
            "water_pump_room_unchanged": True,
            "document_modified": document_modified,
            "document_open": True,
            "save_called": False,
            "save_as_called": False,
            "close_called": False,
            "foreground_requested": foreground_requested,
            "automatic_operations_stopped": True,
            "reference_hash_unchanged": _sha256(reference_original) == EXPECTED_REFERENCE_SHA256,
            "target_hash_unchanged": _sha256(target_original) == EXPECTED_TARGET_SHA256,
            "backup_hash_unchanged": _sha256(backup) == EXPECTED_TARGET_SHA256,
            "production_d1_allowed": False,
        }
        _atomic_json(paths["reports"] / "result.json", result)
        _atomic_json(ROOT / "reports" / "stage6_p1_emergency_full_clean_rerun.json", result)
        return result
    except Exception as exc:
        hard_stop = True
        hard_stop_close_called = _close_without_save(target_doc)
        _close_without_save(source_doc)
        result = {
            "phase": "STAGE6-P1-EMERGENCY-FULL-CLEAN-RERUN",
            "status": "FAILED_FULL_RERUN_HARD_STOP",
            "run_id": run_id,
            "work_file": str(work_file),
            "total_tasks": len(tasks),
            "completed_task_count": len(completed_task_ids),
            "uncompleted_task_count": len(all_task_ids - completed_task_ids),
            "manual_completion_required": manual_tasks,
            "error": f"{type(exc).__name__}: {exc}",
            "hard_stop": hard_stop,
            "hard_stop_close_called": hard_stop_close_called,
            "save_called": False,
            "save_as_called": False,
            "production_d1_allowed": False,
        }
        persist("checkpoint_failed.json")
        _atomic_json(paths["reports"] / "result.json", result)
        _atomic_json(ROOT / "reports" / "stage6_p1_emergency_full_clean_rerun.json", result)
        return result
    finally:
        if acad is not None:
            detach_autocad()


def run_full_rerun() -> dict[str, Any]:
    manifest = prepare_full_rerun()
    return execute_full_rerun(str(manifest["run_id"]))
