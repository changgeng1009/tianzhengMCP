from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.acceptance.stage3_1_runtime import sha256_file
from mcp.acceptance.stage3_3_controlled_repair import source_lock_files
from mcp.orchestration.stage5_1_relationship_reconstruction import (
    REFERENCE,
    REFERENCE_SHA256,
    TARGET,
    TARGET_SHA256,
    TRANSLATION,
    safety_flags,
)


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "artifacts" / "stage5_1_r3"
REPORT_JSON = ROOT / "reports" / "stage5_1_r3_mvp2_final_acceptance.json"
REPORT_MD = ROOT / "reports" / "stage5_1_r3_mvp2_final_acceptance.md"
PRIOR_R2_RUN = ROOT / "artifacts" / "stage5_1_r2" / "stage5_1_r2_20260711_151937"
PRIOR_R2_REPORT = ROOT / "reports" / "stage5_1_r2_required_tdb_readback.json"
STAGE51_RUN = ROOT / "artifacts" / "stage5_1" / "stage5_1_20260711_143721"
GRAPH_PATH = STAGE51_RUN / "reference_tdb_relationship_graph.json"
REQUIRED_PATH = STAGE51_RUN / "final_required_tdb.json"
ALLOWED_POLICY = STAGE51_RUN / "allowed_difference_policy.json"
STAGE4_PLAN = ROOT / "artifacts" / "stage4" / "stage4_20260711_094721" / "tasks" / "approved_execution_plan.json"

CORE_TYPES = {
    "TDbPipe", "TDbPipeFitting", "TDbPipeValve", "TDbPump", "TDbEquipment",
    "TDbWaterTank", "TDbVPipeDim", "TDbSymbMultiLeader",
}


@dataclass(frozen=True)
class R3Paths:
    run_id: str
    root: Path
    archive: Path
    input: Path
    copies: Path
    scans: Path
    plans: Path
    core_reconstruction: Path
    dimension2: Path
    bridge: Path
    execution: Path
    relationships: Path
    topology: Path
    properties: Path
    persistence: Path
    convergence: Path
    idempotency: Path
    drafting_variant: Path
    previews: Path
    reports: Path

    @classmethod
    def build(cls, run_id: str) -> "R3Paths":
        root = RUNS_ROOT / run_id
        names = (
            "archive", "input", "copies", "scans", "plans", "core_reconstruction", "dimension2",
            "bridge", "execution", "relationships", "topology", "properties", "persistence",
            "convergence", "idempotency", "drafting_variant", "previews", "reports",
        )
        return cls(run_id, root, *(root / name for name in names))

    def create(self) -> None:
        for value in self.__dict__.values():
            if isinstance(value, Path):
                value.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"path": str(path.resolve()), "sha256": sha256_file(path), "size": stat.st_size, "modified_time_ns": stat.st_mtime_ns}


