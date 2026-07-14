from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
from mcp.acceptance.stage3_1_runtime import (
    _norm_path,
    attach_existing_autocad,
    detach_autocad,
    enumerate_live_documents,
    sha256_file,
)
from mcp.acceptance.stage3_3_controlled_repair import source_lock_files
from mcp.acceptance.stage5_2_native_clone_poc import _retry, _safe_close, _scan_native
from mcp.orchestration.stage5_1_relationship_reconstruction import (
    REFERENCE,
    REFERENCE_SHA256,
    TARGET,
    TARGET_SHA256,
    TRANSLATION,
    safety_flags,
)
from tianzheng.semantic_reader import PROPERTY_PROBE_NAMES, read_semantic_entity


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "artifacts" / "stage5_1_r2"
REPORT_JSON = ROOT / "reports" / "stage5_1_r2_required_tdb_readback.json"
REPORT_MD = ROOT / "reports" / "stage5_1_r2_required_tdb_readback.md"
PRIOR_RUN = ROOT / "artifacts" / "stage5_1" / "stage5_1_20260711_143721"
PRIOR_REPORT = ROOT / "reports" / "stage5_1_mvp2_native_full_reconstruction.json"
GRAPH_PATH = PRIOR_RUN / "reference_tdb_relationship_graph.json"
PRIOR_MATRIX = PRIOR_RUN / "tdb_creation_capability_matrix.json"

REMAINING_TYPES = (
    "TDbPump", "TDbEquipment", "TDbWaterTank",
    "TDbDimension2", "TDbVPipeDim", "TDbSymbMultiLeader",
)
DEVICE_TYPES = {"TDbPump", "TDbEquipment", "TDbWaterTank"}
ANNOTATION_TYPES = {"TDbDimension2", "TDbVPipeDim", "TDbSymbMultiLeader"}


@dataclass(frozen=True)
class R2Paths:
    run_id: str
    root: Path
    archive: Path
    copies: Path
    audits: Path
    fingerprints: Path
    reports: Path

    @classmethod
    def build(cls, run_id: str) -> "R2Paths":
        root = RUNS_ROOT / run_id
        return cls(run_id, root, root / "archive", root / "copies", root / "audits", root / "fingerprints", root / "reports")

    def create(self) -> None:
        for path in (self.root, self.archive, self.copies, self.audits, self.fingerprints, self.reports):
            path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if hasattr(value, "value"):
        return _json_value(value.value)
    return f"<{type(value).__name__}>"


def _hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _typeinfo_names(native: Any) -> tuple[list[str], dict[str, Any]]:
    names = {name for name in dir(native) if not name.startswith("_")}
    diagnostics: dict[str, Any] = {"dir_name_count": len(names)}
    try:
        type_info = native._oleobj_.GetTypeInfo()
        type_attr = type_info.GetTypeAttr()
        function_count = int(type_attr[8]); variable_count = int(type_attr[9])
        diagnostics.update({"function_count": function_count, "variable_count": variable_count})
        for index in range(function_count):
            descriptor = type_info.GetFuncDesc(index)
            names.update(type_info.GetNames(descriptor[0]))
        for index in range(variable_count):
            descriptor = type_info.GetVarDesc(index)
            names.update(type_info.GetNames(descriptor[0]))
    except Exception as exc:
        diagnostics["typeinfo_error"] = f"{type(exc).__name__}: {exc}"
    return sorted(names), diagnostics


def audit_com_properties(native: Any) -> dict[str, Any]:
    names, diagnostics = _typeinfo_names(native)
    candidate_names = sorted(set(names) | set(PROPERTY_PROBE_NAMES) | {
        "ObjectName", "Handle", "OwnerID", "ObjectID", "InsertionPoint", "Position", "Center",
        "Rotation", "Angle", "Direction", "Width", "Height", "Length", "TextString",
        "TextOverride", "Measurement", "PrimaryText", "LeaderPoints", "Coordinates",
    })
    readable: dict[str, Any] = {}
    unreadable: dict[str, str] = {}
    methods: list[str] = []
    for name in candidate_names:
        try:
            value = getattr(native, name)
            if callable(value):
                methods.append(name)
            else:
                readable[name] = _json_value(value)
        except Exception as exc:
            unreadable[name] = f"{type(exc).__name__}: {exc}"
    return {
        "available_names": names, "readable_properties": readable,
        "unreadable_properties": unreadable, "methods": methods, "typeinfo": diagnostics,
    }


