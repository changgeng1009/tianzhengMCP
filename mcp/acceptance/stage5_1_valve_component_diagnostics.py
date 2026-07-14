from __future__ import annotations

import shutil
from collections import defaultdict
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
from mcp.acceptance.stage5_2_component_clone_poc import _bbox_distance, _system_from_layer
from mcp.acceptance.stage5_2_native_clone_poc import (
    _bbox_close,
    _modelspace_handles,
    _object_array,
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


def _edge_adjacency(graph: Mapping[str, Any]) -> dict[str, dict[str, list[str]]]:
    adjacency: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for edge in graph["edges"]:
        edge_type = edge["edge_type"]
        if edge_type not in {"VALVE_BELONGS_TO_PIPE", "FITTING_JOINS_PIPE", "CONNECTED_TO", "EQUIPMENT_INTERFACE"}:
            continue
        left, right = edge["source_id"], edge["target_id"]
        adjacency[left][edge_type].append(right)
        adjacency[right][edge_type].append(left)
    return adjacency


def select_valve_diagnostic_subject(graph: Mapping[str, Any]) -> dict[str, Any]:
    by_id = {node["task_id"]: node for node in graph["nodes"]}
    component_by_node = {
        node_id: component for component in graph["components"] for node_id in component["node_ids"]
    }
    adjacency = _edge_adjacency(graph)
    candidates = []
    for node in graph["nodes"]:
        if node["object_name"] != "TDbPipeValve":
            continue
        pipes = sorted(
            (by_id[item] for item in adjacency[node["task_id"]]["VALVE_BELONGS_TO_PIPE"] if by_id[item]["object_name"] == "TDbPipe"),
            key=lambda item: (_bbox_distance(node["target_wcs_bbox"], item["target_wcs_bbox"]), item["task_id"]),
        )
        fittings: dict[str, dict[str, Any]] = {}
        for pipe in pipes:
            for fitting_id in adjacency[pipe["task_id"]]["FITTING_JOINS_PIPE"]:
                if by_id[fitting_id]["object_name"] == "TDbPipeFitting":
                    fittings[fitting_id] = by_id[fitting_id]
        component = component_by_node[node["task_id"]]
        if len(pipes) >= 2 and fittings and len(component["node_ids"]) <= 20:
            system_known = node.get("sys_type") not in (None, "", "unknown")
            candidates.append((not system_known, len(component["node_ids"]), len(pipes), node["task_id"], node, pipes, list(fittings.values()), component))
    if not candidates:
        raise ValueError("no valve has two inferred pipes, a fitting, and a bounded local component")
    _, _, _, _, valve, pipes, fittings, component = sorted(candidates, key=lambda row: (row[0], row[1], row[2], row[3]))[0]
    return {
        "valve": valve, "pipes": pipes, "fittings": sorted(fittings, key=lambda item: item["task_id"]),
        "component": component,
    }


def build_valve_variants(subject: Mapping[str, Any], graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_id = {node["task_id"]: node for node in graph["nodes"]}
    valve = subject["valve"]
    pipes = subject["pipes"]
    fittings = subject["fittings"]
    full_component = [by_id[item] for item in subject["component"]["node_ids"]]
    first_fitting = fittings[:1]
    local = {item["task_id"]: item for item in [valve, *pipes, *fittings]}
    variants = [
        ("01_single_valve_control", [valve], False),
        ("02_valve_single_pipe", [valve, pipes[0]], False),
        ("03_valve_two_side_pipes", [valve, pipes[0], pipes[1]], False),
        ("04_valve_pipes_fitting", [valve, pipes[0], pipes[1], *first_fitting], False),
        ("05_minimal_local_component", list(local.values()), False),
        ("06_full_connected_component_with_metadata", full_component, True),
    ]
    return [
        {
            "variant_id": variant_id, "nodes": nodes, "include_internal_metadata_dependencies": metadata,
            "expected_handles": [node["reference_handle"] for node in nodes],
            "expected_task_ids": [node["task_id"] for node in nodes],
        }
        for variant_id, nodes, metadata in variants
    ]


def _parse_copyobjects_return(returned: Any, source_doc: Any, target_doc: Any) -> dict[str, Any]:
    import win32com.client

    def leaves(value: Any) -> list[Any]:
        if isinstance(value, (tuple, list)):
            return [leaf for child in value for leaf in leaves(child)]
        return [] if value is None else [value]

    primary_values: list[Any] = []
    pair_values: list[Any] = []
    unknown_values: list[dict[str, Any]] = []
    for value in leaves(returned):
        if isinstance(value, (str, int, float, bool)):
            unknown_values.append({"python_type": type(value).__name__, "value": value})
            continue
        wrapped = win32com.client.Dispatch(value)
        try:
            getattr(wrapped, "ObjectName")
            primary_values.append(value)
            continue
        except Exception:
            pass
        try:
            getattr(wrapped, "Key")
            getattr(wrapped, "Value")
            pair_values.append(value)
            continue
        except Exception as exc:
            unknown_values.append({"python_type": type(value).__name__, "error": f"{type(exc).__name__}: {exc}"})
    primaries = []
    for value in primary_values:
        wrapped = win32com.client.Dispatch(value)
        record = {"python_type": type(value).__name__}
        for field in ("Handle", "ObjectName"):
            try:
                record[field.lower()] = str(getattr(wrapped, field))
            except Exception as exc:
                record[f"{field.lower()}_error"] = f"{type(exc).__name__}: {exc}"
        primaries.append(record)
    pairs = []
    for pair in pair_values:
        wrapped = win32com.client.Dispatch(pair)
        record: dict[str, Any] = {"python_type": type(pair).__name__}
        for field in ("Key", "Value", "IsPrimary", "IsCloned", "IsOwnerXlated"):
            try:
                record[field] = getattr(wrapped, field)
            except Exception as exc:
                record[f"{field}_error"] = f"{type(exc).__name__}: {exc}"
        if record.get("Key") is not None:
            try:
                record["source_handle"] = str(source_doc.ObjectIDToObject(record["Key"]).Handle).upper()
            except Exception:
                record["source_handle"] = None
        if record.get("Value") is not None:
            try:
                record["target_handle"] = str(target_doc.ObjectIDToObject(record["Value"]).Handle).upper()
            except Exception:
                record["target_handle"] = None
        pairs.append(record)
    return {"primary_return_records": primaries, "idpairs": pairs, "unknown_return_records": unknown_values}


def _copyobjects_with_explicit_idpairs(source_doc: Any, source_objects: Sequence[Any], owner: Any) -> Any:
    import pythoncom
    import win32com.client

    idpairs = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, 0)
    returned = source_doc.CopyObjects(_object_array(source_objects), owner, idpairs)
    return returned, idpairs.value


def _match_expected(records: Sequence[Mapping[str, Any]], nodes: Sequence[Mapping[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    matches: dict[str, dict[str, Any]] = {}
    unused = list(records)
    errors = []
    for node in nodes:
        candidates = [
            record for record in unused
            if record.get("object_name") == node["object_name"] and _bbox_close(record.get("bbox"), node.get("target_wcs_bbox"))
        ]
        if len(candidates) != 1:
            errors.append(f"{node['task_id']}: match_count={len(candidates)}")
            continue
        matches[node["task_id"]] = dict(candidates[0]); unused.remove(candidates[0])
    if unused:
        errors.append(f"unmatched_new_handles={[record.get('handle') for record in unused]}")
    return matches, errors


def _variant_qa(variant: Mapping[str, Any], records: Sequence[Mapping[str, Any]], copy_map: Mapping[str, Any]) -> dict[str, Any]:
    nodes = variant["nodes"]
    valve = next(node for node in nodes if node["object_name"] == "TDbPipeValve")
    matches, errors = _match_expected(records, nodes)
    valve_record = matches.get(valve["task_id"])
    pipe_nodes = [node for node in nodes if node["object_name"] == "TDbPipe"]
    pipe_records = [matches[node["task_id"]] for node in pipe_nodes if node["task_id"] in matches]
    fitting_count = sum(node["object_name"] == "TDbPipeFitting" for node in nodes)
    attached = [
        record for record in pipe_records
        if valve_record and _bbox_distance(valve_record.get("bbox"), record.get("bbox")) is not None
        and _bbox_distance(valve_record.get("bbox"), record.get("bbox")) <= 100.0
    ]
    expected_system = valve.get("sys_type")
    if expected_system in (None, "", "unknown"):
        expected_system = _system_from_layer(valve.get("layer"))
    systems = [(record.get("attributes") or {}).get("sys_type") for record in attached]
    dns = [(record.get("attributes") or {}).get("dn_diameter") for record in attached]
    idpair_source_handles = {
        pair.get("source_handle") for pair in copy_map.get("idpairs", [])
        if pair.get("source_handle") and pair.get("IsCloned") is not False
    }
    expected_handles = set(variant["expected_handles"])
    all_expected_idpairs_mapped = expected_handles.issubset(idpair_source_handles)
    native_valve_persisted = bool(valve_record and valve_record.get("object_name") == "TDbPipeValve")
    no_unrelated_objects = not errors and len(records) == len(nodes)
    relationship_ready = all((
        native_valve_persisted, len(attached) >= 2, fitting_count >= 1,
        expected_system is not None, all(system == expected_system for system in systems),
        all(dn not in (None, 0, 0.0) for dn in dns), all_expected_idpairs_mapped,
        no_unrelated_objects,
    ))
    return {
        "passed": not errors and len(records) == len(nodes), "relationship_ready": relationship_ready,
        "errors": errors, "native_valve_persisted": native_valve_persisted,
        "attached_pipe_count": len(attached), "fitting_count": fitting_count,
        "system_match": bool(systems and expected_system and all(system == expected_system for system in systems)),
        "dn_match": bool(dns and all(dn not in (None, 0, 0.0) for dn in dns)),
        "geometry_and_direction_match": bool(valve_record and _bbox_close(valve_record.get("bbox"), valve.get("target_wcs_bbox"))),
        "all_expected_idpairs_mapped": all_expected_idpairs_mapped,
        "idpair_mapped_source_handles": sorted(value for value in idpair_source_handles if value),
        "no_unrelated_objects": no_unrelated_objects,
        "relationship_evidence_source": "copyobjects_idpairs_component_behavior_and_persisted_native_geometry",
    }


def run_valve_variant(paths: Stage51Paths, variant: Mapping[str, Any]) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    variant_id = variant["variant_id"]
    route_dir = paths.capabilities / "valve_diagnostics" / variant_id
    route_dir.mkdir(parents=True, exist_ok=True)
    reference_copy = route_dir / "reference_component_copy.dwg"
    target_sandbox = route_dir / "target_component_sandbox.dwg"
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
    records: list[dict[str, Any]] = []; persisted_records: list[dict[str, Any]] = []
    copy_map: dict[str, Any] = {"primary_return_records": [], "idpairs": []}
    saved = False; error: str | None = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, target_sandbox, _retry(lambda: acad.Documents.Open(str(target_sandbox), False), "valve diagnostic target open"))
        source_objects = [
            _retry(lambda handle=node["reference_handle"]: source_doc.HandleToObject(handle), f"diagnostic Handle {node['reference_handle']} lookup")
            for node in variant["nodes"]
        ]
        before_handles = _modelspace_handles(target_doc)
        returned = _retry(
            lambda: _copyobjects_with_explicit_idpairs(source_doc, source_objects, target_doc.ModelSpace),
            f"{variant_id} CopyObjects with explicit IDPairs",
        )
        copy_map = _parse_copyobjects_return(returned, source_doc, target_doc)
        after_handles = _modelspace_handles(target_doc)
        created_handles = sorted(after_handles - before_handles)
        if len(created_handles) != len(variant["nodes"]):
            raise RuntimeError(f"created Handle delta {len(created_handles)} != approved node count {len(variant['nodes'])}")
        for handle in created_handles:
            native = _retry(lambda value=handle: target_doc.HandleToObject(value), f"created Handle {handle} lookup")
            _retry(lambda obj=native: obj.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), f"move {handle}")
            records.append(_scan_native(native, "stage5_1_valve_variant"))
        qa = _variant_qa(variant, records, copy_map)
        if not qa["passed"]:
            raise RuntimeError(f"variant pre-save QA failed: {qa}")
        _retry(lambda: target_doc.Save(), f"{variant_id} save")
        saved = True
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        reopened = _resolve_open_document(acad, target_sandbox, _open_document_with_retry(acad, target_sandbox))
        try:
            for handle in created_handles:
                persisted_records.append(_scan_native(
                    _retry(lambda value=handle: reopened.HandleToObject(value), f"persisted {handle} lookup"),
                    "stage5_1_valve_variant_persisted",
                ))
        finally:
            _safe_close(reopened)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()
    pre_save_qa = _variant_qa(variant, records, copy_map)
    persistence_qa = _variant_qa(variant, persisted_records, copy_map)
    status = "VERIFIED_COMPONENT_CLONE" if saved and persistence_qa["relationship_ready"] and error is None else (
        "FAILED_RELATIONSHIP_PERSISTENCE" if saved and not persistence_qa["relationship_ready"] else "BLOCKED_DEPENDENCY"
    )
    result = {
        "phase": "STAGE5.1-D", "variant_id": variant_id, "status": status,
        "input_task_ids": variant["expected_task_ids"], "input_reference_handles": variant["expected_handles"],
        "expected_object_count": len(variant["nodes"]), "actual_new_handle_count": len(created_handles),
        "created_handles": created_handles, "copyobjects_mapping": copy_map,
        "pre_save_qa": pre_save_qa, "persistence_qa": persistence_qa,
        "saved": saved, "reopened": bool(persisted_records),
        "unrelated_object_count": max(0, len(created_handles) - len(variant["nodes"])),
        "source_hashes_unchanged": sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256,
        "error": error,
        "safety_flags": {
            **safety_flags(), "autocad_connected": True, "selective_copyobjects_used": True,
            "disposable_sandbox_modified": bool(records), "disposable_sandbox_saved": saved,
            "source_reference_opened": False, "source_target_opened": False,
        },
    }
    write_json(route_dir / "result.json", result)
    return result


def run_valve_relationship_diagnostics(paths: Stage51Paths) -> dict[str, Any]:
    report_c = paths.reports / "checkpoint_c.json"
    if not report_c.is_file() or read_json(report_c).get("status") != "PASS_STAGE5_1_C_COMPONENTS":
        return {"phase": "STAGE5.1-D", "status": "BLOCKED_CHECKPOINT_C_NOT_PASS", "safety_flags": safety_flags()}
    if source_lock_files(REFERENCE) or source_lock_files(TARGET):
        return {"phase": "STAGE5.1-D", "status": "BLOCKED_SOURCE_LOCKED", "safety_flags": safety_flags()}
    graph = read_json(paths.root / "reference_tdb_relationship_graph.json")
    subject = select_valve_diagnostic_subject(graph)
    variants = build_valve_variants(subject, graph)
    write_json(paths.capabilities / "valve_diagnostic_subject.json", {
        "valve": subject["valve"], "pipe_ids": [node["task_id"] for node in subject["pipes"]],
        "fitting_ids": [node["task_id"] for node in subject["fittings"]], "component": subject["component"],
    })
    results = [run_valve_variant(paths, variant) for variant in variants]
    verified = [result for result in results if result["status"] in {"VERIFIED_COMPONENT_CLONE", "VERIFIED_RELATIONSHIP_REMAP"}]
    best = verified[0] if verified else None
    final_status = "VERIFIED_COMPONENT_CLONE" if best else "BLOCKED_VALVE_RELATIONSHIP_UNRESOLVED"
    report = {
        "phase": "STAGE5.1-D", "status": final_status,
        "subject_valve_task_id": subject["valve"]["task_id"],
        "subject_valve_reference_handle": subject["valve"]["reference_handle"],
        "variant_count": len(results), "variant_results": results,
        "verified_variant_id": best["variant_id"] if best else None,
        "valve_capability": final_status,
        "source_hashes_unchanged": all(result["source_hashes_unchanged"] for result in results),
        "safety_flags": {
            **safety_flags(), "autocad_connected": True, "selective_copyobjects_used": True,
            "source_reference_opened": False, "source_target_opened": False,
        },
    }
    write_json(paths.root / "valve_relationship_diagnostics.json", report)
    checkpoint(
        paths, "VALVE_RELATIONSHIP_VERIFIED",
        status="completed" if best else "blocked",
        details={"status": final_status, "verified_variant_id": report["verified_variant_id"]},
    )
    return report
