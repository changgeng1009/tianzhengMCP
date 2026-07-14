from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from mcp.acceptance.stage3_1_runtime import sha256_file
from mcp.acceptance.stage3_3_controlled_repair import source_lock_files


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "artifacts" / "stage5_1"
REPORT_JSON = ROOT / "reports" / "stage5_1_mvp2_native_full_reconstruction.json"
REPORT_MD = ROOT / "reports" / "stage5_1_mvp2_native_full_reconstruction.md"

REFERENCE = ROOT / "artifacts" / "stage3_1_r1" / "stage3_1_r1_20260711_002112" / "copies" / "reference_working_copy.dwg"
TARGET = Path(r"E:\SampleDrawings\target_sample.dwg")
REFERENCE_SHA256 = None  # External run configuration required; no bundled private default.
TARGET_SHA256 = None  # External run configuration required; no bundled private default.
TRANSLATION = None  # External run configuration required; no bundled private default.

PRIOR_RUN = ROOT / "artifacts" / "stage5" / "stage5_20260711_141525"
PRIOR_REPORT = ROOT / "reports" / "stage5_mvp2_full_reconstruction.json"
PRIOR_MATRIX = PRIOR_RUN / "tdb_creation_capability_matrix.json"
PRIOR_HANDLE_MAP = PRIOR_RUN / "source_to_target_handle_map.json"
PRIOR_INVENTORY = PRIOR_RUN / "tdb_inventory.json"
PRIOR_REQUIRED = PRIOR_RUN / "required_missing_tdb.json"
ALLOWED_POLICY = PRIOR_RUN / "allowed_difference_policy.json"

CHECKPOINTS = (
    "INPUT_AND_HISTORY_FROZEN", "RELATIONSHIP_GRAPH_COMPLETE", "COMPONENTS_COMPLETE",
    "VALVE_RELATIONSHIP_VERIFIED", "CAPABILITY_MATRIX_COMPLETE", "PLAN_FROZEN",
    "FULL_RECONSTRUCTION_COMPLETE", "TOPOLOGY_QA_COMPLETE", "PROPERTY_QA_COMPLETE",
    "PERSISTENCE_QA_COMPLETE", "CONVERGENCE_COMPLETE", "IDEMPOTENCY_COMPLETE", "FINALIZED",
)


@dataclass(frozen=True)
class Stage51Paths:
    run_id: str
    root: Path
    archive: Path
    input: Path
    copies: Path
    scans: Path
    relationships: Path
    components: Path
    capabilities: Path
    plans: Path
    execution: Path
    topology: Path
    properties: Path
    annotations: Path
    convergence: Path
    qa: Path
    previews: Path
    reports: Path

    @classmethod
    def build(cls, run_id: str) -> "Stage51Paths":
        root = RUNS_ROOT / run_id
        names = (
            "archive", "input", "copies", "scans", "relationships", "components", "capabilities",
            "plans", "execution", "topology", "properties", "annotations", "convergence", "qa", "previews", "reports",
        )
        values = [root / name for name in names]
        return cls(run_id, root, *values)

    def create(self) -> None:
        for path in self.__dict__.values():
            if isinstance(path, Path):
                path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _json_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()), "sha256": sha256_file(path), "size": stat.st_size,
        "modified_time": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
    }


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def safety_flags() -> dict[str, bool]:
    return {
        "source_reference_opened": False, "source_target_opened": False,
        "source_reference_saved": False, "source_target_saved": False, "source_modified": False,
        "saveas_used": False, "whole_modelspace_copyobjects_used": False,
        "sendcommand_used": False, "lisp_executed": False, "netload_used": False,
        "external_dll_loaded": False, "automatic_fallback_used": False,
        "new_autocad_instance_created": False, "existing_object_modified": False,
        "existing_object_deleted": False, "mvp3_executed": False, "production_d1_allowed": False,
    }


def checkpoint(paths: Stage51Paths, name: str, *, status: str = "completed", details: Mapping[str, Any] | None = None) -> None:
    if name not in CHECKPOINTS:
        raise ValueError(f"unknown Stage 5.1 checkpoint: {name}")
    path = paths.root / "checkpoints.json"
    data = read_json(path) if path.is_file() else {
        "run_id": paths.run_id, "completed": [], "current": None, "history": [], "resume_checkpoint": "INPUT_AND_HISTORY_FROZEN",
    }
    if status == "completed" and name not in data["completed"]:
        data["completed"].append(name)
    data["current"] = name
    index = CHECKPOINTS.index(name)
    data["resume_checkpoint"] = CHECKPOINTS[index + 1] if status == "completed" and index + 1 < len(CHECKPOINTS) else name
    data["history"].append({
        "checkpoint": name, "status": status, "at": datetime.now().astimezone().isoformat(), "details": dict(details or {}),
    })
    write_json(path, data)


