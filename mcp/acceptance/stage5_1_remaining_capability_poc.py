from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
from mcp.acceptance.stage3_1_runtime import (
    _norm_path,
    attach_existing_autocad,
    detach_autocad,
    enumerate_live_documents,
    sha256_file,
)
from mcp.acceptance.stage3_3_controlled_repair import source_lock_files
from mcp.acceptance.stage5_1_valve_component_diagnostics import (
    _copyobjects_with_explicit_idpairs,
    _match_expected,
    _parse_copyobjects_return,
)
from mcp.acceptance.stage5_2_component_clone_poc import _bbox_distance
from mcp.acceptance.stage5_2_native_clone_poc import (
    _modelspace_handles,
    _retry,
    _safe_close,
    _scan_native,
    _variant,
)
from mcp.orchestration.stage5_1_relationship_reconstruction import (
    REFERENCE,
    REFERENCE_SHA256,
    TARGET,
    TARGET_SHA256,
    TRANSLATION,
    Stage51Paths,
    checkpoint,
    read_json,
    safety_flags,
    write_json,
)
from tianzheng.semantic_reader import read_semantic_entity


REMAINING_TYPES = (
    "TDbPump", "TDbEquipment", "TDbWaterTank",
    "TDbDimension2", "TDbVPipeDim", "TDbSymbMultiLeader",
)
DEVICE_TYPES = {"TDbPump", "TDbEquipment", "TDbWaterTank"}
ANNOTATION_TYPES = {"TDbDimension2", "TDbVPipeDim", "TDbSymbMultiLeader"}


def select_capability_package(graph: Mapping[str, Any], object_name: str) -> dict[str, Any]:
    by_id = {node["task_id"]: node for node in graph["nodes"]}
    candidates = [node for node in graph["nodes"] if node["object_name"] == object_name]
    if not candidates:
        raise ValueError(f"required type absent from graph: {object_name}")
    options = []
    for primary in candidates:
        dependencies: dict[str, dict[str, Any]] = {}
        relationship_edges = []
        for edge in graph["edges"]:
            if primary["task_id"] not in {edge["source_id"], edge["target_id"]}:
                continue
            other_id = edge["target_id"] if edge["source_id"] == primary["task_id"] else edge["source_id"]
            if edge["edge_type"] in {"EQUIPMENT_INTERFACE", "ANNOTATES_OBJECT"} and other_id in by_id:
                dependencies[other_id] = by_id[other_id]
                relationship_edges.append(edge)
        if object_name in DEVICE_TYPES:
            pipe_dependencies = [node for node in dependencies.values() if node["object_name"] == "TDbPipe"]
            if pipe_dependencies:
                dependencies = {pipe_dependencies[0]["task_id"]: pipe_dependencies[0]}
        options.append((0 if dependencies else 1, len(dependencies), primary["task_id"], primary, list(dependencies.values()), relationship_edges))
    _, _, _, primary, dependencies, edges = sorted(options, key=lambda row: (row[0], row[1], row[2]))[0]
    return {
        "object_name": object_name, "primary": primary, "dependencies": dependencies,
        "relationship_edges": edges, "nodes": [*dependencies, primary],
    }


def _semantic_properties(native: Any) -> dict[str, Any]:
    semantic = read_semantic_entity(native)
    properties = semantic.get("properties") or {}
    return {
        "semantic_type": semantic.get("semantic_type"),
        "object_name": semantic.get("object_name"),
        "system_type": semantic.get("system_type"), "diameter": semantic.get("diameter"),
        "text": semantic.get("text"), "measurement": semantic.get("measurement"),
        "custom_properties": {
            key: value for key, value in properties.items()
            if key not in {"readable_properties", "failed_properties"}
        },
        "readable_properties": properties.get("readable_properties", []),
        "failed_properties": properties.get("failed_properties", {}),
    }