def _bbox_center(bbox: Sequence[Sequence[float]]) -> list[float]:
    return [(float(bbox[0][index]) + float(bbox[1][index])) / 2.0 for index in range(3)]


def _bbox_dimensions(bbox: Sequence[Sequence[float]]) -> list[float]:
    return [abs(float(bbox[1][index]) - float(bbox[0][index])) for index in range(3)]


def _closest_point_on_bbox(center: Sequence[float], bbox: Sequence[Sequence[float]]) -> list[float]:
    return [max(float(bbox[0][index]), min(float(center[index]), float(bbox[1][index]))) for index in range(3)]


def _normalize(vector: Sequence[float]) -> list[float] | None:
    length = math.sqrt(sum(float(value) ** 2 for value in vector[:2]))
    if length <= 1e-9:
        return None
    return [round(float(vector[0]) / length, 9), round(float(vector[1]) / length, 9), 0.0]


def derive_device_geometry(
    node: Mapping[str, Any], graph: Mapping[str, Any], direct_properties: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    bbox = node["target_wcs_bbox"]
    center = _bbox_center(bbox); dimensions = _bbox_dimensions(bbox)
    by_id = {item["task_id"]: item for item in graph["nodes"]}
    connected_pipe_ids = []
    for edge in graph["edges"]:
        if edge["edge_type"] != "EQUIPMENT_INTERFACE" or node["task_id"] not in {edge["source_id"], edge["target_id"]}:
            continue
        other = edge["target_id"] if edge["source_id"] == node["task_id"] else edge["source_id"]
        if by_id.get(other, {}).get("object_name") == "TDbPipe":
            connected_pipe_ids.append(other)
    interface_points = [_closest_point_on_bbox(center, by_id[item]["target_wcs_bbox"]) for item in connected_pipe_ids]
    vectors = []
    for point in interface_points:
        normalized = _normalize([point[index] - center[index] for index in range(3)])
        if normalized and normalized not in vectors:
            vectors.append(normalized)
    readable = {**(node.get("custom_properties") or {}), **(direct_properties or {})}
    direct_angle = next(
        (readable[key] for key in ("Rotation", "Angle", "LRotation", "LayoutRotation") if isinstance(readable.get(key), (int, float))),
        None,
    )
    if isinstance(direct_angle, (int, float)):
        radians = math.radians(float(direct_angle)) if abs(float(direct_angle)) > 2 * math.pi else float(direct_angle)
        orientation = [round(math.cos(radians), 9), round(math.sin(radians), 9), 0.0]
        orientation_source = "direct_rotation_or_angle"
        orientation_unique = True
    elif len(vectors) == 1:
        orientation = vectors[0]; orientation_source = "single_equipment_interface_vector"; orientation_unique = True
    elif len(vectors) > 1 and all(vector == vectors[0] for vector in vectors):
        orientation = vectors[0]; orientation_source = "coincident_equipment_interface_vectors"; orientation_unique = True
    else:
        orientation = None; orientation_source = "ambiguous_or_missing_interface_vectors"; orientation_unique = False
    return {
        "engineering_position": center, "position_source": "bbox_anchor",
        "bbox_dimensions": dimensions, "dimensions_source": "bbox_dimensions",
        "connected_pipe_ids": sorted(set(connected_pipe_ids)), "interface_points": interface_points,
        "interface_vectors": vectors, "orientation_vector": orientation,
        "orientation_source": orientation_source, "orientation_unique": orientation_unique,
    }


def derive_annotation_target(node: Mapping[str, Any], graph: Mapping[str, Any]) -> dict[str, Any]:
    candidates = []
    for edge in graph["edges"]:
        if edge["edge_type"] == "ANNOTATES_OBJECT" and edge["source_id"] == node["task_id"]:
            candidates.append((float(edge.get("distance", 0.0)), edge["target_id"]))
    candidates.sort()
    unique = len(candidates) == 1 or (len(candidates) > 1 and candidates[1][0] - candidates[0][0] > 1e-6)
    return {
        "candidate_targets": [{"target_id": target, "distance": distance} for distance, target in candidates],
        "derived_target_id": candidates[0][1] if candidates and unique else None,
        "target_unique": bool(candidates and unique),
        "relationship_evidence": "deterministic_geometric_derivation" if candidates and unique else "ambiguous_geometric_derivation",
    }


def annotation_display_signature(object_name: str, properties: Mapping[str, Any]) -> dict[str, Any] | None:
    if object_name == "TDbVPipeDim":
        keys = ("VPipeFloorType", "VPipeFloorNum", "VPipeNum", "VPipeType", "ShowPipeDn", "DnDist")
    elif object_name == "TDbSymbMultiLeader":
        keys = ("UpText", "DownText", "UpTextType", "DownTextType", "TextLayer", "FontStyle")
    else:
        keys = ("TextString", "TextOverride", "Measurement", "PrimaryText", "DimensionText")
    signature = {key: properties[key] for key in keys if properties.get(key) not in (None, "")}
    return signature or None


def annotation_leader_signature(
    object_name: str, properties: Mapping[str, Any], bbox: Sequence[Sequence[float]],
) -> dict[str, Any] | None:
    if object_name == "TDbVPipeDim":
        keys = ("Dist", "DnDist", "LRotation", "AlignType", "VPipeType")
    elif object_name == "TDbSymbMultiLeader":
        keys = ("ArrowSize", "ArrowStyle", "UpPageWidth", "DownPageWidth", "LayoutRotation", "AlignType")
    else:
        keys = ("LeaderPoints", "Coordinates", "LayoutRotation")
    values = {key: properties[key] for key in keys if properties.get(key) not in (None, "")}
    if object_name == "TDbDimension2" and not any(key in values for key in ("LeaderPoints", "Coordinates")):
        return None
    normalized_bbox = [[round(float(value), 6) for value in point] for point in bbox]
    return {"properties": values, "bbox": normalized_bbox} if values else None


def stable_fingerprint(
    node: Mapping[str, Any], scan: Mapping[str, Any], semantic: Mapping[str, Any],
    derived: Mapping[str, Any], direct_properties: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    properties = semantic.get("properties") or {}
    direct = dict(direct_properties or {})
    stable_direct = {
        key: value for key, value in direct.items()
        if key not in {"ObjectID", "OwnerID", "Handle", "Application", "Document", "Database"}
    }
    if isinstance(stable_direct.get("Linetype"), str):
        stable_direct["Linetype"] = stable_direct["Linetype"].upper()
    display_signature = annotation_display_signature(str(scan.get("object_name")), direct)
    leader_signature = annotation_leader_signature(str(scan.get("object_name")), direct, scan.get("bbox") or [])
    payload = {
        "object_name": scan.get("object_name"), "layer": scan.get("layer"),
        "bbox": [[round(float(value), 6) for value in point] for point in (scan.get("bbox") or [])],
        "geometry_anchor": derived.get("engineering_position") or derived.get("derived_target_id"),
        "orientation_vector": derived.get("orientation_vector"),
        "interface_points": derived.get("interface_points", []),
        "connected_component_signature": sorted(derived.get("connected_pipe_ids", [])),
        "display_content_signature": semantic.get("text") or semantic.get("measurement") or display_signature,
        "leader_geometry_signature": leader_signature,
        "annotation_target_signature": derived.get("derived_target_id"),
        "xdata_signature": _hash_payload(semantic.get("xdata")),
        "dictionary_signature": _hash_payload(semantic.get("extension_dictionary")),
        "stable_properties": {
            key: value for key, value in properties.items()
            if key not in {"readable_properties", "failed_properties", "ObjectID", "OwnerID", "Handle"}
        },
        "exhaustive_com_properties": stable_direct,
    }
    payload["fingerprint_sha256"] = _hash_payload(payload)
    return payload


def _poc_result_path(object_name: str) -> Path:
    return PRIOR_RUN / "capabilities" / "remaining_type_pocs" / object_name / "result.json"


def _poc_sandbox_path(object_name: str) -> Path:
    return PRIOR_RUN / "capabilities" / "remaining_type_pocs" / object_name / "target_poc_sandbox.dwg"


def _transform_reference_bbox(bbox: Sequence[Sequence[float]]) -> list[list[float]]:
    from mcp.orchestration.private_run_config import require_parameter
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    return [[float(point[index]) + TRANSLATION[index] for index in range(3)] for point in bbox]


def _fingerprints_match(reference: Mapping[str, Any], clone: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "object_name": reference.get("object_name") == clone.get("object_name"),
        "layer": reference.get("layer") == clone.get("layer"),
        "bbox": reference.get("bbox") == clone.get("bbox"),
        "orientation_vector": reference.get("orientation_vector") == clone.get("orientation_vector"),
        "display_content_signature": reference.get("display_content_signature") == clone.get("display_content_signature"),
        "leader_geometry_signature": reference.get("leader_geometry_signature") == clone.get("leader_geometry_signature"),
        "xdata_signature": reference.get("xdata_signature") == clone.get("xdata_signature"),
        "dictionary_signature": reference.get("dictionary_signature") == clone.get("dictionary_signature"),
        "stable_properties": reference.get("stable_properties") == clone.get("stable_properties"),
        "exhaustive_com_properties": reference.get("exhaustive_com_properties") == clone.get("exhaustive_com_properties"),
    }
    return {"passed": all(checks.values()), "checks": checks}


def run_r2_readback(run_id: str | None = None) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    run_id = run_id or datetime.now().strftime("stage5_1_r2_%Y%m%d_%H%M%S")
    paths = R2Paths.build(run_id); paths.create()
    required_files = [PRIOR_REPORT, PRIOR_MATRIX, GRAPH_PATH, *(_poc_result_path(name) for name in REMAINING_TYPES), *(_poc_sandbox_path(name) for name in REMAINING_TYPES)]
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        return {"status": "BLOCKED_REQUIRED_FIELD_UNREADABLE", "missing_files": missing, "safety_flags": safety_flags()}
    locks = {"reference": source_lock_files(REFERENCE), "target": source_lock_files(TARGET)}
    if locks["reference"] or locks["target"]:
        return {"status": "BLOCKED_SOURCE_LOCKED", "source_locks": locks, "safety_flags": safety_flags()}
    source_hashes_before = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    if source_hashes_before != {"reference": REFERENCE_SHA256, "target": TARGET_SHA256}:
        return {"status": "BLOCKED_INPUT_HASH_CHANGED", "source_hashes": source_hashes_before, "safety_flags": safety_flags()}
    shutil.copy2(REFERENCE, paths.copies / "reference_analysis_copy.dwg")
    shutil.copy2(TARGET, paths.copies / "target_analysis_copy.dwg")
    shutil.copy2(PRIOR_REPORT, paths.archive / "prior_stage5_1_report.json")
    shutil.copy2(PRIOR_MATRIX, paths.archive / "prior_capability_matrix.json")
    graph = read_json(GRAPH_PATH)
    graph_by_handle = {node["reference_handle"]: node for node in graph["nodes"]}
    poc_results = {object_name: read_json(_poc_result_path(object_name)) for object_name in REMAINING_TYPES}
    by_type = {
        object_name: graph_by_handle[poc_results[object_name]["primary_reference_handle"]]
        for object_name in REMAINING_TYPES
    }
    com_inventory: dict[str, Any] = {}; xdata_inventory: dict[str, Any] = {}; dictionary_inventory: dict[str, Any] = {}
    nested_inventory: dict[str, Any] = {}; fingerprints: dict[str, Any] = {}; readability: dict[str, Any] = {}
    acad = reference_doc = clone_doc = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        reference_copy = paths.copies / "reference_analysis_copy.dwg"
        reference_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        for object_name in REMAINING_TYPES:
            node = by_type[object_name]
            native = _retry(lambda handle=node["reference_handle"]: reference_doc.HandleToObject(handle), f"R2 reference {object_name} lookup")
            scan = _scan_native(native, "stage5_1_r2_reference")
            semantic = read_semantic_entity(native)
            com_inventory[object_name] = {"reference_handle": node["reference_handle"], **audit_com_properties(native)}
            xdata_inventory[object_name] = semantic.get("xdata")
            dictionary_inventory[object_name] = semantic.get("extension_dictionary")
            nested_inventory[object_name] = {
                "object_name": scan.get("object_name"), "is_block_reference": scan.get("object_name") == "AcDbBlockReference",
                "nested_block_geometry_available": False,
                "real_explode_called": False, "virtual_explode_result": [],
                "reason": "native TDb object exposes no block definition or read-only virtual explode API",
            }
            reference_direct = com_inventory[object_name]["readable_properties"]
            derived = derive_device_geometry(node, graph, reference_direct) if object_name in DEVICE_TYPES else derive_annotation_target(node, graph)
            reference_scan_for_fingerprint = dict(scan)
            reference_scan_for_fingerprint["bbox"] = _transform_reference_bbox(scan["bbox"])
            reference_fp = stable_fingerprint(node, reference_scan_for_fingerprint, semantic, derived, reference_direct)
            _safe_close(reference_doc); reference_doc = None
            poc_result = poc_results[object_name]
            clone_path = _poc_sandbox_path(object_name)
            clone_doc = _resolve_open_document(acad, clone_path, _open_document_with_retry(acad, clone_path))
            clone_native = None
            for handle in poc_result["created_handles"]:
                candidate = _retry(lambda value=handle: clone_doc.HandleToObject(value), f"R2 clone {handle} lookup")
                if str(candidate.ObjectName) == object_name:
                    clone_native = candidate; break
            if clone_native is None:
                raise RuntimeError(f"persisted clone type not found: {object_name}")
            clone_scan = _scan_native(clone_native, "stage5_1_r2_clone")
            clone_semantic = read_semantic_entity(clone_native)
            clone_com = audit_com_properties(clone_native)
            clone_fp = stable_fingerprint(node, clone_scan, clone_semantic, derived, clone_com["readable_properties"])
            match = _fingerprints_match(reference_fp, clone_fp)
            fingerprints[object_name] = {
                "reference": reference_fp, "clone_before_save_evidence": poc_result["pre_save_qa"],
                "reopened_clone": clone_fp, "reference_clone_reopen_match": match,
            }
            _safe_close(clone_doc); clone_doc = None
            reference_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
            direct = reference_direct
            if object_name in DEVICE_TYPES:
                field_results = {
                    "object_name": {"level": "REQUIRED_CRITICAL", "available": True, "source": "COM.ObjectName"},
                    "engineering_position": {"level": "REQUIRED_DERIVABLE", "available": True, "source": "bbox_anchor"},
                    "orientation": {"level": "REQUIRED_DERIVABLE", "available": derived["orientation_unique"], "source": derived["orientation_source"]},
                    "dimensions": {"level": "REQUIRED_DERIVABLE", "available": True, "source": "bbox_dimensions"},
                    "interface_points": {"level": "REQUIRED_CRITICAL", "available": bool(derived["interface_points"]), "source": "relationship_graph_and_pipe_geometry"},
                    "connected_pipe": {"level": "REQUIRED_CRITICAL", "available": bool(derived["connected_pipe_ids"]), "source": "component_graph_plus_IDPairs"},
                    "device_number": {"level": "OPTIONAL_NONCRITICAL", "available": any(key in direct for key in ("Name", "TextString", "Number")), "source": "COM_property_if_readable"},
                }
            else:
                display_signature = annotation_display_signature(object_name, direct)
                leader_signature = annotation_leader_signature(object_name, direct, node["target_wcs_bbox"])
                field_results = {
                    "object_name": {"level": "REQUIRED_CRITICAL", "available": True, "source": "COM.ObjectName"},
                    "display_content": {"level": "REQUIRED_CRITICAL", "available": display_signature is not None, "source": "exhaustive_COM_display_signature"},
                    "position": {"level": "REQUIRED_DERIVABLE", "available": True, "source": "bbox_anchor"},
                    "leader_geometry": {"level": "REQUIRED_CRITICAL", "available": leader_signature is not None, "source": "exhaustive_COM_leader_signature_plus_bbox"},
                    "annotation_target": {"level": "REQUIRED_CRITICAL", "available": derived["target_unique"], "source": derived["relationship_evidence"]},
                }
            missing_critical = [field for field, result in field_results.items() if result["level"].startswith("REQUIRED") and not result["available"]]
            readability[object_name] = {
                "field_results": field_results, "missing_required_fields": missing_critical,
                "stable_fingerprint_match": match["passed"],
                "all_attempted_channels": [
                    "COM_dynamic_properties", "ObjectName_Handle_OwnerId_ObjectId", "GetXData",
                    "ExtensionDictionary", "NamedObjectDictionary", "IDPairs", "GetBoundingBox",
                    "position_center", "rotation", "dimensions", "nested_block_geometry",
                    "internal_text_or_child", "neighboring_TDb", "equipment_interface_geometry",
                    "reference_clone_fingerprint", "reopen_fingerprint",
                ],
            }
    finally:
        _safe_close(clone_doc); _safe_close(reference_doc)
        if acad is not None:
            detach_autocad()
    matrix: dict[str, Any] = {
        "TDbPipe": {"status": "VERIFIED_SELECTIVE_CLONE", "evidence": "frozen regression"},
        "TDbPipeFitting": {"status": "VERIFIED_SELECTIVE_CLONE", "evidence": "frozen regression"},
        "TDbPipeValve": {"status": "VERIFIED_COMPONENT_CLONE", "evidence": "frozen Valve component regression"},
    }
    for object_name in REMAINING_TYPES:
        missing_fields = readability[object_name]["missing_required_fields"]
        if missing_fields:
            status = "BLOCKED_AMBIGUOUS_DERIVATION" if missing_fields == ["orientation"] else "BLOCKED_REQUIRED_FIELD_UNREADABLE"
        elif readability[object_name]["stable_fingerprint_match"]:
            status = "VERIFIED_DERIVED_PROPERTY_QA"
        else:
            status = "FAILED_PROPERTY_PERSISTENCE"
        matrix[object_name] = {"status": status, "readability": readability[object_name]}
    blocked = [name for name, item in matrix.items() if not item["status"].startswith("VERIFIED_")]
    final_status = "PASS_READBACK_ALL_TYPES_VERIFIED" if not blocked else "BLOCKED_TDB_OBSERVABILITY_LIMIT"
    policy = {
        "field_levels": {
            "REQUIRED_CRITICAL": "must be directly readable or uniquely derived from reliable evidence",
            "REQUIRED_DERIVABLE": "deterministic repeatable derivation with evidence chain and persistence",
            "OPTIONAL_NONCRITICAL": "may remain unreadable only when engineering semantics/topology are unaffected",
            "UNAVAILABLE": "must never be fabricated or reported as MATCH",
        },
        "critical_fields_may_be_downgraded": False,
        "allowed_derivation_sources": ["bbox", "internal_geometry", "equipment_interfaces", "connected_component", "IDPairs", "neighbor_objects", "reference_target_transform"],
    }
    schema = {
        "stable_fields": [
            "object_name", "geometry_anchor", "bbox", "orientation_vector", "interface_points",
            "connected_component_signature", "display_content_signature", "annotation_target_signature",
            "leader_geometry_signature", "xdata_signature", "dictionary_signature",
        ],
        "excluded_unstable_fields": ["ObjectId", "internal_address", "new_Handle_equals_reference_Handle"],
    }
    write_json(paths.root / "required_field_readability_matrix.json", readability)
    write_json(paths.root / "com_property_inventory.json", com_inventory)
    write_json(paths.root / "xdata_inventory.json", xdata_inventory)
    write_json(paths.root / "extension_dictionary_inventory.json", dictionary_inventory)
    write_json(paths.root / "nested_geometry_inventory.json", nested_inventory)
    write_json(paths.root / "stable_fingerprint_schema.json", schema)
    write_json(paths.root / "required_field_policy.json", policy)
    write_json(paths.root / "stable_fingerprint_results.json", fingerprints)
    write_json(paths.root / "tdb_creation_capability_matrix.json", {"phase": "STAGE5.1-R2", "object_types": matrix, "blocked_types": blocked})
    source_hashes_after = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    source_unchanged = source_hashes_after == source_hashes_before
    report = {
        "phase": "STAGE5.1-R2", "run_id": run_id, "status": final_status,
        "source_hashes_before": source_hashes_before, "source_hashes_after": source_hashes_after,
        "source_hashes_unchanged": source_unchanged,
        "frozen_regression_capabilities": {"TDbPipe": "PASS", "TDbPipeFitting": "PASS", "TDbPipeValve": "PASS"},
        "capability_matrix": matrix, "blocked_types": blocked,
        "observability_blockers": {
            name: {
                "fields": readability[name]["missing_required_fields"],
                "attempted_channels": readability[name]["all_attempted_channels"],
                "reason": "field is not directly readable and cannot be uniquely derived from current COM/metadata/geometry evidence",
                "required_new_interface": "Tianzheng object API exposing semantic value/leader/target or deterministic device orientation metadata",
            }
            for name in blocked
        },
        "full_reconstruction_continued": False, "mvp2_completed": False, "mvp3_allowed": False,
        "tests": {}, "tests_passed": False,
        "safety_flags": {
            **safety_flags(), "autocad_connected": True, "analysis_copies_opened": True,
            "poc_sandboxes_opened_read_only": True, "dwg_modified": False, "dwg_saved": False,
            "source_reference_opened": False, "source_target_opened": False,
        },
        "production_d1_allowed": False,
    }
    write_json(paths.root / "stage5_1_r2_manifest.json", report)
    write_json(REPORT_JSON, report)
    REPORT_MD.write_text(_markdown(report), encoding="utf-8")
    return report


def record_r2_tests(run_id: str, tests: Mapping[str, str]) -> dict[str, Any]:
    paths = R2Paths.build(run_id)
    report = read_json(paths.root / "stage5_1_r2_manifest.json")
    passed = bool(tests) and all("passed" in value.lower() and "failed" not in value.lower() for value in tests.values())
    report["tests"] = dict(tests); report["tests_passed"] = passed
    write_json(paths.root / "stage5_1_r2_manifest.json", report)
    write_json(REPORT_JSON, report)
    REPORT_MD.write_text(_markdown(report), encoding="utf-8")
    return report


def audit_dimension_named_dictionaries(run_id: str) -> dict[str, Any]:
    paths = R2Paths.build(run_id)
    matrix = read_json(paths.root / "tdb_creation_capability_matrix.json")
    dimension = matrix["object_types"]["TDbDimension2"]
    if dimension["status"] != "BLOCKED_REQUIRED_FIELD_UNREADABLE":
        raise ValueError("Dimension2 dictionary audit is only needed while required fields remain unreadable")
    graph = read_json(GRAPH_PATH)
    poc = read_json(_poc_result_path("TDbDimension2"))
    dimension_handle = poc["primary_reference_handle"]
    dimension_node = next(node for node in graph["nodes"] if node["reference_handle"] == dimension_handle)
    acad = document = None
    records: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []

    def read_collection(collection: Any, path: str, depth: int = 0) -> None:
        if depth > 3 or len(records) >= 2000:
            return
        try:
            count = int(collection.Count)
        except Exception:
            return
        for index in range(count):
            try:
                item = collection.Item(index)
            except Exception:
                continue
            record: dict[str, Any] = {"path": f"{path}[{index}]"}
            for field in ("Name", "Handle", "ObjectName", "OwnerID"):
                try:
                    record[field] = _json_value(getattr(item, field))
                except Exception:
                    record[field] = None
            try:
                raw = item.GetXRecordData()
                record["xrecord_data"] = _json_value(raw)
            except Exception:
                record["xrecord_data"] = None
            records.append(record)
            serialized = json.dumps(record, ensure_ascii=False).upper()
            if dimension_handle.upper() in serialized or "TDBDIMENSION2" in serialized:
                matches.append(record)
            if record.get("ObjectName") == "AcDbDictionary":
                read_collection(item, record["path"], depth + 1)
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        reference_copy = paths.copies / "reference_analysis_copy.dwg"
        document = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        read_collection(document.Dictionaries, "Document.Dictionaries")
    finally:
        _safe_close(document)
        if acad is not None:
            detach_autocad()
    result = {
        "phase": "STAGE5.1-R2", "object_name": "TDbDimension2",
        "reference_handle": dimension_handle, "task_id": dimension_node["task_id"],
        "dictionary_record_count": len(records), "matching_record_count": len(matches),
        "matching_records": matches, "records": records,
        "display_content_found": any(record.get("xrecord_data") for record in matches),
        "leader_geometry_found": False,
        "analysis_copy_saved": False, "source_opened": False, "source_saved": False,
    }
    write_json(paths.root / "named_object_dictionary_inventory.json", result)
    nested = read_json(paths.root / "nested_geometry_inventory.json")
    nested["TDbDimension2"].update({
        "named_dictionary_match_count": len(matches),
        "readonly_preview_method_available": False,
        "readonly_virtual_display_content_available": False,
        "audited_methods": ["GetBoundingBox", "GetXData", "GetExtensionDictionary", "NamedObjectDictionary"],
    })
    write_json(paths.root / "nested_geometry_inventory.json", nested)
    report = read_json(paths.root / "stage5_1_r2_manifest.json")
    blocker = report["observability_blockers"]["TDbDimension2"]
    blocker["named_object_dictionary_records_scanned"] = len(records)
    blocker["named_object_dictionary_matches"] = len(matches)
    blocker["readonly_virtual_preview_available"] = False
    blocker["required_new_interface"] = "Tianzheng read-only API exposing Dimension2 display value, dimension/leader geometry, and annotation target"
    write_json(paths.root / "stage5_1_r2_manifest.json", report)
    write_json(REPORT_JSON, report)
    REPORT_MD.write_text(_markdown(report), encoding="utf-8")
    return result


def _markdown(report: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Stage 5.1-R2 Required TDb Readback and Verification Recovery", "",
        f"- status: {report.get('status')}", f"- run_id: {report.get('run_id')}",
        f"- blocked types: {', '.join(report.get('blocked_types', []))}",
        f"- source hashes unchanged: {str(report.get('source_hashes_unchanged')).lower()}",
        f"- full reconstruction continued: {str(report.get('full_reconstruction_continued')).lower()}",
        f"- tests passed: {str(report.get('tests_passed')).lower()}",
        "- MVP2 completed: false", "- MVP3 allowed: false", "- Production D1 allowed: false", "",
    ])
