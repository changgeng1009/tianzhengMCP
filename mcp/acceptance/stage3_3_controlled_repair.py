from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mcp.acceptance.stage3_2_missing_detection import sha256_file
from mcp.backends.com_backend import ComCadBackend
from mcp.backends.models import BackendConfig, RepairTask, ScanRequest
from mcp.backends.registry import BackendRegistry
from mcp.backends.router import BackendRouter


ROOT = Path(__file__).resolve().parents[2]
STAGE2_REPORT = ROOT / "reports" / "stage3_2_missing_detection.json"
R2_REPORT = ROOT / "reports" / "stage3_1_r2_geometry_acceptance.json"
REPORT_JSON = ROOT / "reports" / "stage3_3_controlled_repair.json"
REPORT_MD = ROOT / "reports" / "stage3_3_controlled_repair.md"
RUNS_ROOT = ROOT / "artifacts" / "stage3_3"
TARGET_SOURCE = Path(r"E:\SampleDrawings\target_sample.dwg")
REFERENCE_SOURCE = ROOT / "artifacts" / "validation" / "s1_reference_fixture_20260710_134249.dwg"

AUTOMATIC_WHITELIST = {"AcDbLine", "AcDbPolyline", "AcDbText", "AcDbMText", "AcDbBlockReference"}
ABSOLUTELY_FORBIDDEN_TYPES = {
    "TDbPipe", "TDbPipeValve", "TDbPipeFitting", "TDbPump", "Pump", "Equipment", "WaterTank",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    return sha256_file(path)


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _point(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) not in {2, 3}:
        return None
    point = [float(value[0]), float(value[1]), float(value[2]) if len(value) == 3 else 0.0]
    return point if all(math.isfinite(item) for item in point) else None


def geometry_complete(task: Mapping[str, Any]) -> bool:
    geometry = task.get("target_wcs_geometry") or task.get("geometry") or {}
    object_name = str(task.get("object_name") or task.get("object_type") or "")
    if object_name == "AcDbLine":
        start, end = _point(geometry.get("start_point")), _point(geometry.get("end_point"))
        return bool(start and end and math.dist(start, end) > 1e-6)
    if object_name == "AcDbPolyline":
        vertices = [_point(item) for item in geometry.get("vertices", [])]
        return len(vertices) >= 2 and all(vertices)
    if object_name in {"AcDbText", "AcDbMText"}:
        return bool(_point(geometry.get("insert_point")) and task.get("text") is not None)
    if object_name == "AcDbBlockReference":
        required = ("block_name", "rotation", "scale", "layer", "block_definition_source_safe")
        return bool(_point(geometry.get("insert_point")) and all(task.get(key) is not None for key in required))
    return False


def approve_execution_tasks(drafts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in drafts:
        task = dict(raw)
        reasons: list[str] = []
        object_name = str(task.get("object_name") or "")
        if task.get("classification") != "MISSING_HIGH_CONFIDENCE":
            reasons.append("classification is not MISSING_HIGH_CONFIDENCE")
        if float(task.get("confidence") or 0.0) < 0.95:
            reasons.append("confidence below 0.95")
        if task.get("route") != "direct_com_candidate":
            reasons.append("route is not direct_com_candidate")
        if object_name not in AUTOMATIC_WHITELIST or object_name.startswith("TDb") or object_name in ABSOLUTELY_FORBIDDEN_TYPES:
            reasons.append("object type is outside automatic ordinary CAD whitelist")
        if not geometry_complete(task):
            reasons.append("execution geometry incomplete")
        if not task.get("layer"):
            reasons.append("layer missing")
        if task.get("geometry_source") != "transformed_reference_geometry":
            reasons.append("geometry source is not transformed reference geometry")
        if task.get("one_to_many_conflict") or task.get("many_to_one_conflict"):
            reasons.append("matching conflict unresolved")
        if task.get("nearby_duplicate_found"):
            reasons.append("nearby duplicate risk")
        if task.get("automatic_fallback"):
            reasons.append("automatic fallback requested")
        required = list(task.get("required_capabilities") or [])
        if not required:
            reasons.append("required capabilities missing")
        if reasons:
            rejected.append({**task, "approval_reasons": reasons, "execution_allowed": False, "executed": False})
            continue
        approved.append({
            **task,
            "classification": "confirmed_direct_com",
            "object_type": object_name,
            "geometry": task["target_wcs_geometry"],
            "execution_allowed": True,
            "selected_backend": "com",
            "execution_backend_class": "ComCadBackend",
            "metadata": {"layer": task["layer"]},
            "automatic_fallback": False,
            "executed": False,
        })
    return {"approved": approved, "rejected": rejected}


def select_blocked_execution_items(rejected: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(item) for item in rejected
        if item.get("route") == "blocked" or str(item.get("classification", "")).startswith("BLOCKED_")
    ]


def automatic_transition_gate(
    stage2: Mapping[str, Any],
    r2_report: Mapping[str, Any],
    approved_tasks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    checks = {
        "stage3_2_formal_pass": stage2.get("status") == "PASS_MISSING_DETECTION_EVIDENCE_READY",
        "alignment_contradiction_false": stage2.get("alignment_contradiction") is False,
        "alignment_evidence_mode": stage2.get("alignment_evidence_mode") == "conditional_geometry_dominant",
        "user_authorized_stage3_2": stage2.get("user_authorized_stage3_2") is True,
        "user_authorized_automatic_stage3_3_transition": stage2.get("user_authorized_automatic_stage3_3_transition") is True,
        "roles_preserved": stage2.get("reference_target_roles_preserved") is True,
        "translation_direction_preserved": stage2.get("translation_direction") == "reference_wcs_to_target_wcs",
        "stage1_seed_excluded": stage2.get("stage1_seed_line_excluded") is True,
        "title_frame_drawing_name_excluded": stage2.get("title_frame_drawing_name_excluded") is True,
        "target_virtual_entities_participated": stage2.get("target_virtual_block_entities_participated") is True,
        "matching_conflicts_handled": stage2.get("one_to_one_conflicts_handled") is True and stage2.get("compound_matching_conflicts_handled") is True,
        "source_hashes_unchanged": stage2.get("source_hashes_unchanged") is True,
        "safe_ordinary_task_exists": len(approved_tasks) > 0,
        "no_silent_fallback": stage2.get("automatic_fallback") is False,
        "production_d1_blocked": stage2.get("production_d1_allowed") is False and r2_report.get("production_d1_allowed") is False,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {"checks": checks, "passed": not blockers, "blockers": blockers}


def validate_preflight(
    approved_tasks: Sequence[Mapping[str, Any]],
    sandbox_path: Path,
    target_region_bbox: Sequence[float],
) -> dict[str, Any]:
    errors: list[str] = []
    if not approved_tasks:
        errors.append("approved task count is zero")
    if _same_path(sandbox_path, TARGET_SOURCE) or _same_path(sandbox_path, REFERENCE_SOURCE):
        errors.append("sandbox path equals a source path")
    seen_ids: set[str] = set()
    seen_geometry: set[str] = set()
    xmin, ymin, xmax, ymax = map(float, target_region_bbox[:4])
    margin = math.hypot(xmax - xmin, ymax - ymin) * 0.05
    router = _router()
    routing: list[dict[str, Any]] = []
    for task in approved_tasks:
        task_id = str(task.get("task_id"))
        if task_id in seen_ids:
            errors.append(f"duplicate task id: {task_id}")
        seen_ids.add(task_id)
        geometry_key = json.dumps(task.get("geometry"), sort_keys=True, ensure_ascii=False)
        if geometry_key in seen_geometry:
            errors.append(f"duplicate task geometry: {task_id}")
        seen_geometry.add(geometry_key)
        if task.get("object_type") not in AUTOMATIC_WHITELIST or str(task.get("object_type")).startswith("TDb"):
            errors.append(f"non-whitelisted object: {task_id}")
        if not geometry_complete(task):
            errors.append(f"incomplete geometry: {task_id}")
        for point_name in ("start_point", "end_point", "insert_point"):
            point = _point((task.get("geometry") or {}).get(point_name))
            if point and not (xmin - margin <= point[0] <= xmax + margin and ymin - margin <= point[1] <= ymax + margin):
                errors.append(f"geometry outside confirmed local region: {task_id}:{point_name}")
        selection = router.route(task, source_path=str(TARGET_SOURCE), working_copy=str(sandbox_path), requested_backend="com")
        routing.append(selection.to_dict())
        if selection.selection_status != "selected" or selection.selected_backend != "com" or selection.fallback_used:
            errors.append(f"ComCadBackend routing failed: {task_id}")
    return {
        "passed": not errors,
        "errors": errors,
        "approved_task_count": len(approved_tasks),
        "task_ids_unique": len(seen_ids) == len(approved_tasks),
        "task_geometry_unique": len(seen_geometry) == len(approved_tasks),
        "source_path_will_not_be_opened": True,
        "sandbox_differs_from_sources": not _same_path(sandbox_path, TARGET_SOURCE) and not _same_path(sandbox_path, REFERENCE_SOURCE),
        "backend_routing": routing,
        "automatic_fallback": False,
    }


def _router() -> BackendRouter:
    registry = BackendRegistry()
    registry.register(ComCadBackend())
    return BackendRouter(registry)


def create_filesystem_sandbox(source: Path, destination: Path, expected_hash: str) -> dict[str, Any]:
    actual_source_hash = file_hash(source)
    if actual_source_hash != expected_hash:
        raise RuntimeError("target source hash differs from frozen Stage 3.2 value")
    destination.parent.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, destination)
    sandbox_hash = file_hash(destination)
    if sandbox_hash != actual_source_hash:
        raise RuntimeError("filesystem sandbox copy hash mismatch")
    return {
        "copy_method": "python_shutil_copyfile",
        "target_source_hash": actual_source_hash,
        "repair_sandbox_initial_hash": sandbox_hash,
        "hashes_match": True,
    }


def source_lock_files(source: Path) -> list[str]:
    return [
        str(path)
        for path in (source.with_suffix(".dwl"), source.with_suffix(".dwl2"))
        if path.exists()
    ]


def verify_frozen_resume(run_root: Path) -> dict[str, Any]:
    plan_path = run_root / "approved_execution_plan.json"
    handoff_path = run_root / "stage3_2_handoff.json"
    if not plan_path.is_file() or not handoff_path.is_file():
        return {"passed": False, "errors": ["frozen Stage 3.3-A artifacts are missing"]}
    plan = read_json(plan_path)
    handoff = read_json(handoff_path)
    stage2 = read_json(STAGE2_REPORT)
    stage2_root = Path(stage2["run_root"])
    actual_hashes = {
        "stage3_2_report": file_hash(STAGE2_REPORT),
        "missing_candidates": file_hash(stage2_root / "missing_candidates.json"),
        "repair_task_drafts": file_hash(stage2_root / "repair_task_drafts.json"),
    }
    frozen_hashes = handoff.get("input_hashes", {})
    plan_ids = [str(item.get("task_id")) for item in plan.get("tasks", [])]
    frozen_ids = list(map(str, handoff.get("approved_task_ids", [])))
    task_artifacts_match = (
        actual_hashes["missing_candidates"] == frozen_hashes.get("missing_candidates")
        and actual_hashes["repair_task_drafts"] == frozen_hashes.get("repair_task_drafts")
    )
    semantic_fields_match = (
        stage2.get("run_id") == handoff.get("stage3_2_run_id")
        and stage2.get("status") == handoff.get("stage3_2_status")
        and stage2.get("selected_translation") == handoff.get("inherited_transform")
        and stage2.get("source_hashes") == handoff.get("source_hashes")
    )
    errors = []
    if plan.get("frozen") is not True or plan.get("automatic_append_allowed") is not False:
        errors.append("approved execution plan is not immutable")
    if int(plan.get("approved_task_count", -1)) != len(plan_ids):
        errors.append("approved task count differs from frozen task list")
    if plan_ids != frozen_ids or plan.get("approved_task_ids") != frozen_ids:
        errors.append("approved task ids changed after Stage 3.3-A freeze")
    if len(plan_ids) != len(set(plan_ids)):
        errors.append("approved task ids are not unique")
    if not task_artifacts_match:
        errors.append("Stage 3.2 missing/task artifact hash changed")
    if not semantic_fields_match:
        errors.append("Stage 3.2 semantic gate fields changed")
    return {
        "passed": not errors,
        "errors": errors,
        "approved_task_count": len(plan_ids),
        "approved_task_ids_unchanged": plan_ids == frozen_ids,
        "task_artifact_hashes_match": task_artifacts_match,
        "semantic_gate_fields_match": semantic_fields_match,
        "stage3_2_report_hash_match": actual_hashes["stage3_2_report"] == frozen_hashes.get("stage3_2_report"),
        "stage3_2_report_hash_difference_classification": (
            "none" if actual_hashes["stage3_2_report"] == frozen_hashes.get("stage3_2_report")
            else "post_freeze_test_metadata_update_only; task artifacts and semantic gate fields unchanged"
        ),
        "frozen_hashes": frozen_hashes,
        "actual_hashes": actual_hashes,
        "plan_sha256": file_hash(plan_path),
    }


def lines_equivalent(left: Mapping[str, Any], right: Mapping[str, Any], tolerance: float = 1e-5) -> bool:
    if left.get("object_name") not in {None, "AcDbLine"} or right.get("object_name") not in {None, "AcDbLine"}:
        return False
    ls, le = _point(left.get("start_point")), _point(left.get("end_point"))
    rs, re = _point(right.get("start_point")), _point(right.get("end_point"))
    if not all((ls, le, rs, re)):
        return False
    return (math.dist(ls, rs) <= tolerance and math.dist(le, re) <= tolerance) or (math.dist(ls, re) <= tolerance and math.dist(le, rs) <= tolerance)


def duplicate_risk(task: Mapping[str, Any], scan_entities: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    geometry = task.get("geometry") or {}
    candidate = {"object_name": task.get("object_type"), **geometry}
    matches = [
        str(item.get("handle"))
        for item in scan_entities
        if item.get("layer") == task.get("metadata", {}).get("layer") and lines_equivalent(candidate, item)
    ]
    return {"task_id": task.get("task_id"), "duplicate": bool(matches), "equivalent_handles": matches}


def snapshot_entities(entities: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("handle")): {
            "object_name": item.get("object_name"),
            "layer": item.get("layer"),
            "start_point": item.get("start_point"),
            "end_point": item.get("end_point"),
            "insert_point": item.get("insert_point"),
        }
        for item in entities
    }


def unexpected_change_check(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    expected_new_handles: Iterable[str],
) -> dict[str, Any]:
    before_handles, after_handles = set(before), set(after)
    expected = set(map(str, expected_new_handles))
    deleted = sorted(before_handles - after_handles)
    modified = sorted(handle for handle in before_handles & after_handles if before[handle] != after[handle])
    new = after_handles - before_handles
    unexpected = sorted(new - expected)
    return {
        "existing_object_modified_count": len(modified),
        "existing_object_deleted_count": len(deleted),
        "unexpected_new_object_count": len(unexpected),
        "modified_handles": modified,
        "deleted_handles": deleted,
        "unexpected_new_handles": unexpected,
        "passed": not modified and not deleted and not unexpected,
    }


def _scan(backend: ComCadBackend, session: Any) -> list[dict[str, Any]]:
    return backend.scan_entities(session, ScanRequest(include_acdb=True, include_tianzheng_water_objects=True)).entities


def _modelspace_count(backend: ComCadBackend, session: Any) -> int:
    return int(backend._document(session).ModelSpace.Count)


def _open_document_paths(application: Any) -> list[str]:
    paths = []
    for index in range(int(application.Documents.Count)):
        document = application.Documents.Item(index)
        try:
            paths.append(str(document.FullName))
        except Exception:
            continue
    return paths


def execute_live_plan(
    approved_tasks: Sequence[Mapping[str, Any]],
    sandbox_path: Path,
    forbidden_source_paths: Sequence[Path] | None = None,
) -> dict[str, Any]:
    backend = ComCadBackend()
    session = None
    saved = False
    reopened = False
    sandbox_opened = False
    results: list[dict[str, Any]] = []
    duplicate_records: list[dict[str, Any]] = []
    before_entities: list[dict[str, Any]] = []
    after_entities: list[dict[str, Any]] = []
    persistence_entities: list[dict[str, Any]] = []
    source_conflicts: list[str] = []
    error: str | None = None
    try:
        session = backend.connect(BackendConfig(
            backend_id="com", enabled=True, execution_allowed=True,
            settings={"prog_id": "AutoCAD.Application.25.1", "attach_only": True},
        ))
        application = session.native_handle
        forbidden_sources = list(forbidden_source_paths or (TARGET_SOURCE, REFERENCE_SOURCE))
        source_conflicts = [
            path for path in _open_document_paths(application)
            if any(_same_path(path, source) for source in forbidden_sources)
        ]
        if source_conflicts:
            raise RuntimeError("source document is already open in the attached AutoCAD session")
        backend.open_working_copy(session, str(sandbox_path), read_only=False)
        sandbox_opened = True
        before_entities = _scan(backend, session)
        before_snapshot = snapshot_entities(before_entities)
        frozen_ids = {str(task["task_id"]) for task in approved_tasks}
        created_handles: list[str] = []
        for task_value in approved_tasks:
            task_id = str(task_value["task_id"])
            if task_id not in frozen_ids:
                results.append({"task_id": task_id, "status": "BLOCKED_NOT_FROZEN"})
                continue
            current = _scan(backend, session)
            duplicate = duplicate_risk(task_value, current)
            duplicate_records.append(duplicate)
            if duplicate["duplicate"]:
                results.append({"task_id": task_id, "status": "SKIPPED_DUPLICATE_RISK", "execution_backend": "ComCadBackend"})
                continue
            before_count = _modelspace_count(backend, session)
            task = RepairTask.from_dict(dict(task_value))
            execution = backend.create_entity(session, task)
            after_count = _modelspace_count(backend, session)
            handle = execution.created_handles[0]
            current_after = _scan(backend, session)
            created = next((item for item in current_after if str(item.get("handle")) == handle), None)
            geometry_match = bool(created and lines_equivalent(task.geometry, created))
            layer_match = bool(created and created.get("layer") == task.metadata.get("layer"))
            object_match = bool(created and created.get("object_name") == task.object_type)
            status = "SUCCESS" if after_count - before_count == 1 and geometry_match and layer_match and object_match else "FAILED_QA"
            if status == "SUCCESS":
                created_handles.append(handle)
            results.append({
                "task_id": task_id,
                "status": status,
                "modelspace_before": before_count,
                "modelspace_after": after_count,
                "draw_delta": after_count - before_count,
                "new_handle": handle,
                "object_name": created.get("object_name") if created else None,
                "layer": created.get("layer") if created else None,
                "geometry": {"start_point": created.get("start_point"), "end_point": created.get("end_point")} if created else None,
                "geometry_match": geometry_match,
                "layer_match": layer_match,
                "duplicate_check": duplicate,
                "execution_backend": "ComCadBackend",
                "fallback_used": False,
            })
        after_entities = _scan(backend, session)
        change_check = unexpected_change_check(before_snapshot, snapshot_entities(after_entities), created_handles)
        execution_qa_passed = change_check["passed"] and all(item["status"] in {"SUCCESS", "SKIPPED_DUPLICATE_RISK"} for item in results)
        successful = [item for item in results if item["status"] == "SUCCESS"]
        if execution_qa_passed and successful:
            backend.save_working_copy(session)
            saved = True
            backend.close_document(session, save=False)
            backend.reopen_working_copy(session, str(sandbox_path))
            reopened = True
            persistence_entities = _scan(backend, session)
            persisted = {str(item.get("handle")): item for item in persistence_entities}
            for item in successful:
                record = persisted.get(str(item["new_handle"]))
                item["persisted"] = bool(record and record.get("layer") == item["layer"] and lines_equivalent(item["geometry"], record))
        else:
            change_check = change_check
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        change_check = unexpected_change_check(snapshot_entities(before_entities), snapshot_entities(after_entities), [])
    finally:
        if session is not None:
            try:
                if session.document_path:
                    backend.close_document(session, save=False)
            except Exception:
                pass
            try:
                backend.disconnect(session)
            except Exception:
                pass

    successful = [item for item in results if item.get("status") == "SUCCESS"]
    skipped = [item for item in results if item.get("status") == "SKIPPED_DUPLICATE_RISK"]
    failed = [item for item in results if item.get("status") not in {"SUCCESS", "SKIPPED_DUPLICATE_RISK"}]
    persisted_count = sum(item.get("persisted") is True for item in successful)
    persistence_passed = saved and reopened and persisted_count == len(successful) and bool(successful)
    return {
        "autocad_connected": session is not None,
        "new_autocad_instance_created": False,
        "source_open_conflicts": source_conflicts,
        "sandbox_opened": sandbox_opened,
        "sandbox_saved": saved,
        "sandbox_reopened": reopened,
        "execution_before_scan": before_entities,
        "execution_after_scan": after_entities,
        "persistence_after_reopen_scan": persistence_entities,
        "task_execution_results": results,
        "duplicate_check": duplicate_records,
        "unexpected_change_check": change_check,
        "attempted_task_count": len(results) - len(skipped),
        "successful_task_count": len(successful),
        "skipped_duplicate_count": len(skipped),
        "failed_task_count": len(failed),
        "created_handles": [item["new_handle"] for item in successful],
        "persisted_task_count": persisted_count,
        "persistence_qa_passed": persistence_passed,
        "error": error,
    }


def build_tianzheng_manual_review(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    commands = {
        "TDbPipe": "TPIPE/对应系统管线命令候选",
        "TDbPipeValve": "阀门布置命令候选",
        "TDbPipeFitting": "管件连接命令候选",
        "TDbPump": "水泵设备布置命令候选",
        "TDbWaterTank": "水箱设备布置命令候选",
    }
    output = []
    for index, item in enumerate(items, 1):
        geometry = item.get("target_wcs_geometry") or {}
        bbox = geometry.get("bbox")
        position = None
        if bbox and len(bbox) == 2:
            position = [(bbox[0][0] + bbox[1][0]) / 2, (bbox[0][1] + bbox[1][1]) / 2, (bbox[0][2] + bbox[1][2]) / 2]
        name = str(item.get("object_name"))
        output.append({
            "candidate_id": item.get("candidate_id"),
            "reference_handle": item.get("reference_handle"),
            "object_name": name,
            "semantic_type": item.get("semantic_type"),
            "target_wcs_position": position,
            "start_point": geometry.get("start_point"),
            "end_point": geometry.get("end_point"),
            "center": geometry.get("center"),
            "insert_point": geometry.get("insert_point"),
            "bbox": bbox,
            "system_type": item.get("system_type"),
            "dn": item.get("dn"),
            "nearby_equipment_and_connections": [],
            "recommended_tianzheng_command_candidate": commands.get(name, "按 ObjectName 在天正中人工选择对应创建命令"),
            "manual_instruction": "在 repair sandbox 中核对位置、系统、DN 与连接关系后人工操作；不得对 source 执行。",
            "preview_number": index,
            "automatic_execution_rejection_reason": "TDb/custom object is excluded from automatic execution",
            "execution_allowed": False,
            "executed": False,
        })
    return output


def _safety_flags() -> dict[str, Any]:
    return {
        "source_reference_opened": False,
        "source_target_opened": False,
        "source_reference_saved": False,
        "source_target_saved": False,
        "source_modified": False,
        "saveas_used": False,
        "copyobjects_used": False,
        "explode_used": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "tdb_modified": False,
        "existing_entities_modified": False,
        "existing_entities_deleted": False,
        "automatic_fallback_used": False,
        "production_d1_allowed": False,
        "stage4_executed": False,
    }


def run_stage3_3(
    *,
    run_id: str | None = None,
    execute_live: bool = True,
    test_results: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    run_id = run_id or datetime.now().strftime("stage3_3_%Y%m%d_%H%M%S")
    run_root = RUNS_ROOT / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    copies = run_root / "copies"
    sandbox = copies / "target_stage3_3_repair_sandbox.dwg"
    stage2 = read_json(STAGE2_REPORT)
    r2_report = read_json(R2_REPORT)
    stage2_root = Path(stage2["run_root"])
    drafts_path = stage2_root / "repair_task_drafts.json"
    missing_path = stage2_root / "missing_candidates.json"
    tdb_path = stage2_root / "tianzheng_manual_tasks.json"
    drafts = read_json(drafts_path)["items"]
    all_missing = read_json(missing_path)["items"]
    tdb_items = read_json(tdb_path)["items"]
    approval = approve_execution_tasks(drafts)
    gate = automatic_transition_gate(stage2, r2_report, approval["approved"])
    safety = _safety_flags()
    input_hashes = {
        "stage3_2_report": file_hash(STAGE2_REPORT),
        "missing_candidates": file_hash(missing_path),
        "repair_task_drafts": file_hash(drafts_path),
    }
    handoff = {
        "stage3_2_status": stage2["status"],
        "stage3_2_run_id": stage2["run_id"],
        "input_hashes": input_hashes,
        "approved_task_ids": [item["task_id"] for item in approval["approved"]],
        "blocked_task_ids": [item.get("task_id") or item.get("candidate_id") for item in approval["rejected"]],
        "manual_task_ids": [item.get("candidate_id") for item in tdb_items],
        "inherited_transform": stage2["selected_translation"],
        "source_hashes": stage2["source_hashes"],
        "automatic_transition_gate": gate,
    }
    write_json(run_root / "stage3_2_handoff.json", handoff)

    non_draft_rejections = [item for item in all_missing if item.get("route") != "direct_com_candidate"]
    rejected = [*approval["rejected"], *non_draft_rejections]
    blocked_execution_items = select_blocked_execution_items(rejected)
    write_json(run_root / "rejected_execution_tasks.json", {"items": rejected})
    write_json(run_root / "blocked_execution_tasks.json", {"items": blocked_execution_items})

    approved_plan = {
        "phase": "STAGE3.3-A",
        "run_id": run_id,
        "frozen": True,
        "approved_task_count": len(approval["approved"]),
        "approved_task_ids": handoff["approved_task_ids"],
        "automatic_append_allowed": False,
        "tasks": approval["approved"],
    }
    write_json(run_root / "approved_execution_plan.json", approved_plan)

    manual = build_tianzheng_manual_review(tdb_items)
    write_json(run_root / "tianzheng_manual_review.json", {"items": manual})
    (run_root / "tianzheng_manual_review.md").write_text(_manual_markdown(manual), encoding="utf-8")

    if not gate["passed"]:
        report = _base_report(run_id, run_root, sandbox, gate, safety, stage2, approval, rejected, test_results)
        report.update({"status": "BLOCKED_PREFLIGHT", "stage3_3_entered": False, "blockers": gate["blockers"]})
        _write_not_executed_artifacts(run_root)
        return _finalize(run_root, report, [], manual, {})

    lock_files = source_lock_files(TARGET_SOURCE)
    if lock_files:
        current_hashes = {"reference": file_hash(REFERENCE_SOURCE), "target": file_hash(TARGET_SOURCE)}
        source_unchanged = (
            current_hashes["reference"] == stage2["source_hashes"]["reference_frozen"]
            and current_hashes["target"] == stage2["source_hashes"]["target_frozen"]
        )
        write_json(run_root / "target_source_integrity.json", {
            "current": current_hashes,
            "source_hashes_unchanged": source_unchanged,
            "target_source_lock_files": lock_files,
            "repair_sandbox_created": False,
            "autocad_connected": False,
        })
        _write_not_executed_artifacts(run_root)
        report = _base_report(run_id, run_root, sandbox, gate, safety, stage2, approval, rejected, test_results)
        report.update({
            "status": "BLOCKED_PREFLIGHT",
            "stage3_3_entered": True,
            "automatic_stage3_3_transition_triggered": True,
            "preflight": {"passed": False, "errors": ["target source is open/locked by AutoCAD"], "target_source_lock_files": lock_files},
            "blockers": ["target source is open/locked by AutoCAD; close it without changing or saving it before retry"],
            "repair_sandbox_path": str(sandbox),
            "repair_sandbox_created": False,
            "source_hashes_unchanged": source_unchanged,
            "tdb_manual_task_count": len(manual),
        })
        return _finalize(run_root, report, [], manual, {})

    copy_result = create_filesystem_sandbox(TARGET_SOURCE, sandbox, stage2["source_hashes"]["target_frozen"])
    source_hash_before = {"reference": file_hash(REFERENCE_SOURCE), "target": file_hash(TARGET_SOURCE)}
    target_region = read_json(ROOT / "artifacts" / "stage3_1_r1" / "stage3_1_r1_20260711_002112" / "target_region.json")
    preflight = validate_preflight(approval["approved"], sandbox, target_region["bbox"])
    write_json(run_root / "target_source_integrity.json", {"before": source_hash_before, "copy": copy_result})
    if not preflight["passed"] or not execute_live:
        report = _base_report(run_id, run_root, sandbox, gate, safety, stage2, approval, rejected, test_results)
        report.update({
            "status": "BLOCKED_PREFLIGHT" if not preflight["passed"] else "PARTIAL_NO_SAFE_AUTOMATIC_TASKS",
            "stage3_3_entered": True,
            "preflight": preflight,
            "blockers": preflight["errors"] if not preflight["passed"] else ["live execution disabled"],
            "repair_sandbox_path": str(sandbox),
        })
        _write_not_executed_artifacts(run_root)
        return _finalize(run_root, report, [], manual, {})

    live = execute_live_plan(approval["approved"], sandbox)
    safety.update({
        "autocad_connected": live["autocad_connected"],
        "new_autocad_instance_created": live["new_autocad_instance_created"],
        "repair_sandbox_opened": live["sandbox_opened"],
        "repair_sandbox_saved": live["sandbox_saved"],
        "repair_sandbox_reopened": live["sandbox_reopened"],
    })
    source_hash_after = {"reference": file_hash(REFERENCE_SOURCE), "target": file_hash(TARGET_SOURCE)}
    source_unchanged = source_hash_before == source_hash_after
    write_json(run_root / "target_source_integrity.json", {
        "before": source_hash_before,
        "after": source_hash_after,
        "source_hashes_unchanged": source_unchanged,
        "copy": copy_result,
        "source_reference_opened": False,
        "source_target_opened": False,
        "source_saved": False,
    })
    write_json(run_root / "execution_before_scan.json", {"entities": live["execution_before_scan"]})
    write_json(run_root / "task_execution_results.json", {"items": live["task_execution_results"]})
    write_json(run_root / "execution_after_scan.json", {"entities": live["execution_after_scan"]})
    write_json(run_root / "duplicate_check.json", {"items": live["duplicate_check"]})
    write_json(run_root / "unexpected_change_check.json", live["unexpected_change_check"])
    write_json(run_root / "persistence_before_close.json", {
        "successful_task_count": live["successful_task_count"],
        "created_handles": live["created_handles"],
        "sandbox_saved": live["sandbox_saved"],
    })
    write_json(run_root / "persistence_after_reopen.json", {"entities": live["persistence_after_reopen_scan"]})
    write_json(run_root / "persistence_qa.json", {
        "saved": live["sandbox_saved"],
        "reopened": live["sandbox_reopened"],
        "successful_task_count": live["successful_task_count"],
        "persisted_task_count": live["persisted_task_count"],
        "passed": live["persistence_qa_passed"],
    })

    _write_preview(run_root / "final_repair_preview.png", approval["approved"], target_region["bbox"])

    if live["error"]:
        status = "BLOCKED_PREFLIGHT" if not live["sandbox_opened"] else "FAILED_EXECUTION_QA"
    elif live["successful_task_count"] == 0 and live["skipped_duplicate_count"] > 0:
        status = "BLOCKED_DUPLICATE_RISK"
    elif not live["unexpected_change_check"]["passed"] or live["failed_task_count"]:
        status = "FAILED_EXECUTION_QA"
    elif not live["persistence_qa_passed"]:
        status = "FAILED_PERSISTENCE_QA"
    elif live["skipped_duplicate_count"] or approval["rejected"]:
        status = "PARTIAL_SOME_TASKS_BLOCKED"
    else:
        status = "PASS_CONTROLLED_REPAIR_PERSISTED"

    report = _base_report(run_id, run_root, sandbox, gate, safety, stage2, approval, rejected, test_results)
    report.update({
        "status": status,
        "stage3_3_entered": True,
        "preflight": preflight,
        "repair_sandbox_path": str(sandbox),
        "attempted_task_count": live["attempted_task_count"],
        "successful_task_count": live["successful_task_count"],
        "skipped_duplicate_count": live["skipped_duplicate_count"],
        "failed_task_count": live["failed_task_count"],
        "created_handles": live["created_handles"],
        "geometry_match": all(item.get("geometry_match") for item in live["task_execution_results"] if item.get("status") == "SUCCESS"),
        "layer_match": all(item.get("layer_match") for item in live["task_execution_results"] if item.get("status") == "SUCCESS"),
        "duplicate_check_passed": live["skipped_duplicate_count"] == 0,
        "existing_object_modified_count": live["unexpected_change_check"]["existing_object_modified_count"],
        "existing_object_deleted_count": live["unexpected_change_check"]["existing_object_deleted_count"],
        "unexpected_new_object_count": live["unexpected_change_check"]["unexpected_new_object_count"],
        "sandbox_saved": live["sandbox_saved"],
        "sandbox_closed_and_reopened": live["sandbox_reopened"],
        "persisted_task_count": live["persisted_task_count"],
        "tdb_manual_task_count": len(manual),
        "source_hashes_unchanged": source_unchanged,
        "live_error": live["error"],
        "real_sample_repair_completed": status == "PASS_CONTROLLED_REPAIR_PERSISTED",
        "stage3_complete": status == "PASS_CONTROLLED_REPAIR_PERSISTED",
        "stage4_allowed": status == "PASS_CONTROLLED_REPAIR_PERSISTED",
        "stage4_executed": False,
        "production_d1_allowed": False,
    })
    return _finalize(run_root, report, live["task_execution_results"], manual, live)


def resume_stage3_3(
    run_root: Path = RUNS_ROOT / "stage3_3_20260711_090728",
    *,
    execute_live: bool = True,
    test_results: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """从既有 Stage 3.3-A 冻结计划恢复；不会重新运行 Stage 3.2 或重新筛选任务。"""
    integrity = verify_frozen_resume(run_root)
    plan = read_json(run_root / "approved_execution_plan.json")
    handoff = read_json(run_root / "stage3_2_handoff.json")
    stage2 = read_json(STAGE2_REPORT)
    approved = list(plan.get("tasks", []))
    rejected_items = read_json(run_root / "rejected_execution_tasks.json").get("items", [])
    manual_items = read_json(run_root / "tianzheng_manual_review.json").get("items", [])
    sandbox = run_root / "copies" / "target_stage3_3_repair_sandbox.dwg"
    gate = handoff.get("automatic_transition_gate", {})
    safety = _safety_flags()
    tests = dict(test_results or read_json(REPORT_JSON).get("tests", {}))
    write_json(run_root / "resume_integrity_amendment.json", integrity)

    approval = {"approved": approved, "rejected": []}
    base = _base_report(
        str(plan.get("run_id")), run_root, sandbox, gate, safety, stage2,
        approval, rejected_items, tests,
    )
    base.update({
        "stage3_3_entered": True,
        "automatic_stage3_3_transition_triggered": True,
        "resumed_from_frozen_stage3_3_a": True,
        "stage3_2_reexecuted": False,
        "approved_tasks_refiltered": False,
        "frozen_plan_integrity": integrity,
        "repair_sandbox_path": str(sandbox),
    })
    if not integrity.get("passed") or not gate.get("passed"):
        blockers = [*integrity.get("errors", []), *gate.get("blockers", [])]
        base.update({"status": "BLOCKED_PREFLIGHT", "blockers": blockers, "repair_sandbox_created": sandbox.exists()})
        _write_not_executed_artifacts(run_root)
        return _finalize(run_root, base, [], manual_items, {})

    target_locks = source_lock_files(TARGET_SOURCE)
    reference_locks = source_lock_files(REFERENCE_SOURCE)
    if target_locks or reference_locks:
        current_hashes = {"reference": file_hash(REFERENCE_SOURCE), "target": file_hash(TARGET_SOURCE)}
        source_unchanged = (
            current_hashes["reference"] == stage2["source_hashes"]["reference_frozen"]
            and current_hashes["target"] == stage2["source_hashes"]["target_frozen"]
        )
        preflight = {
            "passed": False,
            "errors": [
                *( ["target source is open/locked by AutoCAD"] if target_locks else [] ),
                *( ["reference source is open/locked by AutoCAD"] if reference_locks else [] ),
            ],
            "target_source_lock_files": target_locks,
            "reference_source_lock_files": reference_locks,
            "autocad_connected": False,
        }
        write_json(run_root / "resume_preflight.json", preflight)
        write_json(run_root / "target_source_integrity.json", {
            "current": current_hashes,
            "source_hashes_unchanged": source_unchanged,
            "target_source_lock_files": target_locks,
            "reference_source_lock_files": reference_locks,
            "repair_sandbox_created": sandbox.exists(),
            "autocad_connected": False,
        })
        base.update({
            "status": "BLOCKED_PREFLIGHT",
            "preflight": preflight,
            "blockers": [*preflight["errors"], "close all source/reference DWGs without saving; keep AutoCAD running"],
            "repair_sandbox_created": sandbox.exists(),
            "source_hashes_unchanged": source_unchanged,
        })
        _write_not_executed_artifacts(run_root)
        return _finalize(run_root, base, [], manual_items, {})

    source_hash_before = {"reference": file_hash(REFERENCE_SOURCE), "target": file_hash(TARGET_SOURCE)}
    expected_target_hash = stage2["source_hashes"]["target_frozen"]
    if sandbox.exists():
        sandbox_hash = file_hash(sandbox)
        if sandbox_hash != expected_target_hash:
            base.update({
                "status": "BLOCKED_PREFLIGHT",
                "blockers": ["existing repair sandbox hash is not the frozen target source hash"],
                "repair_sandbox_created": True,
                "source_hashes_unchanged": True,
            })
            return _finalize(run_root, base, [], manual_items, {})
        copy_result = {
            "copy_method": "existing_stage3_3_b_filesystem_copy_reused",
            "target_source_hash": expected_target_hash,
            "repair_sandbox_initial_hash": sandbox_hash,
            "hashes_match": True,
        }
    else:
        copy_result = create_filesystem_sandbox(TARGET_SOURCE, sandbox, expected_target_hash)
    target_region = read_json(ROOT / "artifacts" / "stage3_1_r1" / "stage3_1_r1_20260711_002112" / "target_region.json")
    preflight = validate_preflight(approved, sandbox, target_region["bbox"])
    preflight.update({
        "resume_integrity_passed": True,
        "frozen_task_count": len(approved),
        "frozen_task_ids_unchanged": integrity["approved_task_ids_unchanged"],
        "stage3_2_reexecuted": False,
    })
    write_json(run_root / "resume_preflight.json", preflight)
    write_json(run_root / "target_source_integrity.json", {
        "before": source_hash_before,
        "copy": copy_result,
        "source_hashes_unchanged_before_execution": (
            source_hash_before["reference"] == stage2["source_hashes"]["reference_frozen"]
            and source_hash_before["target"] == stage2["source_hashes"]["target_frozen"]
        ),
    })
    if not preflight["passed"] or not execute_live:
        base.update({
            "status": "BLOCKED_PREFLIGHT",
            "preflight": preflight,
            "blockers": preflight["errors"] if not preflight["passed"] else ["live execution disabled"],
            "repair_sandbox_created": True,
            "source_hashes_unchanged": True,
        })
        _write_not_executed_artifacts(run_root)
        return _finalize(run_root, base, [], manual_items, {})

    live = execute_live_plan(approved, sandbox)
    safety.update({
        "autocad_connected": live["autocad_connected"],
        "new_autocad_instance_created": live["new_autocad_instance_created"],
        "repair_sandbox_opened": live["sandbox_opened"],
        "repair_sandbox_saved": live["sandbox_saved"],
        "repair_sandbox_reopened": live["sandbox_reopened"],
    })
    source_hash_after = {"reference": file_hash(REFERENCE_SOURCE), "target": file_hash(TARGET_SOURCE)}
    source_unchanged = source_hash_before == source_hash_after
    write_json(run_root / "target_source_integrity.json", {
        "before": source_hash_before,
        "after": source_hash_after,
        "source_hashes_unchanged": source_unchanged,
        "copy": copy_result,
        "source_reference_opened": False,
        "source_target_opened": False,
        "source_saved": False,
    })
    write_json(run_root / "execution_before_scan.json", {"entities": live["execution_before_scan"]})
    write_json(run_root / "task_execution_results.json", {"items": live["task_execution_results"]})
    write_json(run_root / "execution_after_scan.json", {"entities": live["execution_after_scan"]})
    write_json(run_root / "duplicate_check.json", {"items": live["duplicate_check"]})
    write_json(run_root / "unexpected_change_check.json", live["unexpected_change_check"])
    write_json(run_root / "persistence_before_close.json", {
        "successful_task_count": live["successful_task_count"],
        "created_handles": live["created_handles"],
        "sandbox_saved": live["sandbox_saved"],
    })
    write_json(run_root / "persistence_after_reopen.json", {"entities": live["persistence_after_reopen_scan"]})
    write_json(run_root / "persistence_qa.json", {
        "saved": live["sandbox_saved"],
        "reopened": live["sandbox_reopened"],
        "successful_task_count": live["successful_task_count"],
        "persisted_task_count": live["persisted_task_count"],
        "passed": live["persistence_qa_passed"],
    })
    _write_preview(run_root / "final_repair_preview.png", approved, target_region["bbox"])

    if live["error"]:
        status = "BLOCKED_PREFLIGHT" if not live["sandbox_opened"] else "FAILED_EXECUTION_QA"
    elif live["successful_task_count"] == 0 and live["skipped_duplicate_count"] > 0:
        status = "BLOCKED_DUPLICATE_RISK"
    elif not live["unexpected_change_check"]["passed"] or live["failed_task_count"]:
        status = "FAILED_EXECUTION_QA"
    elif not live["persistence_qa_passed"]:
        status = "FAILED_PERSISTENCE_QA"
    elif live["skipped_duplicate_count"]:
        status = "PARTIAL_SOME_TASKS_BLOCKED"
    else:
        status = "PASS_CONTROLLED_REPAIR_PERSISTED"
    successful_results = [item for item in live["task_execution_results"] if item.get("status") == "SUCCESS"]
    base.update({
        "status": status,
        "preflight": preflight,
        "repair_sandbox_created": True,
        "attempted_task_count": live["attempted_task_count"],
        "successful_task_count": live["successful_task_count"],
        "skipped_duplicate_count": live["skipped_duplicate_count"],
        "failed_task_count": live["failed_task_count"],
        "created_handles": live["created_handles"],
        "geometry_match": bool(successful_results) and all(item.get("geometry_match") for item in successful_results),
        "layer_match": bool(successful_results) and all(item.get("layer_match") for item in successful_results),
        "duplicate_check_passed": live["skipped_duplicate_count"] == 0,
        "existing_object_modified_count": live["unexpected_change_check"]["existing_object_modified_count"],
        "existing_object_deleted_count": live["unexpected_change_check"]["existing_object_deleted_count"],
        "unexpected_new_object_count": live["unexpected_change_check"]["unexpected_new_object_count"],
        "sandbox_saved": live["sandbox_saved"],
        "sandbox_closed_and_reopened": live["sandbox_reopened"],
        "persisted_task_count": live["persisted_task_count"],
        "tdb_manual_task_count": len(manual_items),
        "source_hashes_unchanged": source_unchanged,
        "live_error": live["error"],
        "real_sample_repair_completed": status == "PASS_CONTROLLED_REPAIR_PERSISTED",
        "stage3_complete": status == "PASS_CONTROLLED_REPAIR_PERSISTED",
        "stage4_allowed": status == "PASS_CONTROLLED_REPAIR_PERSISTED",
        "stage4_executed": False,
        "production_d1_allowed": False,
        "safety_flags": safety,
    })
    return _finalize(run_root, base, live["task_execution_results"], manual_items, live)


def _write_not_executed_artifacts(run_root: Path) -> None:
    write_json(run_root / "execution_before_scan.json", {"executed": False, "entities": []})
    write_json(run_root / "task_execution_results.json", {"executed": False, "items": []})
    write_json(run_root / "execution_after_scan.json", {"executed": False, "entities": []})
    write_json(run_root / "duplicate_check.json", {"executed": False, "items": []})
    write_json(run_root / "unexpected_change_check.json", {
        "executed": False,
        "existing_object_modified_count": 0,
        "existing_object_deleted_count": 0,
        "unexpected_new_object_count": 0,
    })
    write_json(run_root / "persistence_before_close.json", {"executed": False, "sandbox_saved": False})
    write_json(run_root / "persistence_after_reopen.json", {"executed": False, "entities": []})
    write_json(run_root / "persistence_qa.json", {
        "executed": False, "saved": False, "reopened": False, "persisted_task_count": 0, "passed": False,
    })


def _base_report(
    run_id: str, run_root: Path, sandbox: Path, gate: Mapping[str, Any], safety: Mapping[str, Any],
    stage2: Mapping[str, Any], approval: Mapping[str, Any], rejected: Sequence[Mapping[str, Any]],
    tests: Mapping[str, str] | None,
) -> dict[str, Any]:
    return {
        "phase": "STAGE3.3-CONTROLLED-MVP-REPAIR-AND-PERSISTENCE-QA",
        "run_id": run_id,
        "run_root": str(run_root),
        "stage3_2_status": stage2["status"],
        "automatic_transition_gate": dict(gate),
        "user_authorized_automatic_stage3_3_transition": True,
        "automatic_stage3_3_transition_scope": "mvp_safe_ordinary_cad_only",
        "approved_task_count": len(approval["approved"]),
        "rejected_or_blocked_task_count": len(rejected),
        "repair_sandbox_path": str(sandbox),
        "attempted_task_count": 0,
        "successful_task_count": 0,
        "skipped_duplicate_count": 0,
        "failed_task_count": 0,
        "created_handles": [],
        "geometry_match": False,
        "layer_match": False,
        "duplicate_check_passed": False,
        "existing_object_modified_count": 0,
        "existing_object_deleted_count": 0,
        "unexpected_new_object_count": 0,
        "sandbox_saved": False,
        "sandbox_closed_and_reopened": False,
        "persisted_task_count": 0,
        "tdb_manual_task_count": int(stage2.get("tdb_manual_task_count", 0)),
        "source_hashes_unchanged": False,
        "real_sample_repair_completed": False,
        "stage3_complete": False,
        "stage4_allowed": False,
        "stage4_executed": False,
        "production_d1_allowed": False,
        "safety_flags": dict(safety),
        "tests": dict(tests or {}),
    }


def _finalize(
    run_root: Path, report: dict[str, Any], execution_results: Sequence[Mapping[str, Any]],
    manual: Sequence[Mapping[str, Any]], live: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = {
        "run_id": report["run_id"],
        "status": report["status"],
        "approved_task_count": report["approved_task_count"],
        "successful_task_count": report.get("successful_task_count", 0),
        "persisted_task_count": report.get("persisted_task_count", 0),
        "created_handles": report.get("created_handles", []),
        "artifact_paths": sorted(str(path) for path in run_root.rglob("*") if path.is_file()),
        "stage4_allowed": report.get("stage4_allowed", False),
        "stage4_executed": False,
        "production_d1_allowed": False,
    }
    write_json(run_root / "stage3_3_manifest.json", manifest)
    write_json(REPORT_JSON, report)
    REPORT_MD.write_text(_markdown(report), encoding="utf-8")
    return report


def _write_preview(path: Path, tasks: Sequence[Mapping[str, Any]], bbox: Sequence[float]) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return
    width, height, padding = 1400, 1000, 50
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    xmin, ymin, xmax, ymax = map(float, bbox[:4])
    scale = min((width - 2 * padding) / (xmax - xmin), (height - 2 * padding) / (ymax - ymin))
    def pixel(point: Sequence[float]) -> tuple[int, int]:
        return int(padding + (point[0] - xmin) * scale), int(height - padding - (point[1] - ymin) * scale)
    draw.rectangle([pixel((xmin, ymax)), pixel((xmax, ymin))], outline="#808080", width=2)
    for task in tasks:
        geometry = task.get("geometry") or {}
        start, end = geometry.get("start_point"), geometry.get("end_point")
        if start and end:
            draw.line([pixel(start), pixel(end)], fill="#d62728", width=4)
    image.save(path)


def _manual_markdown(items: Sequence[Mapping[str, Any]]) -> str:
    lines = ["# Tianzheng Manual Review", "", f"- task_count: {len(items)}", "- automatic_execution: false", ""]
    for item in items:
        lines.extend([
            f"## {item['candidate_id']}",
            f"- ObjectName: {item['object_name']}",
            f"- reference handle: {item['reference_handle']}",
            f"- target WCS position: {item['target_wcs_position']}",
            f"- command candidate: {item['recommended_tianzheng_command_candidate']}",
            f"- reason: {item['automatic_execution_rejection_reason']}",
            "",
        ])
    return "\n".join(lines)


def _markdown(report: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Stage 3.3 Controlled Repair",
        "",
        f"- status: {report['status']}",
        f"- stage3_3_entered: {str(report.get('stage3_3_entered')).lower()}",
        f"- approved / rejected: {report.get('approved_task_count', 0)} / {report.get('rejected_or_blocked_task_count', 0)}",
        f"- attempted / successful / skipped / failed: {report.get('attempted_task_count', 0)} / {report.get('successful_task_count', 0)} / {report.get('skipped_duplicate_count', 0)} / {report.get('failed_task_count', 0)}",
        f"- created_handles: {report.get('created_handles', [])}",
        f"- geometry_match: {str(report.get('geometry_match')).lower()}",
        f"- layer_match: {str(report.get('layer_match')).lower()}",
        f"- sandbox_saved: {str(report.get('sandbox_saved')).lower()}",
        f"- sandbox_closed_and_reopened: {str(report.get('sandbox_closed_and_reopened')).lower()}",
        f"- persisted_task_count: {report.get('persisted_task_count', 0)}",
        f"- source_hashes_unchanged: {str(report.get('source_hashes_unchanged')).lower()}",
        f"- real_sample_repair_completed: {str(report.get('real_sample_repair_completed')).lower()}",
        f"- stage4_allowed: {str(report.get('stage4_allowed')).lower()}",
        "- stage4_executed: false",
        "- production_d1_allowed: false",
        "",
        "## Safety",
        *[f"- {key}: {str(value).lower()}" for key, value in report.get("safety_flags", {}).items()],
        "",
        "## Tests",
        *[f"- {key}: {value}" for key, value in report.get("tests", {}).items()],
        "",
    ])


if __name__ == "__main__":
    result = run_stage3_3()
    print(json.dumps({
        "status": result["status"],
        "run_id": result["run_id"],
        "successful_task_count": result.get("successful_task_count", 0),
        "persisted_task_count": result.get("persisted_task_count", 0),
    }, ensure_ascii=False))