def evaluate_capability_package(
    package: Mapping[str, Any], records: Sequence[Mapping[str, Any]], semantics: Mapping[str, Mapping[str, Any]],
    copy_map: Mapping[str, Any],
) -> dict[str, Any]:
    nodes = package["nodes"]
    primary = package["primary"]
    matches, errors = _match_expected(records, nodes)
    primary_record = matches.get(primary["task_id"])
    primary_semantic = semantics.get(primary["task_id"], {})
    expected_handles = {node["reference_handle"] for node in nodes}
    mapped_handles = {
        pair.get("source_handle") for pair in copy_map.get("idpairs", [])
        if pair.get("source_handle") and pair.get("IsCloned") is not False
    }
    idpairs_complete = expected_handles.issubset(mapped_handles)
    native_type_match = bool(primary_record and primary_record.get("object_name") == primary["object_name"])
    geometry_match = bool(primary_record and not errors)
    layer_match = bool(primary_record and primary_record.get("layer") == primary.get("layer"))
    expected_properties = primary.get("custom_properties") or {}
    actual_properties = primary_semantic.get("custom_properties") or {}
    comparable = {key: value for key, value in expected_properties.items() if key in actual_properties}
    property_match = bool(comparable) and all(actual_properties[key] == value for key, value in comparable.items())
    readable = set(primary.get("readable_properties") or [])
    position_readable = bool(readable & {"InsertionPoint", "Position", "Location", "Center"})
    rotation_readable = bool(readable & {"Rotation", "Angle", "Direction"})
    dimensions_readable = bool(readable & {"Width", "Height", "Length"})
    dependency_records = [matches[node["task_id"]] for node in package["dependencies"] if node["task_id"] in matches]
    interface_match = False
    annotation_target_match = False
    if primary["object_name"] in DEVICE_TYPES:
        interface_match = bool(
            dependency_records and primary_record
            and any(_bbox_distance(primary_record.get("bbox"), record.get("bbox")) <= 200.0 for record in dependency_records)
            and idpairs_complete
        )
    if primary["object_name"] in ANNOTATION_TYPES:
        annotation_target_match = bool(dependency_records and idpairs_complete and primary_semantic.get("text") not in (None, ""))
    required_fields = {
        "position_readable": position_readable,
        "rotation_readable": rotation_readable,
        "dimensions_readable": dimensions_readable,
        "interface_match": interface_match,
        "annotation_text_readable": primary_semantic.get("text") not in (None, ""),
        "annotation_value_readable": primary_semantic.get("measurement") is not None,
        "annotation_target_match": annotation_target_match,
    }
    if primary["object_name"] in DEVICE_TYPES:
        required_complete = all((position_readable, rotation_readable, dimensions_readable, interface_match))
    else:
        required_complete = all((required_fields["annotation_text_readable"], annotation_target_match))
    core_passed = all((not errors, native_type_match, geometry_match, layer_match, property_match, idpairs_complete))
    return {
        "core_passed": core_passed, "required_fields_complete": required_complete,
        "native_type_match": native_type_match, "geometry_match": geometry_match,
        "layer_match": layer_match, "property_match": property_match,
        "comparable_properties": comparable, "idpairs_complete": idpairs_complete,
        "required_field_results": required_fields, "errors": errors,
        "relationship_evidence_source": "copyobjects_idpairs_plus_persisted_native_object",
    }


