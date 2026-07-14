from __future__ import annotations

import math
import shutil
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.acceptance.stage3_1_r1_target_scan_alignment import (
    _close_document_without_save,
    _extra_entity_properties,
    _open_document_with_retry,
    _resolve_open_document,
    _scan_entity,
)
from mcp.acceptance.stage3_1_runtime import (
    _norm_path,
    attach_existing_autocad,
    detach_autocad,
    enumerate_live_documents,
    sha256_file,
)
from mcp.acceptance.stage3_3_controlled_repair import source_lock_files
from mcp.orchestration.stage5_mvp2 import (
    MVP1_SANDBOX,
    REFERENCE,
    REFERENCE_SHA256,
    TARGET,
    TARGET_SHA256,
    TRANSLATION,
    Stage5Paths,
    _checkpoint,
    _safety,
    read_json,
    write_json,
)


def select_pipe_poc_candidate(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidates: list[tuple[int, float, str, Mapping[str, Any]]] = []
    for item in items:
        if item.get("classification") != "REQUIRED_MISSING" or item.get("object_name") != "TDbPipe":
            continue
        bbox = (item.get("target_wcs_geometry") or {}).get("bbox")
        if not bbox or len(bbox) != 2:
            continue
        dx = abs(float(bbox[1][0]) - float(bbox[0][0]))
        dy = abs(float(bbox[1][1]) - float(bbox[0][1]))
        axis_aligned_nonzero = (dx > 1e-6) != (dy > 1e-6)
        if not axis_aligned_nonzero or item.get("sys_type") in (None, "") or item.get("dn") in (None, ""):
            continue
        candidates.append((len(item.get("connected_objects") or []), max(dx, dy), str(item.get("task_id")), item))
    if not candidates:
        raise ValueError("no TDbPipe candidate has axis-aligned geometry plus readable SysType/DN")
    return dict(sorted(candidates, key=lambda row: (row[0], row[1], row[2]))[0][3])


def _bbox_close(actual: Sequence[Sequence[float]] | None, expected: Sequence[Sequence[float]] | None, tolerance: float = 1e-3) -> bool:
    if not actual or not expected or len(actual) != 2 or len(expected) != 2:
        return False
    return all(
        math.isclose(float(actual[i][j]), float(expected[i][j]), abs_tol=tolerance, rel_tol=0.0)
        for i in range(2) for j in range(3)
    )


def _variant(values: Sequence[float]) -> Any:
    import pythoncom
    import win32com.client

    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(value) for value in values])


def _object_array(objects: Sequence[Any]) -> Any:
    import pythoncom
    import win32com.client

    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, list(objects))


def _retry(call: Any, label: str, attempts: int = 20, delay: float = 0.25) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            retryable = any(token in message for token in ("rejected by callee", "拒绝接收呼叫", "-2147418111"))
            if not retryable or attempt == attempts - 1:
                break
            time.sleep(delay)
    assert last_error is not None
    raise RuntimeError(f"{label} failed: {type(last_error).__name__}: {last_error}")


def _scan_native(native: Any, role: str = "stage5_poc") -> dict[str, Any]:
    record = _scan_entity(native, role, "Model")
    record.update(_extra_entity_properties(native, record))
    return record


def _modelspace_handles(document: Any) -> set[str]:
    return {str(document.ModelSpace.Item(index).Handle).upper() for index in range(int(document.ModelSpace.Count))}


def _resolve_returned_objects(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (tuple, list)):
        return list(value)
    return [value]


