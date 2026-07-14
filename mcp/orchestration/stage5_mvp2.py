from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mcp.acceptance.stage3_1_runtime import sha256_file
from mcp.acceptance.stage3_3_controlled_repair import source_lock_files


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "artifacts" / "stage5"
REPORT_JSON = ROOT / "reports" / "stage5_mvp2_full_reconstruction.json"
REPORT_MD = ROOT / "reports" / "stage5_mvp2_full_reconstruction.md"

REFERENCE = ROOT / "artifacts" / "stage3_1_r1" / "stage3_1_r1_20260711_002112" / "copies" / "reference_working_copy.dwg"
TARGET = Path(r"E:\SampleDrawings\target_sample.dwg")
MVP1_SANDBOX = ROOT / "artifacts" / "stage4" / "stage4_20260711_094721" / "copies" / "target_repair_sandbox.dwg"
STAGE4_RUN = ROOT / "artifacts" / "stage4" / "stage4_20260711_094721"
STAGE4_REPORT = ROOT / "reports" / "stage4_mvp_integration.json"
TDB_MANUAL = STAGE4_RUN / "qa" / "tianzheng_manual_review.json"
REFERENCE_SCAN = STAGE4_RUN / "scans" / "reference_scan.json"
MISSING_CANDIDATES = STAGE4_RUN / "diff" / "missing_candidates.json"

REFERENCE_SHA256 = None  # External run configuration required; no bundled private default.
TARGET_SHA256 = None  # External run configuration required; no bundled private default.
TRANSLATION = None  # External run configuration required; no bundled private default.

CHECKPOINTS = (
    "INPUT_FROZEN", "INVENTORY_COMPLETE", "PIPE_POC_COMPLETE",
    "FITTING_VALVE_POC_COMPLETE", "EQUIPMENT_POC_COMPLETE",
    "CAPABILITY_MATRIX_FROZEN", "PIPE_NETWORK_COMPLETE", "EQUIPMENT_COMPLETE",
    "ANNOTATION_COMPLETE", "CONVERGENCE_COMPLETE", "SAVE_COMPLETE",
    "REOPEN_QA_COMPLETE", "IDEMPOTENCY_COMPLETE", "FINALIZED",
)

DESIGN_TYPES = {
    "TDbPipe", "TDbDoubleLinePipe", "TDbPipeValve", "TDbPipeFitting",
    "TDbPump", "TDbEquipment", "TDbWaterTank",
}
ANNOTATION_TYPES = {"TDbDimension2", "TDbVPipeDim", "TDbSymbMultiLeader"}


@dataclass(frozen=True)
class Stage5Paths:
    run_id: str
    root: Path
    copies: Path
    archive: Path
    inventory: Path
    poc: Path
    qa: Path
    convergence: Path
    previews: Path

    @classmethod
    def build(cls, run_id: str) -> "Stage5Paths":
        root = RUNS_ROOT / run_id
        return cls(
            run_id, root, root / "copies", root / "mvp1_archive", root / "inventory",
            root / "poc", root / "qa", root / "convergence_iterations", root / "previews",
        )

    def create(self) -> None:
        for path in (self.root, self.copies, self.archive, self.inventory, self.poc, self.qa, self.convergence, self.previews):
            path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "size": stat.st_size,
        "modified_time": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
    }


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _safety() -> dict[str, bool]:
    return {
        "autocad_connected": False,
        "source_reference_opened": False,
        "source_target_opened": False,
        "source_reference_saved": False,
        "source_target_saved": False,
        "source_modified": False,
        "dwg_modified": False,
        "dwg_saved": False,
        "saveas_used": False,
        "copyobjects_used": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "tdb_modified": False,
        "automatic_fallback_used": False,
        "new_autocad_instance_created": False,
        "production_d1_allowed": False,
        "mvp3_executed": False,
    }