def freeze_input_and_history(paths: Stage51Paths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    TRANSLATION = require_parameter('stage45.translation', 'translation3')
    paths.create()
    required = [
        REFERENCE, TARGET, PRIOR_REPORT, PRIOR_MATRIX, PRIOR_HANDLE_MAP, PRIOR_INVENTORY, PRIOR_REQUIRED, ALLOWED_POLICY,
        PRIOR_RUN / "poc" / "tdbpipe_selective_clone" / "pipe_clone_poc_result.json",
        PRIOR_RUN / "poc" / "fitting_selective_clone" / "fitting_clone_poc_result.json",
        PRIOR_RUN / "poc" / "valve_selective_clone" / "valve_clone_poc_result.json",
        PRIOR_RUN / "poc" / "valve_primary_only_diagnostic" / "valve_primary_only_diagnostic.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return {"status": "BLOCKED_PRIOR_EVIDENCE_MISSING", "missing_files": missing, "safety_flags": safety_flags()}
    if _same_path(REFERENCE, TARGET):
        raise ValueError("reference and target must be different files")
    locks = {"reference": source_lock_files(REFERENCE), "target": source_lock_files(TARGET)}
    if locks["reference"] or locks["target"]:
        return {"status": "BLOCKED_SOURCE_LOCKED", "source_locks": locks, "safety_flags": safety_flags()}
    reference_hash = sha256_file(REFERENCE)
    target_hash = sha256_file(TARGET)
    if reference_hash != REFERENCE_SHA256 or target_hash != TARGET_SHA256:
        return {
            "status": "BLOCKED_INPUT_HASH_CHANGED", "reference_sha256": reference_hash, "target_sha256": target_hash,
            "safety_flags": safety_flags(),
        }
    prior = read_json(PRIOR_REPORT)
    matrix = read_json(PRIOR_MATRIX)
    evidence = [_file_record(path) for path in required[2:]]
    prior_evidence = {
        "phase": "STAGE5.1-A", "prior_run_id": prior.get("run_id"),
        "prior_status": prior.get("stage5_final_status"), "files": evidence,
        "pipe_capability": prior.get("tdbpipe_capability"),
        "fitting_capability": prior.get("fitting_capability"),
        "valve_capability": prior.get("valve_capability"),
        "prior_evidence_hash": _json_hash(evidence),
    }
    write_json(paths.root / "prior_stage5_evidence.json", prior_evidence)
    write_json(paths.root / "capability_baseline.json", {
        "phase": "STAGE5.1-A", "prior_matrix_sha256": sha256_file(PRIOR_MATRIX),
        "object_types": matrix.get("object_types", {}),
        "frozen_verified_capabilities": {
            "TDbPipe": "VERIFIED_SELECTIVE_CLONE", "TDbPipeFitting": "VERIFIED_SELECTIVE_CLONE",
        },
        "valve_relationship_requires_new_evidence": True,
    })
    input_manifest = {
        "phase": "STAGE5.1-A", "reference": _file_record(REFERENCE), "target": _file_record(TARGET),
        "expected_sha256": {"reference": REFERENCE_SHA256, "target": TARGET_SHA256},
        "input_hashes_match": True, "source_locks": locks,
        "alignment": {"translation": TRANSLATION, "rotation": 0.0, "scale": [1.0, 1.0, 1.0], "fixed_hash_pair_only": True},
    }
    write_json(paths.root / "input_manifest.json", input_manifest)
    write_json(paths.root / "source_integrity.json", {
        "reference_sha256_before": reference_hash, "target_sha256_before": target_hash,
        "source_reference_opened": False, "source_target_opened": False,
        "source_reference_saved": False, "source_target_saved": False, "source_modified": False,
    })
    shutil.copy2(ALLOWED_POLICY, paths.root / "allowed_difference_policy.json")
    reference_copy = paths.copies / "reference_analysis_copy.dwg"
    target_copy = paths.copies / "target_analysis_copy.dwg"
    shutil.copy2(REFERENCE, reference_copy)
    shutil.copy2(TARGET, target_copy)
    copy_manifest = {
        "reference_analysis_copy": _file_record(reference_copy), "target_analysis_copy": _file_record(target_copy),
        "reference_copy_hash_matches_source": sha256_file(reference_copy) == reference_hash,
        "target_copy_hash_matches_source": sha256_file(target_copy) == target_hash,
        "copies_created_by_filesystem": True, "saveas_used": False,
    }
    write_json(paths.copies / "copy_manifest.json", copy_manifest)
    passed = all((
        prior.get("stage5_final_status") == "BLOCKED_REQUIRED_TDB_TYPE_UNSUPPORTED",
        prior.get("source_hashes_unchanged") is True,
        prior.get("tests_passed") is True,
        prior.get("tdbpipe_capability") == "VERIFIED_SELECTIVE_CLONE",
        prior.get("fitting_capability") == "VERIFIED_SELECTIVE_CLONE",
        copy_manifest["reference_copy_hash_matches_source"], copy_manifest["target_copy_hash_matches_source"],
    ))
    status = "PASS_STAGE5_1_A_FROZEN" if passed else "BLOCKED_PRIOR_EVIDENCE_INVALID"
    result = {
        "phase": "STAGE5.1-A", "status": status, "run_id": paths.run_id,
        "reference_sha256": reference_hash, "target_sha256": target_hash,
        "prior_evidence_valid": passed, "analysis_copies_created": True,
        "autocad_connected": False, "dwg_modified": False, "dwg_saved": False,
        "safety_flags": safety_flags(),
    }
    write_json(paths.reports / "checkpoint_a.json", result)
    checkpoint(paths, "INPUT_AND_HISTORY_FROZEN", status="completed" if passed else "blocked", details=result)
    return result


def start_stage51_run(run_id: str | None = None) -> tuple[Stage51Paths, dict[str, Any]]:
    run_id = run_id or datetime.now().strftime("stage5_1_%Y%m%d_%H%M%S")
    paths = Stage51Paths.build(run_id)
    return paths, freeze_input_and_history(paths)


def _tests_passed(results: Mapping[str, str]) -> bool:
    return bool(results) and all("passed" in value.lower() and "failed" not in value.lower() for value in results.values())


def finalize_blocked_capability_gate(paths: Stage51Paths, test_results: Mapping[str, str] | None = None) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.reference_sha256', 'sha256')
    TARGET_SHA256 = require_parameter('mcp.orchestration.stage4_mvp.target_sha256', 'sha256')
    matrix_path = paths.root / "tdb_creation_capability_matrix.json"
    valve_path = paths.root / "valve_relationship_diagnostics.json"
    if not matrix_path.is_file() or not valve_path.is_file():
        raise FileNotFoundError("Stage 5.1 capability evidence is incomplete")
    matrix = read_json(matrix_path)
    valve = read_json(valve_path)
    if matrix.get("status") != "BLOCKED_REQUIRED_TDB_TYPE_UNSUPPORTED":
        raise ValueError("blocked finalizer may only run after the capability gate blocks")
    graph = read_json(paths.root / "reference_tdb_relationship_graph.json")
    components = read_json(paths.root / "minimal_self_contained_components.json")
    prior_required = read_json(PRIOR_REQUIRED).get("items", [])
    blocked_types = matrix["blocked_required_types"]
    verified_valve = next(
        result for result in valve["variant_results"]
        if result["variant_id"] == valve["verified_variant_id"]
    )
    remaining_results = {
        name: item["evidence"] for name, item in matrix["object_types"].items() if "evidence" in item
    }
    valve_maps = [
        pair for pair in verified_valve["copyobjects_mapping"]["idpairs"]
        if pair.get("source_handle") in set(verified_valve["input_reference_handles"])
    ]
    remaining_maps = {
        name: [
            pair for pair in evidence["copyobjects_mapping"]["idpairs"]
            if pair.get("source_handle") in set(evidence["approved_reference_handles"])
        ]
        for name, evidence in remaining_results.items()
    }
    write_json(paths.root / "source_to_target_handle_map.json", {
        "phase": "STAGE5.1", "poc_only": True, "final_execution_map_frozen": False,
        "valve_verified_component": valve_maps, "remaining_type_pocs": remaining_maps,
        "rule": "PoC sandbox mappings must not be reused as final target mappings",
    })
    write_json(paths.root / "relationship_remap_results.json", {
        "phase": "STAGE5.1", "valve_route": valve["status"],
        "verified_variant_id": valve["verified_variant_id"],
        "all_expected_idpairs_mapped": verified_valve["persistence_qa"]["all_expected_idpairs_mapped"],
        "valve_attachment_verified": verified_valve["persistence_qa"]["relationship_ready"],
        "relationship_source": verified_valve["persistence_qa"]["relationship_evidence_source"],
        "unsafe_xdata_rewrite_used": False, "guessed_handle_used": False,
    })
    write_json(paths.root / "final_required_tdb.json", {
        "phase": "STAGE5.1-F", "status": "NOT_FROZEN_CAPABILITY_GATE_BLOCKED",
        "candidate_count": len(prior_required), "items": prior_required,
        "execution_allowed": False, "blocked_required_types": blocked_types,
    })
    write_json(paths.root / "frozen_execution_plan.json", {
        "phase": "STAGE5.1-F", "status": "NOT_CREATED_CAPABILITY_GATE_BLOCKED",
        "tasks": [], "components": [], "plan_sha256": None, "execution_allowed": False,
        "blocked_required_types": blocked_types,
    })
    poc_results = [result for result in valve["variant_results"] if result["saved"]] + list(remaining_results.values())
    poc_created_count = sum(result["actual_new_handle_count"] for result in poc_results)
    write_json(paths.root / "object_creation_results.json", {
        "phase": "STAGE5.1-POC", "poc_only": True,
        "attempted_package_count": len(valve["variant_results"]) + len(remaining_results),
        "saved_poc_package_count": len(poc_results), "poc_created_handle_count": poc_created_count,
        "full_reconstruction_attempted_count": 0, "full_reconstruction_success_count": 0,
        "results": poc_results,
    })
    write_json(paths.root / "component_execution_results.json", {
        "phase": "STAGE5.1-G", "status": "NOT_EXECUTED_CAPABILITY_GATE_BLOCKED",
        "approved_component_count": 0, "attempted_component_count": 0,
        "successful_component_count": 0, "failed_component_count": 0,
    })
    topology_qa = {
        "phase": "STAGE5.1-H", "status": "NOT_EXECUTED_CAPABILITY_GATE_BLOCKED",
        "valve_poc_attachment_verified": True,
        "full_network_topology_verified": False,
        "required_node_match_rate": None, "required_edge_match_rate": None,
        "valve_attachment_match_rate": None, "fitting_degree_match_rate": None,
        "equipment_connection_match_rate": None, "tank_connection_match_rate": None,
    }
    property_qa = {
        "phase": "STAGE5.1-I", "status": "BLOCKED_REQUIRED_FIELD_UNREADABLE",
        "blocked_required_types": blocked_types,
        "required_field_results": {
            name: evidence["persistence_qa"]["required_field_results"] for name, evidence in remaining_results.items()
        },
        "full_object_property_match_rate": None,
    }
    persistence_qa = {
        "phase": "STAGE5.1-J", "status": "POC_ONLY_FULL_RECONSTRUCTION_NOT_EXECUTED",
        "saved_poc_package_count": len(poc_results),
        "all_saved_poc_native_types_persisted": all(result["persistence_qa"]["core_passed"] if "core_passed" in result["persistence_qa"] else result["persistence_qa"]["passed"] for result in poc_results),
        "final_sandbox_saved": False, "final_sandbox_reopened": False,
    }
    write_json(paths.root / "topology_qa.json", topology_qa)
    write_json(paths.root / "property_qa.json", property_qa)
    write_json(paths.root / "persistence_qa.json", persistence_qa)
    write_json(paths.root / "final_convergence.json", {
        "phase": "STAGE5.1-K", "status": "NOT_EXECUTED_CAPABILITY_GATE_BLOCKED",
        "remaining_required_missing": len(prior_required),
        "remaining_property_mismatch": None, "remaining_type_mismatch": None,
        "remaining_topology_mismatch": None, "duplicate_count": 0, "unexpected_new_count": 0,
    })
    write_json(paths.root / "idempotency_qa.json", {
        "phase": "STAGE5.1-L", "status": "NOT_EXECUTED_CAPABILITY_GATE_BLOCKED",
        "idempotency_passed": False, "second_pass_task_count": None,
    })
    source_hashes = {"reference": sha256_file(REFERENCE), "target": sha256_file(TARGET)}
    source_unchanged = source_hashes == {"reference": REFERENCE_SHA256, "target": TARGET_SHA256}
    integrity_path = paths.root / "source_integrity.json"
    integrity = read_json(integrity_path)
    integrity.update({
        "reference_sha256_after": source_hashes["reference"], "target_sha256_after": source_hashes["target"],
        "source_hashes_unchanged": source_unchanged,
        "source_reference_opened": False, "source_target_opened": False,
        "source_reference_saved": False, "source_target_saved": False, "source_modified": False,
    })
    write_json(integrity_path, integrity)
    tests = dict(test_results or {})
    tests_ok = _tests_passed(tests)
    report = {
        "phase": "STAGE5.1-MVP2-NATIVE-RELATIONSHIP-AWARE", "run_id": paths.run_id,
        "stage5_1_final_status": "BLOCKED_REQUIRED_TDB_TYPE_UNSUPPORTED",
        "mvp2_final_status": "BLOCKED_REQUIRED_TDB_TYPE_UNSUPPORTED",
        "reference_input": str(REFERENCE), "target_input": str(TARGET),
        "reference_sha256": source_hashes["reference"], "target_sha256": source_hashes["target"],
        "source_hashes_unchanged": source_unchanged,
        "required_tdb_count": len(prior_required),
        "relationship_node_count": graph["node_count"], "relationship_edge_count": graph["edge_count"],
        "minimal_component_count": components["component_count"],
        "valve_relationship_route": "relationship_aware_component_clone",
        "valve_relationship_status": valve["status"],
        "valve_verified_variant_id": valve["verified_variant_id"],
        "capability_matrix": matrix["object_types"], "blocked_required_types": blocked_types,
        "full_attempted_count": 0, "full_success_count": 0, "full_failed_count": 0,
        "poc_new_handle_count": poc_created_count, "poc_handles_are_disposable_only": True,
        "object_name_match": "POC_PASS_FULL_NOT_RUN", "sys_type_dn_geometry_match": "POC_PARTIAL_FULL_NOT_RUN",
        "valve_attachment": "POC_VERIFIED_COMPONENT_CLONE",
        "fitting_degree": "FULL_NOT_RUN", "equipment_tank_interfaces": "POC_INTERFACE_ONLY_REQUIRED_FIELDS_UNREADABLE",
        "professional_annotation_relationships": "PARTIAL_VISUAL_ONLY_REQUIRED_FIELDS_UNREADABLE",
        "topology_qa": topology_qa, "property_qa": property_qa,
        "remaining_required_missing": len(prior_required),
        "remaining_property_mismatch": None, "remaining_type_mismatch": None, "remaining_topology_mismatch": None,
        "duplicate_count": 0, "unexpected_new_count": 0,
        "existing_modified_count": 0, "existing_deleted_count": 0,
        "final_sandbox_saved": False, "final_sandbox_reopened": False,
        "native_types_and_relationships_persisted": "POC_ONLY",
        "idempotency_passed": False,
        "final_reconstruction_dwg": None, "drafting_variant_dwg": None,
        "blocked_at_checkpoint": "CAPABILITY_MATRIX_COMPLETE",
        "blocked_reason": "required device and annotation fields are unreadable; six required ObjectName types remain PARTIAL_VISUAL_ONLY",
        "tests": tests, "tests_passed": tests_ok,
        "safety_flags": {
            **safety_flags(), "autocad_connected": True, "selective_copyobjects_used": True,
            "disposable_sandboxes_modified": True, "disposable_sandboxes_saved": True,
            "source_reference_opened": False, "source_target_opened": False,
            "full_reconstruction_executed": False, "drafting_variant_created": False,
        },
        "mvp2_completed": False, "fixed_sample_full_reconstruction": False,
        "native_tdb_creation": False, "native_tdb_relationships_restored": False,
        "pipe_network_topology_restored": False, "equipment_connections_restored": False,
        "professional_annotations_restored": False, "mvp3_allowed": False,
        "production_d1_allowed": False,
    }
    write_json(paths.root / "stage5_1_manifest.json", report)
    write_json(REPORT_JSON, report)
    REPORT_MD.write_text(_blocked_markdown(report), encoding="utf-8")
    return report


def _blocked_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Stage 5.1 MVP2 Native TDb Relationship-Aware Full Reconstruction", "",
        f"- status: {report.get('stage5_1_final_status')}",
        f"- run_id: {report.get('run_id')}",
        f"- required TDb: {report.get('required_tdb_count')}",
        f"- relationship graph: {report.get('relationship_node_count')} nodes / {report.get('relationship_edge_count')} edges",
        f"- minimal components: {report.get('minimal_component_count')}",
        f"- valve: {report.get('valve_relationship_status')} via {report.get('valve_verified_variant_id')}",
        f"- blocked types: {', '.join(report.get('blocked_required_types', []))}",
        f"- blocked checkpoint: {report.get('blocked_at_checkpoint')}",
        f"- source hashes unchanged: {str(report.get('source_hashes_unchanged')).lower()}",
        f"- tests passed: {str(report.get('tests_passed')).lower()}",
        "- full reconstruction executed: false",
        "- MVP2 completed: false",
        "- MVP3 allowed: false",
        "- Production D1 allowed: false", "",
    ])
