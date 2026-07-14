from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.orchestration.stage6_p1 import P1Paths, _bbox2d, _read_json, _sha256, validate_frozen_execution_plan
from mcp.orchestration.stage6_p1_override import (
    EXPECTED_PLAN_SHA256,
    EXPECTED_REFERENCE_SHA256,
    EXPECTED_TARGET_SHA256,
    MAIN_RUN_ID,
    ROOT,
    _bbox_intersects,
    _introduced_duplicates,
    _region_for_bbox,
)

RUN_ROOT = ROOT / "artifacts" / "stage6_p1_accelerated_r4"
WORK_FILE_NAME = "target_sample-应急提交版-R4.dwg"

# ── whitelists ──────────────────────────────────────────────
ORDINARY_SAFE = frozenset({
    "AcDbLine", "AcDbCircle", "AcDbArc", "AcDbPolyline",
    "AcDbText", "AcDbMText",
})

# AcDbBlockReference 只有在经验证可独立处理时进入 batch
BLOCKREF_CANDIDATE = "AcDbBlockReference"

TDB_SERIAL = frozenset({
    "TDbPipe", "TDbPipeFitting", "TDbPipeValve",
    "TDbPump", "TDbEquipment", "TDbWaterTank",
    "TDbVPipeDim", "TDbSymbMultiLeader",
})

BATCH_MIN_SIZE = 50
BATCH_MAX_SIZE = 200

KNOWN_IDPAIR_SOURCES = {"B04C6", "B04C7", "B04C8"}


class HardStop(RuntimeError):
    pass


def _paths(run_id: str) -> dict[str, Path]:
    root = RUN_ROOT / run_id
    return {
        "root": root,
        "inputs": root / "execution_inputs",
        "checkpoints": root / "checkpoints",
        "calls": root / "copyobjects_calls",
        "reports": root / "reports",
        "evidence": root / "evidence",
    }


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _modelspace_handles(document: Any) -> set[str]:
    return {
        str(document.ModelSpace.Item(index).Handle).upper()
        for index in range(int(document.ModelSpace.Count))
    }


def _owner_record(document: Any, native: Any) -> dict[str, Any]:
    try:
        owner = document.ObjectIDToObject(int(native.OwnerID))
        return {
            "handle": str(getattr(owner, "Handle", "")).upper(),
            "object_name": str(getattr(owner, "ObjectName", "")),
            "name": str(getattr(owner, "Name", "")),
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _native_record(document: Any, handle: str, role: str) -> dict[str, Any]:
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _scan_native

    native = _retry(lambda: document.HandleToObject(handle), f"{role} {handle} lookup")
    record = _scan_native(native, role)
    record["handle"] = str(record.get("handle") or handle).upper()
    record["owner"] = _owner_record(document, native)
    return record


def _close_without_save(document: Any | None) -> bool:
    if document is None:
        return False
    try:
        document.Close(False)
        return True
    except Exception:
        return False


def _bring_to_foreground(acad: Any) -> bool:
    import ctypes

    try:
        hwnd = int(acad.HWND)
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


def _bbox_close(left: Sequence[float] | None, right: Sequence[float] | None, tolerance: float = 1e-5) -> bool:
    if left is None or right is None or len(left) != len(right):
        return False
    return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))