def _bbox_distance(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> float:
    dx = max(float(left[0][0]) - float(right[1][0]), float(right[0][0]) - float(left[1][0]), 0.0)
    dy = max(float(left[0][1]) - float(right[1][1]), float(right[0][1]) - float(left[1][1]), 0.0)
    dz = max(float(left[0][2]) - float(right[1][2]), float(right[0][2]) - float(left[1][2]), 0.0)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


class _UnionFind:
    def __init__(self, values: Sequence[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _route(object_name: str) -> str:
    return {
        "TDbPipe": "selective_native_clone",
        "TDbPipeFitting": "selective_native_clone",
        "TDbPipeValve": "relationship_aware_component_clone",
        "TDbPump": "derived_property_validated_component_clone",
        "TDbEquipment": "derived_property_validated_component_clone",
        "TDbWaterTank": "derived_property_validated_component_clone",
        "TDbVPipeDim": "derived_property_validated_clone",
        "TDbSymbMultiLeader": "derived_property_validated_clone",
    }[object_name]


def freeze_r3_inputs(paths: R3Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    paths.create()
    required_files = [REFERENCE, TARGET, PRIOR_R2_REPORT, PRIOR_R2_RUN / "tdb_creation_capability_matrix.json", GRAPH_PATH, REQUIRED_PATH, ALLOWED_POLICY, STAGE4_PLAN]
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        return {"status": "BLOCKED_REQUIRED_EVIDENCE_MISSING", "missing_files": missing, "safety_flags": safety_flags()}
    locks = {"reference": source_lock_files(REFERENCE), "target": source_lock_files(TARGET)}
    if locks["reference"] or locks["target"]:
        return {"status": "BLOCKED_SOURCE_LOCKED", "source_locks": locks, "safety_flags": safety_flags()}
    hashes = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    if hashes != {"reference": REFERENCE_SHA256, "target": TARGET_SHA256}:
        return {"status": "BLOCKED_INPUT_HASH_CHANGED", "source_hashes": hashes, "safety_flags": safety_flags()}
    r2 = read_json(PRIOR_R2_REPORT)
    graph = read_json(GRAPH_PATH)
    core_nodes = [node for node in graph["nodes"] if node["object_name"] in CORE_TYPES]
    dimension_nodes = [node for node in graph["nodes"] if node["object_name"] == "TDbDimension2"]
    verified = {
        name: item["status"] for name, item in r2["capability_matrix"].items()
        if name in CORE_TYPES
    }
    passed = all((len(core_nodes) == 331, len(dimension_nodes) == 6, all(status.startswith("VERIFIED_") for status in verified.values())))
    shutil.copy2(REFERENCE, paths.copies / "reference_analysis_copy.dwg")
    shutil.copy2(TARGET, paths.copies / "target_analysis_copy.dwg")
    shutil.copy2(PRIOR_R2_REPORT, paths.archive / "stage5_1_r2_report.json")
    shutil.copy2(PRIOR_R2_RUN / "tdb_creation_capability_matrix.json", paths.archive / "stage5_1_r2_capability_matrix.json")
    shutil.copy2(ALLOWED_POLICY, paths.root / "allowed_difference_policy.json")
    write_json(paths.root / "input_manifest.json", {
        "phase": "STAGE5.1-R3-A", "reference": _file_record(REFERENCE), "target": _file_record(TARGET),
        "expected_hashes": {"reference": REFERENCE_SHA256, "target": TARGET_SHA256},
        "source_locks": locks, "input_hashes_match": True,
    })
    write_json(paths.root / "source_integrity.json", {
        "reference_sha256_before": hashes["reference"], "target_sha256_before": hashes["target"],
        "source_reference_opened": False, "source_target_opened": False,
        "source_reference_saved": False, "source_target_saved": False, "source_modified": False,
    })
    write_json(paths.plans / "core_required_objects.json", {"items": core_nodes, "count": len(core_nodes), "dimension2_excluded": True})
    write_json(paths.dimension2 / "dimension2_frozen_objects.json", {"items": dimension_nodes, "count": len(dimension_nodes)})
    result = {
        "phase": "STAGE5.1-R3-A", "status": "PASS_R3_A_FROZEN" if passed else "BLOCKED_CAPABILITY_BASELINE_INVALID",
        "run_id": paths.run_id, "core_count": len(core_nodes), "dimension2_count": len(dimension_nodes),
        "verified_core_capabilities": verified, "analysis_copies_created": True,
        "autocad_connected": False, "dwg_modified": False, "dwg_saved": False,
        "safety_flags": safety_flags(),
    }
    write_json(paths.reports / "checkpoint_a.json", result)
    return result


def build_core_plan(paths: R3Paths) -> dict[str, Any]:
    frozen = read_json(paths.reports / "checkpoint_a.json")
    if frozen["status"] != "PASS_R3_A_FROZEN":
        return {"status": "BLOCKED_CHECKPOINT_A_NOT_PASS", "safety_flags": safety_flags()}
    graph = read_json(GRAPH_PATH)
    core = read_json(paths.plans / "core_required_objects.json")["items"]
    by_id = {node["task_id"]: node for node in core}
    ids = list(by_id)
    union = _UnionFind(ids)
    plan_edges: list[dict[str, Any]] = []
    for edge in graph["edges"]:
        if edge["source_id"] in by_id and edge["target_id"] in by_id and edge["edge_type"] in {
            "CONNECTED_TO", "VALVE_BELONGS_TO_PIPE", "FITTING_JOINS_PIPE", "EQUIPMENT_INTERFACE", "ANNOTATES_OBJECT",
        }:
            union.union(edge["source_id"], edge["target_id"])
            plan_edges.append(dict(edge))
    pipes = [node for node in core if node["object_name"] == "TDbPipe"]
    fittings = [node for node in core if node["object_name"] == "TDbPipeFitting"]
    attached_pipe_ids_by_valve: dict[str, set[str]] = defaultdict(set)
    for edge in graph["edges"]:
        if edge.get("edge_type") != "VALVE_BELONGS_TO_PIPE":
            continue
        source_id, target_id = edge["source_id"], edge["target_id"]
        if source_id in by_id and target_id in by_id:
            if by_id[source_id]["object_name"] == "TDbPipeValve" and by_id[target_id]["object_name"] == "TDbPipe":
                attached_pipe_ids_by_valve[source_id].add(target_id)
            elif by_id[target_id]["object_name"] == "TDbPipeValve" and by_id[source_id]["object_name"] == "TDbPipe":
                attached_pipe_ids_by_valve[target_id].add(source_id)
    valve_remap_tasks: list[dict[str, Any]] = []
    for valve in (node for node in core if node["object_name"] == "TDbPipeValve"):
        expected_attached_pipe_ids = sorted(attached_pipe_ids_by_valve[valve["task_id"]])
        attached_pipes = [by_id[task_id] for task_id in expected_attached_pipe_ids]
        remaining_pipes = sorted(
            (pipe for pipe in pipes if pipe["task_id"] not in attached_pipe_ids_by_valve[valve["task_id"]]),
            key=lambda pipe: (_bbox_distance(valve["target_wcs_bbox"], pipe["target_wcs_bbox"]), pipe["task_id"]),
        )
        dependency_pipes = [*attached_pipes, *remaining_pipes[:max(0, 2 - len(attached_pipes))]]
        for pipe in dependency_pipes:
            union.union(valve["task_id"], pipe["task_id"])
            plan_edges.append({
                "source_id": valve["task_id"], "target_id": pipe["task_id"],
                "edge_type": "VALVE_COMPONENT_CLOSURE", "relationship_source": "deterministic_nearest_pipe_closure",
                "distance": _bbox_distance(valve["target_wcs_bbox"], pipe["target_wcs_bbox"]),
            })
        nearest_fittings = sorted(
            fittings,
            key=lambda fitting: (
                min(_bbox_distance(fitting["target_wcs_bbox"], pipe["target_wcs_bbox"]) for pipe in dependency_pipes),
                fitting["task_id"],
            ),
        )[:1]
        for fitting in nearest_fittings:
            union.union(valve["task_id"], fitting["task_id"])
            plan_edges.append({
                "source_id": valve["task_id"], "target_id": fitting["task_id"],
                "edge_type": "VALVE_FITTING_COMPONENT_CLOSURE", "relationship_source": "deterministic_nearest_fitting_closure",
            })
        valve_remap_tasks.append({
            "task_id": valve["task_id"], "reference_handle": valve["reference_handle"],
            "object_name": "TDbPipeValve", "creation_route": "relationship_remap_after_dependencies",
            "dependency_task_ids": [node["task_id"] for node in [*dependency_pipes, *nearest_fittings]],
            "dependency_reference_handles": [node["reference_handle"] for node in [*dependency_pipes, *nearest_fittings]],
            "expected_attached_pipe_task_ids": expected_attached_pipe_ids,
            "expected_attached_pipe_count": len(expected_attached_pipe_ids),
            "attachment_tolerance": 100.0,
            "expected_fingerprint": {
                "object_name": valve["object_name"], "layer": valve["layer"],
                "target_wcs_bbox": valve["target_wcs_bbox"], "duplicate_precheck_signature": _hash_payload([valve["object_name"], valve["layer"], valve["target_wcs_bbox"]]),
                "relationship": {
                    "attached_pipe_task_ids": expected_attached_pipe_ids,
                    "attached_pipe_count": len(expected_attached_pipe_ids),
                    "attachment_tolerance": 100.0,
                },
            },
        })
    grouped: dict[str, list[str]] = defaultdict(list)
    non_valve_ids = [task_id for task_id in ids if by_id[task_id]["object_name"] != "TDbPipeValve"]
    for task_id in non_valve_ids:
        grouped[union.find(task_id)].append(task_id)
    components = []
    owner: dict[str, str] = {}
    for index, task_ids in enumerate(sorted(grouped.values(), key=lambda values: (-len(values), min(values))), 1):
        nodes = [by_id[task_id] for task_id in sorted(task_ids)]
        component_id = f"r3_core_component_{index:04d}"
        for task_id in task_ids:
            owner[task_id] = component_id
        components.append({
            "component_id": component_id, "task_ids": [node["task_id"] for node in nodes],
            "reference_handles": [node["reference_handle"] for node in nodes],
            "object_name_counts": dict(sorted(Counter(node["object_name"] for node in nodes).items())),
            "expected_object_count": len(nodes),
            "routes": {node["task_id"]: _route(node["object_name"]) for node in nodes},
            "expected_fingerprints": {
                node["task_id"]: {
                    "object_name": node["object_name"], "layer": node["layer"],
                    "target_wcs_bbox": node["target_wcs_bbox"], "sys_type": node.get("sys_type"), "dn": node.get("dn"),
                    "duplicate_precheck_signature": _hash_payload([node["object_name"], node["layer"], node["target_wcs_bbox"]]),
                }
                for node in nodes
            },
            "expected_relationships": [
                edge for edge in plan_edges if edge["source_id"] in task_ids and edge["target_id"] in task_ids
            ],
        })
    covered = [task_id for component in components for task_id in component["task_ids"]] + [task["task_id"] for task in valve_remap_tasks]
    passed = (
        len(core) == 331 and len(covered) == 331 and len(set(covered)) == 331
        and len(valve_remap_tasks) == 88
        and not any(node["object_name"] == "TDbDimension2" for node in core)
    )
    order = [component["component_id"] for component in sorted(
        components,
        key=lambda component: (
            0 if any(name in component["object_name_counts"] for name in ("TDbPump", "TDbEquipment", "TDbWaterTank")) else 1,
            -component["expected_object_count"], component["component_id"],
        ),
    )]
    plan = {
        "phase": "STAGE5.1-R3-B", "core_object_count": len(core), "components": components,
        "component_count": len(components), "component_execution_order": order,
        "valve_remap_tasks": sorted(valve_remap_tasks, key=lambda item: item["task_id"]),
        "valve_remap_task_count": len(valve_remap_tasks),
        "whole_modelspace_copy_allowed": False, "dimension2_included": False,
        "source_reference_handle_count": len(set(covered)),
    }
    plan["plan_sha256"] = _hash_payload(plan)
    write_json(paths.plans / "core_component_graph.json", {"nodes": [component["component_id"] for component in components], "edges": [], "components": components})
    write_json(paths.plans / "core_execution_order.json", {"ordered_component_ids": order})
    write_json(paths.plans / "core_frozen_execution_plan.json", plan)
    result = {
        "phase": "STAGE5.1-R3-B", "status": "PASS_R3_B_PLAN_FROZEN" if passed else "BLOCKED_CORE_PLAN_INVALID",
        "core_object_count": len(core), "component_count": len(components),
        "valve_remap_task_count": len(valve_remap_tasks), "plan_sha256": plan["plan_sha256"],
        "dimension2_included": False, "duplicate_task_ids": len(covered) - len(set(covered)),
        "safety_flags": safety_flags(),
    }
    write_json(paths.reports / "checkpoint_b.json", result)
    return result


def start_r3(run_id: str | None = None) -> tuple[R3Paths, dict[str, Any], dict[str, Any]]:
    run_id = run_id or datetime.now().strftime("stage5_1_r3_%Y%m%d_%H%M%S")
    paths = R3Paths.build(run_id)
    frozen = freeze_r3_inputs(paths)
    plan = build_core_plan(paths) if frozen["status"] == "PASS_R3_A_FROZEN" else {"status": "NOT_RUN"}
    return paths, frozen, plan


def _scan_modelspace(document: Any, role: str) -> list[dict[str, Any]]:
    from mcp.acceptance.stage5_2_native_clone_poc import _scan_native

    return [_scan_native(document.ModelSpace.Item(index), role) for index in range(int(document.ModelSpace.Count))]


def _snapshot(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(record.get("handle")): {
            "object_name": record.get("object_name"), "layer": record.get("layer"), "bbox": record.get("bbox"),
            "geometry": record.get("geometry") or {}, "attributes": record.get("attributes") or {},
        }
        for record in records if record.get("handle")
    }


def _stable_value_equal(left: Any, right: Any, tolerance: float = 1e-6) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(_stable_value_equal(left[key], right[key], tolerance) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(_stable_value_equal(a, b, tolerance) for a, b in zip(left, right))
    return left == right


def _existing_record_unchanged(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    if before.get("object_name") != after.get("object_name") or before.get("layer") != after.get("layer"):
        return False
    if not _stable_value_equal(before.get("attributes") or {}, after.get("attributes") or {}):
        return False
    before_geometry, after_geometry = before.get("geometry") or {}, after.get("geometry") or {}
    if before_geometry or after_geometry:
        return _stable_value_equal(before_geometry, after_geometry)
    from mcp.acceptance.stage5_2_native_clone_poc import _bbox_close
    return _bbox_close(before.get("bbox"), after.get("bbox"))


def _r3_valve_relationship_qa(
    valve_task: Mapping[str, Any],
    nodes: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    copy_map: Mapping[str, Any],
) -> dict[str, Any]:
    from mcp.acceptance.stage5_1_valve_component_diagnostics import _match_expected

    matches, errors = _match_expected(records, nodes)
    valve_node = next(node for node in nodes if node["task_id"] == valve_task["task_id"])
    valve_record = matches.get(valve_node["task_id"])
    tolerance = float(valve_task.get("attachment_tolerance", 100.0))
    expected_attached = set(valve_task.get("expected_attached_pipe_task_ids", []))
    observed_attached = {
        node["task_id"]
        for node in nodes
        if node["object_name"] == "TDbPipe"
        and node["task_id"] in matches
        and valve_record is not None
        and _bbox_distance(valve_record["bbox"], matches[node["task_id"]]["bbox"]) <= tolerance
    }
    property_errors: list[str] = []
    for node in nodes:
        if node["task_id"] not in expected_attached or node["task_id"] not in matches:
            continue
        attributes = matches[node["task_id"]].get("attributes") or {}
        expected_system = node.get("sys_type")
        actual_system = attributes.get("sys_type")
        if expected_system not in (None, "", "unknown") and actual_system != expected_system:
            property_errors.append(f"{node['task_id']}: SysType {actual_system!r} != {expected_system!r}")
        expected_dn = node.get("dn")
        actual_dn = attributes.get("dn_diameter")
        if expected_dn not in (None, 0, 0.0):
            try:
                dn_matches = math.isclose(float(actual_dn), float(expected_dn), rel_tol=0.0, abs_tol=1e-6)
            except (TypeError, ValueError):
                dn_matches = False
            if not dn_matches:
                property_errors.append(f"{node['task_id']}: DN {actual_dn!r} != {expected_dn!r}")
    mapped_source_handles = {
        pair.get("source_handle")
        for pair in copy_map.get("idpairs", [])
        if pair.get("source_handle") and pair.get("target_handle") and pair.get("IsCloned") is not False
    }
    expected_handles = {node["reference_handle"] for node in nodes}
    idpairs_complete = expected_handles.issubset(mapped_source_handles)
    no_unrelated_objects = not errors and len(records) == len(nodes)
    fitting_dependency_count = sum(node["object_name"] == "TDbPipeFitting" for node in nodes)
    relationship_ready = all((
        valve_record is not None,
        observed_attached == expected_attached,
        not property_errors,
        idpairs_complete,
        no_unrelated_objects,
        fitting_dependency_count >= 1,
    ))
    return {
        "passed": not errors and not property_errors,
        "relationship_ready": relationship_ready,
        "errors": [*errors, *property_errors],
        "expected_attached_pipe_task_ids": sorted(expected_attached),
        "observed_attached_pipe_task_ids": sorted(observed_attached),
        "expected_attached_pipe_count": len(expected_attached),
        "observed_attached_pipe_count": len(observed_attached),
        "attachment_tolerance": tolerance,
        "fitting_dependency_count": fitting_dependency_count,
        "all_expected_idpairs_mapped": idpairs_complete,
        "no_unrelated_objects": no_unrelated_objects,
        "relationship_evidence_source": "frozen_reference_graph_and_persisted_native_geometry",
    }


def execute_core_reconstruction(
    paths: R3Paths,
    *,
    sandbox_path: Path | None = None,
    evidence_root: Path | None = None,
    report_path: Path | None = None,
    relationship_map_path: Path | None = None,
) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    import time
    import pythoncom
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import _norm_path, attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage3_3_controlled_repair import execute_live_plan
    from mcp.acceptance.stage5_1_valve_component_diagnostics import (
        _copyobjects_with_explicit_idpairs,
        _match_expected,
        _parse_copyobjects_return,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import (
        _bbox_close,
        _retry,
        _safe_close,
        _scan_native,
        _variant,
    )

    report_b = read_json(paths.reports / "checkpoint_b.json")
    if report_b["status"] != "PASS_R3_B_PLAN_FROZEN":
        return {"status": "BLOCKED_CHECKPOINT_B_NOT_PASS", "safety_flags": safety_flags()}
    plan = read_json(paths.plans / "core_frozen_execution_plan.json")
    frozen_hash = plan["plan_sha256"]
    hash_payload = dict(plan); hash_payload.pop("plan_sha256")
    if _hash_payload(hash_payload) != frozen_hash:
        return {"status": "BLOCKED_FROZEN_PLAN_HASH_MISMATCH", "safety_flags": safety_flags()}
    source_hashes_before = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    if source_hashes_before != {"reference": REFERENCE_SHA256, "target": TARGET_SHA256}:
        return {"status": "BLOCKED_INPUT_HASH_CHANGED", "safety_flags": safety_flags()}
    if source_lock_files(REFERENCE) or source_lock_files(TARGET):
        return {"status": "BLOCKED_SOURCE_LOCKED", "safety_flags": safety_flags()}
    sandbox = sandbox_path or (paths.copies / "target_core_331_sandbox.dwg")
    evidence_root = evidence_root or paths.core_reconstruction
    report_path = report_path or (paths.reports / "checkpoint_c_d.json")
    relationship_map_path = relationship_map_path or (paths.relationships / "core_source_to_target_handle_map.json")
    evidence_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, sandbox)
    ordinary_plan = read_json(STAGE4_PLAN)
    ordinary_tasks = ordinary_plan.get("tasks", ordinary_plan.get("items", []))
    ordinary = execute_live_plan(
        ordinary_tasks, sandbox,
        forbidden_source_paths=(REFERENCE, TARGET, paths.copies / "reference_analysis_copy.dwg", paths.copies / "target_analysis_copy.dwg"),
    )
    write_json(evidence_root / "ordinary_execution.json", ordinary)
    ordinary_passed = all((
        ordinary.get("successful_task_count") == 16,
        ordinary.get("persisted_task_count") == 16,
        ordinary.get("failed_task_count") == 0,
        ordinary.get("persistence_qa_passed") is True,
    ))
    if not ordinary_passed:
        result = {
            "phase": "STAGE5.1-R3-C", "status": "FAILED_CORE_RECONSTRUCTION_QA",
            "ordinary_passed": False, "ordinary_result": ordinary,
            "core_tdb_attempted": 0, "core_tdb_successful": 0,
            "source_hashes_unchanged": sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256,
            "safety_flags": {**safety_flags(), "autocad_connected": ordinary.get("autocad_connected", False)},
        }
        write_json(report_path, result)
        return result
    graph = read_json(GRAPH_PATH)
    by_id = {node["task_id"]: node for node in graph["nodes"]}
    component_by_id = {component["component_id"]: component for component in plan["components"]}
    acad = source_doc = target_doc = None
    component_results: list[dict[str, Any]] = []
    all_created_handles: list[str] = []
    global_source_to_target: dict[str, str] = {}
    global_pairs_by_source: dict[str, dict[str, Any]] = {}
    initial_snapshot: dict[str, dict[str, Any]] = {}
    saved = False; reopened = False; persisted_count = 0; error: str | None = None
    persistence_errors: list[str] = []
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        reference_copy = paths.copies / "reference_analysis_copy.dwg"
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, sandbox, _retry(lambda: acad.Documents.Open(str(sandbox), False), "R3 core sandbox open"))
        initial_records = _retry(
            lambda: _scan_modelspace(target_doc, "r3_core_initial"),
            "R3 core initial ModelSpace scan",
            attempts=60,
            delay=0.5,
        )
        initial_snapshot = _snapshot(initial_records)
        initial_tdb_count = sum(
            str(record.get("object_name", "")).startswith("TDb")
            and record.get("object_name") != "TDbDrawingName"
            for record in initial_records
        )
        if initial_tdb_count:
            raise RuntimeError(f"fresh target core sandbox unexpectedly contains {initial_tdb_count} TDb objects")
        for component_id in plan["component_execution_order"]:
            component = component_by_id[component_id]
            nodes = [by_id[task_id] for task_id in component["task_ids"]]
            source_objects = [
                _retry(lambda handle=node["reference_handle"]: source_doc.HandleToObject(handle), f"core source Handle {node['reference_handle']} lookup")
                for node in nodes
            ]
            returned = _retry(
                lambda: _copyobjects_with_explicit_idpairs(source_doc, source_objects, target_doc.ModelSpace),
                f"core component {component_id} CopyObjects",
            )
            copy_map = _parse_copyobjects_return(returned, source_doc, target_doc)
            expected_source_handles = set(component["reference_handles"])
            primary_pairs = [
                pair for pair in copy_map.get("idpairs", [])
                if pair.get("source_handle") in expected_source_handles
                and pair.get("target_handle")
                and pair.get("IsCloned") is not False
            ]
            source_to_target = {pair["source_handle"]: pair["target_handle"] for pair in primary_pairs}
            if set(source_to_target) != expected_source_handles:
                missing_maps = sorted(expected_source_handles - set(source_to_target))
                raise RuntimeError(f"{component_id}: IDPairs missing frozen source Handles {missing_maps}")
            semantic_target_handles = list(source_to_target.values())
            if len(set(semantic_target_handles)) != len(nodes):
                raise RuntimeError(f"{component_id}: duplicate target Handle mapping detected")
            if set(semantic_target_handles) & set(all_created_handles):
                raise RuntimeError(f"{component_id}: target Handle overlaps an earlier component")
            node_by_source_handle = {node["reference_handle"]: node for node in nodes}
            moved_handles: list[str] = []
            for source_handle, target_handle in source_to_target.items():
                node = node_by_source_handle[source_handle]
                native = _retry(lambda value=target_handle: target_doc.HandleToObject(value), f"core mapped Handle {target_handle} lookup")
                current = _retry(lambda obj=native: _scan_native(obj, "r3_core_pre_move"), f"core mapped Handle {target_handle} scan")
                if not _bbox_close(current.get("bbox"), node["target_wcs_bbox"]):
                    _retry(
                        lambda obj=native: obj.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)),
                        f"core mapped-object move {target_handle}",
                    )
                    moved_handles.append(target_handle)
            records = [
                _scan_native(
                    _retry(lambda value=handle: target_doc.HandleToObject(value), f"core semantic Handle {handle} lookup"),
                    "r3_core_created",
                )
                for handle in semantic_target_handles
            ]
            matches, match_errors = _match_expected(records, nodes)
            if match_errors:
                raise RuntimeError(f"{component_id}: type/geometry mapping failed: {match_errors}")
            valve_count = component["object_name_counts"].get("TDbPipeValve", 0)
            relationship_ready = True
            if valve_count:
                relationship_ready = (
                    component["object_name_counts"].get("TDbPipe", 0) >= 2
                    and component["object_name_counts"].get("TDbPipeFitting", 0) >= 1
                )
            if not relationship_ready:
                raise RuntimeError(f"{component_id}: Valve component lacks two Pipe plus Fitting closure")
            component_results.append({
                "component_id": component_id, "status": "SUCCESS",
                "expected_object_count": len(nodes), "actual_object_count": len(semantic_target_handles),
                "modelspace_root_delta": None,
                "individually_moved_mapped_object_count": len(moved_handles),
                "created_handles": semantic_target_handles,
                "source_to_target_map": primary_pairs,
                "object_name_geometry_match": True, "idpairs_complete": True,
                "relationship_fingerprint_match": relationship_ready,
            })
            all_created_handles.extend(semantic_target_handles)
            global_source_to_target.update(source_to_target)
            for pair in primary_pairs:
                global_pairs_by_source[pair["source_handle"]] = pair
            pythoncom.PumpWaitingMessages()
            time.sleep(0.35)
        for valve_task in plan["valve_remap_tasks"]:
            valve_node = by_id[valve_task["task_id"]]
            dependency_nodes = [by_id[task_id] for task_id in valve_task["dependency_task_ids"]]
            missing_dependencies = [
                node["task_id"] for node in dependency_nodes if node["reference_handle"] not in global_source_to_target
            ]
            if missing_dependencies:
                raise RuntimeError(f"{valve_task['task_id']}: dependencies not completed {missing_dependencies}")
            source_valve = _retry(
                lambda: source_doc.HandleToObject(valve_node["reference_handle"]),
                f"valve remap source {valve_node['reference_handle']} lookup",
            )
            returned = _retry(
                lambda: _copyobjects_with_explicit_idpairs(source_doc, [source_valve], target_doc.ModelSpace),
                f"{valve_task['task_id']} sequential Valve CopyObjects",
            )
            copy_map = _parse_copyobjects_return(returned, source_doc, target_doc)
            valve_pairs = [
                pair for pair in copy_map["idpairs"]
                if pair.get("source_handle") == valve_node["reference_handle"]
                and pair.get("target_handle") and pair.get("IsCloned") is not False
            ]
            if not valve_pairs:
                raise RuntimeError(f"{valve_task['task_id']}: Valve IDPair mapping missing")
            valve_target_handle = valve_pairs[-1]["target_handle"]
            if valve_target_handle in all_created_handles:
                raise RuntimeError(f"{valve_task['task_id']}: duplicate target Valve Handle")
            valve_native = _retry(lambda: target_doc.HandleToObject(valve_target_handle), f"mapped Valve {valve_target_handle} lookup")
            valve_record = _retry(lambda: _scan_native(valve_native, "r3_sequential_valve"), f"mapped Valve {valve_target_handle} scan")
            if not _bbox_close(valve_record.get("bbox"), valve_node["target_wcs_bbox"]):
                _retry(lambda: valve_native.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), f"mapped Valve move {valve_target_handle}")
            package_nodes = [*dependency_nodes, valve_node]
            package_records = [
                _retry(
                    lambda value=global_source_to_target[node["reference_handle"]]: _scan_native(
                        target_doc.HandleToObject(value), "r3_valve_dependency"
                    ),
                    f"valve dependency {node['task_id']} scan",
                )
                for node in dependency_nodes
            ] + [_retry(lambda: _scan_native(valve_native, "r3_valve_created"), f"created Valve {valve_target_handle} QA scan")]
            combined_pairs = [global_pairs_by_source[node["reference_handle"]] for node in dependency_nodes] + [valve_pairs[-1]]
            variant = {
                "nodes": package_nodes,
                "expected_handles": [node["reference_handle"] for node in package_nodes],
                "expected_task_ids": [node["task_id"] for node in package_nodes],
            }
            valve_qa = _r3_valve_relationship_qa(valve_task, package_nodes, package_records, {"idpairs": combined_pairs})
            if not valve_qa["relationship_ready"]:
                raise RuntimeError(f"{valve_task['task_id']}: relationship remap QA failed {valve_qa}")
            component_results.append({
                "component_id": f"valve_remap::{valve_task['task_id']}", "status": "SUCCESS",
                "expected_object_count": 1, "actual_object_count": 1,
                "modelspace_root_delta": None, "individually_moved_owned_object_count": 1,
                "created_handles": [valve_target_handle], "source_to_target_map": [valve_pairs[-1]],
                "object_name_geometry_match": True, "idpairs_complete": True,
                "relationship_fingerprint_match": True, "relationship_route": "VERIFIED_RELATIONSHIP_REMAP",
            })
            all_created_handles.append(valve_target_handle)
            global_source_to_target[valve_node["reference_handle"]] = valve_target_handle
            global_pairs_by_source[valve_node["reference_handle"]] = valve_pairs[-1]
            pythoncom.PumpWaitingMessages(); time.sleep(0.15)
        after_records = _retry(lambda: _scan_modelspace(target_doc, "r3_core_after"), "R3 core final ModelSpace scan", attempts=60, delay=0.5)
        after_snapshot = _snapshot(after_records)
        modified_existing = [
            handle for handle, before in initial_snapshot.items()
            if handle not in after_snapshot or not _existing_record_unchanged(before, after_snapshot[handle])
        ]
        unexpected_new = sorted(set(after_snapshot) - set(initial_snapshot) - set(all_created_handles))
        if modified_existing or unexpected_new or len(all_created_handles) != 331:
            raise RuntimeError(
                f"core global QA failed: created={len(all_created_handles)}, modified_existing={modified_existing}, unexpected_new={unexpected_new}"
            )
        _retry(lambda: target_doc.Save(), "R3 core sandbox save")
        saved = True
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        persisted_doc = _resolve_open_document(acad, sandbox, _open_document_with_retry(acad, sandbox))
        reopened = True
        try:
            for handle in all_created_handles:
                try:
                    object_name = _retry(
                        lambda value=handle: str(persisted_doc.HandleToObject(value).ObjectName),
                        f"persisted core {handle} ObjectName read",
                        attempts=60,
                        delay=0.5,
                    )
                    if not object_name.startswith("TDb"):
                        persistence_errors.append(f"{handle}: type degraded to {object_name}")
                    else:
                        persisted_count += 1
                except Exception as exc:
                    persistence_errors.append(f"{handle}: {type(exc).__name__}: {exc}")
            for valve_task in plan["valve_remap_tasks"]:
                valve_node = by_id[valve_task["task_id"]]
                dependency_nodes = [by_id[task_id] for task_id in valve_task["dependency_task_ids"]]
                package_nodes = [*dependency_nodes, valve_node]
                package_records = [
                    _retry(
                        lambda value=global_source_to_target[node["reference_handle"]]: _scan_native(
                            persisted_doc.HandleToObject(value), "r3_persisted_valve_package"
                        ),
                        f"persisted valve package {node['task_id']} scan",
                    )
                    for node in package_nodes
                ]
                combined_pairs = [global_pairs_by_source[node["reference_handle"]] for node in package_nodes]
                persisted_valve_qa = _r3_valve_relationship_qa(
                    valve_task, package_nodes, package_records, {"idpairs": combined_pairs}
                )
                if not persisted_valve_qa["relationship_ready"]:
                    persistence_errors.append(f"{valve_task['task_id']}: relationship persistence failed {persisted_valve_qa}")
        finally:
            _safe_close(persisted_doc)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()
    source_hashes_unchanged = sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256
    core_passed = all((
        error is None, saved, reopened, len(all_created_handles) == 331,
        persisted_count == 331, not persistence_errors, source_hashes_unchanged,
    ))
    status = "PASS_R3_CORE_331_RECONSTRUCTION" if core_passed else "FAILED_CORE_RECONSTRUCTION_QA"
    result = {
        "phase": "STAGE5.1-R3-C-D", "status": status,
        "ordinary_attempted": ordinary.get("attempted_task_count"), "ordinary_successful": ordinary.get("successful_task_count"),
        "ordinary_persisted": ordinary.get("persisted_task_count"),
        "core_tdb_planned": 331, "core_tdb_attempted": sum(item["expected_object_count"] for item in component_results),
        "core_tdb_successful": len(all_created_handles), "core_tdb_persisted": persisted_count,
        "successful_component_count": len(component_results),
        "planned_component_count": plan["component_count"] + plan["valve_remap_task_count"],
        "component_results": component_results, "created_handles": all_created_handles,
        "sandbox_path": str(sandbox), "sandbox_saved": saved, "sandbox_reopened": reopened,
        "persistence_errors": persistence_errors, "error": error,
        "core_required_missing": 0 if core_passed else 331 - persisted_count,
        "core_type_mismatch": 0 if core_passed else len(persistence_errors),
        "core_property_mismatch": 0 if core_passed else None,
        "core_topology_mismatch": 0 if core_passed else None,
        "duplicate": 0, "unexpected_new": 0,
        "existing_modified": 0, "existing_deleted": 0,
        "core_331_reconstruction_passed": core_passed,
        "source_hashes_unchanged": source_hashes_unchanged,
        "safety_flags": {
            **safety_flags(), "autocad_connected": True, "selective_copyobjects_used": bool(component_results),
            "core_sandbox_modified": bool(component_results), "core_sandbox_saved": saved,
            "source_reference_opened": False, "source_target_opened": False,
        },
        "mvp2_completed": False, "mvp3_allowed": False, "production_d1_allowed": False,
    }
    write_json(evidence_root / "component_execution_results.json", {"items": component_results})
    write_json(relationship_map_path, {
        "components": [{"component_id": item["component_id"], "mappings": item["source_to_target_map"]} for item in component_results]
    })
    write_json(report_path, result)
    return result


def _dimension2_persistence_qa(node: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    from mcp.acceptance.stage5_2_native_clone_poc import _bbox_close

    object_name_match = record.get("object_name") == "TDbDimension2"
    bbox_match = _bbox_close(record.get("bbox"), node.get("target_wcs_bbox"))
    layer_match = record.get("layer") == node.get("layer")
    return {
        "passed": object_name_match and bbox_match and layer_match,
        "object_name_match": object_name_match,
        "bbox_match": bbox_match,
        "layer_match": layer_match,
        "display_content_automatically_verified": False,
        "leader_geometry_automatically_verified": False,
        "full_automated_semantic_verification": False,
    }


def execute_dimension2_native_clone_evidence(paths: R3Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    import time
    import pythoncom
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import _norm_path, attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_1_valve_component_diagnostics import _copyobjects_with_explicit_idpairs, _parse_copyobjects_return
    from mcp.acceptance.stage5_2_native_clone_poc import _bbox_close, _retry, _safe_close, _scan_native, _variant

    core = read_json(paths.reports / "checkpoint_c_d.json")
    if core.get("status") != "PASS_R3_CORE_331_RECONSTRUCTION":
        return {"status": "BLOCKED_CORE_331_NOT_PASS", "safety_flags": safety_flags()}
    if source_lock_files(REFERENCE) or source_lock_files(TARGET):
        return {"status": "BLOCKED_SOURCE_LOCKED", "safety_flags": safety_flags()}
    source_hashes_before = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    if source_hashes_before != {"reference": REFERENCE_SHA256, "target": TARGET_SHA256}:
        return {"status": "BLOCKED_INPUT_HASH_CHANGED", "safety_flags": safety_flags()}
    frozen = read_json(paths.dimension2 / "dimension2_frozen_objects.json")
    nodes = frozen.get("items", [])
    if len(nodes) != 6 or any(node.get("object_name") != "TDbDimension2" for node in nodes):
        return {"status": "BLOCKED_DIMENSION2_FROZEN_SCOPE_INVALID", "safety_flags": safety_flags()}

    acad = source_doc = target_doc = None
    item_results: list[dict[str, Any]] = []
    fatal_error: str | None = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        reference_copy = paths.copies / "reference_analysis_copy.dwg"
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        for index, node in enumerate(nodes, 1):
            task_id = node["task_id"]
            item_dir = paths.dimension2 / f"item_{index:02d}_{task_id}"
            item_dir.mkdir(parents=True, exist_ok=True)
            sandbox = item_dir / "dimension2_disposable_sandbox.dwg"
            shutil.copy2(TARGET, sandbox)
            result: dict[str, Any] = {
                "task_id": task_id,
                "reference_handle": node["reference_handle"],
                "sandbox_path": str(sandbox),
                "expected_target_wcs_bbox": node["target_wcs_bbox"],
                "native_clone_attempted": False,
                "saved": False,
                "reopened": False,
                "manual_acceptance": "PENDING",
            }
            try:
                target_doc = _resolve_open_document(
                    acad, sandbox, _retry(lambda: acad.Documents.Open(str(sandbox), False), f"Dimension2 {task_id} sandbox open")
                )
                source_object = _retry(
                    lambda handle=node["reference_handle"]: source_doc.HandleToObject(handle),
                    f"Dimension2 source {node['reference_handle']} lookup",
                )
                returned = _retry(
                    lambda: _copyobjects_with_explicit_idpairs(source_doc, [source_object], target_doc.ModelSpace),
                    f"Dimension2 {task_id} CopyObjects",
                )
                result["native_clone_attempted"] = True
                copy_map = _parse_copyobjects_return(returned, source_doc, target_doc)
                pairs = [
                    pair for pair in copy_map.get("idpairs", [])
                    if pair.get("source_handle") == node["reference_handle"]
                    and pair.get("target_handle") and pair.get("IsCloned") is not False
                ]
                if not pairs:
                    raise RuntimeError("primary IDPair mapping missing")
                target_handle = pairs[-1]["target_handle"]
                native = _retry(lambda: target_doc.HandleToObject(target_handle), f"Dimension2 mapped {target_handle} lookup")
                pre_move = _retry(lambda: _scan_native(native, "r3_dimension2_pre_move"), f"Dimension2 {task_id} pre-move scan")
                if not _bbox_close(pre_move.get("bbox"), node["target_wcs_bbox"]):
                    _retry(
                        lambda: native.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)),
                        f"Dimension2 {task_id} WCS move",
                    )
                pre_save = _retry(lambda: _scan_native(native, "r3_dimension2_pre_save"), f"Dimension2 {task_id} pre-save scan")
                pre_save_qa = _dimension2_persistence_qa(node, pre_save)
                if not pre_save_qa["passed"]:
                    raise RuntimeError(f"pre-save native QA failed: {pre_save_qa}")
                _retry(lambda: target_doc.Save(), f"Dimension2 {task_id} sandbox save")
                result["saved"] = True
                _safe_close(target_doc); target_doc = None
                persisted_doc = _resolve_open_document(acad, sandbox, _open_document_with_retry(acad, sandbox))
                result["reopened"] = True
                try:
                    persisted = _retry(
                        lambda: _scan_native(persisted_doc.HandleToObject(target_handle), "r3_dimension2_persisted"),
                        f"Dimension2 {task_id} persisted scan",
                    )
                finally:
                    _safe_close(persisted_doc)
                persistence_qa = _dimension2_persistence_qa(node, persisted)
                result.update({
                    "target_handle": target_handle,
                    "copyobjects_mapping": pairs[-1],
                    "pre_save_record": pre_save,
                    "persisted_record": persisted,
                    "pre_save_qa": pre_save_qa,
                    "persistence_qa": persistence_qa,
                    "native_clone_persistence_verified": persistence_qa["passed"],
                    "error": None if persistence_qa["passed"] else "persistence QA failed",
                })
            except Exception as exc:
                result.update({"native_clone_persistence_verified": False, "error": f"{type(exc).__name__}: {exc}"})
                _safe_close(target_doc); target_doc = None
            item_results.append(result)
            write_json(item_dir / "result.json", result)
            pythoncom.PumpWaitingMessages(); time.sleep(0.5)
            if not result["native_clone_persistence_verified"]:
                break
    except Exception as exc:
        fatal_error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()

    verified_count = sum(item.get("native_clone_persistence_verified") is True for item in item_results)
    source_hashes_unchanged = sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256
    native_passed = verified_count == 6 and len(item_results) == 6 and fatal_error is None and source_hashes_unchanged
    manual_template = {
        "phase": "STAGE5.1-R3-DIMENSION2-MANUAL-ACCEPTANCE",
        "manual_dimension2_acceptance": False,
        "dimension2_automated_observability": False,
        "full_automated_semantic_verification": False,
        "instructions": "逐项在 disposable sandbox 中核对显示内容、尺寸/界线/引线、关联目标及可用性；确认后将每项 manual_status 设为 ACCEPTED。",
        "items": [
            {
                "task_id": item["task_id"], "sandbox_path": item["sandbox_path"],
                "target_handle": item.get("target_handle"), "manual_status": "PENDING",
                "display_content_equivalent": None, "leader_geometry_equivalent": None,
                "association_target_equivalent": None, "functional_behavior_acceptable": None,
                "reviewer_notes": "",
            }
            for item in item_results
        ],
    }
    write_json(paths.dimension2 / "dimension2_manual_acceptance.json", manual_template)
    result = {
        "phase": "STAGE5.1-R3-E-H",
        "status": "PASS_DIMENSION2_NATIVE_CLONE_PENDING_MANUAL_ACCEPTANCE" if native_passed else "BLOCKED_DIMENSION2_NATIVE_CLONE_FAILURE",
        "dimension2_frozen_count": len(nodes),
        "dimension2_native_clone_attempted_count": len(item_results),
        "dimension2_native_clone_verified_count": verified_count,
        "dimension2_blocked_count": len(nodes) - verified_count,
        "manual_dimension2_acceptance": False,
        "manual_acceptance_pending_count": verified_count,
        "dimension2_automated_observability": False,
        "full_automated_semantic_verification": False,
        "item_results": item_results,
        "fatal_error": fatal_error,
        "source_hashes_unchanged": source_hashes_unchanged,
        "safety_flags": {
            **safety_flags(), "autocad_connected": acad is not None,
            "selective_copyobjects_used": bool(item_results),
            "dimension2_disposable_sandboxes_saved": any(item.get("saved") for item in item_results),
            "source_reference_opened": False, "source_target_opened": False,
        },
        "mvp2_completed": False,
        "mvp3_allowed": False,
        "production_d1_allowed": False,
    }
    write_json(paths.reports / "checkpoint_e_h.json", result)
    return result


def _manual_dimension2_review_valid(review: Mapping[str, Any]) -> bool:
    return all((
        review.get("manual_status") == "ACCEPTED",
        review.get("display_content_equivalent") is True,
        review.get("leader_geometry_equivalent") is True,
        review.get("association_target_equivalent") is True,
        review.get("functional_behavior_acceptable") is True,
        bool(review.get("screenshot_path")),
        Path(str(review.get("screenshot_path"))).is_file(),
    ))


def finalize_dimension2_manual_acceptance(paths: R3Paths, reviews: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    checkpoint = read_json(paths.reports / "checkpoint_e_h.json")
    if checkpoint.get("status") != "PASS_DIMENSION2_NATIVE_CLONE_PENDING_MANUAL_ACCEPTANCE":
        return {"status": "BLOCKED_DIMENSION2_NATIVE_CLONE_NOT_PASS", "safety_flags": safety_flags()}
    expected_ids = [item["task_id"] for item in checkpoint["item_results"]]
    reviews_by_id = {str(review.get("task_id")): dict(review) for review in reviews}
    valid_scope = len(reviews_by_id) == 6 and set(reviews_by_id) == set(expected_ids)
    accepted_count = sum(_manual_dimension2_review_valid(reviews_by_id[task_id]) for task_id in expected_ids if task_id in reviews_by_id)
    passed = valid_scope and accepted_count == 6
    payload = {
        "phase": "STAGE5.1-R3-DIMENSION2-MANUAL-ACCEPTANCE",
        "status": "PASS_DIMENSION2_MANUAL_ACCEPTANCE" if passed else "BLOCKED_DIMENSION2_MANUAL_ACCEPTANCE_INCOMPLETE",
        "manual_dimension2_acceptance": passed,
        "dimension2_automated_observability": False,
        "full_automated_semantic_verification": False,
        "review_method": "native_clone_save_reopen_plus_manual_visual_functional_review",
        "dimension2_reviewed_count": len(reviews_by_id),
        "dimension2_verified_count": accepted_count,
        "dimension2_blocked_count": 6 - accepted_count,
        "items": [reviews_by_id[task_id] for task_id in expected_ids if task_id in reviews_by_id],
        "source_hashes_unchanged": sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256,
        "safety_flags": safety_flags(),
        "production_d1_allowed": False,
    }
    write_json(paths.dimension2 / "dimension2_manual_acceptance.json", payload)
    checkpoint.update({
        "status": payload["status"],
        "manual_dimension2_acceptance": passed,
        "manual_acceptance_pending_count": 0 if passed else 6 - accepted_count,
        "dimension2_verified_count": accepted_count,
        "dimension2_blocked_count": 6 - accepted_count,
        "dimension2_automated_observability": False,
        "full_automated_semantic_verification": False,
        "manual_acceptance_report": str(paths.dimension2 / "dimension2_manual_acceptance.json"),
        "can_continue_final_full_reconstruction": passed,
        "mvp2_completed": False,
        "mvp3_allowed": False,
        "production_d1_allowed": False,
    })
    write_json(paths.reports / "checkpoint_e_h.json", checkpoint)
    return payload


def freeze_final_execution_plan(paths: R3Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    core = read_json(paths.reports / "checkpoint_c_d.json")
    dimension = read_json(paths.reports / "checkpoint_e_h.json")
    if core.get("status") != "PASS_R3_CORE_331_RECONSTRUCTION" or dimension.get("status") != "PASS_DIMENSION2_MANUAL_ACCEPTANCE":
        return {"status": "BLOCKED_FINAL_PLAN_PREREQUISITE", "safety_flags": safety_flags()}
    ordinary_plan = read_json(STAGE4_PLAN)
    ordinary_tasks = ordinary_plan.get("tasks", ordinary_plan.get("items", []))
    core_plan = read_json(paths.plans / "core_frozen_execution_plan.json")
    dimension_nodes = read_json(paths.dimension2 / "dimension2_frozen_objects.json")["items"]
    final_tdb = read_json(paths.plans / "core_required_objects.json")["items"] + dimension_nodes
    plan = {
        "phase": "STAGE5.1-R3-I",
        "ordinary_tasks": ordinary_tasks,
        "ordinary_task_count": len(ordinary_tasks),
        "required_tdb": final_tdb,
        "required_tdb_count": len(final_tdb),
        "core_plan_sha256": core_plan["plan_sha256"],
        "core_component_count": core_plan["component_count"],
        "valve_remap_task_count": core_plan["valve_remap_task_count"],
        "dimension2_task_ids": [node["task_id"] for node in dimension_nodes],
        "dimension2_manual_acceptance": True,
        "dimension2_automated_observability": False,
        "full_automated_semantic_verification": False,
        "execution_order": ["ordinary_16", "core_tdb_331", "dimension2_6"],
        "source_reference_sha256": REFERENCE_SHA256,
        "source_target_sha256": TARGET_SHA256,
        "production_d1_allowed": False,
    }
    plan["plan_sha256"] = _hash_payload(plan)
    write_json(paths.plans / "final_required_ordinary.json", {"items": ordinary_tasks, "count": len(ordinary_tasks)})
    write_json(paths.plans / "final_required_tdb.json", {"items": final_tdb, "count": len(final_tdb)})
    write_json(paths.plans / "final_component_graph.json", {
        "core_component_graph": str(paths.plans / "core_component_graph.json"),
        "dimension2_independent_components": [node["task_id"] for node in dimension_nodes],
    })
    write_json(paths.plans / "final_execution_order.json", {"ordered_groups": plan["execution_order"]})
    write_json(paths.plans / "final_frozen_execution_plan.json", plan)
    (paths.plans / "final_plan_sha256.txt").write_text(plan["plan_sha256"] + "\n", encoding="ascii")
    passed = len(ordinary_tasks) == 16 and len(final_tdb) == 337 and len(dimension_nodes) == 6
    result = {
        "phase": "STAGE5.1-R3-I",
        "status": "PASS_FINAL_PLAN_FROZEN" if passed else "BLOCKED_FINAL_PLAN_SCOPE_INVALID",
        "ordinary_task_count": len(ordinary_tasks), "required_tdb_count": len(final_tdb),
        "dimension2_task_count": len(dimension_nodes), "plan_sha256": plan["plan_sha256"],
        "safety_flags": safety_flags(), "production_d1_allowed": False,
    }
    write_json(paths.reports / "checkpoint_i.json", result)
    return result


def recover_final_core_persistence_verification(paths: R3Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import attach_existing_autocad, detach_autocad
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _safe_close, _scan_native

    report_path = paths.reports / "checkpoint_j_core.json"
    if not report_path.is_file():
        return {"status": "BLOCKED_FINAL_CORE_REPORT_MISSING", "safety_flags": safety_flags()}
    report = read_json(report_path)
    allowed_transient = all("AttributeError" in error and "ObjectName" in error for error in report.get("persistence_errors", []))
    recoverable = all((
        report.get("status") == "FAILED_CORE_RECONSTRUCTION_QA",
        report.get("core_tdb_successful") == 331,
        report.get("successful_component_count") == report.get("planned_component_count") == 103,
        report.get("sandbox_saved") is True,
        report.get("sandbox_reopened") is True,
        report.get("error") is None,
        allowed_transient,
    ))
    if not recoverable:
        return {"status": "BLOCKED_FINAL_CORE_NOT_TRANSIENT_RECOVERABLE", "safety_flags": safety_flags()}
    sandbox = Path(report["sandbox_path"])
    if not sandbox.is_file() or source_lock_files(REFERENCE) or source_lock_files(TARGET):
        return {"status": "BLOCKED_FINAL_SANDBOX_OR_SOURCE_LOCK", "safety_flags": safety_flags()}
    if sha256_file(REFERENCE) != REFERENCE_SHA256 or sha256_file(TARGET) != TARGET_SHA256:
        return {"status": "BLOCKED_INPUT_HASH_CHANGED", "safety_flags": safety_flags()}
    plan = read_json(paths.plans / "core_frozen_execution_plan.json")
    graph = read_json(GRAPH_PATH); by_id = {node["task_id"]: node for node in graph["nodes"]}
    all_pairs = [pair for component in report["component_results"] for pair in component["source_to_target_map"]]
    pairs_by_source = {pair["source_handle"]: pair for pair in all_pairs}
    source_to_target = {source: pair["target_handle"] for source, pair in pairs_by_source.items()}
    acad = document = None
    handle_errors: list[str] = []
    relationship_errors: list[str] = []
    try:
        acad = attach_existing_autocad()
        document = _resolve_open_document(acad, sandbox, _open_document_with_retry(acad, sandbox))
        for handle in report["created_handles"]:
            try:
                object_name = _retry(
                    lambda value=handle: str(document.HandleToObject(value).ObjectName),
                    f"recovery core {handle} ObjectName read",
                    attempts=60,
                    delay=0.5,
                )
                if not object_name.startswith("TDb"):
                    handle_errors.append(f"{handle}: {object_name}")
            except Exception as exc:
                handle_errors.append(f"{handle}: {type(exc).__name__}: {exc}")
        for valve_task in plan["valve_remap_tasks"]:
            valve_node = by_id[valve_task["task_id"]]
            dependency_nodes = [by_id[task_id] for task_id in valve_task["dependency_task_ids"]]
            package_nodes = [*dependency_nodes, valve_node]
            try:
                records = [
                    _retry(
                        lambda value=source_to_target[node["reference_handle"]]: _scan_native(
                            document.HandleToObject(value), "r3_final_core_recovery"
                        ),
                        f"recovery valve package {node['task_id']} scan",
                        attempts=60,
                        delay=0.5,
                    )
                    for node in package_nodes
                ]
                qa = _r3_valve_relationship_qa(
                    valve_task, package_nodes, records,
                    {"idpairs": [pairs_by_source[node["reference_handle"]] for node in package_nodes]},
                )
                if not qa["relationship_ready"]:
                    relationship_errors.append(f"{valve_task['task_id']}: {qa}")
            except Exception as exc:
                relationship_errors.append(f"{valve_task['task_id']}: {type(exc).__name__}: {exc}")
    finally:
        _safe_close(document)
        if acad is not None:
            detach_autocad()
    source_hashes_unchanged = sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256
    passed = not handle_errors and not relationship_errors and source_hashes_unchanged
    recovery = {
        "phase": "STAGE5.1-R3-J-CORE-PERSISTENCE-RECOVERY",
        "status": "PASS_FINAL_CORE_PERSISTENCE_RECOVERED" if passed else "FAILED_FINAL_CORE_PERSISTENCE_RECOVERY",
        "verified_handle_count": 331 - len(handle_errors),
        "verified_valve_relationship_count": 88 - len(relationship_errors),
        "handle_errors": handle_errors,
        "relationship_errors": relationship_errors,
        "source_hashes_unchanged": source_hashes_unchanged,
        "sandbox_saved_during_recovery": False,
        "safety_flags": safety_flags(),
        "production_d1_allowed": False,
    }
    write_json(paths.persistence / "final_core_persistence_recovery.json", recovery)
    if passed:
        report.update({
            "status": "PASS_R3_CORE_331_RECONSTRUCTION",
            "core_tdb_persisted": 331,
            "persistence_errors": [],
            "core_required_missing": 0,
            "core_type_mismatch": 0,
            "core_property_mismatch": 0,
            "core_topology_mismatch": 0,
            "core_331_reconstruction_passed": True,
            "source_hashes_unchanged": True,
            "persistence_recovery_report": str(paths.persistence / "final_core_persistence_recovery.json"),
        })
        write_json(report_path, report)
    return recovery


def execute_final_full_reconstruction(paths: R3Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import verify_stage45_inputs
    verify_stage45_inputs(REFERENCE, TARGET)
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    import time
    import pythoncom
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import _norm_path, attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_1_valve_component_diagnostics import _copyobjects_with_explicit_idpairs, _parse_copyobjects_return
    from mcp.acceptance.stage5_2_native_clone_poc import _bbox_close, _retry, _safe_close, _scan_native, _variant

    checkpoint_i = read_json(paths.reports / "checkpoint_i.json")
    if checkpoint_i.get("status") != "PASS_FINAL_PLAN_FROZEN":
        return {"status": "BLOCKED_CHECKPOINT_I_NOT_PASS", "safety_flags": safety_flags()}
    final_plan = read_json(paths.plans / "final_frozen_execution_plan.json")
    plan_hash = final_plan["plan_sha256"]
    unhashed = dict(final_plan); unhashed.pop("plan_sha256")
    if _hash_payload(unhashed) != plan_hash:
        return {"status": "BLOCKED_FINAL_PLAN_HASH_MISMATCH", "safety_flags": safety_flags()}
    final_sandbox = paths.copies / "target_mvp2_final_reconstruction.dwg"
    final_core_root = paths.execution / "final_core_331"
    prior_core_report = paths.reports / "checkpoint_j_core.json"
    core_result = read_json(prior_core_report) if (
        prior_core_report.is_file()
        and final_sandbox.is_file()
        and read_json(prior_core_report).get("status") == "PASS_R3_CORE_331_RECONSTRUCTION"
    ) else execute_core_reconstruction(
            paths,
            sandbox_path=final_sandbox,
            evidence_root=final_core_root,
            report_path=prior_core_report,
            relationship_map_path=paths.relationships / "final_core_source_to_target_handle_map.json",
        )
    if core_result.get("status") != "PASS_R3_CORE_331_RECONSTRUCTION":
        result = {
            "phase": "STAGE5.1-R3-J-L", "status": "FAILED_FINAL_CORE_RECONSTRUCTION_QA",
            "core_result": core_result, "mvp2_completed": False, "mvp3_allowed": False,
            "production_d1_allowed": False, "safety_flags": safety_flags(),
        }
        write_json(paths.reports / "checkpoint_j_l.json", result)
        return result

    dimension_nodes = read_json(paths.dimension2 / "dimension2_frozen_objects.json")["items"]
    acad = source_doc = target_doc = None
    dimension_results: list[dict[str, Any]] = []
    dimension_handles: list[str] = []
    persistence_errors: list[str] = []
    saved = reopened = False
    error: str | None = None
    initial_snapshot: dict[str, dict[str, Any]] = {}
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        reference_copy = paths.copies / "reference_analysis_copy.dwg"
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, final_sandbox, _open_document_with_retry(acad, final_sandbox))
        initial_records = _retry(lambda: _scan_modelspace(target_doc, "r3_final_before_dimension2"), "final pre-Dimension2 ModelSpace scan", attempts=60, delay=0.5)
        initial_snapshot = _snapshot(initial_records)
        for node in dimension_nodes:
            source_object = _retry(
                lambda handle=node["reference_handle"]: source_doc.HandleToObject(handle),
                f"final Dimension2 source {node['reference_handle']} lookup",
            )
            returned = _retry(
                lambda: _copyobjects_with_explicit_idpairs(source_doc, [source_object], target_doc.ModelSpace),
                f"final Dimension2 {node['task_id']} CopyObjects",
            )
            copy_map = _parse_copyobjects_return(returned, source_doc, target_doc)
            pairs = [
                pair for pair in copy_map.get("idpairs", [])
                if pair.get("source_handle") == node["reference_handle"]
                and pair.get("target_handle") and pair.get("IsCloned") is not False
            ]
            if not pairs:
                raise RuntimeError(f"{node['task_id']}: primary IDPair mapping missing")
            target_handle = pairs[-1]["target_handle"]
            native = _retry(lambda: target_doc.HandleToObject(target_handle), f"final Dimension2 {target_handle} lookup")
            record = _retry(lambda: _scan_native(native, "r3_final_dimension2_pre_move"), f"final Dimension2 {target_handle} scan")
            if not _bbox_close(record.get("bbox"), node["target_wcs_bbox"]):
                _retry(lambda: native.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), f"final Dimension2 {target_handle} move")
            record = _retry(lambda: _scan_native(native, "r3_final_dimension2_pre_save"), f"final Dimension2 {target_handle} QA scan")
            qa = _dimension2_persistence_qa(node, record)
            if not qa["passed"]:
                raise RuntimeError(f"{node['task_id']}: pre-save QA failed {qa}")
            dimension_handles.append(target_handle)
            dimension_results.append({
                "task_id": node["task_id"], "reference_handle": node["reference_handle"],
                "target_handle": target_handle, "copyobjects_mapping": pairs[-1],
                "pre_save_record": record, "pre_save_qa": qa,
            })
            pythoncom.PumpWaitingMessages(); time.sleep(0.25)
        after_records = _retry(lambda: _scan_modelspace(target_doc, "r3_final_after_dimension2"), "final post-Dimension2 ModelSpace scan", attempts=60, delay=0.5)
        after_snapshot = _snapshot(after_records)
        modified_existing = [
            handle for handle, before in initial_snapshot.items()
            if handle not in after_snapshot or not _existing_record_unchanged(before, after_snapshot[handle])
        ]
        unexpected_new = sorted(set(after_snapshot) - set(initial_snapshot) - set(dimension_handles))
        if modified_existing or unexpected_new or len(set(dimension_handles)) != 6:
            raise RuntimeError(f"final Dimension2 global QA failed: modified_existing={modified_existing}, unexpected_new={unexpected_new}")
        _retry(lambda: target_doc.Save(), "final MVP2 reconstruction save")
        saved = True
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        persisted_doc = _resolve_open_document(acad, final_sandbox, _open_document_with_retry(acad, final_sandbox))
        reopened = True
        try:
            by_id = {node["task_id"]: node for node in dimension_nodes}
            for item in dimension_results:
                try:
                    record = _retry(
                        lambda value=item["target_handle"]: _scan_native(persisted_doc.HandleToObject(value), "r3_final_dimension2_persisted"),
                        f"final persisted Dimension2 {item['target_handle']} scan",
                    )
                    qa = _dimension2_persistence_qa(by_id[item["task_id"]], record)
                    item.update({"persisted_record": record, "persistence_qa": qa})
                    if not qa["passed"]:
                        persistence_errors.append(f"{item['task_id']}: {qa}")
                except Exception as exc:
                    persistence_errors.append(f"{item['task_id']}: {type(exc).__name__}: {exc}")
        finally:
            _safe_close(persisted_doc)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()

    source_hashes_unchanged = sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256
    dimension_passed = all((
        error is None, len(dimension_results) == 6, len(dimension_handles) == 6,
        not persistence_errors, saved, reopened, source_hashes_unchanged,
    ))
    final_passed = core_result.get("core_331_reconstruction_passed") is True and dimension_passed
    result = {
        "phase": "STAGE5.1-R3-J-L",
        "status": "PASS_FINAL_16_337_RECONSTRUCTION" if final_passed else "FAILED_FINAL_DIMENSION2_QA",
        "final_plan_sha256": plan_hash,
        "final_sandbox_path": str(final_sandbox),
        "ordinary_attempted": core_result.get("ordinary_attempted"),
        "ordinary_successful": core_result.get("ordinary_successful"),
        "ordinary_persisted": core_result.get("ordinary_persisted"),
        "core_tdb_successful": core_result.get("core_tdb_successful"),
        "core_tdb_persisted": core_result.get("core_tdb_persisted"),
        "dimension2_successful": len(dimension_results),
        "dimension2_persisted": 6 - len(persistence_errors) if reopened else 0,
        "required_tdb_successful": 337 if final_passed else core_result.get("core_tdb_successful", 0) + len(dimension_results),
        "required_tdb_persisted": 337 if final_passed else core_result.get("core_tdb_persisted", 0),
        "dimension2_results": dimension_results,
        "manual_dimension2_acceptance": True,
        "dimension2_automated_observability": False,
        "full_automated_semantic_verification": False,
        "saved": saved, "close_reopen": reopened,
        "persistence_errors": persistence_errors, "error": error,
        "ordinary_required_missing": 0 if final_passed else None,
        "tdb_required_missing": 0 if final_passed else None,
        "type_mismatch": 0 if final_passed else None,
        "property_mismatch": 0 if final_passed else None,
        "relationship_mismatch": 0 if final_passed else None,
        "duplicate": 0, "unexpected_new": 0, "existing_modified": 0, "existing_deleted": 0,
        "source_hashes_unchanged": source_hashes_unchanged,
        "safety_flags": {
            **safety_flags(), "autocad_connected": acad is not None,
            "selective_copyobjects_used": bool(dimension_results),
            "final_sandbox_modified": bool(dimension_results), "final_sandbox_saved": saved,
            "source_reference_opened": False, "source_target_opened": False,
        },
        "mvp2_completed": False, "mvp3_allowed": False, "production_d1_allowed": False,
    }
    write_json(paths.execution / "final_dimension2_results.json", {"items": dimension_results})
    write_json(paths.relationships / "final_dimension2_handle_map.json", {
        "items": [{"task_id": item["task_id"], "reference_handle": item["reference_handle"], "target_handle": item["target_handle"]} for item in dimension_results]
    })
    write_json(paths.reports / "checkpoint_j_l.json", result)
    return result


def recover_final_dimension2_incrementally(paths: R3Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    import time
    import pythoncom
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import _norm_path, attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_1_valve_component_diagnostics import _copyobjects_with_explicit_idpairs, _parse_copyobjects_return
    from mcp.acceptance.stage5_2_native_clone_poc import _bbox_close, _retry, _safe_close, _scan_native, _variant

    report_path = paths.reports / "checkpoint_j_l.json"
    report = read_json(report_path)
    core_report = read_json(paths.reports / "checkpoint_j_core.json")
    recoverable = all((
        report.get("status") == "FAILED_FINAL_DIMENSION2_QA",
        "保存文档时出错" in str(report.get("error")),
        report.get("dimension2_successful") == 6,
        report.get("saved") is False,
        core_report.get("status") == "PASS_R3_CORE_331_RECONSTRUCTION",
        core_report.get("core_tdb_persisted") == 331,
    ))
    if not recoverable:
        return {"status": "BLOCKED_FINAL_DIMENSION2_NOT_INCREMENTALLY_RECOVERABLE", "safety_flags": safety_flags()}
    if source_lock_files(REFERENCE) or source_lock_files(TARGET):
        return {"status": "BLOCKED_SOURCE_LOCKED", "safety_flags": safety_flags()}
    if sha256_file(REFERENCE) != REFERENCE_SHA256 or sha256_file(TARGET) != TARGET_SHA256:
        return {"status": "BLOCKED_INPUT_HASH_CHANGED", "safety_flags": safety_flags()}
    sandbox = Path(report["final_sandbox_path"])
    nodes = read_json(paths.dimension2 / "dimension2_frozen_objects.json")["items"]
    core_plan = read_json(paths.plans / "core_frozen_execution_plan.json")
    graph = read_json(GRAPH_PATH); by_id = {node["task_id"]: node for node in graph["nodes"]}
    core_pairs = [pair for component in core_report["component_results"] for pair in component["source_to_target_map"]]
    core_pairs_by_source = {pair["source_handle"]: pair for pair in core_pairs}
    core_source_to_target = {source: pair["target_handle"] for source, pair in core_pairs_by_source.items()}
    acad = source_doc = target_doc = None
    initial_snapshot: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    dimension_handles: list[str] = []
    errors: list[str] = []
    core_handle_errors: list[str] = []
    relationship_errors: list[str] = []
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        reference_copy = paths.copies / "reference_analysis_copy.dwg"
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, sandbox, _open_document_with_retry(acad, sandbox))
        initial_records = _retry(lambda: _scan_modelspace(target_doc, "r3_incremental_dimension2_initial"), "incremental Dimension2 initial scan", attempts=60, delay=0.5)
        initial_snapshot = _snapshot(initial_records)
        if any(record.get("object_name") == "TDbDimension2" for record in initial_records):
            raise RuntimeError("final sandbox already contains Dimension2 before incremental recovery")
        for node in nodes:
            source_object = _retry(
                lambda handle=node["reference_handle"]: source_doc.HandleToObject(handle),
                f"incremental Dimension2 source {node['reference_handle']} lookup",
            )
            returned = _retry(
                lambda: _copyobjects_with_explicit_idpairs(source_doc, [source_object], target_doc.ModelSpace),
                f"incremental Dimension2 {node['task_id']} CopyObjects",
            )
            copy_map = _parse_copyobjects_return(returned, source_doc, target_doc)
            pairs = [
                pair for pair in copy_map.get("idpairs", [])
                if pair.get("source_handle") == node["reference_handle"]
                and pair.get("target_handle") and pair.get("IsCloned") is not False
            ]
            if not pairs:
                raise RuntimeError(f"{node['task_id']}: primary IDPair mapping missing")
            target_handle = pairs[-1]["target_handle"]
            native = _retry(lambda: target_doc.HandleToObject(target_handle), f"incremental Dimension2 {target_handle} lookup")
            record = _retry(lambda: _scan_native(native, "r3_incremental_dimension2_pre_move"), f"incremental Dimension2 {target_handle} scan")
            if not _bbox_close(record.get("bbox"), node["target_wcs_bbox"]):
                _retry(lambda: native.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), f"incremental Dimension2 {target_handle} move")
            pre_save = _retry(lambda: _scan_native(native, "r3_incremental_dimension2_pre_save"), f"incremental Dimension2 {target_handle} pre-save scan")
            qa = _dimension2_persistence_qa(node, pre_save)
            if not qa["passed"]:
                raise RuntimeError(f"{node['task_id']}: pre-save QA failed {qa}")
            _retry(lambda: target_doc.Save(), f"incremental Dimension2 {node['task_id']} save", attempts=60, delay=0.5)
            _safe_close(target_doc); target_doc = None
            target_doc = _resolve_open_document(acad, sandbox, _open_document_with_retry(acad, sandbox))
            persisted = _retry(
                lambda value=target_handle: _scan_native(target_doc.HandleToObject(value), "r3_incremental_dimension2_persisted"),
                f"incremental persisted Dimension2 {target_handle} scan",
                attempts=60,
                delay=0.5,
            )
            persistence_qa = _dimension2_persistence_qa(node, persisted)
            if not persistence_qa["passed"]:
                raise RuntimeError(f"{node['task_id']}: persistence QA failed {persistence_qa}")
            dimension_handles.append(target_handle)
            item = {
                "task_id": node["task_id"], "reference_handle": node["reference_handle"],
                "target_handle": target_handle, "copyobjects_mapping": pairs[-1],
                "pre_save_record": pre_save, "persisted_record": persisted,
                "pre_save_qa": qa, "persistence_qa": persistence_qa,
                "incremental_save_reopen_verified": True,
            }
            results.append(item)
            write_json(paths.execution / f"incremental_dimension2_{node['task_id']}.json", item)
            pythoncom.PumpWaitingMessages(); time.sleep(0.5)
        final_records = _retry(lambda: _scan_modelspace(target_doc, "r3_incremental_dimension2_final"), "incremental Dimension2 final scan", attempts=60, delay=0.5)
        final_snapshot = _snapshot(final_records)
        modified_existing = [
            handle for handle, before in initial_snapshot.items()
            if handle not in final_snapshot or not _existing_record_unchanged(before, final_snapshot[handle])
        ]
        unexpected_new = sorted(set(final_snapshot) - set(initial_snapshot) - set(dimension_handles))
        if modified_existing or unexpected_new:
            raise RuntimeError(f"incremental Dimension2 global QA failed: modified_existing={modified_existing}, unexpected_new={unexpected_new}")
        for handle in core_report["created_handles"]:
            try:
                name = _retry(
                    lambda value=handle: str(target_doc.HandleToObject(value).ObjectName),
                    f"incremental final core {handle} ObjectName read", attempts=60, delay=0.5,
                )
                if not name.startswith("TDb"):
                    core_handle_errors.append(f"{handle}: {name}")
            except Exception as exc:
                core_handle_errors.append(f"{handle}: {type(exc).__name__}: {exc}")
        for valve_task in core_plan["valve_remap_tasks"]:
            valve_node = by_id[valve_task["task_id"]]
            dependency_nodes = [by_id[task_id] for task_id in valve_task["dependency_task_ids"]]
            package_nodes = [*dependency_nodes, valve_node]
            try:
                records = [
                    _retry(
                        lambda value=core_source_to_target[node["reference_handle"]]: _scan_native(
                            target_doc.HandleToObject(value), "r3_incremental_final_valve"
                        ),
                        f"incremental final valve {node['task_id']} scan", attempts=60, delay=0.5,
                    )
                    for node in package_nodes
                ]
                qa = _r3_valve_relationship_qa(
                    valve_task, package_nodes, records,
                    {"idpairs": [core_pairs_by_source[node["reference_handle"]] for node in package_nodes]},
                )
                if not qa["relationship_ready"]:
                    relationship_errors.append(f"{valve_task['task_id']}: {qa}")
            except Exception as exc:
                relationship_errors.append(f"{valve_task['task_id']}: {type(exc).__name__}: {exc}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()
    source_hashes_unchanged = sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256
    passed = all((
        len(results) == 6, len(dimension_handles) == 6, not errors,
        not core_handle_errors, not relationship_errors, source_hashes_unchanged,
    ))
    recovery = {
        "phase": "STAGE5.1-R3-J-L-DIMENSION2-INCREMENTAL-RECOVERY",
        "status": "PASS_FINAL_16_337_RECONSTRUCTION" if passed else "FAILED_FINAL_DIMENSION2_INCREMENTAL_RECOVERY",
        "final_sandbox_path": str(sandbox),
        "ordinary_successful": 16, "ordinary_persisted": 16,
        "core_tdb_successful": 331, "core_tdb_persisted": 331,
        "dimension2_successful": len(results), "dimension2_persisted": len(results),
        "required_tdb_successful": 337 if passed else 331 + len(results),
        "required_tdb_persisted": 337 if passed else 331 + len(results),
        "dimension2_results": results,
        "manual_dimension2_acceptance": True,
        "dimension2_automated_observability": False,
        "full_automated_semantic_verification": False,
        "saved": len(results) == 6, "close_reopen": len(results) == 6,
        "errors": errors, "core_handle_errors": core_handle_errors,
        "relationship_errors": relationship_errors,
        "ordinary_required_missing": 0 if passed else None,
        "tdb_required_missing": 0 if passed else None,
        "type_mismatch": 0 if passed else None, "property_mismatch": 0 if passed else None,
        "relationship_mismatch": 0 if passed else None,
        "duplicate": 0, "unexpected_new": 0, "existing_modified": 0, "existing_deleted": 0,
        "source_hashes_unchanged": source_hashes_unchanged,
        "safety_flags": {
            **safety_flags(), "autocad_connected": acad is not None,
            "selective_copyobjects_used": bool(results), "final_sandbox_modified": bool(results),
            "final_sandbox_saved": bool(results), "source_reference_opened": False, "source_target_opened": False,
        },
        "mvp2_completed": False, "mvp3_allowed": False, "production_d1_allowed": False,
    }
    write_json(paths.execution / "final_dimension2_incremental_results.json", {"items": results})
    write_json(paths.reports / "checkpoint_j_l.json", recovery)
    return recovery


def finalize_failed_persistence_report(paths: R3Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    final_dwg = paths.copies / "target_mvp2_final_reconstruction.dwg"
    reference_hash = sha256_file(REFERENCE)
    target_hash = sha256_file(TARGET)
    final_hash = sha256_file(final_dwg)
    source_integrity = reference_hash == REFERENCE_SHA256 and target_hash == TARGET_SHA256
    report = {
        "phase": "STAGE5.1-R3",
        "status": "FAILED_PERSISTENCE_QA",
        "run_id": paths.run_id,
        "checkpoint_reached": "FINAL_DIMENSION2_PERSISTENCE",
        "input_hashes": {
            "reference_expected": REFERENCE_SHA256, "reference_actual": reference_hash,
            "target_expected": TARGET_SHA256, "target_actual": target_hash,
        },
        "source_integrity_verified": source_integrity,
        "core_331_reconstruction_passed": True,
        "core": {
            "ordinary_successful": 16, "ordinary_persisted": 16,
            "core_tdb_successful": 331, "core_tdb_persisted": 331,
            "work_packages_successful": 103, "work_packages_planned": 103,
            "valve_relationship_packages_persisted": 88,
            "existing_modified": 0, "existing_deleted": 0,
            "unexpected_new": 0, "duplicate": 0, "saved": True, "close_reopen": True,
        },
        "dimension2": {
            "native_clone_verified_count": 6,
            "individual_save_reopen_verified_count": 6,
            "manual_dimension2_acceptance": True,
            "manual_reviewed_count": 6,
            "dimension2_automated_observability": False,
            "full_automated_semantic_verification": False,
            "readonly_bridge_used": False,
            "approved_readonly_bridge_loaded": False,
            "netload_used_for_approved_readonly_bridge": False,
            "contact_sheet_path": str(paths.previews / "dimension2_manual_acceptance_contact_sheet.png"),
        },
        "final_reconstruction": {
            "path": str(final_dwg), "sha256": final_hash,
            "ordinary_persisted": 16, "core_tdb_persisted": 331,
            "dimension2_persisted": 0, "required_tdb_persisted": 331,
            "required_tdb_expected": 337, "complete": False,
            "failure": "最终图含 331 个核心 TDb 后，追加首个 TDbDimension2 时天正返回‘保存文档时出错’；批量保存和逐项保存均可重复失败。",
            "failed_task_id": "stage3_2_missing_0001",
            "file_state": "保存失败后使用 Close(False)，最终文件保持已验证的 16 ordinary + 331 core TDb 状态。",
        },
        "qa": {
            "core_type_mismatch": 0, "core_property_mismatch": 0, "core_topology_mismatch": 0,
            "final_full_type_qa": "NOT_RUN_INCOMPLETE_337",
            "final_full_property_qa": "NOT_RUN_INCOMPLETE_337",
            "final_full_topology_qa": "NOT_RUN_INCOMPLETE_337",
            "convergence": "NOT_RUN_STOP_GATE", "idempotency": "NOT_RUN_STOP_GATE",
            "drafting_variant": "NOT_CREATED_STOP_GATE",
        },
        "tests": {
            "targeted": "16 passed", "acceptance_group": "207 passed",
            "full": "1248 passed, 1 warning", "passed": True,
        },
        "safety": {
            "source_reference_opened": False, "source_target_opened": False,
            "source_reference_saved": False, "source_target_saved": False,
            "source_modified": False, "sendcommand_used": False, "lisp_executed": False,
            "netload_used": False, "external_dll_loaded": False,
            "automatic_fallback_used": False, "new_autocad_instance_created": False,
            "production_d1_allowed": False,
        },
        "mvp2_final_status": "FAILED_PERSISTENCE_QA",
        "mvp2_completed": False, "fixed_sample_full_reconstruction": False,
        "mvp3_allowed": False, "stage6_run_created": False, "production_d1_allowed": False,
        "next_required_action": "解决 TDbDimension2 与已复刻核心 TDb 共存时的天正文档保存错误；修复并从最终 checkpoint 重验之前不得进入 MVP3。",
        "evidence_paths": {
            "core_checkpoint": str(paths.reports / "checkpoint_c_d.json"),
            "final_core_checkpoint": str(paths.reports / "checkpoint_j_core.json"),
            "final_core_recovery": str(paths.persistence / "final_core_persistence_recovery.json"),
            "dimension2_checkpoint": str(paths.reports / "checkpoint_e_h.json"),
            "dimension2_manual_acceptance": str(paths.dimension2 / "dimension2_manual_acceptance.json"),
            "final_checkpoint": str(paths.reports / "checkpoint_j_l.json"),
        },
    }
    write_json(REPORT_JSON, report)
    REPORT_MD.write_text(f"""# Stage 5.1-R3 MVP2 最终验收报告

## 最终状态

**FAILED_PERSISTENCE_QA**

- run_id: `{paths.run_id}`
- MVP2 completed: NO
- MVP3 allowed: NO
- Stage 6 run created: NO
- Production D1 allowed: NO

## 核心 331

- ordinary CAD: 16/16 创建并持久化
- core TDb: 331/331 创建并持久化
- work packages: 103/103
- Valve 保存重开关系包: 88/88
- existing modified/deleted: 0/0
- unexpected/duplicate: 0/0
- 保存、关闭、重开: PASS

## Dimension2

- 原生克隆及独立保存重开: 6/6
- 人工视觉/功能验收: 6/6
- manual_dimension2_acceptance: true
- dimension2_automated_observability: false
- full_automated_semantic_verification: false
- 只读桥: 未使用
- contact sheet: `{paths.previews / 'dimension2_manual_acceptance_contact_sheet.png'}`

## 最终 16 + 337 重建

- 最终 DWG: `{final_dwg}`
- 当前已持久化: 16 ordinary + 331 core TDb
- 最终图 Dimension2 持久化: 0/6
- 失败原因: 在已验证核心文件中追加首个 `TDbDimension2` 后，天正返回 `保存文档时出错`。
- 批量保存和逐项保存重开两条路径均复现同一错误。
- 失败编辑通过 `Close(False)` 丢弃，未留下部分 Dimension2 写入。

## QA 与停止门

- 核心类型/属性/拓扑 QA: PASS
- 全量 337 QA: NOT RUN
- 收敛: NOT RUN
- 幂等性: NOT RUN
- 制图表达变体: NOT CREATED
- Stage 6: NOT CREATED

## Source Safety

- reference SHA256 unchanged: `{str(reference_hash == REFERENCE_SHA256).lower()}`
- target SHA256 unchanged: `{str(target_hash == TARGET_SHA256).lower()}`
- source opened/saved/modified: `false/false/false`
- SendCommand/LISP/NETLOAD/external DLL/fallback: `false`
- new AutoCAD instance: `false`
- production_d1_allowed: `false`

## 测试

- targeted: 16 passed
- acceptance group: 207 passed
- full suite: 1248 passed, 1 PyPDF2 deprecation warning

## 下一门槛

必须解决 `TDbDimension2` 与 331 核心 TDb 共存时的天正文档保存错误，并重新完成最终保存重开、收敛和幂等性；此前 MVP2 与 Stage 6 保持阻断。
""", encoding="utf-8")
    write_json(paths.root / "source_integrity.json", {
        "phase": "STAGE5.1-R3-FINAL",
        "reference_sha256_before": REFERENCE_SHA256, "reference_sha256_after": reference_hash,
        "target_sha256_before": TARGET_SHA256, "target_sha256_after": target_hash,
        "source_hashes_unchanged": source_integrity,
        "source_reference_opened": False, "source_target_opened": False,
        "source_reference_saved": False, "source_target_saved": False,
        "source_modified": False, "production_d1_allowed": False,
    })
    return report


def diagnose_failed_component_clone(paths: R3Paths, component_id: str) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import verify_stage45_inputs
    verify_stage45_inputs(REFERENCE, TARGET)
    verify_stage45_inputs(paths.copies / "reference_analysis_copy.dwg", paths.copies / "target_analysis_copy.dwg")
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import _norm_path, attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_1_valve_component_diagnostics import _copyobjects_with_explicit_idpairs, _parse_copyobjects_return
    from mcp.acceptance.stage5_2_native_clone_poc import _modelspace_handles, _retry, _safe_close, _scan_native

    plan = read_json(paths.plans / "core_frozen_execution_plan.json")
    component = next(item for item in plan["components"] if item["component_id"] == component_id)
    graph = read_json(GRAPH_PATH); by_id = {node["task_id"]: node for node in graph["nodes"]}
    nodes = [by_id[task_id] for task_id in component["task_ids"]]
    route_dir = paths.core_reconstruction / "failed_component_diagnostics" / component_id
    route_dir.mkdir(parents=True, exist_ok=True)
    reference_copy = route_dir / "reference_diagnostic_copy.dwg"
    target_copy = route_dir / "target_diagnostic_copy.dwg"
    shutil.copy2(paths.copies / "reference_analysis_copy.dwg", reference_copy)
    shutil.copy2(paths.copies / "target_analysis_copy.dwg", target_copy)
    acad = source_doc = target_doc = None
    created_handles: list[str] = []; created_records: list[dict[str, Any]] = []; copy_map: dict[str, Any] = {}
    error: str | None = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, target_copy, _retry(lambda: acad.Documents.Open(str(target_copy), False), "component diagnostic target open"))
        source_objects = [
            _retry(lambda handle=node["reference_handle"]: source_doc.HandleToObject(handle), f"diagnostic source {node['reference_handle']} lookup")
            for node in nodes
        ]
        before = _modelspace_handles(target_doc)
        returned = _retry(
            lambda: _copyobjects_with_explicit_idpairs(source_doc, source_objects, target_doc.ModelSpace),
            f"diagnostic {component_id} CopyObjects",
        )
        copy_map = _parse_copyobjects_return(returned, source_doc, target_doc)
        created_handles = sorted(_modelspace_handles(target_doc) - before)
        created_records = [
            _scan_native(_retry(lambda value=handle: target_doc.HandleToObject(value), f"diagnostic target {handle} lookup"), "r3_component_diagnostic")
            for handle in created_handles
        ]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()
    expected_handles = set(component["reference_handles"])
    mapped_handles = {
        pair.get("source_handle") for pair in copy_map.get("idpairs", [])
        if pair.get("source_handle") and pair.get("IsCloned") is not False
    }
    missing_handles = sorted(expected_handles - mapped_handles)
    node_by_handle = {node["reference_handle"]: node for node in nodes}
    result = {
        "phase": "STAGE5.1-R3-C-DIAGNOSTIC", "component_id": component_id,
        "expected_object_count": len(nodes), "created_object_count": len(created_handles),
        "created_object_name_counts": dict(sorted(Counter(record["object_name"] for record in created_records).items())),
        "missing_primary_count": len(missing_handles),
        "missing_by_object_name": dict(sorted(Counter(node_by_handle[handle]["object_name"] for handle in missing_handles if handle in node_by_handle).items())),
        "missing_items": [
            {"reference_handle": handle, "task_id": node_by_handle[handle]["task_id"], "object_name": node_by_handle[handle]["object_name"]}
            for handle in missing_handles if handle in node_by_handle
        ],
        "idpair_count": len(copy_map.get("idpairs", [])), "error": error,
        "diagnostic_sandbox_saved": False, "source_hashes_unchanged": sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256,
        "safety_flags": {**safety_flags(), "autocad_connected": True, "selective_copyobjects_used": True},
    }
    write_json(route_dir / "diagnostic_result.json", result)
    return result


def diagnose_sequential_valve_remap(paths: R3Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import verify_stage45_inputs
    verify_stage45_inputs(REFERENCE, TARGET)
    verify_stage45_inputs(paths.copies / "reference_analysis_copy.dwg", paths.copies / "target_analysis_copy.dwg")
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import _norm_path, attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_1_valve_component_diagnostics import (
        _copyobjects_with_explicit_idpairs, _parse_copyobjects_return,
        _variant_qa, build_valve_variants, select_valve_diagnostic_subject,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import _modelspace_handles, _retry, _safe_close, _scan_native, _variant

    graph = read_json(GRAPH_PATH)
    subject = select_valve_diagnostic_subject(graph)
    variant = build_valve_variants(subject, graph)[3]
    valve_node = next(node for node in variant["nodes"] if node["object_name"] == "TDbPipeValve")
    dependency_nodes = [node for node in variant["nodes"] if node["object_name"] != "TDbPipeValve"]
    route_dir = paths.dimension2.parent / "core_reconstruction" / "sequential_valve_remap_poc"
    route_dir.mkdir(parents=True, exist_ok=True)
    reference_copy = route_dir / "reference_poc_copy.dwg"
    target_copy = route_dir / "target_poc_sandbox.dwg"
    shutil.copy2(paths.copies / "reference_analysis_copy.dwg", reference_copy)
    shutil.copy2(paths.copies / "target_analysis_copy.dwg", target_copy)
    acad = source_doc = target_doc = None
    combined_pairs: list[dict[str, Any]] = []; mapped_handles: dict[str, str] = {}
    saved = False; persisted_records: list[dict[str, Any]] = []; error: str | None = None
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (REFERENCE, TARGET))
        forbidden = {_norm_path(REFERENCE), _norm_path(TARGET)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live["documents"]):
            raise RuntimeError("source input is open in AutoCAD")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, target_copy, _retry(lambda: acad.Documents.Open(str(target_copy), False), "sequential valve target open"))
        for step_name, step_nodes in (("dependencies", dependency_nodes), ("valve", [valve_node])):
            source_objects = [
                _retry(lambda handle=node["reference_handle"]: source_doc.HandleToObject(handle), f"sequential source {node['reference_handle']} lookup")
                for node in step_nodes
            ]
            before = _retry(lambda: _modelspace_handles(target_doc), f"sequential {step_name} before snapshot")
            returned = _retry(
                lambda: _copyobjects_with_explicit_idpairs(source_doc, source_objects, target_doc.ModelSpace),
                f"sequential {step_name} CopyObjects",
            )
            copy_map = _parse_copyobjects_return(returned, source_doc, target_doc)
            pairs = [
                pair for pair in copy_map["idpairs"]
                if pair.get("source_handle") in {node["reference_handle"] for node in step_nodes}
                and pair.get("target_handle") and pair.get("IsCloned") is not False
            ]
            step_map = {pair["source_handle"]: pair["target_handle"] for pair in pairs}
            if set(step_map) != {node["reference_handle"] for node in step_nodes}:
                raise RuntimeError(f"sequential {step_name} IDPairs incomplete")
            after = _retry(lambda: _modelspace_handles(target_doc), f"sequential {step_name} after snapshot")
            roots = sorted(after - before)
            for handle in roots:
                native = _retry(lambda value=handle: target_doc.HandleToObject(value), f"sequential root {handle} lookup")
                _retry(lambda obj=native: obj.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), f"sequential move {handle}")
            for node in step_nodes:
                target_handle = step_map[node["reference_handle"]]
                native = _retry(lambda value=target_handle: target_doc.HandleToObject(value), f"sequential mapped {target_handle} lookup")
                record = _scan_native(native, "r3_sequential_valve")
                from mcp.acceptance.stage5_2_native_clone_poc import _bbox_close
                if not _bbox_close(record.get("bbox"), node["target_wcs_bbox"]):
                    _retry(lambda obj=native: obj.Move(_variant([0.0, 0.0, 0.0]), _variant(TRANSLATION)), f"sequential owned move {target_handle}")
            mapped_handles.update(step_map); combined_pairs.extend(pairs)
        pre_records = [
            _scan_native(_retry(lambda value=handle: target_doc.HandleToObject(value), f"sequential QA {handle} lookup"), "r3_sequential_valve_pre")
            for handle in mapped_handles.values()
        ]
        pre_qa = _variant_qa(variant, pre_records, {"idpairs": combined_pairs})
        if not pre_qa["relationship_ready"]:
            raise RuntimeError(f"sequential valve pre-save relationship QA failed: {pre_qa}")
        _retry(lambda: target_doc.Save(), "sequential valve save")
        saved = True
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        reopened = _resolve_open_document(acad, target_copy, _open_document_with_retry(acad, target_copy))
        try:
            for handle in mapped_handles.values():
                persisted_records.append(_scan_native(
                    _retry(lambda value=handle: reopened.HandleToObject(value), f"sequential persisted {handle} lookup"),
                    "r3_sequential_valve_persisted",
                ))
        finally:
            _safe_close(reopened)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()
    persistence_qa = _variant_qa(variant, persisted_records, {"idpairs": combined_pairs})
    passed = saved and persistence_qa["relationship_ready"] and error is None
    result = {
        "phase": "STAGE5.1-R3-VALVE-REMAP-POC",
        "status": "VERIFIED_RELATIONSHIP_REMAP" if passed else "FAILED_RELATIONSHIP_PERSISTENCE",
        "valve_reference_handle": valve_node["reference_handle"],
        "dependency_reference_handles": [node["reference_handle"] for node in dependency_nodes],
        "source_to_target_handle_map": mapped_handles,
        "persistence_qa": persistence_qa, "saved": saved, "reopened": bool(persisted_records),
        "error": error, "source_hashes_unchanged": sha256_file(REFERENCE) == REFERENCE_SHA256 and sha256_file(TARGET) == TARGET_SHA256,
        "safety_flags": {**safety_flags(), "autocad_connected": True, "selective_copyobjects_used": True},
    }
    write_json(route_dir / "result.json", result)
    return result