def run_remaining_type_poc(paths: Stage51Paths, object_name: str) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    graph = read_json(paths.root / "reference_tdb_relationship_graph.json")
    package = select_capability_package(graph, object_name)
    route_dir = paths.capabilities / "remaining_type_pocs" / object_name
    route_dir.mkdir(parents=True, exist_ok=True)
    reference_copy = route_dir / "reference_poc_copy.dwg"
    target_sandbox = route_dir / "target_poc_sandbox.dwg"
    from mcp.orchestration.private_run_config import verify_input_hash
    for input_path, key in (
        (REFERENCE, "mcp.orchestration.stage4_mvp.reference_sha256"),
        (TARGET, "mcp.orchestration.stage4_mvp.target_sha256"),
        (paths.copies / "reference_analysis_copy.dwg", "mcp.orchestration.stage4_mvp.reference_sha256"),
        (paths.copies / "target_analysis_copy.dwg", "mcp.orchestration.stage4_mvp.target_sha256"),
    ):
        verify_input_hash(input_path, key)
    shutil.copy2(paths.copies / "reference_analysis_copy.dwg", reference_copy)
    shutil.copy2(paths.copies / "target_analysis_copy.dwg", target_sandbox)
    acad = source_doc = target_doc = None
    before_handles: set[str] = set(); after_handles: set[str] = set(); created_handles: list[str] = []
    records: list[dict[str, Any]] = []; semantics: dict[str, dict[str, Any]] = {}
    persisted_records: list[dict[str, Any]] = []; persisted_semantics: dict[str, dict[str, Any]] = {}
    copy_map: dict[str, Any] = {"idpairs": [], "primary_return_records": []}
    saved = False; error: str | None = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, target_sandbox, _retry(lambda: acad.Documents.Open(str(target_sandbox), False), "remaining type target open"))
        source_objects = [
            _retry(lambda handle=node["reference_handle"]: source_doc.HandleToObject(handle), f"remaining type Handle {node['reference_handle']} lookup")
            for node in package["nodes"]
        ]
        before_handles = _modelspace_handles(target_doc)
        returned = _retry(
            lambda: _copyobjects_with_explicit_idpairs(source_doc, source_objects, target_doc.ModelSpace),
            f"{object_name} component CopyObjects",
        )
        copy_map = _parse_copyobjects_return(returned, source_doc, target_doc)
        after_handles = _modelspace_handles(target_doc)
        created_handles = sorted(after_handles - before_handles)
        if len(created_handles) != len(package["nodes"]):
            raise RuntimeError(f"created delta {len(created_handles)} != approved package {len(package['nodes'])}")
        for handle in created_handles:
            native = _retry(lambda value=handle: target_doc.HandleToObject(value), f"created {handle} lookup")
            _retry(lambda obj=native: obj.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), f"move {handle}")
            records.append(_scan_native(native, "stage5_1_remaining_type"))
        matches, match_errors = _match_expected(records, package["nodes"])
        if match_errors:
            raise RuntimeError(f"pre-save matching failed: {match_errors}")
        for node in package["nodes"]:
            native = _retry(lambda value=matches[node["task_id"]]["handle"]: target_doc.HandleToObject(value), f"semantic {node['task_id']} lookup")
            semantics[node["task_id"]] = _semantic_properties(native)
        core_qa = evaluate_capability_package(package, records, semantics, copy_map)
        if not core_qa["core_passed"]:
            raise RuntimeError(f"pre-save core QA failed: {core_qa}")
        _retry(lambda: target_doc.Save(), f"{object_name} PoC save")
        saved = True
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        reopened = _resolve_open_document(acad, target_sandbox, _open_document_with_retry(acad, target_sandbox))
        try:
            for handle in created_handles:
                native = _retry(lambda value=handle: reopened.HandleToObject(value), f"persisted {handle} lookup")
                persisted_records.append(_scan_native(native, "stage5_1_remaining_type_persisted"))
            persisted_matches, persisted_errors = _match_expected(persisted_records, package["nodes"])
            if persisted_errors:
                raise RuntimeError(f"persistence matching failed: {persisted_errors}")
            for node in package["nodes"]:
                native = _retry(lambda value=persisted_matches[node["task_id"]]["handle"]: reopened.HandleToObject(value), f"persisted semantic {node['task_id']} lookup")
                persisted_semantics[node["task_id"]] = _semantic_properties(native)
        finally:
            _safe_close(reopened)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()
    pre_qa = evaluate_capability_package(package, records, semantics, copy_map)
    persistence_qa = evaluate_capability_package(package, persisted_records, persisted_semantics, copy_map)
    if saved and persistence_qa["core_passed"] and persistence_qa["required_fields_complete"] and error is None:
        status = "VERIFIED_COMPONENT_CLONE"
    elif saved and persistence_qa["core_passed"]:
        status = "PARTIAL_VISUAL_ONLY"
    else:
        status = "FAILED_PROPERTY_PERSISTENCE"
    result = {
        "phase": "STAGE5.1-E", "object_name": object_name, "status": status,
        "primary_task_id": package["primary"]["task_id"], "primary_reference_handle": package["primary"]["reference_handle"],
        "dependency_task_ids": [node["task_id"] for node in package["dependencies"]],
        "approved_reference_handles": [node["reference_handle"] for node in package["nodes"]],
        "created_handles": created_handles, "expected_object_count": len(package["nodes"]),
        "actual_new_handle_count": len(created_handles), "copyobjects_mapping": copy_map,
        "pre_save_qa": pre_qa, "persistence_qa": persistence_qa,
        "saved": saved, "reopened": bool(persisted_records), "error": error,
        "source_hashes_unchanged": sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256,
        "safety_flags": {
            **safety_flags(), "autocad_connected": True, "selective_copyobjects_used": True,
            "disposable_sandbox_modified": bool(records), "disposable_sandbox_saved": saved,
            "source_reference_opened": False, "source_target_opened": False,
        },
    }
    write_json(route_dir / "result.json", result)
    return result


