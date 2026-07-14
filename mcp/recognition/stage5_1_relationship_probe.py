from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mcp.acceptance.stage3_1_r1_target_scan_alignment import (
    _close_document_without_save,
    _open_document_with_retry,
    _resolve_open_document,
    scan_copy_r1,
)
from mcp.acceptance.stage3_1_runtime import (
    _norm_path,
    attach_existing_autocad,
    detach_autocad,
    enumerate_live_documents,
    sha256_file,
)
from mcp.acceptance.stage5_2_native_clone_poc import _retry, _scan_native
from mcp.orchestration.stage5_1_relationship_reconstruction import (
    PRIOR_REQUIRED,
    REFERENCE,
    TARGET,
    Stage51Paths,
    checkpoint,
    read_json,
    safety_flags,
    write_json,
)
from tianzheng.semantic_reader import read_semantic_entity


HEX_HANDLE = re.compile(r"^[0-9A-Fa-f]{2,16}$")


def _safe_get(obj: Any, name: str) -> tuple[Any, str | None]:
    try:
        return getattr(obj, name), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _flatten_values(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from _flatten_values(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _flatten_values(child, f"{path}[{index}]")
    else:
        yield path, value


def _bbox_distance(left: Sequence[Sequence[float]] | None, right: Sequence[Sequence[float]] | None) -> float | None:
    if not left or not right or len(left) != 2 or len(right) != 2:
        return None
    dx = max(float(left[0][0]) - float(right[1][0]), float(right[0][0]) - float(left[1][0]), 0.0)
    dy = max(float(left[0][1]) - float(right[1][1]), float(right[0][1]) - float(left[1][1]), 0.0)
    dz = max(float(left[0][2]) - float(right[1][2]), float(right[0][2]) - float(left[1][2]), 0.0)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def relation_type(left: str, right: str, distance: float) -> str | None:
    names = {left, right}
    if "TDbPipeValve" in names and "TDbPipe" in names and distance <= 100.0:
        return "VALVE_BELONGS_TO_PIPE"
    if "TDbPipeFitting" in names and "TDbPipe" in names and distance <= 5.0:
        return "FITTING_JOINS_PIPE"
    if names == {"TDbPipe"} and distance <= 5.0:
        return "CONNECTED_TO"
    if any(name in names for name in ("TDbPump", "TDbEquipment", "TDbWaterTank")) and "TDbPipe" in names and distance <= 200.0:
        return "EQUIPMENT_INTERFACE"
    return None


def _component_sets(node_ids: Sequence[str], edges: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.get("edge_type") not in {"CONNECTED_TO", "VALVE_BELONGS_TO_PIPE", "FITTING_JOINS_PIPE", "EQUIPMENT_INTERFACE"}:
            continue
        left, right = str(edge["source_id"]), str(edge["target_id"])
        adjacency[left].add(right); adjacency[right].add(left)
    seen: set[str] = set()
    components: list[list[str]] = []
    for node in sorted(node_ids):
        if node in seen:
            continue
        queue = deque([node]); seen.add(node); component = []
        while queue:
            current = queue.popleft(); component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor not in seen:
                    seen.add(neighbor); queue.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda component: (-len(component), component[0]))


def _annotation_edges(nodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    annotations = [node for node in nodes if node["object_name"] in {"TDbDimension2", "TDbVPipeDim", "TDbSymbMultiLeader"}]
    design = [node for node in nodes if node not in annotations]
    edges = []
    for annotation in annotations:
        candidates = []
        for target in design:
            distance = _bbox_distance(annotation.get("target_wcs_bbox"), target.get("target_wcs_bbox"))
            if distance is not None:
                candidates.append((distance, target))
        if candidates:
            distance, target = min(candidates, key=lambda pair: (pair[0], pair[1]["task_id"]))
            edges.append({
                "source_id": annotation["task_id"], "target_id": target["task_id"],
                "edge_type": "ANNOTATES_OBJECT", "relationship_source": "geometric_inference",
                "distance": distance, "confidence": "review_required",
            })
    return edges


def probe_relationship_graph(paths: Stage51Paths) -> dict[str, Any]:
    checkpoint_a = paths.reports / "checkpoint_a.json"
    if not checkpoint_a.is_file() or read_json(checkpoint_a).get("status") != "PASS_STAGE5_1_A_FROZEN":
        return {"phase": "STAGE5.1-B", "status": "BLOCKED_CHECKPOINT_A_NOT_PASS", "safety_flags": safety_flags()}
    reference_copy = paths.copies / "reference_analysis_copy.dwg"
    target_copy = paths.copies / "target_analysis_copy.dwg"
    required = read_json(PRIOR_REQUIRED).get("items", [])
    required_by_handle = {str(item["reference_handle"]).upper(): item for item in required}
    reference_hash_before = sha256_file(reference_copy)
    target_hash_before = sha256_file(target_copy)
    acad = document = None
    nodes: list[dict[str, Any]] = []
    unreadable: list[dict[str, Any]] = []
    live_audit: dict[str, Any] = {}
    try:
        acad = attach_existing_autocad()
        live_audit = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        opened_sources = [
            item for item in live_audit["documents"]
            if item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden
        ]
        if opened_sources:
            raise RuntimeError(f"source input open in AutoCAD: {opened_sources}")
        document = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        native_records: list[tuple[Any, dict[str, Any]]] = []
        for handle, required_item in required_by_handle.items():
            native = _retry(lambda value=handle: document.HandleToObject(value), f"relationship Handle {handle} lookup")
            scan = _scan_native(native, "stage5_1_reference_relationship")
            semantic = read_semantic_entity(native)
            object_id, object_id_error = _safe_get(native, "ObjectID")
            owner_id, owner_id_error = _safe_get(native, "OwnerID")
            owner_handle = None
            if owner_id is not None:
                try:
                    owner_handle = str(document.ObjectIDToObject(owner_id).Handle).upper()
                except Exception as exc:
                    unreadable.append({"handle": handle, "field": "OwnerHandle", "error": f"{type(exc).__name__}: {exc}"})
            if object_id_error:
                unreadable.append({"handle": handle, "field": "ObjectID", "error": object_id_error})
            if owner_id_error:
                unreadable.append({"handle": handle, "field": "OwnerID", "error": owner_id_error})
            failed_properties = ((semantic.get("properties") or {}).get("failed_properties") or {})
            for field, error in failed_properties.items():
                unreadable.append({"handle": handle, "field": field, "error": str(error)})
            node = {
                "task_id": required_item["task_id"], "reference_handle": handle,
                "object_id": int(object_id) if object_id is not None else None,
                "owner_id": int(owner_id) if owner_id is not None else None, "owner_handle": owner_handle,
                "object_name": scan.get("object_name"), "layer": scan.get("layer"),
                "reference_wcs_bbox": scan.get("bbox"),
                "target_wcs_bbox": (required_item.get("target_wcs_geometry") or {}).get("bbox"),
                "sys_type": required_item.get("sys_type") or semantic.get("system_type"),
                "dn": required_item.get("dn") or semantic.get("diameter"),
                "elevation": required_item.get("elevation") or semantic.get("elevation"),
                "semantic_type": required_item.get("semantic_type"),
                "readable_properties": (semantic.get("properties") or {}).get("readable_properties", []),
                "custom_properties": {
                    key: value for key, value in (semantic.get("properties") or {}).items()
                    if key not in {"readable_properties", "failed_properties"}
                },
                "xdata": semantic.get("xdata"), "extension_dictionary": semantic.get("extension_dictionary"),
                "inferred_geometry": semantic.get("inferred_geometry"),
                "native_reference_candidates": [], "spatially_adjacent_ids": [],
            }
            nodes.append(node); native_records.append((native, node))
        _close_document_without_save(document); document = None
        target_scan, target_block_audit = scan_copy_r1(acad, target_copy, "stage5_1_target", (REFERENCE, TARGET))
    finally:
        if document is not None:
            _close_document_without_save(document)
        if acad is not None:
            detach_autocad()
    reference_hash_after = sha256_file(reference_copy)
    target_hash_after = sha256_file(target_copy)

    by_handle = {node["reference_handle"]: node for node in nodes}
    by_object_id = {node["object_id"]: node for node in nodes if node["object_id"] is not None}
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[str, str, str]] = set()
    for node in nodes:
        metadata = {"custom_properties": node["custom_properties"], "xdata": node["xdata"], "extension_dictionary": node["extension_dictionary"]}
        for value_path, value in _flatten_values(metadata):
            target_node = None
            if isinstance(value, int) and value in by_object_id:
                target_node = by_object_id[value]
            elif isinstance(value, str) and HEX_HANDLE.fullmatch(value.strip()) and value.strip().upper() in by_handle:
                target_node = by_handle[value.strip().upper()]
            if target_node and target_node["task_id"] != node["task_id"]:
                key = (node["task_id"], target_node["task_id"], "XDATA_REFERENCES")
                if key not in edge_keys:
                    edge_keys.add(key)
                    node["native_reference_candidates"].append({"target_id": target_node["task_id"], "value_path": value_path})
                    edges.append({
                        "source_id": node["task_id"], "target_id": target_node["task_id"],
                        "edge_type": "XDATA_REFERENCES", "relationship_source": "native_internal_reference",
                        "value_path": value_path,
                    })
    for index, left in enumerate(nodes):
        for right in nodes[index + 1:]:
            distance = _bbox_distance(left.get("target_wcs_bbox"), right.get("target_wcs_bbox"))
            if distance is None:
                continue
            edge_type = relation_type(left["object_name"], right["object_name"], distance)
            if edge_type:
                edges.append({
                    "source_id": left["task_id"], "target_id": right["task_id"],
                    "edge_type": edge_type, "relationship_source": "geometric_inference",
                    "distance": distance, "tolerance": 100.0 if edge_type == "VALVE_BELONGS_TO_PIPE" else (200.0 if edge_type == "EQUIPMENT_INTERFACE" else 5.0),
                })
                left["spatially_adjacent_ids"].append(right["task_id"])
                right["spatially_adjacent_ids"].append(left["task_id"])
    edges.extend(_annotation_edges(nodes))
    components = _component_sets([node["task_id"] for node in nodes], edges)
    graph = {
        "phase": "STAGE5.1-B", "nodes": nodes, "edges": edges,
        "components": [{"component_id": f"relationship_component_{index:04d}", "node_ids": component} for index, component in enumerate(components, 1)],
        "node_count": len(nodes), "edge_count": len(edges), "component_count": len(components),
        "edge_type_counts": dict(sorted(Counter(edge["edge_type"] for edge in edges).items())),
        "relationship_source_counts": dict(sorted(Counter(edge["relationship_source"] for edge in edges).items())),
    }
    target_nodes = [entity for entity in target_scan["entities"] if str(entity.get("object_name", "")).startswith("TDb")]
    target_graph = {
        "phase": "STAGE5.1-B", "nodes": target_nodes, "edges": [], "components": [],
        "node_count": len(target_nodes), "edge_count": 0,
        "target_scan_path": str(paths.scans / "target_analysis_scan.json"),
    }
    schema = {
        "node_required_fields": ["task_id", "reference_handle", "object_name", "target_wcs_bbox", "relationship fields"],
        "edge_types": [
            "CONNECTED_TO", "ATTACHED_TO_PIPE", "FITTING_JOINS_PIPE", "VALVE_BELONGS_TO_PIPE",
            "EQUIPMENT_INTERFACE", "ANNOTATES_OBJECT", "OWNS", "OWNED_BY", "XDATA_REFERENCES",
            "DICTIONARY_REFERENCES", "GEOMETRICALLY_ADJACENT", "RESOURCE_DEPENDENCY",
        ],
        "relationship_sources": ["native_internal_reference", "geometric_inference", "resource_dependency"],
        "rule": "geometric_inference must never be promoted to native_internal_reference",
    }
    write_json(paths.root / "reference_tdb_relationship_graph.json", graph)
    write_json(paths.root / "target_existing_relationship_graph.json", target_graph)
    write_json(paths.root / "tdb_relationship_schema.json", schema)
    write_json(paths.root / "unreadable_relationship_fields.json", {"items": unreadable, "count": len(unreadable)})
    write_json(paths.scans / "target_analysis_scan.json", target_scan)
    write_json(paths.scans / "target_block_audit.json", target_block_audit)
    write_json(paths.input / "live_document_audit.json", {
        **live_audit, "source_document_open": False, "new_autocad_instance_created": False,
    })
    passed = all((
        len(nodes) == len(required) == 337, reference_hash_before == reference_hash_after,
        target_hash_before == target_hash_after, target_scan.get("copy_hash_unchanged") is True,
    ))
    status = "PASS_STAGE5_1_B_RELATIONSHIP_GRAPH" if passed else "BLOCKED_RELATIONSHIP_PROBE_INCOMPLETE"
    report = {
        "phase": "STAGE5.1-B", "status": status, "required_count": len(required),
        "node_count": len(nodes), "edge_count": len(edges), "component_count": len(components),
        "native_internal_edge_count": sum(edge["relationship_source"] == "native_internal_reference" for edge in edges),
        "geometric_inference_edge_count": sum(edge["relationship_source"] == "geometric_inference" for edge in edges),
        "unreadable_field_count": len(unreadable),
        "reference_analysis_hash_unchanged": reference_hash_before == reference_hash_after,
        "target_analysis_hash_unchanged": target_hash_before == target_hash_after,
        "analysis_copies_saved": False, "source_opened": False, "source_saved": False,
        "safety_flags": {**safety_flags(), "analysis_copies_opened": True},
    }
    write_json(paths.reports / "checkpoint_b.json", report)
    checkpoint(paths, "RELATIONSHIP_GRAPH_COMPLETE", status="completed" if passed else "blocked", details=report)
    return report

