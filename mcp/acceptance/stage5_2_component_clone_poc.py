from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.acceptance.stage3_1_r1_target_scan_alignment import (
    _close_document_without_save,
    _open_document_with_retry,
    _resolve_open_document,
)
from mcp.acceptance.stage3_1_runtime import (
    _norm_path,
    attach_existing_autocad,
    detach_autocad,
    enumerate_live_documents,
    sha256_file,
)
from mcp.acceptance.stage3_3_controlled_repair import source_lock_files
from mcp.acceptance.stage5_2_native_clone_poc import (
    _bbox_close,
    _modelspace_handles,
    _object_array,
    _retry,
    _safe_close,
    _scan_native,
    _variant,
)
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


SUPPORTED_COMPONENT_TYPES = {"TDbPipeValve", "TDbPipeFitting"}


def select_component_candidate(items: Sequence[Mapping[str, Any]], object_name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if object_name not in SUPPORTED_COMPONENT_TYPES:
        raise ValueError(f"unsupported component PoC type: {object_name}")
    by_id = {str(item.get("task_id")): item for item in items}
    candidates: list[tuple[int, str, Mapping[str, Any], list[Mapping[str, Any]]]] = []
    for item in items:
        if item.get("classification") != "REQUIRED_MISSING" or item.get("object_name") != object_name:
            continue
        dependencies = [by_id[task_id] for task_id in item.get("dependency_ids") or [] if task_id in by_id]
        pipe_dependencies = [dependency for dependency in dependencies if dependency.get("object_name") == "TDbPipe"]
        readable_pipes = [
            dependency for dependency in pipe_dependencies
            if dependency.get("sys_type") not in (None, "") and dependency.get("dn") not in (None, "")
        ]
        bbox = (item.get("target_wcs_geometry") or {}).get("bbox")
        if bbox and readable_pipes:
            candidates.append((len(readable_pipes), str(item.get("task_id")), item, readable_pipes))
    if not candidates:
        raise ValueError(f"no {object_name} candidate has an approved readable TDbPipe dependency")
    _, _, primary, pipes = sorted(candidates, key=lambda row: (row[0], row[1]))[0]
    return dict(primary), [dict(pipe) for pipe in pipes]


def _bbox_distance(left: Sequence[Sequence[float]] | None, right: Sequence[Sequence[float]] | None) -> float | None:
    if not left or not right:
        return None
    dx = max(float(left[0][0]) - float(right[1][0]), float(right[0][0]) - float(left[1][0]), 0.0)
    dy = max(float(left[0][1]) - float(right[1][1]), float(right[0][1]) - float(left[1][1]), 0.0)
    dz = max(float(left[0][2]) - float(right[1][2]), float(right[0][2]) - float(left[1][2]), 0.0)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _system_from_layer(layer: Any) -> str | None:
    text = str(layer or "")
    for system in ("消防", "喷淋", "给水", "排水"):
        if system in text:
            return system
    return None


def _match_records(records: Sequence[Mapping[str, Any]], expected: Sequence[Mapping[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    matches: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    unused = list(records)
    for item in expected:
        bbox = (item.get("target_wcs_geometry") or {}).get("bbox")
        candidates = [
            record for record in unused
            if record.get("object_name") == item.get("object_name") and _bbox_close(record.get("bbox"), bbox)
        ]
        if len(candidates) != 1:
            errors.append(f"{item.get('task_id')}: expected exactly one type/geometry match, got {len(candidates)}")
            continue
        record = dict(candidates[0])
        matches[str(item.get("task_id"))] = record
        unused.remove(candidates[0])
    if unused:
        errors.append(f"unmatched created design objects: {[item.get('handle') for item in unused]}")
    return matches, errors


def validate_component_bundle(
    primary: Mapping[str, Any], pipes: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected = [*pipes, primary]
    matches, errors = _match_records(records, expected)
    primary_record = matches.get(str(primary.get("task_id")))
    pipe_records = [matches.get(str(pipe.get("task_id"))) for pipe in pipes]
    pipe_records = [record for record in pipe_records if record]
    native_type_match = bool(primary_record and primary_record.get("object_name") == primary.get("object_name"))
    layer_match = bool(primary_record and primary_record.get("layer") == primary.get("layer"))
    geometry_match = bool(primary_record and _bbox_close(
        primary_record.get("bbox"), (primary.get("target_wcs_geometry") or {}).get("bbox"),
    ))
    attached = [
        record for record in pipe_records
        if _bbox_distance(primary_record.get("bbox") if primary_record else None, record.get("bbox")) is not None
        and _bbox_distance(primary_record.get("bbox") if primary_record else None, record.get("bbox")) <= 5.0
    ]
    expected_system = _system_from_layer(primary.get("layer"))
    systems = [(record.get("attributes") or {}).get("sys_type") for record in attached]
    dns = [(record.get("attributes") or {}).get("dn_diameter") for record in attached]
    system_match = bool(attached and expected_system and all(system == expected_system for system in systems))
    dn_verified_from_attached_pipe = bool(attached and all(dn not in (None, 0, 0.0) for dn in dns))
    connection_count_match = len(attached) == len(pipes)
    passed = all((
        not errors, native_type_match, layer_match, geometry_match, system_match,
        dn_verified_from_attached_pipe, connection_count_match,
    ))
    return {
        "passed": passed, "errors": errors, "native_type_match": native_type_match,
        "layer_match": layer_match, "geometry_match": geometry_match,
        "attached_pipe_count": len(attached), "expected_attached_pipe_count": len(pipes),
        "connection_count_match": connection_count_match, "system_match": system_match,
        "dn_verified_from_attached_pipe": dn_verified_from_attached_pipe,
        "attached_pipe_systems": systems, "attached_pipe_dns": dns,
        "primary_handle": primary_record.get("handle") if primary_record else None,
        "primary_object_name": primary_record.get("object_name") if primary_record else None,
    }


def run_component_selective_clone_poc(paths: Stage5Paths, object_name: str) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    if object_name not in SUPPORTED_COMPONENT_TYPES:
        raise ValueError(f"unsupported component PoC type: {object_name}")
    inventory_path = paths.root / "tdb_inventory.json"
    stage51_path = paths.root / "stage5_1_report.json"
    if not inventory_path.is_file() or not stage51_path.is_file() or read_json(stage51_path).get("status") != "PASS_STAGE5_1_INVENTORY_COMPLETE":
        return {"phase": "STAGE5.2-B", "status": "BLOCKED_STAGE5_1_NOT_PASS", "object_name": object_name, "safety_flags": _safety()}
    items = read_json(inventory_path).get("items", [])
    primary, pipes = select_component_candidate(items, object_name)
    approved = [*pipes, primary]
    slug = "valve" if object_name == "TDbPipeValve" else "fitting"
    route_dir = paths.poc / f"{slug}_selective_clone"
    route_dir.mkdir(parents=True, exist_ok=True)
    reference_copy = route_dir / f"reference_{slug}_poc_copy.dwg"
    target_sandbox = route_dir / f"target_{slug}_poc_sandbox.dwg"
    locks = {"reference": source_lock_files(REFERENCE), "target": source_lock_files(TARGET), "mvp1": source_lock_files(MVP1_SANDBOX)}
    if any(locks.values()):
        return {"phase": "STAGE5.2-B", "status": "BLOCKED_SOURCE_LOCKED", "object_name": object_name, "source_locks": locks, "safety_flags": _safety()}
    before_source_hashes = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    if before_source_hashes != {"reference": REFERENCE_SHA256, "target": TARGET_SHA256}:
        return {"phase": "STAGE5.2-B", "status": "BLOCKED_INPUT_HASH_CHANGED", "object_name": object_name, "safety_flags": _safety()}
    shutil.copy2(REFERENCE, reference_copy)
    shutil.copy2(MVP1_SANDBOX, target_sandbox)
    write_json(route_dir / "approved_clone_bundle.json", {
        "primary_task_id": primary["task_id"], "primary_reference_handle": primary["reference_handle"],
        "approved_dependency_task_ids": [pipe["task_id"] for pipe in pipes],
        "approved_reference_handles": [item["reference_handle"] for item in approved],
        "whole_modelspace_clone_allowed": False,
    })

    acad = source_doc = target_doc = None
    before_handles: set[str] = set()
    after_handles: set[str] = set()
    created_handles: list[str] = []
    pre_records: list[dict[str, Any]] = []
    post_records: list[dict[str, Any]] = []
    persisted_records: list[dict[str, Any]] = []
    raw_created_records: list[dict[str, Any]] = []
    saved = False
    error: str | None = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET, MVP1_SANDBOX))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET), _norm_path(MVP1_SANDBOX)}
        opened = [item for item in live["documents"] if item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden]
        if opened:
            raise RuntimeError(f"source input is open in AutoCAD: {opened}")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, target_sandbox, _retry(lambda: acad.Documents.Open(str(target_sandbox), False), "target component PoC open"))
        source_natives = []
        for item in approved:
            native = _retry(lambda handle=item["reference_handle"]: source_doc.HandleToObject(handle), f"source Handle {item['reference_handle']} lookup")
            record = _scan_native(native, "stage5_component_reference")
            if record.get("object_name") != item.get("object_name"):
                raise RuntimeError(f"source type mismatch for {item['task_id']}")
            source_natives.append(native)
            pre_records.append(record)
        before_handles = _modelspace_handles(target_doc)
        _retry(lambda: source_doc.CopyObjects(_object_array(source_natives), target_doc.ModelSpace), "selective component CopyObjects")
        after_handles = _modelspace_handles(target_doc)
        created_handles = sorted(after_handles - before_handles)
        for handle in created_handles:
            raw_created_records.append(_scan_native(
                _retry(lambda value=handle: target_doc.HandleToObject(value), f"raw target Handle {handle} lookup"),
                "stage5_component_raw_target",
            ))
        if len(created_handles) != len(approved):
            raise RuntimeError(
                f"design delta {len(created_handles)} differs from approved bundle {len(approved)}; "
                f"created types={[record.get('object_name') for record in raw_created_records]}"
            )
        for handle in created_handles:
            native = _retry(lambda value=handle: target_doc.HandleToObject(value), f"target Handle {handle} lookup")
            _retry(lambda obj=native: obj.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), f"move cloned {handle}")
            post_records.append(_scan_native(native, "stage5_component_target"))
        qa = validate_component_bundle(primary, pipes, post_records)
        if not qa["passed"]:
            raise RuntimeError(f"pre-save component QA failed: {qa}")
        _retry(lambda: target_doc.Save(), "target component PoC save")
        saved = True
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        reopened = _resolve_open_document(acad, target_sandbox, _open_document_with_retry(acad, target_sandbox))
        try:
            for handle in created_handles:
                persisted_records.append(_scan_native(
                    _retry(lambda value=handle: reopened.HandleToObject(value), f"persisted Handle {handle} lookup"),
                    "stage5_component_persisted",
                ))
        finally:
            _safe_close(reopened)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()

    pre_save_qa = validate_component_bundle(primary, pipes, post_records)
    persistence_qa = validate_component_bundle(primary, pipes, persisted_records)
    after_source_hashes = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    source_unchanged = before_source_hashes == after_source_hashes
    verified = all((error is None, saved, pre_save_qa["passed"], persistence_qa["passed"], source_unchanged))
    status = "VERIFIED_SELECTIVE_CLONE" if verified else (
        "FAILED_PERSISTENCE" if saved and not persistence_qa["passed"] else
        "FAILED_TYPE_DEGRADED" if post_records and not pre_save_qa["native_type_match"] else
        "BLOCKED_DEPENDENCY"
    )
    dependency_matches, _ = _match_records(persisted_records if saved else post_records, pipes)
    dependency_mappings = [
        {"task_id": pipe["task_id"], "reference_handle": pipe["reference_handle"], "target_handle": dependency_matches[str(pipe["task_id"])]["handle"], "object_name": "TDbPipe"}
        for pipe in pipes if str(pipe["task_id"]) in dependency_matches
    ]
    result = {
        "phase": "STAGE5.2-B", "object_name": object_name, "route": "selective_native_clone", "status": status,
        "primary_task_id": primary["task_id"], "primary_reference_handle": primary["reference_handle"],
        "approved_dependency_task_ids": [pipe["task_id"] for pipe in pipes],
        "approved_reference_handles": [item["reference_handle"] for item in approved],
        "raw_created_records": raw_created_records,
        "dependency_mappings": dependency_mappings,
        "created_handles": created_handles, "modelspace_count_before": len(before_handles),
        "modelspace_count_after": len(after_handles), "draw_delta": len(after_handles) - len(before_handles),
        "pre_save_qa": pre_save_qa, "persistence_qa": persistence_qa,
        "saved": saved, "reopened": bool(persisted_records),
        "repeat_duplicate_precheck_match_count": len(persisted_records) if persistence_qa["passed"] else 0,
        "repeat_execution_blocked_as_duplicate": persistence_qa["passed"],
        "source_hashes_unchanged": source_unchanged, "error": error,
        "safety_flags": {
            **_safety(), "autocad_connected": True, "copyobjects_used": bool(post_records),
            "dwg_modified": bool(post_records), "dwg_saved": saved,
            "existing_tdb_modified": False, "native_tdb_created": bool(post_records),
            "source_reference_opened": False, "source_target_opened": False,
        },
    }
    write_json(route_dir / f"{slug}_clone_poc_result.json", result)
    return result


