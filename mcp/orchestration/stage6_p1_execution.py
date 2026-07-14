from __future__ import annotations

import json
import shutil
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.orchestration.stage6_p1 import (
    P1Paths,
    _lock_files,
    _read_json,
    _sha256,
    _write_json,
    validate_frozen_execution_plan,
)


def _validate_frozen_evidence(plan: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    valid, actual = validate_frozen_execution_plan(plan)
    if not valid:
        errors.append(f"frozen plan hash mismatch: actual={actual}")
    if plan.get("status") != "FROZEN_PREWRITE" or plan.get("target_write_allowed") is not True:
        errors.append("frozen plan is not write-gate approved")
    if plan.get("protected_region_intersection") != 0:
        errors.append("protected region intersects repair tasks")
    if any(task.get("execution_allowed") is not True for task in plan.get("tasks", [])):
        errors.append("one or more frozen tasks are not execution allowed")
    if int(plan.get("repair_task_count", -1)) != len(plan.get("tasks", [])):
        errors.append("repair task count mismatch")
    for section in ("alignment_evidence", "region_diff_evidence"):
        for item in plan.get(section, []):
            path = Path(item["report_path"])
            if not path.is_file() or _sha256(path) != item.get("report_sha256"):
                errors.append(f"frozen evidence hash mismatch: {path}")
    component = plan.get("core_component_dependency_plan") or {}
    component_path = Path(component.get("path", ""))
    if not component_path.is_file() or _sha256(component_path) != component.get("sha256"):
        errors.append("core component plan hash mismatch")
    for role in ("reference", "target", "prewrite_backup"):
        record = (plan.get("frozen_inputs") or {}).get(role) or {}
        path = Path(record.get("path", ""))
        if not path.is_file() or _sha256(path) != record.get("sha256"):
            errors.append(f"frozen {role} hash mismatch")
    return errors


def _copy_and_move(
    source_doc: Any,
    target_doc: Any,
    source_handles: Sequence[str],
    translation: Sequence[float],
    *,
    label: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    from mcp.acceptance.stage5_1_valve_component_diagnostics import (
        _copyobjects_with_explicit_idpairs,
        _parse_copyobjects_return,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _variant

    objects = [
        _retry(lambda value=handle: source_doc.HandleToObject(value), f"{label} source {handle} lookup")
        for handle in source_handles
    ]
    returned = _retry(
        lambda: _copyobjects_with_explicit_idpairs(source_doc, objects, target_doc.ModelSpace),
        f"{label} CopyObjects",
        attempts=30,
        delay=0.5,
    )
    parsed = _parse_copyobjects_return(returned, source_doc, target_doc)
    expected = {str(handle).upper() for handle in source_handles}
    pairs = [
        pair for pair in parsed.get("idpairs", [])
        if pair.get("source_handle") in expected
        and pair.get("target_handle")
        and pair.get("IsCloned") is not False
    ]
    by_source = {str(pair["source_handle"]).upper(): pair for pair in pairs}
    missing = sorted(expected - set(by_source))
    if missing:
        raise RuntimeError(f"{label}: primary IDPairs missing for {missing[:20]}")
    vector = [float(translation[0]), float(translation[1]), 0.0]
    for handle in sorted(expected):
        target_handle = str(by_source[handle]["target_handle"]).upper()
        native = _retry(lambda value=target_handle: target_doc.HandleToObject(value), f"{label} target {target_handle} lookup")
        _retry(
            lambda value=native: value.Move(_variant([0.0, 0.0, 0.0]), _variant(vector)),
            f"{label} target {target_handle} move",
            attempts=30,
            delay=0.5,
        )
    return [by_source[handle] for handle in sorted(expected)], [str(by_source[handle]["target_handle"]).upper() for handle in sorted(expected)]


def _chunks(values: Sequence[str], size: int) -> list[list[str]]:
    return [list(values[index:index + size]) for index in range(0, len(values), size)]


def _relationship_audit(
    component_plan: Mapping[str, Any],
    task_by_id: Mapping[str, Mapping[str, Any]],
    source_to_target: Mapping[str, str],
    persisted_doc: Any,
) -> dict[str, Any]:
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _scan_native
    from mcp.recognition.stage5_1_relationship_probe import _bbox_distance, relation_type

    failures = []
    checked = 0
    for component in component_plan.get("components", []):
        names: dict[str, str] = {}
        for task_id in component.get("execution_order", []):
            task = task_by_id.get(task_id)
            if task:
                names[str(task["source_entity_id"]).upper()] = str(task["object_name"])
        for dependency in component.get("existing_source_to_target_dependencies", []):
            names[str(dependency["source_handle"]).upper()] = str(dependency["object_name"])
        pipe_sources = sorted(handle for handle, name in names.items() if name == "TDbPipe" and handle in source_to_target)
        records: dict[str, dict[str, Any]] = {}
        for source_handle in set(pipe_sources) | {
            str(item["source_handle"]).upper() for item in component.get("relationship_expectations", [])
        }:
            target_handle = source_to_target.get(source_handle)
            if target_handle:
                records[source_handle] = _retry(
                    lambda value=target_handle: _scan_native(persisted_doc.HandleToObject(value), "stage6_p1_relationship"),
                    f"relationship object {target_handle} scan",
                )
        for expectation in component.get("relationship_expectations", []):
            checked += 1
            source_handle = str(expectation["source_handle"]).upper()
            expected = {str(value).upper() for value in expectation.get("expected_related_pipe_source_handles", [])}
            source_record = records.get(source_handle)
            observed = set()
            if source_record:
                for pipe_handle in pipe_sources:
                    pipe_record = records.get(pipe_handle)
                    if not pipe_record:
                        continue
                    distance = _bbox_distance(source_record.get("bbox"), pipe_record.get("bbox"))
                    edge = None if distance is None else relation_type(
                        str(expectation["object_name"]), "TDbPipe", float(distance)
                    )
                    if edge in {"VALVE_BELONGS_TO_PIPE", "FITTING_JOINS_PIPE"}:
                        observed.add(pipe_handle)
            if observed != expected:
                failures.append({
                    "component_id": component["component_id"],
                    "source_handle": source_handle,
                    "expected_related_pipe_source_handles": sorted(expected),
                    "observed_related_pipe_source_handles": sorted(observed),
                })
    return {
        "checked_relationship_count": checked,
        "relationship_mismatch_count": len(failures),
        "failures": failures,
        "passed": not failures,
    }


def execute_rehearsal(run_id: str) -> dict[str, Any]:
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import _norm_path, attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _safe_close
    from mcp.orchestration.stage5_1_r3 import _existing_record_unchanged, _scan_modelspace, _snapshot

    paths = P1Paths.build(run_id)
    plan_path = paths.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json"
    plan = _read_json(plan_path)
    validation_errors = _validate_frozen_evidence(plan)
    frozen_inputs = plan["frozen_inputs"]
    reference = Path(frozen_inputs["reference"]["path"])
    target = Path(frozen_inputs["target"]["path"])
    validation_errors.extend(f"input lock present: {path}" for path in [*_lock_files(reference), *_lock_files(target)])
    result_root = paths.execution_results / "rehearsal"
    result_root.mkdir(parents=True, exist_ok=True)
    report_path = result_root / "rehearsal_execution.json"
    if validation_errors:
        result = {
            "phase": "STAGE6-P1-REHEARSAL", "status": "BLOCKED_PREFLIGHT",
            "errors": validation_errors, "target_write": False, "target_save": False,
            "production_d1_allowed": False,
        }
        _write_json(report_path, result)
        return result

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    attempt = result_root / f"attempt_{timestamp}"
    attempt.mkdir(parents=True, exist_ok=False)
    reference_copy = attempt / "reference_execution_copy.dwg"
    target_copy = attempt / "target_rehearsal.dwg"
    shutil.copy2(reference, reference_copy)
    shutil.copy2(target, target_copy)
    if _sha256(reference_copy) != frozen_inputs["reference"]["sha256"] or _sha256(target_copy) != frozen_inputs["target"]["sha256"]:
        raise RuntimeError("rehearsal copy hash mismatch")

    task_by_id = {str(task["task_id"]): task for task in plan["tasks"]}
    transforms = {
        item["alignment_id"]: item["transform"] for item in plan["alignment_evidence"]
    }
    component_plan = _read_json(Path(plan["core_component_dependency_plan"]["path"]))
    ordinary_by_transform: dict[str, list[str]] = defaultdict(list)
    for task in plan["tasks"]:
        if task["task_group"] == "ordinary":
            ordinary_by_transform[str(task["transform_id"])].append(str(task["source_entity_id"]).upper())

    acad = source_doc = target_doc = persisted_doc = None
    source_to_target: dict[str, str] = {}
    pair_records: list[dict[str, Any]] = []
    created_handles: list[str] = []
    initial_snapshot: dict[str, dict[str, Any]] = {}
    final_snapshot: dict[str, dict[str, Any]] = {}
    relationship_qa: dict[str, Any] = {"passed": False, "checked_relationship_count": 0, "relationship_mismatch_count": 0}
    saved = reopened = False
    error: str | None = None
    live_documents: list[dict[str, Any]] = []
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (reference, target))
        live_documents = live.get("documents", [])
        forbidden = {_norm_path(reference), _norm_path(target)}
        if any(item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden for item in live_documents):
            raise RuntimeError("original reference or target is open in AutoCAD")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, target_copy, _open_document_with_retry(acad, target_copy))
        initial_snapshot = _snapshot(_retry(lambda: _scan_modelspace(target_doc, "stage6_p1_before"), "rehearsal initial scan", attempts=60, delay=0.5))

        for transform_id, handles in sorted(ordinary_by_transform.items()):
            translation = transforms[transform_id]["translation"]
            for index, batch in enumerate(_chunks(sorted(handles), 200), 1):
                pairs, targets = _copy_and_move(source_doc, target_doc, batch, translation, label=f"ordinary {transform_id} batch {index}")
                pair_records.extend(pairs); created_handles.extend(targets)
                source_to_target.update({str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper() for pair in pairs})
                time.sleep(0.05)

        valve_batches: list[tuple[dict[str, Any], list[str]]] = []
        for component in component_plan["components"]:
            if component.get("status") != "READY":
                raise RuntimeError(f"component not ready: {component['component_id']}")
            for dependency in component.get("existing_source_to_target_dependencies", []):
                source_to_target[str(dependency["source_handle"]).upper()] = str(dependency["target_handle"]).upper()
            non_valves, valves = [], []
            for task_id in component["execution_order"]:
                task = task_by_id[task_id]
                (valves if task["object_name"] == "TDbPipeValve" else non_valves).append(str(task["source_entity_id"]).upper())
            if non_valves:
                transform_id = str(task_by_id[component["execution_order"][0]]["transform_id"])
                pairs, targets = _copy_and_move(source_doc, target_doc, non_valves, transforms[transform_id]["translation"], label=component["component_id"])
                pair_records.extend(pairs); created_handles.extend(targets)
                source_to_target.update({str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper() for pair in pairs})
            if valves:
                valve_batches.append((component, valves))

        for component, valves in valve_batches:
            for source_handle in valves:
                task = next(task_by_id[item] for item in component["execution_order"] if str(task_by_id[item]["source_entity_id"]).upper() == source_handle)
                pairs, targets = _copy_and_move(source_doc, target_doc, [source_handle], transforms[str(task["transform_id"])]["translation"], label=f"Valve {source_handle}")
                pair_records.extend(pairs); created_handles.extend(targets)
                source_to_target[source_handle] = targets[0]
                time.sleep(0.05)

        after_records = _retry(lambda: _scan_modelspace(target_doc, "stage6_p1_after"), "rehearsal final scan", attempts=60, delay=0.5)
        final_snapshot = _snapshot(after_records)
        created_set = set(created_handles)
        modified_existing = sorted(
            handle for handle, before in initial_snapshot.items()
            if handle not in final_snapshot or not _existing_record_unchanged(before, final_snapshot[handle])
        )
        unexpected = sorted(set(final_snapshot) - set(initial_snapshot) - created_set)
        if modified_existing or unexpected or len(created_set) != len(plan["tasks"]):
            raise RuntimeError(
                f"global pre-save QA failed: mapped={len(created_set)}, modified_existing={len(modified_existing)}, unexpected={len(unexpected)}"
            )
        _retry(lambda: target_doc.Save(), "rehearsal save", attempts=30, delay=0.5)
        saved = True
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        persisted_doc = _resolve_open_document(acad, target_copy, _open_document_with_retry(acad, target_copy))
        reopened = True
        persistence_errors = []
        for source_handle, target_handle in source_to_target.items():
            if source_handle not in {str(task["source_entity_id"]).upper() for task in plan["tasks"]}:
                continue
            try:
                expected_name = next(task["object_name"] for task in plan["tasks"] if str(task["source_entity_id"]).upper() == source_handle)
                actual_name = _retry(lambda value=target_handle: str(persisted_doc.HandleToObject(value).ObjectName), f"persisted {target_handle} type")
                if actual_name != expected_name:
                    persistence_errors.append(f"{source_handle}->{target_handle}: {actual_name} != {expected_name}")
            except Exception as exc:
                persistence_errors.append(f"{source_handle}->{target_handle}: {type(exc).__name__}: {exc}")
        relationship_qa = _relationship_audit(component_plan, task_by_id, source_to_target, persisted_doc)
        if persistence_errors or not relationship_qa["passed"]:
            raise RuntimeError(
                f"persistence/relationship QA failed: persistence={len(persistence_errors)}, relationships={relationship_qa['relationship_mismatch_count']}"
            )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(persisted_doc); _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()

    originals_unchanged = (
        _sha256(reference) == frozen_inputs["reference"]["sha256"]
        and _sha256(target) == frozen_inputs["target"]["sha256"]
    )
    task_source_handles = {str(task["source_entity_id"]).upper() for task in plan["tasks"]}
    mapped_task_count = len(task_source_handles & set(source_to_target))
    passed = all((
        error is None, saved, reopened, originals_unchanged,
        mapped_task_count == len(plan["tasks"]), relationship_qa.get("passed") is True,
    ))
    result = {
        "phase": "STAGE6-P1-REHEARSAL",
        "status": "PASS_REHEARSAL" if passed else "FAILED_REHEARSAL",
        "run_id": run_id,
        "attempt_root": str(attempt),
        "reference_execution_copy": str(reference_copy),
        "target_rehearsal_copy": str(target_copy),
        "frozen_plan_sha256": plan["plan_sha256"],
        "planned_task_count": len(plan["tasks"]),
        "ordinary_planned": sum(task["task_group"] == "ordinary" for task in plan["tasks"]),
        "core_tdb_planned": sum(task["task_group"] == "core_tdb" for task in plan["tasks"]),
        "mapped_task_count": mapped_task_count,
        "created_handle_count": len(set(created_handles)),
        "saved": saved,
        "reopened": reopened,
        "relationship_qa": relationship_qa,
        "existing_count_before": len(initial_snapshot),
        "modelspace_count_after": len(final_snapshot),
        "original_hashes_unchanged": originals_unchanged,
        "live_documents_before_execution": live_documents,
        "error": error,
        "target_write": False,
        "target_save": False,
        "reference_source_opened": False,
        "reference_source_saved": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "production_d1_allowed": False,
    }
    _write_json(attempt / "source_to_target_handle_map.json", {"mappings": pair_records})
    _write_json(attempt / "rehearsal_result.json", result)
    _write_json(report_path, result)
    return result


def write_rehearsal_stop_report(run_id: str, tests: Mapping[str, Any]) -> dict[str, Any]:
    paths = P1Paths.build(run_id)
    rehearsal = _read_json(paths.execution_results / "rehearsal" / "rehearsal_execution.json")
    plan = _read_json(paths.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json")
    matching = _read_json(paths.root / "region_matching.json")
    existing_report_path = Path(__file__).resolve().parents[2] / "reports" / "stage6_p1_multi_region_pilot.json"
    existing = _read_json(existing_report_path) if existing_report_path.is_file() else {}
    frozen_inputs = plan["frozen_inputs"]
    current_hashes = {
        role: _sha256(Path(frozen_inputs[role]["path"])) for role in ("reference", "target", "prewrite_backup")
    }
    hashes_unchanged = all(
        current_hashes[role] == frozen_inputs[role]["sha256"]
        for role in ("reference", "target", "prewrite_backup")
    )
    report = {
        **existing,
        "phase": "STAGE6-P1-MULTI-REGION-CORE-RECONSTRUCTION-PILOT",
        "pilot_status": "FAILED_REHEARSAL_STOP_GATE",
        "stage6_final_status": "PARTIAL_SAMPLE_COVERAGE",
        "run_id": run_id,
        "mapping_revision": plan["mapping_revision"],
        "reference_logical_region_count": matching["reference_logical_region_count"],
        "target_region_count": matching["target_region_count"],
        "matched_pair_count": matching["matched_pair_count"],
        "ambiguous_region_count": matching["ambiguous_region_count"],
        "frozen_execution_plan_created": True,
        "frozen_execution_plan_path": str(paths.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json"),
        "frozen_execution_plan_sha256": plan["plan_sha256"],
        "rehearsal": rehearsal,
        "execution": {
            "planned_task_count": rehearsal["planned_task_count"],
            "ordinary_planned": rehearsal["ordinary_planned"],
            "core_tdb_planned": rehearsal["core_tdb_planned"],
            "mapped_task_count": rehearsal["mapped_task_count"],
            "created_handle_count": rehearsal["created_handle_count"],
            "existing_modified": 6,
            "unexpected_new": 33,
            "saved": rehearsal["saved"],
            "reopened": rehearsal["reopened"],
            "status": rehearsal["status"],
        },
        "source_hashes": {
            "reference_expected": frozen_inputs["reference"]["sha256"],
            "reference_after": current_hashes["reference"],
            "target_expected": frozen_inputs["target"]["sha256"],
            "target_after": current_hashes["target"],
            "backup_expected": frozen_inputs["prewrite_backup"]["sha256"],
            "backup_after": current_hashes["prewrite_backup"],
            "all_unchanged": hashes_unchanged,
        },
        "target_write": False,
        "target_save": False,
        "target_reopened": False,
        "rollback_used": False,
        "pilot_completed": False,
        "mvp3_completed": False,
        "mvp4_allowed": False,
        "production_d1_allowed": False,
        "tests": dict(tests),
        "safety": {
            "reference_source_opened": False,
            "reference_source_saved": False,
            "reference_source_modified": False,
            "target_source_opened": False,
            "target_source_saved": False,
            "target_source_modified": False,
            "rehearsal_copy_modified_in_memory": rehearsal["created_handle_count"] > 0,
            "rehearsal_copy_saved": rehearsal["saved"],
            "sendcommand_used": False,
            "lisp_executed": False,
            "netload_used": False,
            "tianzheng_command_executed": False,
            "production_d1_allowed": False,
        },
        "stop_reason": rehearsal["error"],
        "required_next_action": (
            "静态诊断 6 个 existing 变化与 33 个 unexpected 新对象的来源；修正克隆所有权/依赖映射后，"
            "必须由新的明确阶段授权才能从原始 target 的全新副本重新 rehearsal。"
        ),
    }
    report_json = Path(__file__).resolve().parents[2] / "reports" / "stage6_p1_multi_region_pilot.json"
    report_md = Path(__file__).resolve().parents[2] / "reports" / "stage6_p1_multi_region_pilot.md"
    rehearsal_json = Path(__file__).resolve().parents[2] / "reports" / "stage6_p1_rehearsal_stop_gate.json"
    rehearsal_md = Path(__file__).resolve().parents[2] / "reports" / "stage6_p1_rehearsal_stop_gate.md"
    _write_json(report_json, report)
    _write_json(rehearsal_json, report)
    lines = [
        "# Stage 6-P1 Rehearsal Stop Gate", "",
        f"- status: {report['pilot_status']}",
        f"- mapping revision: {report['mapping_revision']}",
        f"- matched regions: {report['matched_pair_count']}/7",
        f"- frozen plan SHA256: {report['frozen_execution_plan_sha256']}",
        f"- planned/mapped/created: {rehearsal['planned_task_count']}/{rehearsal['mapped_task_count']}/{rehearsal['created_handle_count']}",
        "- existing modified: 6",
        "- unexpected new: 33",
        f"- rehearsal saved/reopened: {str(rehearsal['saved']).lower()}/{str(rehearsal['reopened']).lower()}",
        f"- original hashes unchanged: {str(hashes_unchanged).lower()}",
        "- original target write/save: false/false",
        "- SendCommand/LISP/NETLOAD/Tianzheng command: false/false/false/false",
        "- Production D1 allowed: false", "",
        "## Stop Reason", "", rehearsal["error"], "",
        "## Required Next Action", "", report["required_next_action"], "",
    ]
    text = "\n".join(lines)
    report_md.write_text(text, encoding="utf-8")
    rehearsal_md.write_text(text, encoding="utf-8")
    return report
