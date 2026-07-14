"""Stage 6-P4.1 仅针对既有实验副本的分批 CopyObjects 执行器。"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.acceptance.stage3_1_runtime import (
    _close_document_without_save, _norm_path, _open_document_with_retry,
    _resolve_open_document, attach_existing_autocad, detach_autocad,
    enumerate_live_documents, sha256_file,
)
from mcp.acceptance.stage5_1_valve_component_diagnostics import (
    _copyobjects_with_explicit_idpairs, _parse_copyobjects_return,
)
from mcp.acceptance.stage5_2_native_clone_poc import _retry, _scan_native, _variant
from mcp.orchestration.stage6_p3_p4_controlled_candidate import _bbox_flat, bbox_intersects, payload_sha256, write_json, write_jsonl
from mcp.orchestration.stage6_p4_1_whole_drawing_completion import L3_APPROVAL_PHRASE, manual_save_handoff


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_execution_inputs(plan: Mapping[str, Any], reference: Path, target: Path, candidate: Path, backup: Path, expected_reference_hash: str, expected_target_hash: str, approval_text: str) -> list[str]:
    errors = []
    if L3_APPROVAL_PHRASE not in approval_text:
        errors.append("L3_APPROVAL_PHRASE_MISSING")
    if payload_sha256(plan) != plan.get("plan_sha256"):
        errors.append("PLAN_HASH_MISMATCH")
    if plan.get("old_4068_frozen_plan_reused") is not False:
        errors.append("OLD_PLAN_REUSE_FORBIDDEN")
    if sha256_file(reference) != expected_reference_hash:
        errors.append("REFERENCE_HASH_MISMATCH")
    if sha256_file(target) != expected_target_hash:
        errors.append("TARGET_HASH_MISMATCH")
    if not candidate.is_file() or not backup.is_file():
        errors.append("CANDIDATE_OR_BACKUP_MISSING")
    elif sha256_file(candidate) != expected_target_hash or sha256_file(backup) != expected_target_hash:
        errors.append("CANDIDATE_NOT_CLEAN_BASELINE")
    if len({_norm_path(reference), _norm_path(target), _norm_path(candidate), _norm_path(backup)}) != 4:
        errors.append("PATH_ISOLATION_FAILED")
    return errors


def ordered_batches(tasks: Sequence[Mapping[str, Any]], tdb_batch_size: int = 50, ordinary_batch_size: int = 100) -> list[dict[str, Any]]:
    groups: dict[tuple[int, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for task in tasks:
        name = str(task["object_name"])
        priority = 0 if name.startswith("AcDb") else 2
        groups[(priority, str(task["target_region_id"]), name)].append(task)
    batches = []
    for key in sorted(groups):
        values = sorted(groups[key], key=lambda item: item["task_id"])
        size = ordinary_batch_size if key[2].startswith("AcDb") else tdb_batch_size
        for offset in range(0, len(values), size):
            batches.append({
                "batch_id": f"p4_1_batch_{len(batches)+1:04d}",
                "priority": key[0], "target_region_id": key[1], "object_name": key[2],
                "tasks": values[offset:offset+size],
            })
    return batches


def _bbox_close(actual: Sequence[float] | None, expected: Sequence[float] | None, tolerance: float = 5.0) -> bool:
    return bool(actual and expected and len(actual) == len(expected) and all(math.isclose(float(a), float(b), abs_tol=tolerance, rel_tol=0) for a, b in zip(actual, expected)))


def _resolve_batch_mapping(parsed: Mapping[str, Any], tasks: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    expected = {str(task["reference_handle"]).upper() for task in tasks}
    mapping = {
        str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper()
        for pair in parsed.get("idpairs", [])
        if pair.get("source_handle") and pair.get("target_handle") and str(pair["source_handle"]).upper() in expected
    }
    if len(mapping) != len(expected):
        primaries = [item for item in parsed.get("primary_return_records", []) if item.get("handle")]
        if len(primaries) == len(tasks):
            for task, primary in zip(tasks, primaries):
                mapping.setdefault(str(task["reference_handle"]).upper(), str(primary["handle"]).upper())
    return mapping


def execute_batch(source_doc: Any, candidate_doc: Any, batch: Mapping[str, Any], protected_bboxes: Sequence[Sequence[float]]) -> dict[str, Any]:
    tasks = list(batch["tasks"])
    source_objects = [_retry(lambda h=task["reference_handle"]: source_doc.HandleToObject(h), f"source Handle {task['reference_handle']}") for task in tasks]
    returned = _retry(lambda: _copyobjects_with_explicit_idpairs(source_doc, source_objects, candidate_doc.ModelSpace), f"{batch['batch_id']} CopyObjects", attempts=30, delay=0.5)
    parsed = _parse_copyobjects_return(returned, source_doc, candidate_doc)
    mapping = _resolve_batch_mapping(parsed, tasks)
    if len(mapping) != len(tasks):
        raise RuntimeError(f"PRIMARY_MAPPING_INCOMPLETE:{len(mapping)}/{len(tasks)}")
    records = []
    for task in tasks:
        source_handle = str(task["reference_handle"]).upper()
        target_handle = mapping[source_handle]
        created = _retry(lambda h=target_handle: candidate_doc.HandleToObject(h), f"created Handle {target_handle}")
        tx, ty = float(task["transform"]["x"]), float(task["transform"]["y"])
        _retry(lambda obj=created: obj.Move(_variant([0.0, 0.0, 0.0]), _variant([tx, ty, 0.0])), f"move {target_handle}", attempts=30, delay=0.5)
        scanned = _scan_native(created, "stage6_p4_1_candidate")
        bbox = _bbox_flat(scanned)
        if bbox and any(bbox_intersects(bbox, protected) for protected in protected_bboxes):
            raise RuntimeError(f"PROTECTED_REGION_INTERSECTION:{target_handle}")
        display_bbox_review = False
        if not _bbox_close(bbox, task.get("expected_target_bbox")) and task["object_name"] not in {"TDbSymbMultiLeader", "TDbVPipeDim"}:
            raise RuntimeError(f"TRANSFORMED_BBOX_MISMATCH:{target_handle}")
        if not _bbox_close(bbox, task.get("expected_target_bbox")):
            display_bbox_review = True
        records.append({
            "task_id": task["task_id"], "reference_handle": source_handle,
            "new_target_handle": target_handle, "object_name": scanned.get("object_name"),
            "layer": scanned.get("layer"), "region_id": task["target_region_id"],
            "copy_method": "Document.CopyObjects", "transform_applied": True,
            "copy_status": "SUCCESS", "native_object_preserved": scanned.get("object_name") == task["object_name"],
            "visual_fallback_object": False, "bbox": bbox,
            "display_bbox_review_required": display_bbox_review,
        })
    return {"records": records, "parsed_return": parsed}


def execute(*, run_root: Path, reference: Path, original_target: Path, candidate: Path, backup: Path, p2_run: Path, expected_reference_hash: str, expected_target_hash: str, approval_text: str, resume_records: Sequence[Mapping[str, Any]] = (), completed_batch_count: int = 0) -> dict[str, Any]:
    plan_path = run_root / "frozen_plan" / "whole_drawing_write_plan.json"
    plan = read_json(plan_path)
    errors = validate_execution_inputs(plan, reference, original_target, candidate, backup, expected_reference_hash, expected_target_hash, approval_text)
    if completed_batch_count and "CANDIDATE_NOT_CLEAN_BASELINE" in errors:
        errors.remove("CANDIDATE_NOT_CLEAN_BASELINE")
    if errors:
        raise RuntimeError(";".join(errors))
    protected_bboxes = [item["frame_bbox"] for item in read_json(p2_run / "protected_regions.json")["regions"]]
    batches = ordered_batches(plan["tasks"])
    execution_dir = run_root / "execution"
    execution_dir.mkdir(exist_ok=True)
    write_json(execution_dir / "batch_manifest.json", {"batch_count": len(batches), "task_count": len(plan["tasks"]), "batches": [{k:v for k,v in batch.items() if k != "tasks"} | {"task_count":len(batch["tasks"])} for batch in batches]})
    acad = source_doc = candidate_doc = None
    all_records: list[dict[str, Any]] = [dict(item) for item in resume_records]
    batch_results: list[dict[str, Any]] = []
    failed_regions: set[str] = set()
    manual_state = None
    object_count_before = 0
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (reference, original_target, candidate, backup))
        if live["documents"]:
            raise RuntimeError(f"AUTOCAD_INSTANCE_CONFLICT:{live['documents']}")
        source_doc = _resolve_open_document(acad, reference, _open_document_with_retry(acad, reference))
        candidate_doc = _resolve_open_document(acad, candidate, _retry(lambda: acad.Documents.Open(str(candidate), False), "open writable candidate", attempts=30, delay=0.5))
        if _norm_path(Path(str(candidate_doc.FullName))) != _norm_path(candidate) or bool(candidate_doc.ReadOnly):
            raise RuntimeError("ACTIVE_DOCUMENT_NOT_WRITABLE_EXPERIMENTAL_COPY")
        object_count_before = int(candidate_doc.ModelSpace.Count) - len(all_records)
        for index, batch in enumerate(batches, 1):
            if index <= completed_batch_count:
                continue
            region = batch["target_region_id"]
            if region in failed_regions:
                batch_results.append({"batch_id": batch["batch_id"], "status": "SKIPPED_REGION_AFTER_FAILURE", "task_count": len(batch["tasks"])})
                continue
            try:
                outcome = execute_batch(source_doc, candidate_doc, batch, protected_bboxes)
                try:
                    _retry(lambda: candidate_doc.Save(), f"{batch['batch_id']} save", attempts=10, delay=0.5)
                except Exception as save_exc:
                    manual_state = manual_save_handoff(
                        write_completed=True, active_document_is_experimental_copy=_norm_path(Path(str(candidate_doc.FullName))) == _norm_path(candidate),
                        document_name=str(candidate_doc.Name), document_full_path=str(candidate_doc.FullName),
                        document_saved_state=bool(candidate_doc.Saved), document_read_only_state=bool(candidate_doc.ReadOnly),
                        object_count_before=object_count_before, object_count_after=int(candidate_doc.ModelSpace.Count),
                        new_object_handles=[record["new_target_handle"] for record in all_records + outcome["records"]],
                        copyobjects_success_count=len(all_records) + len(outcome["records"]), copyobjects_failure_count=sum(item.get("failed_task_count", 0) for item in batch_results),
                        save_error_type=type(save_exc).__name__, save_error_message=str(save_exc),
                    )
                    all_records.extend(outcome["records"])
                    write_json(execution_dir / "manual_save_handoff.json", manual_state)
                    write_jsonl(execution_dir / "created_entity_map.jsonl", all_records)
                    candidate_doc.Activate(); acad.Visible = True
                    return {"status": manual_state["status"], "manual_save": manual_state, "created_records": all_records, "batch_results": batch_results}
                all_records.extend(outcome["records"])
                batch_results.append({"batch_id": batch["batch_id"], "region_id": region, "object_name": batch["object_name"], "status": "SAVED", "task_count": len(batch["tasks"]), "created_count": len(outcome["records"])})
                print(f"[{index}/{len(batches)}] saved {batch['batch_id']} tasks={len(batch['tasks'])} total={len(all_records)}", flush=True)
                write_json(execution_dir / "execution_checkpoint.json", {"completed_batches": index, "total_batches": len(batches), "created_count": len(all_records), "last_batch": batch["batch_id"], "candidate_path": str(candidate)})
                write_jsonl(execution_dir / "created_entity_map_checkpoint.jsonl", all_records)
            except Exception as exc:
                failed_regions.add(region)
                batch_results.append({"batch_id": batch["batch_id"], "region_id": region, "object_name": batch["object_name"], "status": "FAILED_DISCARDED_UNSAVED_BATCH", "task_count": len(batch["tasks"]), "failed_task_count": len(batch["tasks"]), "error": f"{type(exc).__name__}: {exc}"})
                _close_document_without_save(candidate_doc); candidate_doc = None
                candidate_doc = _resolve_open_document(acad, candidate, _retry(lambda: acad.Documents.Open(str(candidate), False), "reopen candidate after batch failure", attempts=30, delay=0.5))
                print(f"[{index}/{len(batches)}] failed {batch['batch_id']} region={region}: {exc}", flush=True)
        write_jsonl(execution_dir / "created_entity_map.jsonl", all_records)
        write_json(execution_dir / "execution_batches.json", {"batches": batch_results})
        object_count_after = int(candidate_doc.ModelSpace.Count)
        _retry(lambda: candidate_doc.Save(), "final candidate save", attempts=10, delay=0.5)
        candidate_doc.Close(False); candidate_doc = None
        source_doc.Close(False); source_doc = None
        reopened = _resolve_open_document(acad, candidate, _open_document_with_retry(acad, candidate))
        try:
            persisted = []
            for record in all_records:
                try:
                    obj = reopened.HandleToObject(record["new_target_handle"])
                    persisted.append({**record, "persisted": True, "object_type_preserved": str(obj.ObjectName) == record["object_name"], "layer_preserved": str(obj.Layer) == record["layer"]})
                except Exception as exc:
                    persisted.append({**record, "persisted": False, "error": f"{type(exc).__name__}: {exc}"})
        finally:
            reopened.Close(False)
        result = {
            "status": "AUTO_SAVE_AND_REOPEN_PASS" if len(persisted) == len(all_records) and all(item["persisted"] for item in persisted) else "PARTIAL_WHOLE_DRAWING_COMPLETION",
            "planned_count": len(plan["tasks"]), "created_count": len(all_records),
            "failed_task_count": sum(item.get("failed_task_count", 0) for item in batch_results),
            "failed_regions": sorted(failed_regions), "object_count_before": object_count_before,
            "object_count_after": object_count_after, "saved": True, "closed": True, "reopened": True,
            "persisted_count": sum(item["persisted"] for item in persisted),
            "batch_results": batch_results, "persisted_records": persisted,
        }
        write_json(execution_dir / "execution_result.json", result)
        write_json(execution_dir / "persistence_verification.json", {"records": persisted})
        return result
    finally:
        if manual_state is None:
            if candidate_doc is not None:
                try: _close_document_without_save(candidate_doc)
                except Exception: pass
            if source_doc is not None:
                try: _close_document_without_save(source_doc)
                except Exception: pass
        if acad is not None:
            detach_autocad()


def recover_completed_records(*, run_root: Path, candidate: Path, prior_target_scan: Path, completed_batch_count: int) -> dict[str, Any]:
    plan = read_json(run_root / "frozen_plan" / "whole_drawing_write_plan.json")
    batches = ordered_batches(plan["tasks"])
    completed_tasks = [task for batch in batches[:completed_batch_count] for task in batch["tasks"]]
    target_scan = read_json(prior_target_scan)
    original_handles = {str(item["handle"]).upper() for item in target_scan["entities"] if item.get("handle")}
    acad = document = None
    try:
        acad = attach_existing_autocad()
        if enumerate_live_documents(acad, (candidate,))["documents"]:
            raise RuntimeError("AUTOCAD_INSTANCE_CONFLICT")
        document = _resolve_open_document(acad, candidate, _open_document_with_retry(acad, candidate))
        def live_model_space() -> Any:
            active_document = acad.ActiveDocument
            if Path(str(active_document.FullName)).resolve() != candidate.resolve():
                raise RuntimeError("RECOVERY_ACTIVE_DOCUMENT_IDENTITY_MISMATCH")
            model_space_proxy = active_document.ModelSpace
            int(model_space_proxy.Count)
            return model_space_proxy

        model_space = _retry(live_model_space, "read recovery ModelSpace", attempts=30, delay=0.5)
        new_records = []
        model_space_count = int(model_space.Count)
        for index in range(model_space_count):
            native = _retry(lambda index=index: model_space.Item(index), f"read recovery ModelSpace item {index}", attempts=10, delay=0.2)
            handle = str(native.Handle).upper()
            if handle not in original_handles:
                new_records.append(_scan_native(native, "stage6_p4_1_recovery"))
    finally:
        if document is not None:
            _close_document_without_save(document)
        if acad is not None:
            detach_autocad()
    unmatched = list(new_records)
    recovered = []
    for task in completed_tasks:
        candidates = [item for item in unmatched if item.get("object_name") == task["object_name"] and _bbox_close(_bbox_flat(item), task.get("expected_target_bbox"))]
        if len(candidates) != 1:
            candidates = [item for item in unmatched if item.get("object_name") == task["object_name"]]
            if candidates:
                expected = task.get("expected_target_bbox") or [0,0,0,0]
                candidates.sort(key=lambda item: sum(abs(float(a)-float(b)) for a,b in zip(_bbox_flat(item) or [math.inf]*4, expected)))
                candidates = candidates[:1]
        if len(candidates) != 1:
            continue
        item = candidates[0]; unmatched.remove(item)
        recovered.append({
            "task_id": task["task_id"], "reference_handle": str(task["reference_handle"]).upper(),
            "new_target_handle": str(item["handle"]).upper(), "object_name": item.get("object_name"),
            "layer": item.get("layer"), "region_id": task["target_region_id"],
            "copy_method": "RECOVERED_FROM_SAVED_CHECKPOINT", "transform_applied": True,
            "copy_status": "SUCCESS_RECOVERED", "native_object_preserved": item.get("object_name") == task["object_name"],
            "visual_fallback_object": False, "bbox": _bbox_flat(item),
        })
    result = {"completed_batch_count": completed_batch_count, "expected_task_count": len(completed_tasks), "candidate_new_handle_count": len(new_records), "recovered_count": len(recovered), "unmatched_new_handles": [item.get("handle") for item in unmatched], "records": recovered}
    write_json(run_root / "execution" / "recovery_checkpoint.json", result)
    write_jsonl(run_root / "execution" / "created_entity_map_checkpoint.jsonl", recovered)
    return result
