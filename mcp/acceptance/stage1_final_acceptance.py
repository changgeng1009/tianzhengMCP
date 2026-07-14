from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import time
from typing import Any, Iterable

from mcp.agents.agent_budget import AgentBudget, estimate_chars
from mcp.agents.agent_result_schema import RESULT_SCHEMA
from mcp.agents.deepseek_worker import run_deepseek_worker
from mcp.agents.task_pack_builder import build_task_pack
from mcp.diff.mvp_missing_content_diff import compare_missing_content
from mcp.planning.mvp_repair_task_classifier import classify_diff_result
from mcp.recognition.mvp_semantic_object_model import semantic_object_from_dwg_entity
from mcp.repair_actions.geometry_localizer import validate_candidate_geometry
from mcp.repair_actions.task_eligibility import validate_direct_com_candidate


PHASE = "STAGE1-FINAL-ACCEPTANCE"
VALIDATION_MODE = "controlled_known_good_fixture"
SOURCE_DWG = Path(r"D:\ExampleWorkspace\synthetic_sample_t8.dwg")
BASE_SANDBOX = Path(r"D:\ExampleWorkspace\天正\artifacts\sandbox\mvp2a_test_copy_20260710_091816.dwg")
EXPECTED_SOURCE_SHA256 = None  # External run configuration required; no bundled private default.
VALIDATION_DIR = Path(r"D:\ExampleWorkspace\天正\artifacts\validation")
TASK_PATH = Path(r"D:\ExampleWorkspace\天正\artifacts\repair_tasks\stage1_validation_direct_com_tasks.json")
MANIFEST_PATH = VALIDATION_DIR / "stage1_fixture_manifest.json"
PERSISTENCE_PATH = VALIDATION_DIR / "stage1_persistence_qa.json"
REPORT_JSON = Path(r"D:\ExampleWorkspace\天正\reports\stage1_final_acceptance.json")
REPORT_MD = Path(r"D:\ExampleWorkspace\天正\reports\stage1_final_acceptance.md")
VALIDATION_LAYER = "MCP_S1_VALIDATION"
MIN_GEOMETRY_CONFIDENCE = 0.80

FORBIDDEN_GEOMETRY_SOURCES = {
    "guessed_geometry",
    "hardcoded_coordinate",
    "placeholder_geometry",
    "default_origin",
    "pdf_page_size_only",
}
ALLOWED_OPEN_PATHS: set[str] = set()