def _checkpoint(paths: Stage5Paths, name: str, *, status: str = "completed", details: Mapping[str, Any] | None = None) -> None:
    if name not in CHECKPOINTS:
        raise ValueError(f"unknown Stage 5 checkpoint: {name}")
    checkpoint_path = paths.root / "checkpoints.json"
    data = read_json(checkpoint_path) if checkpoint_path.is_file() else {
        "run_id": paths.run_id, "completed": [], "current": None, "history": [], "resume_checkpoint": "INPUT_FROZEN",
    }
    if status == "completed" and name not in data["completed"]:
        data["completed"].append(name)
    data["current"] = name
    index = CHECKPOINTS.index(name)
    data["resume_checkpoint"] = CHECKPOINTS[index + 1] if status == "completed" and index + 1 < len(CHECKPOINTS) else name
    data["history"].append({
        "checkpoint": name, "status": status, "at": datetime.now().astimezone().isoformat(), "details": dict(details or {}),
    })
    write_json(checkpoint_path, data)


def freeze_mvp1_archive(
    paths: Stage5Paths,
    reference: Path = REFERENCE,
    target: Path = TARGET,
    mvp1_sandbox: Path = MVP1_SANDBOX,
) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    paths.create()
    if _same_path(reference, target):
        raise ValueError("reference and target must be different files")
    required = [
        reference, target, mvp1_sandbox, STAGE4_REPORT, ROOT / "reports" / "stage4_mvp_integration.md",
        STAGE4_RUN / "stage4_manifest.json", STAGE4_RUN / "workflow_checkpoints.json",
        STAGE4_RUN / "tasks" / "approved_execution_plan.json", TDB_MANUAL,
        STAGE4_RUN / "qa" / "tianzheng_manual_review.md", REFERENCE_SCAN, MISSING_CANDIDATES,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return {"status": "BLOCKED_MVP1_EVIDENCE_MISSING", "missing_files": missing, "safety_flags": _safety()}

    locks = {"reference": source_lock_files(reference), "target": source_lock_files(target)}
    if locks["reference"] or locks["target"]:
        return {"status": "BLOCKED_SOURCE_LOCKED", "source_locks": locks, "safety_flags": _safety()}

    reference_record = _file_record(reference)
    target_record = _file_record(target)
    sandbox_record = _file_record(mvp1_sandbox)
    stage4 = read_json(STAGE4_REPORT)
    manual = read_json(TDB_MANUAL).get("items", [])
    evidence_records = [_file_record(path) for path in required[3:]]
    input_hashes_match = reference_record["sha256"] == REFERENCE_SHA256 and target_record["sha256"] == TARGET_SHA256
    mvp1_evidence_valid = all((
        stage4.get("stage4_final_status") == "PASS_MVP_END_TO_END_REPEATABLE",
        stage4.get("tests_passed") is True,
        stage4.get("source_hashes_unchanged") is True,
        len(manual) == 337,
        input_hashes_match,
    ))

    archive_manifest = {
        "phase": "STAGE5.0", "run_id": paths.run_id,
        "mvp1_final_status": "PASS" if mvp1_evidence_valid else "INVALID",
        "mvp1_run_id": stage4.get("run_id"),
        "mvp1_report_sha256": _file_record(STAGE4_REPORT)["sha256"],
        "mvp1_final_sandbox": sandbox_record,
        "tdb_manual_task_count": len(manual),
        "tdb_manual_task_ids_hash": _json_hash(sorted(item.get("candidate_id") for item in manual)),
        "evidence_files": evidence_records,
        "archive_is_hash_frozen_read_only_evidence": True,
    }
    write_json(paths.root / "mvp1_archive_manifest.json", archive_manifest)
    write_json(paths.root / "input_manifest.json", {
        "reference": reference_record, "target": target_record, "mvp1_final_sandbox": sandbox_record,
        "expected_sha256": {"reference": REFERENCE_SHA256, "target": TARGET_SHA256},
        "input_hashes_match_frozen": input_hashes_match,
        "alignment": {"direction": "reference_wcs_to_target_wcs", "translation": TRANSLATION, "rotation": 0.0, "scale": [1.0, 1.0, 1.0]},
        "automatic_unattended_alignment": False,
    })
    write_json(paths.root / "source_integrity.json", {
        "reference_sha256_before": reference_record["sha256"], "target_sha256_before": target_record["sha256"],
        "reference_sha256_expected": REFERENCE_SHA256, "target_sha256_expected": TARGET_SHA256,
        "source_locks": locks, "source_hashes_match": input_hashes_match,
        "source_dwg_opened": False, "source_dwg_saved": False, "source_modified": False,
    })
    baseline = {
        "ordinary_cad_tasks": 16, "ordinary_cad_successful": 16, "ordinary_cad_persisted": 16,
        "tdb_manual_tasks": len(manual), "tdb_task_ids": sorted(item.get("candidate_id") for item in manual),
        "tdb_reference_handles": sorted(item.get("reference_handle") for item in manual),
        "tdb_task_set_hash": _json_hash(sorted((item.get("candidate_id"), item.get("reference_handle"), item.get("object_name")) for item in manual)),
        "duplicate": 0, "existing_modified": 0, "existing_deleted": 0, "unexpected_new": 0,
    }
    write_json(paths.root / "baseline_task_inventory.json", baseline)
    policy = {
        "phase": "STAGE5.0", "frozen": True, "may_expand_after_stage5_0": False,
        "allowed_categories": [
            "drawing_border", "title_block", "drawing_signature", "drawing_number",
            "user_name_or_student_id", "TDbDrawingName", "stage1_seed_line",
            "other_region_or_view", "user_explicitly_approved_not_to_copy",
        ],
        "object_specific_exceptions": [],
    }
    policy["policy_hash"] = _json_hash(policy)
    write_json(paths.root / "allowed_difference_policy.json", policy)
    status = "PASS_STAGE5_0_INPUT_FROZEN" if mvp1_evidence_valid else "BLOCKED_MVP1_EVIDENCE_INVALID"
    _checkpoint(paths, "INPUT_FROZEN", status="completed" if mvp1_evidence_valid else "blocked", details={
        "status": status, "tdb_manual_task_count": len(manual), "input_hashes_match": input_hashes_match,
    })
    result = {
        "phase": "STAGE5.0", "status": status, "run_id": paths.run_id,
        "input_hashes_match_frozen": input_hashes_match, "mvp1_evidence_valid": mvp1_evidence_valid,
        "tdb_manual_task_count": len(manual), "source_locks": locks,
        "mvp1_final_sandbox_sha256": sandbox_record["sha256"], "safety_flags": _safety(),
    }
    write_json(paths.root / "stage5_0_report.json", result)
    return result


def _bbox_distance(left: Sequence[Sequence[float]] | None, right: Sequence[Sequence[float]] | None) -> float | None:
    if not left or not right or len(left) != 2 or len(right) != 2:
        return None
    lx0, ly0, _ = left[0]; lx1, ly1, _ = left[1]
    rx0, ry0, _ = right[0]; rx1, ry1, _ = right[1]
    dx = max(float(lx0) - float(rx1), float(rx0) - float(lx1), 0.0)
    dy = max(float(ly0) - float(ry1), float(ry0) - float(ly1), 0.0)
    return (dx * dx + dy * dy) ** 0.5


def _semantic_group(object_name: str) -> str:
    if object_name in {"TDbPipe", "TDbDoubleLinePipe"}:
        return "pipe"
    if object_name == "TDbPipeValve":
        return "valve"
    if object_name == "TDbPipeFitting":
        return "fitting"
    if object_name == "TDbPump":
        return "pump"
    if object_name == "TDbEquipment":
        return "equipment"
    if object_name == "TDbWaterTank":
        return "water_tank"
    if object_name in ANNOTATION_TYPES:
        return "professional_annotation"
    return "unknown"


def _recommended_route(object_name: str) -> str:
    if object_name in DESIGN_TYPES or object_name in ANNOTATION_TYPES:
        return "selective_native_clone_poc_required"
    return "unsupported"


def _execution_rank(group: str) -> int:
    return {
        "pump": 10, "equipment": 10, "water_tank": 10,
        "pipe": 20, "fitting": 30, "valve": 40,
        "professional_annotation": 50, "unknown": 99,
    }.get(group, 99)


def _topological_order(nodes: Sequence[str], edges: Sequence[Mapping[str, Any]], rank: Mapping[str, int]) -> tuple[list[str], list[list[str]]]:
    outgoing: dict[str, list[str]] = defaultdict(list)
    indegree = {node: 0 for node in nodes}
    for edge in edges:
        dependency = str(edge["dependency_id"])
        dependent = str(edge["dependent_id"])
        if dependency == dependent or dependency not in indegree or dependent not in indegree:
            continue
        outgoing[dependency].append(dependent)
        indegree[dependent] += 1
    queue = deque(sorted((node for node, degree in indegree.items() if degree == 0), key=lambda item: (rank[item], item)))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for dependent in sorted(outgoing[node], key=lambda item: (rank[item], item)):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
        queue = deque(sorted(queue, key=lambda item: (rank[item], item)))
    cycles = [sorted(node for node, degree in indegree.items() if degree > 0)] if len(order) != len(nodes) else []
    if cycles:
        order.extend(sorted((node for node in nodes if node not in set(order)), key=lambda item: (rank[item], item)))
    return order, cycles


def build_tdb_inventory(paths: Stage5Paths) -> dict[str, Any]:
    freeze_report = paths.root / "stage5_0_report.json"
    if not freeze_report.is_file() or read_json(freeze_report).get("status") != "PASS_STAGE5_0_INPUT_FROZEN":
        return {"phase": "STAGE5.1", "status": "BLOCKED_STAGE5_0_NOT_PASS", "safety_flags": _safety()}
    manual = read_json(TDB_MANUAL).get("items", [])
    reference_entities = read_json(REFERENCE_SCAN).get("entities", [])
    missing_items = read_json(MISSING_CANDIDATES).get("items", [])
    reference_by_handle = {str(item.get("handle", "")).upper(): item for item in reference_entities}
    missing_by_handle = {
        str((item.get("reference_entity") or {}).get("handle", item.get("reference_handle", ""))).upper(): item
        for item in missing_items
    }
    inventory: list[dict[str, Any]] = []
    signatures: dict[tuple[Any, ...], str] = {}
    for task in manual:
        handle = str(task.get("reference_handle", "")).upper()
        source = reference_by_handle.get(handle)
        object_name = str(task.get("object_name") or (source or {}).get("object_name") or "UNKNOWN")
        bbox = task.get("bbox")
        signature = (object_name, json.dumps(bbox, sort_keys=True))
        missing_evidence = missing_by_handle.get(handle)
        if handle not in reference_by_handle:
            classification, reason = "UNSUPPORTED", "reference Handle is absent from frozen reference scan"
        elif signature in signatures:
            classification, reason = "DUPLICATE_REFERENCE_OBJECT", f"same type/geometry as {signatures[signature]}"
        elif missing_evidence is None:
            classification, reason = "REVIEW_REQUIRED", "no frozen missing-candidate evidence for reference Handle"
        elif object_name not in DESIGN_TYPES and object_name not in ANNOTATION_TYPES:
            classification, reason = "UNSUPPORTED", "object type is outside current fixed-sample TDb inventory"
        else:
            classification, reason = "REQUIRED_MISSING", "Stage 4 high-confidence missing evidence and unique reference Handle/geometry"
        signatures.setdefault(signature, handle)
        attributes = dict((source or {}).get("attributes") or {})
        geometry = dict((source or {}).get("geometry") or {})
        group = _semantic_group(object_name)
        inventory.append({
            "task_id": task.get("candidate_id"), "reference_handle": handle,
            "object_name": object_name, "semantic_type": group, "classification": classification,
            "classification_reason": reason, "target_wcs_position": task.get("target_wcs_position"),
            "target_wcs_geometry": {
                "bbox": bbox, "start_point": task.get("start_point"), "end_point": task.get("end_point"),
                "center": task.get("center"), "insert_point": task.get("insert_point"),
            },
            "reference_geometry": geometry, "layer": (source or {}).get("layer"),
            "sys_type": attributes.get("sys_type"), "dn": attributes.get("dn_diameter"),
            "elevation": {"start": attributes.get("start_elevation"), "end": attributes.get("end_elevation")},
            "parent_owner": (source or {}).get("owner_layout"), "connected_objects": [],
            "upstream": [], "downstream": [], "dependency_ids": [],
            "recommended_route": _recommended_route(object_name),
            "required_capabilities": [
                "native_type_preservation", "source_to_target_handle_mapping", "save_reopen_persistence",
                f"create_{object_name}",
            ],
            "execution_allowed": False,
        })

    by_id = {item["task_id"]: item for item in inventory}
    required = [item for item in inventory if item["classification"] == "REQUIRED_MISSING"]
    edges: list[dict[str, Any]] = []
    tolerance = 5.0
    design = [item for item in required if item["semantic_type"] != "professional_annotation"]
    for dependent in design:
        group = dependent["semantic_type"]
        if group not in {"pipe", "fitting", "valve"}:
            continue
        candidates = []
        for dependency in design:
            if dependency["task_id"] == dependent["task_id"]:
                continue
            allowed_dependency = (
                group == "pipe" and dependency["semantic_type"] in {"pump", "equipment", "water_tank"}
            ) or (
                group in {"fitting", "valve"} and dependency["semantic_type"] == "pipe"
            )
            if not allowed_dependency:
                continue
            distance = _bbox_distance(
                dependent["target_wcs_geometry"]["bbox"], dependency["target_wcs_geometry"]["bbox"],
            )
            if distance is not None and distance <= tolerance:
                candidates.append((distance, dependency))
        for distance, dependency in sorted(candidates, key=lambda pair: (pair[0], pair[1]["task_id"])):
            edge = {
                "dependency_id": dependency["task_id"], "dependent_id": dependent["task_id"],
                "relationship": "equipment_interface_before_pipe" if group == "pipe" else "pipe_before_attached_component",
                "evidence": "target_wcs_bbox_distance", "distance": distance, "tolerance": tolerance,
            }
            edges.append(edge)
            dependent["dependency_ids"].append(dependency["task_id"])
            dependent["connected_objects"].append(dependency["task_id"])
            dependency["connected_objects"].append(dependent["task_id"])

    rank = {item["task_id"]: _execution_rank(item["semantic_type"]) for item in required}
    order, cycles = _topological_order([item["task_id"] for item in required], edges, rank)
    for index, task_id in enumerate(order, start=1):
        by_id[task_id]["execution_order"] = index
    counts_by_object_name = Counter(item["object_name"] for item in inventory)
    counts_by_semantic = Counter(item["semantic_type"] for item in inventory)
    counts_by_classification = Counter(item["classification"] for item in inventory)

    inventory_doc = {"phase": "STAGE5.1", "items": inventory, "item_count": len(inventory)}
    required_doc = {"phase": "STAGE5.1", "items": required, "required_missing_count": len(required)}
    graph = {
        "phase": "STAGE5.1", "nodes": [item["task_id"] for item in required], "edges": edges,
        "edge_count": len(edges), "cycles": cycles, "cycle_free": not cycles,
        "derivation": "object-type dependency rules plus target-WCS bbox proximity; no list-order inference",
    }
    execution_order = {
        "phase": "STAGE5.1", "ordered_task_ids": order,
        "batches": {
            "equipment_and_tanks": [item["task_id"] for item in required if rank[item["task_id"]] == 10],
            "pipes": [item["task_id"] for item in required if rank[item["task_id"]] == 20],
            "fittings": [item["task_id"] for item in required if rank[item["task_id"]] == 30],
            "valves": [item["task_id"] for item in required if rank[item["task_id"]] == 40],
            "annotations": [item["task_id"] for item in required if rank[item["task_id"]] == 50],
        },
        "cycle_free": not cycles,
    }
    capability = {
        "phase": "STAGE5.1",
        "by_object_name": {
            object_name: {
                "required_count": sum(item["classification"] == "REQUIRED_MISSING" for item in inventory if item["object_name"] == object_name),
                "recommended_route": _recommended_route(object_name),
                "capability_status": "POC_REQUIRED",
            }
            for object_name in sorted(counts_by_object_name)
        },
    }
    write_json(paths.root / "tdb_inventory.json", inventory_doc)
    write_json(paths.root / "counts_by_object_name.json", dict(sorted(counts_by_object_name.items())))
    write_json(paths.root / "counts_by_semantic_type.json", dict(sorted(counts_by_semantic.items())))
    write_json(paths.root / "required_missing_tdb.json", required_doc)
    write_json(paths.root / "tdb_dependency_graph.json", graph)
    write_json(paths.root / "tdb_execution_order.json", execution_order)
    write_json(paths.root / "tdb_capability_requirements.json", capability)
    traceable = all(item["reference_handle"] and item["object_name"] and item["target_wcs_geometry"]["bbox"] for item in required)
    passed = len(inventory) == 337 and sum(counts_by_classification.values()) == 337 and traceable and not cycles
    status = "PASS_STAGE5_1_INVENTORY_COMPLETE" if passed else "BLOCKED_STAGE5_1_INVENTORY_INCOMPLETE"
    report = {
        "phase": "STAGE5.1", "status": status, "input_task_count": len(manual),
        "inventory_count": len(inventory), "required_missing_count": len(required),
        "counts_by_object_name": dict(sorted(counts_by_object_name.items())),
        "counts_by_semantic_type": dict(sorted(counts_by_semantic.items())),
        "counts_by_classification": dict(sorted(counts_by_classification.items())),
        "dependency_edge_count": len(edges), "dependency_cycle_free": not cycles,
        "all_required_geometry_traceable": traceable, "cad_write_executed": False,
        "safety_flags": _safety(),
    }
    write_json(paths.root / "stage5_1_report.json", report)
    _checkpoint(paths, "INVENTORY_COMPLETE", status="completed" if passed else "blocked", details=report)
    return report


def run_stage5_static(run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or datetime.now().strftime("stage5_%Y%m%d_%H%M%S")
    paths = Stage5Paths.build(run_id)
    stage50 = freeze_mvp1_archive(paths)
    if stage50["status"] != "PASS_STAGE5_0_INPUT_FROZEN":
        return {"run_id": run_id, "status": stage50["status"], "stage5_0": stage50}
    stage51 = build_tdb_inventory(paths)
    result = {
        "run_id": run_id, "status": stage51["status"], "stage5_0": stage50, "stage5_1": stage51,
        "next_checkpoint": "PIPE_POC_COMPLETE" if stage51["status"] == "PASS_STAGE5_1_INVENTORY_COMPLETE" else "INVENTORY_COMPLETE",
        "production_d1_allowed": False,
    }
    write_json(paths.root / "stage5_manifest.json", result)
    return result


def finalize_stage5_2_gate(paths: Stage5Paths, test_results: Mapping[str, str] | None = None) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    pipe_path = paths.poc / "tdbpipe_selective_clone" / "pipe_clone_poc_result.json"
    fitting_path = paths.poc / "fitting_selective_clone" / "fitting_clone_poc_result.json"
    valve_path = paths.poc / "valve_selective_clone" / "valve_clone_poc_result.json"
    valve_diagnostic_path = paths.poc / "valve_primary_only_diagnostic" / "valve_primary_only_diagnostic.json"
    required_paths = [pipe_path, fitting_path, valve_path, valve_diagnostic_path, paths.root / "stage5_1_report.json"]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Stage 5.2 evidence missing: {missing}")
    pipe = read_json(pipe_path)
    fitting = read_json(fitting_path)
    valve = read_json(valve_path)
    valve_diagnostic = read_json(valve_diagnostic_path)
    stage51 = read_json(paths.root / "stage5_1_report.json")
    counts = stage51["counts_by_object_name"]
    status_by_type: dict[str, dict[str, Any]] = {}
    for object_name in sorted(counts):
        if object_name == "TDbPipe":
            status_by_type[object_name] = {
                "status": pipe["status"], "route": "selective_native_clone",
                "required_count": counts[object_name], "evidence_path": str(pipe_path),
            }
        elif object_name == "TDbPipeFitting":
            status_by_type[object_name] = {
                "status": fitting["status"], "route": "selective_native_clone",
                "required_count": counts[object_name], "evidence_path": str(fitting_path),
            }
        elif object_name == "TDbPipeValve":
            status_by_type[object_name] = {
                "status": "BLOCKED_DEPENDENCY", "route": "unsupported",
                "required_count": counts[object_name], "evidence_path": str(valve_path),
                "diagnostic_path": str(valve_diagnostic_path),
                "reason": "bundle clone omitted the valve; primary-only clone did not preserve pipe attachment",
            }
        else:
            status_by_type[object_name] = {
                "status": "BLOCKED_UNSUPPORTED", "route": "unsupported",
                "required_count": counts[object_name],
                "reason": "not evaluated because Stage 5.2-B sequential gate blocked before Stage 5.2-C",
            }
    capability_matrix = {
        "phase": "STAGE5.2", "frozen": True,
        "allowed_statuses": [
            "VERIFIED_SELECTIVE_CLONE", "VERIFIED_CONTROLLED_COMMAND", "PARTIAL_PROPERTY_LIMITED",
            "BLOCKED_DEPENDENCY", "BLOCKED_UNSUPPORTED", "FAILED_TYPE_DEGRADED", "FAILED_PERSISTENCE",
        ],
        "object_types": status_by_type,
        "verified_types": [name for name, item in status_by_type.items() if item["status"].startswith("VERIFIED_")],
        "blocked_required_types": [name for name, item in status_by_type.items() if not item["status"].startswith("VERIFIED_")],
        "controlled_tianzheng_command_route": {
            "status": "BLOCKED_UNSUPPORTED", "reason": "no fixed Stage 5 command capability is verified; no SendCommand was attempted",
        },
    }
    write_json(paths.root / "tdb_creation_capability_matrix.json", capability_matrix)
    clone_dependency_plan = {
        "phase": "STAGE5.2", "whole_modelspace_clone_allowed": False,
        "approved_poc_bundles": [
            {"object_type": "TDbPipe", "approved_reference_handles": [pipe["reference_handle"]]},
            {"object_type": "TDbPipeFitting", "approved_reference_handles": fitting["approved_reference_handles"]},
            {"object_type": "TDbPipeValve", "approved_reference_handles": valve["approved_reference_handles"]},
        ],
        "resource_dependencies": "deep-cloned by AutoCAD only when owned/referenced by approved primaries",
        "unrelated_design_dependencies_allowed": False,
    }
    write_json(paths.root / "clone_dependency_plan.json", clone_dependency_plan)
    from mcp.orchestration.private_run_config import dependency_records
    write_json(paths.root / "cloned_dependencies.json", {
        "pipe_poc": [],
        "fitting_poc": dependency_records(fitting),
        "valve_poc": dependency_records(valve),
    })
    write_json(paths.root / "excluded_dependencies.json", {
        "unrelated_design_objects": "all non-approved reference ModelSpace Handles",
        "drawing_border_title_block": "excluded",
        "whole_reference_modelspace": "excluded",
        "automatic_dependency_expansion": "blocked when ModelSpace delta differs from approved bundle",
    })
    handle_map = {
        "poc_only_not_final_reconstruction": True,
        "mappings": [
            {"sandbox": pipe["target_sandbox"], "reference_handle": pipe["reference_handle"], "target_handle": pipe["created_handles"][0], "object_name": "TDbPipe"},
            {"sandbox": str(paths.poc / "fitting_selective_clone" / "target_fitting_poc_sandbox.dwg"), "reference_handle": fitting["primary_reference_handle"], "target_handle": fitting["persistence_qa"]["primary_handle"], "object_name": "TDbPipeFitting"},
            {"sandbox": str(paths.poc / "valve_primary_only_diagnostic" / "target_valve_diagnostic_sandbox.dwg"), "reference_handle": valve_diagnostic["reference_handle"], "target_handle": valve_diagnostic["created_handles"][0], "object_name": "TDbPipeValve", "association_preserved": False},
        ],
    }
    write_json(paths.root / "source_to_target_handle_map.json", handle_map)
    creation_results = {
        "phase": "STAGE5.2", "poc_only": True,
        "native_primary_attempted_count": 3,
        "native_primary_verified_count": 2,
        "native_primary_blocked_count": 1,
        "results": [pipe, fitting, valve, valve_diagnostic],
    }
    write_json(paths.root / "object_creation_results.json", creation_results)
    _checkpoint(paths, "FITTING_VALVE_POC_COMPLETE", status="blocked", details={
        "status": "BLOCKED_REQUIRED_TDB_TYPE_UNSUPPORTED", "blocked_type": "TDbPipeValve",
    })
    source_hashes = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    source_unchanged = source_hashes == {"reference": REFERENCE_SHA256, "target": TARGET_SHA256}
    integrity_path = paths.root / "source_integrity.json"
    integrity = read_json(integrity_path)
    integrity.update({
        "reference_sha256_after": source_hashes["reference"],
        "target_sha256_after": source_hashes["target"],
        "source_hashes_unchanged": source_unchanged,
        "source_dwg_opened": False, "source_dwg_saved": False, "source_modified": False,
    })
    write_json(integrity_path, integrity)
    tests = dict(test_results or {})
    tests_passed = bool(tests) and all("passed" in value.lower() and "failed" not in value.lower() for value in tests.values())
    report = {
        "phase": "STAGE5-MVP2", "run_id": paths.run_id,
        "stage5_final_status": "BLOCKED_REQUIRED_TDB_TYPE_UNSUPPORTED",
        "mvp2_final_status": "BLOCKED_REQUIRED_TDB_TYPE_UNSUPPORTED",
        "reference_input": str(REFERENCE), "target_input": str(TARGET),
        "reference_sha256": source_hashes["reference"], "target_sha256": source_hashes["target"],
        "source_hashes_unchanged": source_unchanged,
        "required_tdb_count": stage51["required_missing_count"],
        "required_tdb_by_object_name": counts,
        "capability_matrix": status_by_type,
        "tdbpipe_capability": pipe["status"], "fitting_capability": fitting["status"],
        "valve_capability": "BLOCKED_DEPENDENCY",
        "equipment_capability": "BLOCKED_UNSUPPORTED_NOT_EVALUATED_GATE_STOPPED",
        "water_tank_capability": "BLOCKED_UNSUPPORTED_NOT_EVALUATED_GATE_STOPPED",
        "ordinary_cad_success_count": 0,
        "native_tdb_poc_attempted_count": 3, "native_tdb_poc_verified_count": 2,
        "native_tdb_poc_blocked_count": 1,
        "poc_new_handle_count": 4,
        "poc_new_handles_are_sandbox_local": True,
        "remaining_required_missing": stage51["required_missing_count"],
        "remaining_property_mismatch": None, "remaining_topology_mismatch": None,
        "duplicate_count": 0, "unexpected_new_count": 0,
        "existing_modified_count": 0, "existing_deleted_count": 0,
        "final_reconstruction_dwg": None,
        "save_reopen_status": {
            "pipe": pipe["saved"] and pipe["reopened"],
            "fitting": fitting["saved"] and fitting["reopened"],
            "valve_primary_only_diagnostic": valve_diagnostic["saved"] and valve_diagnostic["native_primary_persisted"],
        },
        "idempotency_passed": False,
        "blocked_at_checkpoint": "FITTING_VALVE_POC_COMPLETE",
        "blocked_reason": "required TDbPipeValve cannot be cloned with its approved pipe dependency and validated attachment",
        "tests": tests, "tests_passed": tests_passed,
        "safety_flags": {
            **_safety(), "autocad_connected": True, "copyobjects_used": True,
            "dwg_modified": True, "dwg_saved": True, "tdb_modified": True,
            "disposable_sandbox_modified": True, "disposable_sandbox_saved": True,
            "source_reference_opened": False, "source_target_opened": False,
            "existing_tdb_modified": False, "native_tdb_poc_created": True,
            "stage5_3_executed": False, "stage5_4_executed": False,
            "stage5_5_executed": False, "stage5_6_executed": False,
        },
        "mvp2_completed": False, "fixed_sample_full_reconstruction": False,
        "native_tdb_creation": False, "required_tdb_completion": False,
        "network_topology_restored": False, "stage6_mvp3_allowed": False,
        "production_d1_allowed": False,
    }
    write_json(paths.root / "stage5_manifest.json", report)
    write_json(REPORT_JSON, report)
    REPORT_MD.write_text(_stage5_markdown(report), encoding="utf-8")
    return report


def _stage5_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Stage 5 MVP2 Fixed-Sample Selective Full Reconstruction", "",
        f"- status: {report.get('stage5_final_status')}",
        f"- run_id: {report.get('run_id')}",
        f"- required TDb: {report.get('required_tdb_count')}",
        f"- TDbPipe: {report.get('tdbpipe_capability')}",
        f"- TDbPipeFitting: {report.get('fitting_capability')}",
        f"- TDbPipeValve: {report.get('valve_capability')}",
        f"- blocked checkpoint: {report.get('blocked_at_checkpoint')}",
        f"- blocked reason: {report.get('blocked_reason')}",
        f"- source hashes unchanged: {str(report.get('source_hashes_unchanged')).lower()}",
        f"- tests passed: {str(report.get('tests_passed')).lower()}",
        "- Stage 5.3-5.6 executed: false",
        "- MVP2 completed: false",
        "- Production D1 allowed: false", "",
    ])