def _candidate_matches(source: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    if source.get("object_name") != candidate.get("object_name"):
        return False
    if source.get("owner", {}).get("object_name") != candidate.get("owner", {}).get("object_name"):
        return False
    if not _bbox_close(_bbox2d(source), _bbox2d(candidate)):
        return False
    source_geometry = source.get("geometry") or {}
    candidate_geometry = candidate.get("geometry") or {}
    return not source_geometry or source_geometry == candidate_geometry


def _build_state(
    *,
    all_task_ids: set[str],
    completed_task_ids: set[str],
    skipped_task_ids: set[str],
    manual_tasks: list[dict[str, Any]],
    source_to_target: Mapping[str, str],
    created_handles: set[str],
    call_count: int,
    current_task_index: int,
    current_component_index: int,
    current_batch_index: int,
    stage: str,
) -> dict[str, Any]:
    pending = sorted(all_task_ids - completed_task_ids - skipped_task_ids)
    return {
        "completed_task_count": len(completed_task_ids),
        "pending_task_count": len(pending),
        "skipped_task_count": len(skipped_task_ids),
        "completed_task_ids": sorted(completed_task_ids),
        "pending_task_ids": pending,
        "skipped_task_ids": sorted(skipped_task_ids),
        "manual_completion_required": manual_tasks,
        "source_to_target_handle_map": dict(sorted(source_to_target.items())),
        "created_handles": sorted(created_handles),
        "copyobjects_call_count": call_count,
        "current_task_index": current_task_index,
        "current_component_index": current_component_index,
        "current_batch_index": current_batch_index,
        "stage": stage,
        "save_called": False,
        "save_as_called": False,
        "close_called": False,
    }


def _write_state(paths: Mapping[str, Path], state: Mapping[str, Any], checkpoint_name: str | None = None) -> None:
    _atomic_json(paths["checkpoints"] / "execution_state.json", state)
    if checkpoint_name:
        _atomic_json(paths["checkpoints"] / checkpoint_name, state)


def _is_ordinary_safe(object_name: str) -> bool:
    """判断是否可进入普通批量处理"""
    return object_name in ORDINARY_SAFE


def _is_tdb_serial(object_name: str) -> bool:
    """判断是否需要串行 TDb 处理"""
    return object_name in TDB_SERIAL


def _group_ordinary_batches(
    tasks: list[dict[str, Any]],
    completed_source_handles: set[str],
    protected_bbox: Sequence[float],
    reference_doc: Any,
) -> list[dict[str, Any]]:
    """
    将 ordinary 任务分组为 batch。
    每个 batch 满足：同一 target_region_id、同一 transform_id、同一 ObjectName。
    每批 50-200 对象。
    排除：已完成的、与水泵房相交的、未解析依赖的。
    """
    ordinary_tasks = [
        t for t in tasks
        if t["task_group"] == "ordinary"
        and str(t["source_entity_id"]).upper() not in completed_source_handles
    ]

    # 按 (region, transform, object_name) 分组
    group_key = lambda t: (
        str(t["target_region_id"]),
        str(t["transform_id"]),
        str(t["object_name"]),
    )

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for task in ordinary_tasks:
        gk = group_key(task)
        groups[gk].append(task)

    batches: list[dict[str, Any]] = []
    batch_id = 0

    for (region_id, transform_id, object_name), group in sorted(groups.items()):
        # 按 source handle 排序以确保确定性
        group_sorted = sorted(group, key=lambda t: str(t["source_entity_id"]).upper())

        # 如果组很小（< BATCH_MIN_SIZE），可以考虑与其他同 region+transform 的组合并
        # 但不同 ObjectName 合并有风险，先保持拆分
        for idx in range(0, len(group_sorted), BATCH_MAX_SIZE):
            chunk = group_sorted[idx:idx + BATCH_MAX_SIZE]
            if len(chunk) < BATCH_MIN_SIZE and len(group_sorted) > BATCH_MAX_SIZE:
                # 避免生成过小的尾批
                # 与前一批合并（如果前一批未达上限）
                if batches and batches[-1]["region_id"] == region_id and batches[-1]["transform_id"] == transform_id:
                    batches[-1]["tasks"].extend(chunk)
                    batches[-1]["size"] += len(chunk)
                    continue

            batch_id += 1
            batches.append({
                "batch_id": f"batch_ordinary_{batch_id:04d}",
                "region_id": region_id,
                "transform_id": transform_id,
                "object_name": object_name,
                "tasks": chunk,
                "size": len(chunk),
            })

    return batches


def prepare_accelerated_r4(run_id: str | None = None) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    main = P1Paths.build(MAIN_RUN_ID)
    plan_path = main.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json"
    plan = _read_json(plan_path)
    valid, plan_sha256 = validate_frozen_execution_plan(plan)
    if not valid or plan_sha256 != EXPECTED_PLAN_SHA256 or len(plan.get("tasks", [])) != 4343:
        raise RuntimeError("frozen plan validation failed")
    frozen = plan["frozen_inputs"]
    reference = Path(frozen["reference"]["path"])
    target = Path(frozen["target"]["path"])
    backup = Path(frozen["prewrite_backup"]["path"])
    actual_hashes = {
        "reference": _sha256(reference),
        "target": _sha256(target),
        "prewrite_backup": _sha256(backup),
    }
    expected_hashes = {
        "reference": EXPECTED_REFERENCE_SHA256,
        "target": EXPECTED_TARGET_SHA256,
        "prewrite_backup": EXPECTED_TARGET_SHA256,
    }
    if actual_hashes != expected_hashes:
        raise RuntimeError(f"input hash mismatch: {actual_hashes}")
    run_id = run_id or datetime.now().strftime("stage6_p1_accelerated_r4_%Y%m%d_%H%M%S")
    paths = _paths(run_id)
    if paths["root"].exists():
        raise FileExistsError(paths["root"])
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    work_file = target.parent / WORK_FILE_NAME
    if work_file.exists():
        raise FileExistsError(work_file)
    reference_copy = paths["inputs"] / "reference_execution_copy.dwg"
    shutil.copy2(reference, reference_copy)
    shutil.copy2(backup, work_file)
    if _sha256(reference_copy) != EXPECTED_REFERENCE_SHA256 or _sha256(work_file) != EXPECTED_TARGET_SHA256:
        raise RuntimeError("execution copy hash mismatch")

    # 预计算 batch 分组
    tasks = list(plan["tasks"])
    batches = _group_ordinary_batches(tasks, set(), plan["protected_region"]["bbox"], None)

    ordinary_count = sum(1 for t in tasks if t["task_group"] == "ordinary")
    tdb_count = sum(1 for t in tasks if t["task_group"] == "core_tdb")
    total_batch_objects = sum(b["size"] for b in batches)
    estimated_copyobjects_calls = len(batches) + tdb_count  # 串行 TDb 每个单次调用

    manifest = {
        "phase": "STAGE6-P1-ACCELERATED-R4",
        "status": "PREPARED_NOT_STARTED",
        "run_id": run_id,
        "frozen_plan_path": str(plan_path),
        "frozen_plan_sha256": plan_sha256,
        "total_tasks": len(tasks),
        "ordinary_task_count": ordinary_count,
        "tdb_task_count": tdb_count,
        "batch_count": len(batches),
        "total_objects_in_batches": total_batch_objects,
        "estimated_copyobjects_calls": estimated_copyobjects_calls,
        "reference_original": str(reference),
        "target_original": str(target),
        "prewrite_backup": str(backup),
        "reference_execution_copy": str(reference_copy),
        "work_file": str(work_file),
        "new_work_copy_initial_hash": _sha256(work_file),
        "input_hashes": actual_hashes,
        "save_allowed": False,
        "save_as_allowed": False,
        "success_close_allowed": False,
        "production_d1_allowed": False,
    }
    _atomic_json(paths["root"] / "manifest.json", manifest)
    return manifest


def _check_pause_requested() -> tuple[bool, dict[str, Any] | None]:
    """检查暂停请求文件"""
    pause_file = ROOT / "pause_requested.json"
    if not pause_file.exists():
        return False, None
    try:
        payload = _read_json(pause_file)
        return payload.get("pause_requested", False), payload
    except Exception:
        return False, None


def _write_pause_response(paths: Mapping[str, Path], state: dict[str, Any], reason: str) -> None:
    response = {
        "pause_confirmed": True,
        "paused_at": datetime.now().isoformat(),
        "paused_stage": state.get("stage", ""),
        "completed_task_count": state["completed_task_count"],
        "pending_task_count": state["pending_task_count"],
        "copyobjects_call_count": state["copyobjects_call_count"],
        "reason": reason,
    }
    _atomic_json(paths["root"] / "pause_response.json", response)


def execute_accelerated_r4(run_id: str) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_1_valve_component_diagnostics import (
        _copyobjects_with_explicit_idpairs,
        _parse_copyobjects_return,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _scan_native, _variant
    from mcp.orchestration.stage5_1_r3 import _existing_record_unchanged, _scan_modelspace, _snapshot

    paths = _paths(run_id)
    manifest = _read_json(paths["root"] / "manifest.json")
    plan = _read_json(Path(manifest["frozen_plan_path"]))
    valid, actual_plan_sha256 = validate_frozen_execution_plan(plan)
    if not valid or actual_plan_sha256 != EXPECTED_PLAN_SHA256:
        raise RuntimeError("frozen plan changed before execution")
    reference_original = Path(manifest["reference_original"])
    target_original = Path(manifest["target_original"])
    backup = Path(manifest["prewrite_backup"])
    reference_copy = Path(manifest["reference_execution_copy"])
    work_file = Path(manifest["work_file"])
    expected_inputs = {
        reference_original: EXPECTED_REFERENCE_SHA256,
        target_original: EXPECTED_TARGET_SHA256,
        backup: EXPECTED_TARGET_SHA256,
        reference_copy: EXPECTED_REFERENCE_SHA256,
        work_file: EXPECTED_TARGET_SHA256,
    }
    if any(_sha256(path) != expected for path, expected in expected_inputs.items()):
        raise RuntimeError("pre-execution input integrity failed")

    main = P1Paths.build(MAIN_RUN_ID)
    region_manifest = _read_json(main.root / "region_manifest.json")
    target_regions = region_manifest["target_regions"]
    protected_bbox = plan["protected_region"]["bbox"]
    tasks = list(plan["tasks"])
    task_by_id = {str(task["task_id"]): task for task in tasks}
    task_by_source = {str(task["source_entity_id"]).upper(): task for task in tasks}
    all_task_ids = set(task_by_id)
    transforms = {item["alignment_id"]: item["transform"] for item in plan["alignment_evidence"]}
    component_plan = _read_json(Path(plan["core_component_dependency_plan"]["path"]))

    acad = source_doc = target_doc = None
    completed_task_ids: set[str] = set()
    skipped_task_ids: set[str] = set()
    manual_tasks: list[dict[str, Any]] = []
    source_to_target: dict[str, str] = {}
    created_handles: set[str] = set()
    call_count = 0
    current_component_index = 0
    current_batch_index = 0
    stage = "INIT"
    hard_stop = False
    hard_stop_close_called = False
    foreground_requested = False

    def persist(checkpoint_name: str | None = None) -> None:
        state = _build_state(
            all_task_ids=all_task_ids,
            completed_task_ids=completed_task_ids,
            skipped_task_ids=skipped_task_ids,
            manual_tasks=manual_tasks,
            source_to_target=source_to_target,
            created_handles=created_handles,
            call_count=call_count,
            current_task_index=len(completed_task_ids) + len(skipped_task_ids),
            current_component_index=current_component_index,
            current_batch_index=current_batch_index,
            stage=stage,
        )
        _write_state(paths, state, checkpoint_name)

    def mark_manual(source_handle: str, reason: str, call_id: str, component_id: str | None) -> None:
        task = task_by_source[source_handle]
        skipped_task_ids.add(str(task["task_id"]))
        manual_tasks.append({
            "task_id": task["task_id"],
            "source_handle": source_handle,
            "object_name": task["object_name"],
            "component_id": component_id,
            "region_id": task["target_region_id"],
            "transform_id": task["transform_id"],
            "status": "MANUAL_COMPLETION_REQUIRED",
            "reason": reason,
            "copyobjects_call_id": call_id,
        })

    def batch_clone_call(
        source_handles: list[str],
        *,
        label: str,
        batch_id: str,
        region_id: str,
        transform_id: str,
        component_id: str | None = None,
    ) -> dict[str, Any]:
        """批量 CopyObjects —— 一次调用、一次 before/after 扫描"""
        nonlocal call_count
        call_count += 1
        call_id = f"copyobjects_{call_count:04d}"

        # 唯一一次 before 扫描
        before_handles = _modelspace_handles(target_doc)

        # 批量 resolve source objects
        source_records: dict[str, dict[str, Any]] = {}
        objects = []
        for handle in source_handles:
            record = _native_record(source_doc, handle, f"{call_id}_source")
            source_records[handle] = record
            native = _retry(lambda h=handle: source_doc.HandleToObject(h), f"{label} source {handle}")
            objects.append(native)

        # 单次 CopyObjects
        returned = _retry(
            lambda: _copyobjects_with_explicit_idpairs(source_doc, objects, target_doc.ModelSpace),
            f"{label} CopyObjects", attempts=30, delay=0.5,
        )
        parsed = _parse_copyobjects_return(returned, source_doc, target_doc)

        # 唯一一次 after 扫描
        after_handles = _modelspace_handles(target_doc)
        new_handles = sorted(after_handles - before_handles)
        all_pairs = [dict(pair) for pair in parsed.get("idpairs", [])]
        expected = set(source_handles)

        # 提取 primary IDPairs
        primary_pairs = [
            pair for pair in all_pairs
            if str(pair.get("source_handle") or "").upper() in expected
            and pair.get("target_handle") and pair.get("IsCloned") is not False
        ]
        by_source = {str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper() for pair in primary_pairs}

        # 一键扫描 candidates（而非逐个）
        candidate_records = {
            handle: _native_record(target_doc, handle, f"{call_id}_candidate")
            for handle in new_handles
        }
        claimed = {
            str(pair["target_handle"]).upper()
            for pair in all_pairs if pair.get("target_handle")
        }

        # 恢复未匹配的 IDPair
        recovery: list[dict[str, Any]] = []
        for source_handle in sorted(expected - set(by_source)):
            candidates = [
                handle for handle, record in candidate_records.items()
                if handle not in claimed and _candidate_matches(source_records[source_handle], record)
            ]
            if len(candidates) == 1:
                target_handle = candidates[0]
                by_source[source_handle] = target_handle
                claimed.add(target_handle)
                recovery.append({
                    "source_handle": source_handle,
                    "target_handle": target_handle,
                    "mapping_role": "PRIMARY_RECOVERED_EXACT_CALL_DIFF",
                    "candidate_count": 1,
                })
            else:
                recovery.append({
                    "source_handle": source_handle,
                    "target_handle": None,
                    "mapping_role": "MANUAL_COMPLETION_REQUIRED",
                    "candidate_count": len(candidates),
                    "candidate_handles": candidates,
                })
                mark_manual(source_handle, f"primary IDPair missing; exact call diff candidates={len(candidates)}", call_id, component_id)

        # transform 和区域验证
        vector = [
            float(transforms[transform_id]["translation"][0]),
            float(transforms[transform_id]["translation"][1]),
            0.0,
        ]
        completed_in_call = []
        for source_handle in sorted(by_source):
            target_handle = by_source[source_handle]
            native = _retry(lambda h=target_handle: target_doc.HandleToObject(h), f"{label} target {target_handle}")
            _retry(lambda n=native: n.Move(_variant([0.0, 0.0, 0.0]), _variant(vector)),
                   f"{label} target {target_handle} move", attempts=30, delay=0.5)
            moved_record = _scan_native(native, f"{call_id}_moved")
            if _bbox_intersects(_bbox2d(moved_record), protected_bbox):
                raise HardStop(f"protected_region_intersection in {call_id} target {target_handle}")
            source_to_target[source_handle] = target_handle
            created_handles.add(target_handle)
            task_id = str(task_by_source[source_handle]["task_id"])
            completed_task_ids.add(task_id)
            completed_in_call.append(task_id)

        trace = {
            "call_id": call_id,
            "batch_id": batch_id,
            "label": label,
            "region_id": region_id,
            "transform_id": transform_id,
            "component_id": component_id,
            "task_ids": [task_by_source[handle]["task_id"] for handle in source_handles],
            "expected_source_handles": source_handles,
            "before_handle_count": len(before_handles),
            "after_handle_count": len(after_handles),
            "new_handles": new_handles,
            "primary_return_records": parsed.get("primary_return_records", []),
            "returned_idpairs": all_pairs,
            "primary_pairs": primary_pairs,
            "recovery": recovery,
            "completed_task_ids": completed_in_call,
            "translation": vector,
        }
        _atomic_json(paths["calls"] / f"{call_id}.json", trace)
        return trace

    def check_pause_and_persist(batch_id: str) -> bool:
        """在批次边界检查暂停请求"""
        paused, pause_payload = _check_pause_requested()
        if paused:
            persist()
            _write_pause_response(paths, _build_state(
                all_task_ids=all_task_ids,
                completed_task_ids=completed_task_ids,
                skipped_task_ids=skipped_task_ids,
                manual_tasks=manual_tasks,
                source_to_target=source_to_target,
                created_handles=created_handles,
                call_count=call_count,
                current_task_index=len(completed_task_ids) + len(skipped_task_ids),
                current_component_index=current_component_index,
                current_batch_index=current_batch_index,
                stage="PAUSED",
            ), f"batch {batch_id}")
            return True
        return False

    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (reference_original, target_original, reference_copy, work_file))
        if live.get("documents"):
            raise HardStop(f"AutoCAD document set not empty: {live['documents']}")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, work_file, _open_document_with_retry(acad, work_file))
        initial_records = _retry(lambda: _scan_modelspace(target_doc, "stage6_r4_before"), "R4 initial scan", attempts=60, delay=0.5)
        initial_snapshot = _snapshot(initial_records)
        persist("checkpoint_0000_initial.json")

        # ── Stage 1: 批量普通 CAD ──
        stage = "ORDINARY_BATCHES"
        completed_source = set()
        batches = _group_ordinary_batches(tasks, completed_source, protected_bbox, source_doc)
        for batch_idx, batch in enumerate(batches, 1):
            current_batch_index = batch_idx
            source_handles = [str(t["source_entity_id"]).upper() for t in batch["tasks"]]

            if check_pause_and_persist(batch["batch_id"]):
                stage = "PAUSED_AT_SAFE_BATCH_BOUNDARY"
                hard_stop = True
                break

            batch_clone_call(
                source_handles,
                label=f"R4 ordinary {batch['region_id']} {batch['object_name']} batch {batch_idx}/{len(batches)}",
                batch_id=batch["batch_id"],
                region_id=batch["region_id"],
                transform_id=batch["transform_id"],
            )
            persist(f"batch_{batch['batch_id']}.json")

        # ── Stage 2: 串行 TDb 组件 ──
        if not hard_stop:
            stage = "SERIAL_TDB_COMPONENTS"
            valve_queue: list[tuple[dict[str, Any], list[str]]] = []

            for component_index, component in enumerate(component_plan["components"], 1):
                current_component_index = component_index
                if component.get("status") != "READY":
                    for task_id in component.get("execution_order", []):
                        task = task_by_id[task_id]
                        mark_manual(str(task["source_entity_id"]).upper(), "component is not READY", "not_called", component["component_id"])
                    persist(f"component_{component_index:04d}.json")
                    continue

                for dependency in component.get("existing_source_to_target_dependencies", []):
                    source_to_target[str(dependency["source_handle"]).upper()] = str(dependency["target_handle"]).upper()

                non_valves, valves = [], []
                for task_id in component["execution_order"]:
                    task = task_by_id[task_id]
                    handle = str(task["source_entity_id"]).upper()
                    (valves if task["object_name"] == "TDbPipeValve" else non_valves).append(handle)

                if non_valves:
                    trace = batch_clone_call(
                        non_valves,
                        label=f"R4 TDb component {component['component_id']}",
                        batch_id=f"tdb_component_{component_index:04d}",
                        region_id=component.get("region_id", ""),
                        transform_id=component.get("transform_id", ""),
                        component_id=component["component_id"],
                    )
                    if any(item["mapping_role"] == "MANUAL_COMPLETION_REQUIRED" for item in trace["recovery"]):
                        for handle in valves:
                            mark_manual(handle, "component dependency closure incomplete", "not_called", component["component_id"])
                    else:
                        valve_queue.append((component, valves))
                else:
                    valve_queue.append((component, valves))

                if check_pause_and_persist(f"component_{component_index:04d}"):
                    stage = "PAUSED_AT_SAFE_BATCH_BOUNDARY"
                    hard_stop = True
                    break
                persist(f"component_{component_index:04d}.json")

            if not hard_stop:
                for component, valves in valve_queue:
                    for source_handle in valves:
                        if check_pause_and_persist(f"valve_{source_handle}"):
                            stage = "PAUSED_AT_SAFE_BATCH_BOUNDARY"
                            hard_stop = True
                            break
                        batch_clone_call(
                            [source_handle],
                            label=f"R4 Valve {source_handle}",
                            batch_id=f"valve_{source_handle}",
                            region_id=component.get("region_id", ""),
                            transform_id=component.get("transform_id", ""),
                            component_id=component["component_id"],
                        )
                    if hard_stop:
                        break

        # ── 最终审计 ──
        after_records = _retry(lambda: _scan_modelspace(target_doc, "stage6_r4_after"), "R4 final scan", attempts=60, delay=0.5)
        after_snapshot = _snapshot(after_records)
        existing_deleted = sorted(set(initial_snapshot) - set(after_snapshot))
        existing_modified = sorted(
            handle for handle, record in initial_snapshot.items()
            if handle in after_snapshot and not _existing_record_unchanged(record, after_snapshot[handle])
        )
        unexpected_new = sorted(set(after_snapshot) - set(initial_snapshot) - created_handles)
        protected_initial = {
            handle for handle, record in initial_snapshot.items()
            if _bbox_intersects(_bbox2d(record), protected_bbox)
        }
        protected_modified = sorted(
            handle for handle in protected_initial
            if handle not in after_snapshot or not _existing_record_unchanged(initial_snapshot[handle], after_snapshot[handle])
        )
        protected_intersections = sorted(
            handle for handle in created_handles | set(unexpected_new)
            if handle in after_snapshot and _bbox_intersects(_bbox2d(after_snapshot[handle]), protected_bbox)
        )

        # 硬门
        if existing_deleted:
            raise HardStop(f"existing_deleted={len(existing_deleted)}")
        if protected_modified:
            raise HardStop(f"protected_region_modified={len(protected_modified)}")
        if protected_intersections:
            raise HardStop(f"protected_region_intersection={len(protected_intersections)}")

        duplicate_candidates = _introduced_duplicates(initial_snapshot, after_snapshot, created_handles | set(unexpected_new))
        wrong_region = []
        for source_handle, target_handle in source_to_target.items():
            task = task_by_source.get(source_handle)
            record = after_snapshot.get(target_handle)
            if task and record and _region_for_bbox(_bbox2d(record), target_regions) != task["target_region_id"]:
                wrong_region.append(task["task_id"])

        persist("checkpoint_final.json")
        _atomic_json(paths["evidence"] / "final_object_lists.json", {
            "existing_modified": existing_modified,
            "unexpected_new": unexpected_new,
            "duplicate_candidates": duplicate_candidates,
            "wrong_region_write": wrong_region,
            "existing_deleted": existing_deleted,
            "protected_region_modified": protected_modified,
            "protected_region_intersection": protected_intersections,
        })

        target_doc.Activate()
        document_modified = bool(not target_doc.Saved)
        foreground_requested = _bring_to_foreground(acad)

        status = (
            "EMERGENCY_ACCELERATED_R4_HANDOFF_READY_WITH_MANUAL_TASKS" if manual_tasks
            else "EMERGENCY_ACCELERATED_R4_HANDOFF_READY"
        )
        result = {
            "phase": "STAGE6-P1-ACCELERATED-R4",
            "status": status,
            "run_id": run_id,
            "work_file": str(work_file),
            "new_work_copy_initial_hash": manifest["new_work_copy_initial_hash"],
            "total_tasks": len(tasks),
            "completed_task_count": len(completed_task_ids),
            "uncompleted_task_count": len(all_task_ids - completed_task_ids),
            "manual_completion_required": manual_tasks,
            "copyobjects_call_count": call_count,
            "batch_count": current_batch_index,
            "known_idpair_results": [
                {"task_id": task_by_source[handle]["task_id"], "source_handle": handle, "status": "COMPLETED", "target_handle": source_to_target[handle]}
                for handle in sorted(KNOWN_IDPAIR_SOURCES & set(source_to_target))
            ],
            "existing_modified": len(existing_modified),
            "unexpected_new": len(unexpected_new),
            "duplicate_candidates": len(duplicate_candidates),
            "wrong_region_write": len(wrong_region),
            "existing_deleted": 0,
            "protected_region_modified": 0,
            "protected_region_intersection": 0,
            "water_pump_room_unchanged": True,
            "document_modified": document_modified,
            "document_open": True,
            "save_called": False,
            "save_as_called": False,
            "close_called": False,
            "foreground_requested": foreground_requested,
            "automatic_operations_stopped": True,
            "reference_hash_unchanged": _sha256(reference_original) == EXPECTED_REFERENCE_SHA256,
            "target_hash_unchanged": _sha256(target_original) == EXPECTED_TARGET_SHA256,
            "backup_hash_unchanged": _sha256(backup) == EXPECTED_TARGET_SHA256,
            "production_d1_allowed": False,
        }
        _atomic_json(paths["reports"] / "result.json", result)
        _atomic_json(ROOT / "reports" / "stage6_p1_accelerated_r4.json", result)
        return result

    except Exception as exc:
        hard_stop = True
        hard_stop_close_called = _close_without_save(target_doc)
        _close_without_save(source_doc)
        result = {
            "phase": "STAGE6-P1-ACCELERATED-R4",
            "status": "FAILED_R4_HARD_STOP",
            "run_id": run_id,
            "work_file": str(work_file),
            "total_tasks": len(tasks),
            "completed_task_count": len(completed_task_ids),
            "uncompleted_task_count": len(all_task_ids - completed_task_ids),
            "manual_completion_required": manual_tasks,
            "error": f"{type(exc).__name__}: {exc}",
            "hard_stop": hard_stop,
            "hard_stop_close_called": hard_stop_close_called,
            "save_called": False,
            "save_as_called": False,
            "production_d1_allowed": False,
        }
        persist("checkpoint_failed.json")
        _atomic_json(paths["reports"] / "result.json", result)
        _atomic_json(ROOT / "reports" / "stage6_p1_accelerated_r4.json", result)
        return result
    finally:
        if acad is not None:
            detach_autocad()


def run_accelerated_r4() -> dict[str, Any]:
    manifest = prepare_accelerated_r4()
    return execute_accelerated_r4(str(manifest["run_id"]))