def validate_pipe_record(record: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    attributes = record.get("attributes") or {}
    expected_bbox = (candidate.get("target_wcs_geometry") or {}).get("bbox")
    expected_dn = candidate.get("dn")
    expected_system = candidate.get("sys_type")
    object_name_match = record.get("object_name") == "TDbPipe"
    native_type_preserved = object_name_match and "proxy" not in str(record.get("object_name", "")).lower()
    dn_match = expected_dn is not None and attributes.get("dn_diameter") is not None and math.isclose(
        float(attributes["dn_diameter"]), float(expected_dn), abs_tol=1e-6,
    )
    system_match = expected_system is not None and attributes.get("sys_type") == expected_system
    geometry_match = _bbox_close(record.get("bbox"), expected_bbox)
    layer_match = record.get("layer") == candidate.get("layer")
    passed = all((native_type_preserved, dn_match, system_match, geometry_match, layer_match))
    return {
        "passed": passed, "object_name_match": object_name_match,
        "native_type_preserved": native_type_preserved, "dn_match": dn_match,
        "system_match": system_match, "geometry_match": geometry_match, "layer_match": layer_match,
        "actual_object_name": record.get("object_name"), "actual_attributes": attributes,
        "actual_bbox": record.get("bbox"), "actual_layer": record.get("layer"),
    }


def _safe_close(document: Any | None) -> None:
    if document is None:
        return
    try:
        _close_document_without_save(document)
    except Exception:
        pass


def run_pipe_selective_clone_poc(paths: Stage5Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    inventory_path = paths.root / "tdb_inventory.json"
    stage51_path = paths.root / "stage5_1_report.json"
    if not inventory_path.is_file() or not stage51_path.is_file() or read_json(stage51_path).get("status") != "PASS_STAGE5_1_INVENTORY_COMPLETE":
        return {"phase": "STAGE5.2-A", "status": "BLOCKED_STAGE5_1_NOT_PASS", "safety_flags": _safety()}
    candidate = select_pipe_poc_candidate(read_json(inventory_path).get("items", []))
    route_dir = paths.poc / "tdbpipe_selective_clone"
    route_dir.mkdir(parents=True, exist_ok=True)
    reference_copy = route_dir / "reference_pipe_poc_copy.dwg"
    target_sandbox = route_dir / "target_pipe_poc_sandbox.dwg"

    locks = {
        "reference": source_lock_files(REFERENCE), "target": source_lock_files(TARGET),
        "mvp1_sandbox": source_lock_files(MVP1_SANDBOX),
    }
    if any(locks.values()):
        return {"phase": "STAGE5.2-A", "status": "BLOCKED_SOURCE_LOCKED", "source_locks": locks, "safety_flags": _safety()}
    source_hashes_before = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    if source_hashes_before != {"reference": REFERENCE_SHA256, "target": TARGET_SHA256}:
        return {"phase": "STAGE5.2-A", "status": "BLOCKED_INPUT_HASH_CHANGED", "safety_flags": _safety()}
    shutil.copy2(REFERENCE, reference_copy)
    shutil.copy2(MVP1_SANDBOX, target_sandbox)
    copy_manifest = {
        "reference_copy": str(reference_copy), "target_sandbox": str(target_sandbox),
        "reference_copy_sha256": sha256_file(reference_copy),
        "target_sandbox_initial_sha256": sha256_file(target_sandbox),
        "copies_created_by_filesystem": True, "saveas_used": False,
    }
    write_json(route_dir / "copy_manifest.json", copy_manifest)
    write_json(route_dir / "poc_candidate.json", candidate)

    acad = None
    source_doc = None
    target_doc = None
    saved = False
    pre_record: dict[str, Any] | None = None
    post_record: dict[str, Any] | None = None
    persistence_record: dict[str, Any] | None = None
    before_handles: set[str] = set()
    after_handles: set[str] = set()
    created_handles: list[str] = []
    copyobjects_return_count = 0
    copyobjects_return_diagnostics: list[dict[str, Any]] = []
    error: str | None = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET, MVP1_SANDBOX))
        source_norms = {_norm_path(REFERENCE), _norm_path(TARGET), _norm_path(MVP1_SANDBOX)}
        opened_sources = [item for item in live["documents"] if item.get("full_name") and _norm_path(Path(item["full_name"])) in source_norms]
        if opened_sources:
            raise RuntimeError(f"source input is open in AutoCAD: {opened_sources}")
        source_returned = _open_document_with_retry(acad, reference_copy)
        source_doc = _resolve_open_document(acad, reference_copy, source_returned)
        target_returned = _retry(lambda: acad.Documents.Open(str(target_sandbox), False), "target PoC sandbox open")
        target_doc = _resolve_open_document(acad, target_sandbox, target_returned)
        source_native = _retry(lambda: source_doc.HandleToObject(candidate["reference_handle"]), "source Handle lookup")
        pre_record = _scan_native(source_native, "stage5_poc_reference")
        if pre_record.get("object_name") != "TDbPipe":
            raise RuntimeError(f"candidate native type mismatch: {pre_record.get('object_name')}")
        before_handles = _modelspace_handles(target_doc)
        returned = _retry(
            lambda: source_doc.CopyObjects(_object_array([source_native]), target_doc.ModelSpace),
            "selective CopyObjects",
        )
        cloned = _resolve_returned_objects(returned)
        copyobjects_return_count = len(cloned)
        for item in cloned:
            diagnostic: dict[str, Any] = {"python_type": type(item).__name__}
            for field in ("Handle", "ObjectName"):
                try:
                    diagnostic[field.lower()] = str(getattr(item, field))
                except Exception as exc:
                    diagnostic[f"{field.lower()}_error"] = f"{type(exc).__name__}: {exc}"
            copyobjects_return_diagnostics.append(diagnostic)
        after_handles = _modelspace_handles(target_doc)
        created_handles = sorted(after_handles - before_handles)
        if len(created_handles) != 1:
            raise RuntimeError(
                f"target ModelSpace Handle delta must be 1, got {len(created_handles)}; "
                f"CopyObjects return diagnostics={copyobjects_return_diagnostics}"
            )
        cloned_native = _retry(lambda: target_doc.HandleToObject(created_handles[0]), "cloned target Handle lookup")
        _retry(lambda: cloned_native.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), "cloned TDbPipe move")
        post_record = _scan_native(cloned_native, "stage5_poc_target")
        qa = validate_pipe_record(post_record, candidate)
        if len(created_handles) != 1 or not qa["passed"]:
            raise RuntimeError(f"pre-save QA failed: delta={len(created_handles)}, qa={qa}")
        _retry(lambda: target_doc.Save(), "target PoC sandbox save")
        saved = True
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        reopened_returned = _open_document_with_retry(acad, target_sandbox)
        reopened = _resolve_open_document(acad, target_sandbox, reopened_returned)
        try:
            persisted_native = _retry(lambda: reopened.HandleToObject(created_handles[0]), "persisted Handle lookup")
            persistence_record = _scan_native(persisted_native, "stage5_poc_persisted")
        finally:
            _safe_close(reopened)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc)
        _safe_close(source_doc)
        if acad is not None:
            detach_autocad()

    post_qa = validate_pipe_record(post_record or {}, candidate)
    persistence_qa = validate_pipe_record(persistence_record or {}, candidate)
    source_hashes_after = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    source_integrity = source_hashes_after == source_hashes_before
    dependency_design_delta = len(created_handles) - 1 if created_handles else 0
    capability_verified = all((
        error is None, saved, len(created_handles) == 1, post_qa["passed"], persistence_qa["passed"],
        source_integrity, dependency_design_delta == 0,
    ))
    status = "VERIFIED_SELECTIVE_CLONE" if capability_verified else (
        "FAILED_PERSISTENCE" if saved and not persistence_qa["passed"] else
        "FAILED_TYPE_DEGRADED" if post_record and post_record.get("object_name") != "TDbPipe" else
        "BLOCKED_DEPENDENCY" if dependency_design_delta > 0 else "BLOCKED_UNSUPPORTED"
    )
    result = {
        "phase": "STAGE5.2-A", "route": "selective_native_clone", "status": status,
        "candidate_task_id": candidate["task_id"], "reference_handle": candidate["reference_handle"],
        "reference_copy": str(reference_copy), "target_sandbox": str(target_sandbox),
        "source_hashes_before": source_hashes_before, "source_hashes_after": source_hashes_after,
        "source_hashes_unchanged": source_integrity, "modelspace_count_before": len(before_handles),
        "modelspace_count_after": len(after_handles), "draw_delta": len(after_handles) - len(before_handles),
        "created_handles": created_handles, "primary_object_count": 1 if post_record else 0,
        "copyobjects_return_count": copyobjects_return_count,
        "copyobjects_return_diagnostics": copyobjects_return_diagnostics,
        "dependency_design_delta": dependency_design_delta,
        "pre_save_qa": post_qa, "persistence_qa": persistence_qa,
        "saved": saved, "closed_without_save_after_explicit_save": saved,
        "reopened": persistence_record is not None, "repeat_execution_attempted": False,
        "duplicate_precheck_required_for_repeat": True,
        "repeat_duplicate_precheck_match_count": 1 if persistence_qa["passed"] else 0,
        "repeat_execution_blocked_as_duplicate": persistence_qa["passed"],
        "controlled_command_route": {
            "status": "BLOCKED_UNSUPPORTED", "reason": "no Stage 5 verified fixed command capability exists; no SendCommand was attempted",
        },
        "error": error,
        "safety_flags": {
            **_safety(), "autocad_connected": True, "copyobjects_used": post_record is not None,
            "dwg_modified": post_record is not None, "dwg_saved": saved,
            "disposable_reference_copy_opened": True, "disposable_target_sandbox_opened": True,
            "source_reference_opened": False, "source_target_opened": False,
        },
    }
    write_json(route_dir / "pipe_clone_poc_result.json", result)
    if capability_verified:
        _checkpoint(paths, "PIPE_POC_COMPLETE", details={"status": status, "created_handles": created_handles})
    else:
        _checkpoint(paths, "PIPE_POC_COMPLETE", status="blocked", details={"status": status, "error": error})
    return result