def run_primary_only_component_diagnostic(paths: Stage5Paths, object_name: str) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    if object_name not in SUPPORTED_COMPONENT_TYPES:
        raise ValueError(f"unsupported component diagnostic type: {object_name}")
    items = read_json(paths.root / "tdb_inventory.json").get("items", [])
    primary, pipes = select_component_candidate(items, object_name)
    slug = "valve" if object_name == "TDbPipeValve" else "fitting"
    route_dir = paths.poc / f"{slug}_primary_only_diagnostic"
    route_dir.mkdir(parents=True, exist_ok=True)
    reference_copy = route_dir / f"reference_{slug}_diagnostic_copy.dwg"
    target_sandbox = route_dir / f"target_{slug}_diagnostic_sandbox.dwg"
    if source_lock_files(REFERENCE) or source_lock_files(TARGET) or source_lock_files(MVP1_SANDBOX):
        return {"phase": "STAGE5.2-B", "status": "BLOCKED_SOURCE_LOCKED", "diagnostic_only": True, "safety_flags": _safety()}
    before_hashes = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    expected = {"reference": require_parameter("mcp.orchestration.stage4_mvp.reference_sha256"), "target": require_parameter("mcp.orchestration.stage4_mvp.target_sha256")}
    if before_hashes != expected:
        raise RuntimeError("Source hash mismatch before primary-only diagnostic")
    shutil.copy2(REFERENCE, reference_copy)
    shutil.copy2(MVP1_SANDBOX, target_sandbox)
    acad = source_doc = target_doc = None
    created_handles: list[str] = []
    record: dict[str, Any] | None = None
    persisted: dict[str, Any] | None = None
    saved = False
    error: str | None = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET, MVP1_SANDBOX))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET), _norm_path(MVP1_SANDBOX)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("a source input is open in AutoCAD")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, target_sandbox, _retry(lambda: acad.Documents.Open(str(target_sandbox), False), "primary diagnostic open"))
        source_native = _retry(lambda: source_doc.HandleToObject(primary["reference_handle"]), "primary diagnostic source lookup")
        before_handles = _modelspace_handles(target_doc)
        _retry(lambda: source_doc.CopyObjects(_object_array([source_native]), target_doc.ModelSpace), "primary-only CopyObjects")
        created_handles = sorted(_modelspace_handles(target_doc) - before_handles)
        if len(created_handles) != 1:
            raise RuntimeError(f"primary-only Handle delta must be 1, got {len(created_handles)}")
        native = _retry(lambda: target_doc.HandleToObject(created_handles[0]), "primary diagnostic target lookup")
        _retry(lambda: native.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), "primary diagnostic move")
        record = _scan_native(native, "stage5_component_primary_diagnostic")
        basic_pass = all((
            record.get("object_name") == object_name,
            record.get("layer") == primary.get("layer"),
            _bbox_close(record.get("bbox"), (primary.get("target_wcs_geometry") or {}).get("bbox")),
        ))
        if not basic_pass:
            raise RuntimeError(f"primary-only native/type/geometry QA failed: {record}")
        _retry(lambda: target_doc.Save(), "primary diagnostic save")
        saved = True
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        reopened = _resolve_open_document(acad, target_sandbox, _open_document_with_retry(acad, target_sandbox))
        try:
            persisted = _scan_native(_retry(lambda: reopened.HandleToObject(created_handles[0]), "primary diagnostic persisted lookup"), "stage5_component_primary_persisted")
        finally:
            _safe_close(reopened)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()
    after_hashes = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    native_persisted = bool(
        persisted and persisted.get("object_name") == object_name
        and _bbox_close(persisted.get("bbox"), (primary.get("target_wcs_geometry") or {}).get("bbox"))
    )
    result = {
        "phase": "STAGE5.2-B", "object_name": object_name, "diagnostic_only": True,
        "status": "BLOCKED_DEPENDENCY" if native_persisted else "BLOCKED_UNSUPPORTED",
        "primary_task_id": primary["task_id"], "reference_handle": primary["reference_handle"],
        "created_handles": created_handles, "native_primary_created": bool(record and record.get("object_name") == object_name),
        "native_primary_persisted": native_persisted, "saved": saved,
        "required_pipe_dependency_ids": [pipe["task_id"] for pipe in pipes],
        "pipe_association_preserved": False,
        "reason": "primary-only clone cannot satisfy required pipe attachment and DN verification",
        "source_hashes_unchanged": before_hashes == after_hashes, "error": error,
        "safety_flags": {
            **_safety(), "autocad_connected": True, "copyobjects_used": bool(record),
            "dwg_modified": bool(record), "dwg_saved": saved, "existing_tdb_modified": False,
            "native_tdb_created": bool(record), "source_reference_opened": False, "source_target_opened": False,
        },
    }
    write_json(route_dir / f"{slug}_primary_only_diagnostic.json", result)
    return result