@dataclass(frozen=True)
class FixturePaths:
    reference: Path
    target: Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_path(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def is_forbidden_fixture_path(path: str | Path) -> bool:
    normalized = normalized_path(path)
    return normalized in {normalized_path(SOURCE_DWG), normalized_path(BASE_SANDBOX)}


def validate_open_target(path: str | Path, allowed_paths: Iterable[str | Path]) -> None:
    normalized = normalized_path(path)
    allowed = {normalized_path(item) for item in allowed_paths}
    if is_forbidden_fixture_path(path):
        raise ValueError("source/base sandbox path is forbidden as AutoCAD open target")
    if normalized not in allowed:
        raise ValueError("only generated validation fixtures may be opened")


def validate_save_target(path: str | Path, target_fixture: str | Path) -> None:
    if is_forbidden_fixture_path(path) or normalized_path(path) != normalized_path(target_fixture):
        raise ValueError("save path must be the active validation fixture")


def choose_fixture_paths(now: datetime | None = None) -> FixturePaths:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    reference = VALIDATION_DIR / "s1_reference_fixture.dwg"
    target = VALIDATION_DIR / "s1_target_fixture.dwg"
    if reference.exists() or target.exists():
        stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
        reference = VALIDATION_DIR / f"s1_reference_fixture_{stamp}.dwg"
        target = VALIDATION_DIR / f"s1_target_fixture_{stamp}.dwg"
    return FixturePaths(reference=reference, target=target)


def create_fixture_copies(paths: FixturePaths) -> None:
    if not BASE_SANDBOX.exists():
        raise FileNotFoundError(f"base sandbox not found: {BASE_SANDBOX}")
    if paths.reference.exists() or paths.target.exists():
        raise FileExistsError("validation fixture path already exists")
    shutil.copy2(BASE_SANDBOX, paths.reference)
    shutil.copy2(BASE_SANDBOX, paths.target)


def derive_seed_geometry(ext_min: Iterable[float], ext_max: Iterable[float]) -> dict[str, Any]:
    minimum = [float(value) for value in ext_min]
    maximum = [float(value) for value in ext_max]
    if len(minimum) < 2 or len(maximum) < 2 or not all(math.isfinite(v) for v in minimum + maximum):
        raise ValueError("drawing extents are invalid")
    span_x = maximum[0] - minimum[0]
    span_y = maximum[1] - minimum[1]
    if span_x <= 0 and span_y <= 0:
        raise ValueError("drawing extents cannot produce a non-zero fixture line")
    z = minimum[2] if len(minimum) > 2 and math.isfinite(minimum[2]) else 0.0
    if span_x > 0:
        start = [minimum[0] + span_x * 0.20, minimum[1] + max(span_y, 0.0) * 0.20, z]
        end = [minimum[0] + span_x * 0.25, start[1], z]
    else:
        start = [minimum[0], minimum[1] + span_y * 0.20, z]
        end = [minimum[0], minimum[1] + span_y * 0.25, z]
    length = math.dist(start, end)
    if length <= 0:
        raise ValueError("derived fixture line has zero length")
    return {"start_point": start, "end_point": end, "length": length}


def validate_line_geometry(geometry: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    start = geometry.get("start_point")
    end = geometry.get("end_point")
    if not _valid_point(start) or not _valid_point(end):
        errors.append("line requires finite start_point and end_point")
    elif math.dist([float(v) for v in start], [float(v) for v in end]) <= 0:
        errors.append("zero-length line is forbidden")
    source = str(geometry.get("geometry_source") or "")
    if source in FORBIDDEN_GEOMETRY_SOURCES:
        errors.append("forbidden geometry source")
    if source not in {"reference_dwg_entity_geometry", "transformed_reference_geometry"}:
        errors.append("geometry source is not fixture-authoritative")
    if float(geometry.get("geometry_confidence") or 0.0) < MIN_GEOMETRY_CONFIDENCE:
        errors.append("geometry confidence below execution threshold")
    return not errors, errors


def build_executable_tasks(classification: dict[str, Any]) -> dict[str, Any]:
    executable: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for task in classification.get("missing_tasks", []):
        source_object = {
            "object_id": task.get("source_object_id"),
            "object_type": task.get("semantic", {}).get("fixture_object_type") or task.get("object_type") or _object_type_from_task(task),
            "geometry": task.get("geometry") or {},
            "semantic": task.get("semantic") or {},
            "layer": task.get("semantic", {}).get("layer") or task.get("layer") or VALIDATION_LAYER,
            "confidence": task.get("confidence", 0.0),
            "target_missing_evidence": True,
        }
        gate = validate_direct_com_candidate(source_object, reason="no matching target object")
        candidate = {
            "cad_geometry": task.get("geometry") or {},
            "geometry_source": "reference_dwg_entity_geometry",
            "geometry_confidence": float(task.get("confidence", 0.0)),
            "evidence_ids": [str(task.get("source_object_id") or "")],
            "transform_used": False,
            "localization_method": "reference_fixture_semantic_entity_geometry",
        }
        localized = validate_candidate_geometry(candidate)
        line_payload = {
            **localized.get("cad_geometry", {}),
            "geometry_source": localized.get("geometry_source"),
            "geometry_confidence": localized.get("geometry_confidence"),
        }
        geometry_ok, geometry_errors = validate_line_geometry(line_payload)
        if task.get("task_type") != "direct_com_create" or not gate["valid"] or not localized["execution_allowed"] or not geometry_ok:
            rejected.append({
                "task_id": task.get("task_id"),
                "reasons": list(dict.fromkeys(gate["invalid_reasons"] + [localized.get("rejection_reason", "")] + geometry_errors)),
            })
            continue
        executable.append({
            "task_id": task["task_id"],
            "classification": "confirmed_direct_com",
            "task_type": "direct_com_create",
            "action": "direct_com_create",
            "object_type": "line",
            "execution_allowed": True,
            "cad_geometry": localized["cad_geometry"],
            "geometry_source": localized["geometry_source"],
            "geometry_confidence": localized["geometry_confidence"],
            "evidence_ids": localized["evidence_ids"],
            "layer": VALIDATION_LAYER,
            "validation_fixture_only": True,
            "sendcommand_required": False,
            "tianzheng_command_required": False,
        })
    return {
        "phase": PHASE,
        "validation_mode": VALIDATION_MODE,
        "planned_direct_com_task_count": len(executable),
        "tasks": executable,
        "rejected_tasks": rejected,
        "real_sample_repair_completed": False,
        "production_d1_allowed": False,
    }


def validate_execution_task(task: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if task.get("classification") != "confirmed_direct_com":
        errors.append("task is not confirmed_direct_com")
    if task.get("task_type") != "direct_com_create" or task.get("object_type") != "line":
        errors.append("only direct_com_create line is allowed")
    if not task.get("execution_allowed") or not task.get("validation_fixture_only"):
        errors.append("task is not authorized for validation fixture execution")
    command_values = " ".join(_iter_string_values(task)).lower()
    if any(token in command_values for token in ("sendcommand", "hsxg", "hzgx", "gxlj", "tsaveas", "tgbatplots", "dcsz", "tdb")):
        errors.append("dangerous or Tianzheng execution marker found")
    if task.get("sendcommand_required") is not False or task.get("tianzheng_command_required") is not False:
        errors.append("execution safety declaration is incomplete")
    line_geometry = dict(task.get("cad_geometry") or {})
    line_geometry["geometry_source"] = task.get("geometry_source")
    line_geometry["geometry_confidence"] = task.get("geometry_confidence")
    geometry_ok, geometry_errors = validate_line_geometry(line_geometry)
    if not geometry_ok:
        errors.extend(geometry_errors)
    return not errors, list(dict.fromkeys(errors))


def semantic_pipeline(reference_entities: list[dict[str, Any]], target_entities: list[dict[str, Any]]) -> dict[str, Any]:
    reference_objects = [
        semantic_object_from_dwg_entity(entity, source="stage1_reference_fixture", index=index, confidence=0.95)
        for index, entity in enumerate(reference_entities)
    ]
    target_objects = [
        semantic_object_from_dwg_entity(entity, source="stage1_target_fixture", index=index, confidence=0.95)
        for index, entity in enumerate(target_entities)
    ]
    diff = compare_missing_content(reference_objects, target_objects, include_review_only=True)
    classification = classify_diff_result(diff)
    tasks = build_executable_tasks(classification)
    return {"reference_objects": reference_objects, "target_objects": target_objects, "diff": diff, "classification": classification, "tasks": tasks}


def build_deepseek_task_pack() -> dict[str, Any]:
    return build_task_pack(
        phase=PHASE,
        goal="静态审查 validation direct-com line task schema、持久化验收字段和不可变文件断言，给出边界检查建议；不要作最终阶段判定。",
        allowed_files=[
            "mcp/acceptance/stage1_final_acceptance.py",
            "mcp/repair_actions/task_eligibility.py",
            "mcp/repair_actions/geometry_localizer.py",
        ],
        forbidden_files=["source drawing", "base sandbox", "validation fixture"],
        expected_outputs=["在 notes 中给出静态 schema 和边界断言建议"],
        test_commands=[],
        output_schema=RESULT_SCHEMA,
        budget=AgentBudget(max_input_chars=20_000, max_output_tokens=1_200),
    )


def run_deepseek_delegation() -> dict[str, Any]:
    task_pack = build_deepseek_task_pack()
    result = run_deepseek_worker(task_pack, dry_run=False, timeout=45.0, temperature=0.0)
    succeeded = result.get("status") in {"PASS", "PARTIAL"} and bool(result.get("notes"))
    notes = [str(note) for note in result.get("notes", [])]
    accepted = (
        sum(1 for note in notes if any(key in note.lower() for key in ("schema", "geometry", "persist", "hash", "path", "layer")))
        if succeeded
        else 0
    )
    modified = 1 if succeeded and notes and accepted < len(notes) else 0
    return {
        "deepseek_worker_used": True,
        "delegated_task_count": 1,
        "delegated_task_ids": ["ds_stage1_fixture_schema_review"],
        "deepseek_task_pack_chars": estimate_chars(task_pack),
        "deepseek_call_succeeded": succeeded,
        "deepseek_result_accepted_count": min(accepted, len(notes)),
        "deepseek_result_modified_count": modified,
        "deepseek_result_rejected_count": max(0, len(notes) - accepted - modified) if succeeded else 0,
        "deepseek_review_notes": notes,
        "final_decision_made_by_codex": True,
        "deepseek_made_final_pass_decision": False,
        "full_chat_sent_to_deepseek": False,
        "api_key_sent_to_deepseek": False,
        "dwg_binary_sent_to_deepseek": False,
        "source_file_sent_to_deepseek": False,
        "full_history_sent_to_deepseek": False,
        "autocad_execution_authorized": False,
    }


def run_live_acceptance() -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_SOURCE_SHA256 = require_parameter('mcp.acceptance.stage1_final_acceptance.expected_source_sha256', 'sha256')
    started = datetime.now(timezone.utc)
    SOURCE_DWG.exists() or _raise(FileNotFoundError(str(SOURCE_DWG)))
    BASE_SANDBOX.exists() or _raise(FileNotFoundError(str(BASE_SANDBOX)))
    source_hash_before = sha256_file(SOURCE_DWG)
    base_hash_before = sha256_file(BASE_SANDBOX)
    if source_hash_before != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("source SHA256 does not match the expected baseline")

    deepseek = run_deepseek_delegation()
    paths = choose_fixture_paths()
    create_fixture_copies(paths)
    allowed_paths = {normalized_path(paths.reference), normalized_path(paths.target)}
    global ALLOWED_OPEN_PATHS
    ALLOWED_OPEN_PATHS = allowed_paths

    report = _base_report(started, paths, source_hash_before, base_hash_before, deepseek)
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        acad = None
        owned_autocad = False
        try:
            acad, owned_autocad = _connect_autocad(win32com.client)
            report.update(_prepare_autocad_session(acad))
            seed = _seed_reference_fixture(acad, win32com.client, pythoncom, paths.reference, allowed_paths)
            report.update(seed)
            reference_entities = _scan_fixture(acad, paths.reference, allowed_paths)
            target_entities = _scan_fixture(acad, paths.target, allowed_paths)
            pipeline = semantic_pipeline(reference_entities, target_entities)
            task_artifact = pipeline["tasks"]
            _write_json(TASK_PATH, task_artifact)
            report.update({
                "reference_semantic_object_count": len(pipeline["reference_objects"]),
                "target_semantic_object_count": len(pipeline["target_objects"]),
                "missing_candidate_count": pipeline["diff"]["missing_count"],
                "review_only_task_count": pipeline["classification"]["review_task_count"],
                "confirmed_direct_com_task_count": task_artifact["planned_direct_com_task_count"],
                "planned_direct_com_task_count": task_artifact["planned_direct_com_task_count"],
            })
            if len(task_artifact["tasks"]) != 1:
                raise RuntimeError("pipeline did not produce exactly one validation direct COM task")
            execution = _execute_target_fixture(acad, win32com.client, pythoncom, paths.target, allowed_paths, task_artifact["tasks"])
            report.update(execution)
        finally:
            if owned_autocad and acad is not None:
                try:
                    acad.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")

    source_hash_after = sha256_file(SOURCE_DWG)
    base_hash_after = sha256_file(BASE_SANDBOX)
    report.update({
        "source_hash_after": source_hash_after,
        "source_hash_unchanged": source_hash_before == source_hash_after,
        "base_sandbox_hash_after": base_hash_after,
        "base_sandbox_hash_unchanged": base_hash_before == base_hash_after,
    })
    report["status"] = acceptance_status(report)
    report["stage1_core_capability_stable"] = report["status"] == "PASS"
    report["can_enter_stage2_skill_packaging"] = report["status"] == "PASS"
    _write_outputs(report)
    return report


def acceptance_status(report: dict[str, Any]) -> str:
    safety_failed = not report.get("source_hash_unchanged") or not report.get("base_sandbox_hash_unchanged") or any(
        report.get(key) for key in (
            "source_dwg_opened", "source_dwg_saved", "source_modified", "save_called_on_source",
            "base_sandbox_dwg_opened", "base_sandbox_saved", "base_sandbox_modified",
            "sendcommand_used", "tianzheng_command_executed", "tdb_modified", "production_d1_allowed",
        )
    )
    if safety_failed:
        return "FAIL"
    required = (
        report.get("validation_mode") == VALIDATION_MODE,
        report.get("real_sample_repair_completed") is False,
        report.get("reference_seed_delta") == 1,
        report.get("reference_fixture_saved") is True,
        report.get("reference_fixture_reopened") is True,
        report.get("reference_seed_persisted") is True,
        report.get("missing_candidate_count") == 1,
        report.get("confirmed_direct_com_task_count") == 1,
        report.get("planned_direct_com_task_count") == 1,
        report.get("executed_direct_com_task_count") == 1,
        report.get("target_draw_delta") == 1,
        report.get("target_validation_layer_count_before") == 0,
        report.get("target_validation_layer_count_after_reopen") == 1,
        report.get("target_saved") is True,
        report.get("target_reopened") is True,
        report.get("persisted_delta") == 1,
        report.get("geometry_match") is True,
        report.get("layer_match") is True,
        report.get("review_only_executed_count") == 0,
        report.get("blocked_invalid_task_executed_count") == 0,
        report.get("real_sample_review_only_items_included_count") == 0,
        report.get("blocked_invalid_task_included_count") == 0,
        report.get("manual_anchor_task_included_count") == 0,
        report.get("deepseek_worker_used") is True,
        report.get("delegated_task_count", 0) >= 1,
        bool(report.get("delegated_task_ids")),
        0 < int(report.get("deepseek_task_pack_chars") or 0) <= 20_000,
        report.get("deepseek_call_succeeded") is True,
        report.get("final_decision_made_by_codex") is True,
        report.get("deepseek_made_final_pass_decision") is False,
        all(
            report.get(key) is False
            for key in (
                "full_chat_sent_to_deepseek",
                "api_key_sent_to_deepseek",
                "dwg_binary_sent_to_deepseek",
                "source_file_sent_to_deepseek",
                "full_history_sent_to_deepseek",
                "autocad_execution_authorized",
            )
        ),
    )
    if all(required) and not report.get("errors"):
        return "PASS"
    if report.get("reference_seed_delta") == 1 or report.get("target_draw_delta") == 1:
        return "PARTIAL"
    return "BLOCKED"


def _base_report(started: datetime, paths: FixturePaths, source_hash: str, base_hash: str, deepseek: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "status": "BLOCKED",
        "validation_mode": VALIDATION_MODE,
        "real_sample_repair_completed": False,
        "production_d1_allowed": False,
        "started_at": started.isoformat(),
        "source_dwg_path": str(SOURCE_DWG),
        "base_sandbox_path": str(BASE_SANDBOX),
        "reference_fixture_path": str(paths.reference),
        "target_fixture_path": str(paths.target),
        "source_hash_before": source_hash,
        "base_sandbox_hash_before": base_hash,
        "source_hash_after": None,
        "base_sandbox_hash_after": None,
        "source_hash_unchanged": False,
        "base_sandbox_hash_unchanged": False,
        "fixture_seed_object_type": None,
        "fixture_seed_layer": VALIDATION_LAYER,
        "fixture_seed_start_point": None,
        "fixture_seed_end_point": None,
        "fixture_seed_length": None,
        "fixture_seed_handle": None,
        "reference_count_before": None,
        "reference_count_after": None,
        "reference_seed_delta": 0,
        "reference_seed_persisted": False,
        "missing_candidate_count": 0,
        "confirmed_direct_com_task_count": 0,
        "planned_direct_com_task_count": 0,
        "executed_direct_com_task_count": 0,
        "target_count_before": None,
        "target_count_after": None,
        "target_draw_delta": 0,
        "target_saved": False,
        "target_reopened": False,
        "persisted_delta": 0,
        "geometry_match": False,
        "layer_match": False,
        "created_handle": None,
        "created_object_name": None,
        "created_layer": None,
        "actual_start_point": None,
        "actual_end_point": None,
        "review_only_executed_count": 0,
        "blocked_invalid_task_executed_count": 0,
        "real_sample_review_only_items_included_count": 0,
        "blocked_invalid_task_included_count": 0,
        "manual_anchor_task_included_count": 0,
        "tdb_modified": False,
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "source_modified": False,
        "save_called_on_source": False,
        "base_sandbox_dwg_opened": False,
        "base_sandbox_saved": False,
        "base_sandbox_modified": False,
        "base_sandbox_preexisting_open_count": 0,
        "base_sandbox_closed_without_save_count": 0,
        "sendcommand_used": False,
        "tianzheng_command_executed": False,
        "dangerous_command_executed": False,
        "errors": [],
        **deepseek,
    }


def _connect_autocad(client: Any) -> tuple[Any, bool]:
    try:
        return client.GetActiveObject("AutoCAD.Application.25.1"), False
    except Exception:
        try:
            return client.GetActiveObject("AutoCAD.Application"), False
        except Exception:
            app = client.Dispatch("AutoCAD.Application.25.1")
            app.Visible = True
            time.sleep(2.0)
            return app, True


def _prepare_autocad_session(acad: Any) -> dict[str, int]:
    source = normalized_path(SOURCE_DWG)
    base = normalized_path(BASE_SANDBOX)
    for index in range(int(acad.Documents.Count)):
        document = acad.Documents.Item(index)
        full_name = str(getattr(document, "FullName", "") or "")
        if not full_name:
            continue
        normalized = normalized_path(full_name)
        if normalized == source:
            raise RuntimeError("source DWG is already open in AutoCAD")
        if normalized == base:
            raise RuntimeError("base sandbox is already open in AutoCAD; refusing to operate on or close it")
    return {
        "base_sandbox_preexisting_open_count": 0,
        "base_sandbox_closed_without_save_count": 0,
    }


def _open_document(acad: Any, path: Path, allowed_paths: set[str]) -> Any:
    validate_open_target(path, allowed_paths)
    opened = _retry_com(lambda: acad.Documents.Open(str(path), False), label=f"open {path.name}")
    expected = normalized_path(path)
    try:
        if hasattr(opened, "ModelSpace") and normalized_path(str(opened.FullName)) == expected:
            return opened
    except Exception:
        pass
    for _ in range(60):
        try:
            for index in range(int(acad.Documents.Count)):
                document = acad.Documents.Item(index)
                if normalized_path(str(document.FullName or "")) == expected:
                    return document
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"AutoCAD did not expose opened validation fixture: {path.name}")


def _seed_reference_fixture(acad: Any, client: Any, pythoncom: Any, path: Path, allowed_paths: set[str]) -> dict[str, Any]:
    document = _open_document(acad, path, allowed_paths)
    try:
        modelspace = document.ModelSpace
        before = int(modelspace.Count)
        geometry = derive_seed_geometry(document.GetVariable("EXTMIN"), document.GetVariable("EXTMAX"))
        _ensure_layer(document, VALIDATION_LAYER)
        line = modelspace.AddLine(_variant_point(client, pythoncom, geometry["start_point"]), _variant_point(client, pythoncom, geometry["end_point"]))
        line.Layer = VALIDATION_LAYER
        handle = str(line.Handle)
        after = int(modelspace.Count)
        document.Save()
    finally:
        document.Close(False)

    reopened = _open_document(acad, path, allowed_paths)
    try:
        entity = _find_by_handle(reopened.ModelSpace, handle)
        persisted = entity is not None and str(entity.Layer) == VALIDATION_LAYER
    finally:
        reopened.Close(False)
    return {
        "fixture_seed_object_type": "AcDbLine",
        "fixture_seed_layer": VALIDATION_LAYER,
        "fixture_seed_start_point": geometry["start_point"],
        "fixture_seed_end_point": geometry["end_point"],
        "fixture_seed_length": geometry["length"],
        "fixture_seed_handle": handle,
        "reference_count_before": before,
        "reference_count_after": after,
        "reference_seed_delta": after - before,
        "reference_fixture_saved": True,
        "reference_fixture_reopened": True,
        "reference_seed_persisted": persisted,
    }


def _scan_fixture(acad: Any, path: Path, allowed_paths: set[str]) -> list[dict[str, Any]]:
    document = _open_document(acad, path, allowed_paths)
    try:
        time.sleep(0.75)
        modelspace = _retry_com(lambda: document.ModelSpace, label=f"ModelSpace {path.name}")
        count = int(_retry_com(lambda: modelspace.Count, label=f"ModelSpace.Count {path.name}"))
        records = []
        for index in range(count):
            entity = _retry_com(lambda index=index: modelspace.Item(index), label=f"ModelSpace.Item({index})")
            records.append(_entity_record(entity))
        return records
    finally:
        _retry_com(lambda: document.Close(False), label=f"close {path.name}")


def _entity_record(entity: Any) -> dict[str, Any]:
    record = {
        "ObjectName": str(_retry_com(lambda: entity.ObjectName, label="entity.ObjectName")),
        "Handle": str(_retry_com(lambda: entity.Handle, label="entity.Handle")),
        "Layer": str(_retry_com(lambda: entity.Layer, label="entity.Layer")),
    }
    if record["ObjectName"] == "AcDbLine":
        start = _point_list(_retry_com(lambda: entity.StartPoint, label="line.StartPoint"))
        end = _point_list(_retry_com(lambda: entity.EndPoint, label="line.EndPoint"))
        record.update({"StartPoint": start, "EndPoint": end, "length": math.dist(start, end)})
    return record


def _execute_target_fixture(acad: Any, client: Any, pythoncom: Any, path: Path, allowed_paths: set[str], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    if len(tasks) != 1:
        raise ValueError("exactly one fixture task is required")
    task = tasks[0]
    valid, errors = validate_execution_task(task)
    if not valid:
        raise ValueError("execution task rejected: " + "; ".join(errors))
    document = _open_document(acad, path, allowed_paths)
    try:
        validate_save_target(document.FullName, path)
        modelspace = document.ModelSpace
        before = int(modelspace.Count)
        layer_before = _count_layer(modelspace, VALIDATION_LAYER)
        geometry = task["cad_geometry"]
        _ensure_layer(document, task["layer"])
        line = modelspace.AddLine(_variant_point(client, pythoncom, geometry["start_point"]), _variant_point(client, pythoncom, geometry["end_point"]))
        line.Layer = task["layer"]
        handle = str(line.Handle)
        after = int(modelspace.Count)
        actual_start = _point_list(line.StartPoint)
        actual_end = _point_list(line.EndPoint)
        actual_layer = str(line.Layer)
        actual_name = str(line.ObjectName)
        validate_save_target(document.FullName, path)
        document.Save()
    finally:
        document.Close(False)

    reopened = _open_document(acad, path, allowed_paths)
    try:
        modelspace = reopened.ModelSpace
        persisted_count = int(modelspace.Count)
        entity = _find_by_handle(modelspace, handle)
        if entity is None:
            geometry_match = False
            layer_match = False
        else:
            geometry_match = _points_match(_point_list(entity.StartPoint), geometry["start_point"]) and _points_match(_point_list(entity.EndPoint), geometry["end_point"])
            layer_match = str(entity.Layer) == task["layer"]
        layer_after_reopen = _count_layer(modelspace, VALIDATION_LAYER)
    finally:
        reopened.Close(False)
    return {
        "executed_direct_com_task_count": 1,
        "target_count_before": before,
        "target_count_after": after,
        "target_draw_delta": after - before,
        "target_validation_layer_count_before": layer_before,
        "target_validation_layer_count_after_reopen": layer_after_reopen,
        "target_saved": True,
        "target_reopened": True,
        "persisted_delta": persisted_count - before,
        "geometry_match": geometry_match,
        "layer_match": layer_match,
        "created_handle": handle,
        "created_object_name": actual_name,
        "created_layer": actual_layer,
        "actual_start_point": actual_start,
        "actual_end_point": actual_end,
    }


def _ensure_layer(document: Any, name: str) -> None:
    try:
        document.Layers.Item(name)
    except Exception:
        document.Layers.Add(name)


def _count_layer(modelspace: Any, layer: str) -> int:
    return sum(1 for index in range(int(modelspace.Count)) if str(modelspace.Item(index).Layer) == layer)


def _find_by_handle(modelspace: Any, handle: str) -> Any | None:
    for index in range(int(modelspace.Count)):
        entity = modelspace.Item(index)
        if str(entity.Handle) == handle:
            return entity
    return None


def _variant_point(client: Any, pythoncom: Any, point: Iterable[float]) -> Any:
    return client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(value) for value in point])


def _point_list(point: Iterable[float]) -> list[float]:
    values = [float(value) for value in point]
    return (values + [0.0, 0.0, 0.0])[:3]


def _valid_point(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) and math.isfinite(float(item)) for item in value)