def run_remaining_capability_matrix(paths: Stage51Paths) -> dict[str, Any]:
    valve = read_json(paths.root / "valve_relationship_diagnostics.json")
    if valve.get("status") not in {"VERIFIED_COMPONENT_CLONE", "VERIFIED_RELATIONSHIP_REMAP"}:
        return {"phase": "STAGE5.1-E", "status": "BLOCKED_VALVE_RELATIONSHIP_UNRESOLVED", "safety_flags": safety_flags()}
    if source_lock_files(REFERENCE) or source_lock_files(TARGET):
        return {"phase": "STAGE5.1-E", "status": "BLOCKED_SOURCE_LOCKED", "safety_flags": safety_flags()}
    results = [run_remaining_type_poc(paths, object_name) for object_name in REMAINING_TYPES]
    baseline = read_json(paths.root / "capability_baseline.json")["frozen_verified_capabilities"]
    matrix = {
        "TDbPipe": {"status": baseline["TDbPipe"], "route": "selective_native_clone"},
        "TDbPipeFitting": {"status": baseline["TDbPipeFitting"], "route": "selective_native_clone"},
        "TDbPipeValve": {"status": valve["status"], "route": "relationship_aware_component_clone"},
    }
    for result in results:
        matrix[result["object_name"]] = {"status": result["status"], "route": "relationship_aware_component_clone", "evidence": result}
    verified = {"VERIFIED_SELECTIVE_CLONE", "VERIFIED_COMPONENT_CLONE", "VERIFIED_RELATIONSHIP_REMAP"}
    blocked_types = [name for name, item in matrix.items() if item["status"] not in verified]
    status = "PASS_STAGE5_1_E_ALL_TYPES_VERIFIED" if not blocked_types else "BLOCKED_REQUIRED_TDB_TYPE_UNSUPPORTED"
    report = {
        "phase": "STAGE5.1-E", "status": status, "object_types": matrix,
        "blocked_required_types": blocked_types, "all_required_types_verified": not blocked_types,
        "source_hashes_unchanged": all(result["source_hashes_unchanged"] for result in results),
        "safety_flags": {
            **safety_flags(), "autocad_connected": True, "selective_copyobjects_used": True,
            "source_reference_opened": False, "source_target_opened": False,
        },
    }
    write_json(paths.root / "tdb_creation_capability_matrix.json", report)
    checkpoint(paths, "CAPABILITY_MATRIX_COMPLETE", status="completed" if not blocked_types else "blocked", details={
        "status": status, "blocked_required_types": blocked_types,
    })
    return report