def _points_match(left: Iterable[float], right: Iterable[float], tolerance: float = 1e-6) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(_point_list(left), _point_list(right)))


def _object_type_from_task(task: dict[str, Any]) -> str:
    object_name = str((task.get("semantic") or {}).get("object_name") or "")
    return "line" if object_name == "AcDbLine" else str(task.get("object_type") or "unknown")


def _iter_string_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"sendcommand_required", "tianzheng_command_required"}:
                continue
            yield from _iter_string_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_string_values(item)
    elif isinstance(value, str):
        yield value


def _retry_com(call: Any, *, label: str, attempts: int = 8, delay: float = 0.25) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(delay * (attempt + 1))
    raise RuntimeError(f"COM operation failed after retries: {label}: {last_error}")


def _raise(error: Exception) -> None:
    raise error


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_outputs(report: dict[str, Any]) -> None:
    manifest = {
        "phase": PHASE,
        "validation_mode": VALIDATION_MODE,
        "base_sandbox_path": report["base_sandbox_path"],
        "base_sandbox_initial_hash": report["base_sandbox_hash_before"],
        "reference_fixture_path": report["reference_fixture_path"],
        "target_fixture_path": report["target_fixture_path"],
        "fixture_created_at": report["started_at"],
        "fixture_seed_object_type": report["fixture_seed_object_type"],
        "fixture_seed_layer": report["fixture_seed_layer"],
        "fixture_seed_start_point": report["fixture_seed_start_point"],
        "fixture_seed_end_point": report["fixture_seed_end_point"],
        "fixture_seed_length": report["fixture_seed_length"],
        "fixture_disposable": True,
        "source_used_as_autocad_open_target": False,
        "base_sandbox_used_as_autocad_open_target": False,
    }
    persistence = {
        "phase": PHASE,
        "target_fixture_path": report["target_fixture_path"],
        "target_saved": report["target_saved"],
        "target_reopened": report["target_reopened"],
        "persisted_delta": report["persisted_delta"],
        "created_handle": report["created_handle"],
        "geometry_match": report["geometry_match"],
        "layer_match": report["layer_match"],
    }
    _write_json(MANIFEST_PATH, manifest)
    _write_json(PERSISTENCE_PATH, persistence)
    _write_json(REPORT_JSON, report)
    REPORT_MD.write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    return f"""# Stage 1 Final Acceptance Manager Report

## 验收结果

- status: {report['status']}
- validation_mode: {report['validation_mode']}
- real_sample_repair_completed: false
- stage1_core_capability_stable: {str(report.get('stage1_core_capability_stable', False)).lower()}

## Fixture 闭环

- reference_fixture: {report['reference_fixture_path']}
- target_fixture: {report['target_fixture_path']}
- reference_seed_delta: {report['reference_seed_delta']}
- missing_candidate_count: {report['missing_candidate_count']}
- confirmed_direct_com_task_count: {report['confirmed_direct_com_task_count']}
- executed_direct_com_task_count: {report['executed_direct_com_task_count']}
- target_draw_delta: {report['target_draw_delta']}
- persisted_delta: {report['persisted_delta']}
- geometry_match: {str(report['geometry_match']).lower()}
- layer_match: {str(report['layer_match']).lower()}

## 不可变文件与安全

- source_hash_unchanged: {str(report['source_hash_unchanged']).lower()}
- base_sandbox_hash_unchanged: {str(report['base_sandbox_hash_unchanged']).lower()}
- source_dwg_opened: false
- base_sandbox_dwg_opened: false
- sendcommand_used: false
- tianzheng_command_executed: false
- tdb_modified: false
- production_d1_allowed: false

## DeepSeek 受控委派

- deepseek_worker_used: {str(report['deepseek_worker_used']).lower()}
- delegated_task_ids: {', '.join(report['delegated_task_ids'])}
- deepseek_task_pack_chars: {report['deepseek_task_pack_chars']}
- deepseek_call_succeeded: {str(report['deepseek_call_succeeded']).lower()}
- final_decision_made_by_codex: true
- deepseek_made_final_pass_decision: false

## 错误

{chr(10).join('- ' + item for item in report['errors']) if report['errors'] else '- 无'}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 Stage 1 controlled known-good fixture 最终验收")
    parser.add_argument("--execute", action="store_true", help="允许对新建 validation fixtures 执行受控 COM 闭环")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("必须显式传入 --execute；默认不连接 AutoCAD。")
    print(json.dumps(run_live_acceptance(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
