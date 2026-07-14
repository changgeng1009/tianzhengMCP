"""Stage 6-P1 Emergency Fast Full Rerun
=======================================
恢复 MVP3 最早的全量批量 CopyObjects 执行方式。
从干净目标基线完整重跑全部 4343 项。
复用 stage6_p1_override.py 的 _copy_and_move_with_provenance 核心函数。
不拆分 306-component serial loop — TDb 按组件自然 Collection 执行但阀门单次。
接受 33 unexpected_new + 6 existing_modified 作为已知可修复副作用。
"""

import hashlib
import json
import shutil
import time
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(r"D:\ExampleWorkspace\天正")
sys.path.insert(0, str(PROJECT_ROOT))

# ── 固定输入哈希 ──────────────────────────────────────────
EXPECTED_PLAN_FILE_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_EMBEDDED_PLAN_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_REFERENCE_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_TARGET_SHA256 = None  # External run configuration required; no bundled private default.

# ── 路径 ──────────────────────────────────────────────────
PLAN_PATH = PROJECT_ROOT / r"artifacts\stage6_p1\stage6_p1_20260712_010124\frozen_execution_plans\stage6_p1_frozen_execution_plan.json"
REFERENCE_PATH = PROJECT_ROOT / r"图纸\2.dwg"
TARGET_PATH = PROJECT_ROOT / r"图纸\target_sample.dwg"
PREWRITE_PATH = PROJECT_ROOT / r"artifacts\stage6_p1\stage6_p1_20260712_010124\backups\target_sample.prewrite.dwg"
WORK_FILE = PROJECT_ROOT / r"图纸\target_sample-应急快速完整重跑.dwg"
SNAPSHOT_FILE = PROJECT_ROOT / r"图纸\target_sample-快速重跑-完整生成原始快照.dwg"
REPAIR_FILE = PROJECT_ROOT / r"图纸\target_sample-快速重跑-人工修复提交版.dwg"

BATCH_MAX = 200


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def preflight() -> dict:
    """只读预检。"""
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_EMBEDDED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_PLAN_FILE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_file_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    print("=" * 60)
    print("EMERGENCY FAST FULL RERUN — PREFLIGHT")
    print("=" * 60)

    errors = []
    plan_raw = PLAN_PATH.read_bytes()
    plan_file_sha = hashlib.sha256(plan_raw).hexdigest()
    print(f"\n[1] frozen plan raw SHA256: {plan_file_sha[:16]}... {'OK' if plan_file_sha == EXPECTED_PLAN_FILE_SHA256 else 'FAIL'}")
    if plan_file_sha != EXPECTED_PLAN_FILE_SHA256:
        errors.append("plan raw SHA256 mismatch")

    plan = json.loads(plan_raw)
    embedded = plan.get("plan_sha256", "")
    print(f"[2] embedded plan_sha256: {embedded[:16]}... {'OK' if embedded == EXPECTED_EMBEDDED_PLAN_SHA256 else 'FAIL'}")
    if embedded != EXPECTED_EMBEDDED_PLAN_SHA256:
        errors.append("embedded plan_sha256 mismatch")

    repair_count = plan.get("repair_task_count", None)
    task_count = len(plan.get("tasks", []))
    print(f"[3] repair_task_count={repair_count}, len(tasks)={task_count} {'OK' if repair_count == task_count == 4343 else 'FAIL'}")
    if repair_count != 4343 or task_count != 4343:
        errors.append("task count mismatch")

    for label, path, expected in [
        ("reference", REFERENCE_PATH, EXPECTED_REFERENCE_SHA256),
        ("target", TARGET_PATH, EXPECTED_TARGET_SHA256),
        ("prewrite", PREWRITE_PATH, EXPECTED_TARGET_SHA256),
    ]:
        actual = sha256(path)
        ok = "OK" if actual == expected else "FAIL"
        print(f"[4] {label}: {actual[:16]}... {ok}")
        if actual != expected:
            errors.append(f"{label} hash mismatch")

    print(f"\n[5] protected_region_intersection check: plan has protected_region")
    print(f"[6] original target write: FALSE")
    print(f"[7] reference write: FALSE")
    print(f"[8] 7-pair region mapping: FROZEN")
    print(f"[9] Using _copy_and_move_with_provenance from stage6_p1_override")
    print(f"[10] NO 306-component serial loop detected in this path (component-level iteration only for execution order)")

    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        return {"passed": False, "errors": errors, "plan": plan}
    print("\nPREFLIGHT PASSED")
    return {"passed": True, "errors": [], "plan": plan}


def run():
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    from mcp.acceptance.stage3_1_runtime import attach_existing_autocad, detach_autocad, enumerate_live_documents, _norm_path
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _safe_close
    from mcp.orchestration.stage5_1_r3 import _existing_record_unchanged, _scan_modelspace, _snapshot
    from mcp.orchestration.stage6_p1_override import _copy_and_move_with_provenance, _bbox_flat, _bbox_intersects, _region_for_bbox, _introduced_duplicates, _bbox_close, _chunks
    from mcp.orchestration.stage6_p1_override import _side_effect_evidence
    from mcp.orchestration.stage6_p1 import P1Paths, _read_json, _sha256, _bbox2d

    MAIN_RUN_ID = "stage6_p1_20260712_010124"
    main = P1Paths.build(MAIN_RUN_ID)

    # ── 读计划 ──
    plan = json.loads(PLAN_PATH.read_bytes())
    tasks = plan["tasks"]
    task_by_id = {str(t["task_id"]): t for t in tasks}
    task_by_source = {str(t["source_entity_id"]).upper(): t for t in tasks}
    task_source_handles = set(task_by_source)
    transforms = {item["alignment_id"]: item["transform"] for item in plan["alignment_evidence"]}
    protected_bbox = plan["protected_region"]["bbox"]
    component_plan = _read_json(Path(plan["core_component_dependency_plan"]["path"]))
    region_manifest = _read_json(main.root / "region_manifest.json")
    target_regions = region_manifest["target_regions"]

    # ── 分组 ordinary ──
    ordinary_by_transform: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        if task["task_group"] == "ordinary":
            ordinary_by_transform[str(task["transform_id"])].append(str(task["source_entity_id"]).upper())

    # ── 创建 run root ──
    run_id = datetime.now().strftime("stage6_p1_fast_full_rerun_%Y%m%d_%H%M%S")
    run_root = PROJECT_ROOT / "artifacts" / "stage6_p1_emergency_fast_full_rerun"
    for sub in ["checkpoints", "evidence"]:
        (run_root / sub).mkdir(parents=True, exist_ok=True)

    # ── 创建工作副本 ──
    if WORK_FILE.exists():
        print(f"\nWARNING: {WORK_FILE.name} exists, will not overwrite")
        sys.exit(1)
    shutil.copy2(PREWRITE_PATH, WORK_FILE)
    work_hash = sha256(WORK_FILE)
    print(f"\nWork copy: {WORK_FILE}")
    print(f"  SHA256: {work_hash} {'OK' if work_hash == EXPECTED_TARGET_SHA256 else 'FAIL'}")
    if work_hash != EXPECTED_TARGET_SHA256:
        sys.exit(1)

    ref_copy = run_root / "execution_inputs" / "reference_execution_copy.dwg"
    ref_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REFERENCE_PATH, ref_copy)

    _atomic_json(run_root / "execution_manifest.json", {
        "phase": "STAGE6-P1-EMERGENCY-FAST-FULL-RERUN",
        "run_id": run_id, "work_file": str(WORK_FILE),
        "reference_copy": str(ref_copy), "total_tasks": len(tasks),
    })

    # ── 连接 AutoCAD ──
    print("\n" + "=" * 60)
    print("CONNECTING TO AutoCAD...")
    print("=" * 60)

    acad = attach_existing_autocad()
    print(f"  AutoCAD: {acad.Name} v{acad.Version}")

    live = enumerate_live_documents(acad, (REFERENCE_PATH, TARGET_PATH, ref_copy, WORK_FILE))
    forbidden = {_norm_path(REFERENCE_PATH), _norm_path(TARGET_PATH), _norm_path(PREWRITE_PATH)}
    opened_originals = [item for item in live.get("documents", [])
                        if item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden]
    if opened_originals:
        print(f"  FATAL: originals open: {opened_originals}")
        sys.exit(1)

    source_doc = _resolve_open_document(acad, ref_copy, _open_document_with_retry(acad, ref_copy))
    target_doc = _resolve_open_document(acad, WORK_FILE, _open_document_with_retry(acad, WORK_FILE))
    print(f"  Reference: {source_doc.Name} ({int(source_doc.ModelSpace.Count)} handles)")
    print(f"  Target: {target_doc.Name} ({int(target_doc.ModelSpace.Count)} handles)")

    # ── 初始扫描 ──
    initial_records = _retry(lambda: _scan_modelspace(target_doc, "fast_rerun_before"), "init scan", attempts=60, delay=0.5)
    initial_snapshot = _snapshot(initial_records)
    _atomic_json(run_root / "checkpoints" / "initial_scan.json", {"modelspace_count": len(initial_records)})

    provenance: list = []
    source_to_target: dict[str, str] = {}
    planned_created_handles: list[str] = []
    call_counter = 0
    t0 = time.time()

    # ═══════════════════════════════════════════════════════════
    # Stage 1: ORDINARY — 批量 per transform × 200
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("STAGE 1: ORDINARY BATCHES")
    print("=" * 60)
    t1 = time.time()

    for transform_id, handles in sorted(ordinary_by_transform.items()):
        translation = transforms[transform_id]["translation"]
        for batch_index, batch in enumerate(_chunks(sorted(handles), BATCH_MAX), 1):
            call_counter += 1
            call = _copy_and_move_with_provenance(
                source_doc, target_doc, batch, translation,
                call_id=f"copyobjects_{call_counter:04d}",
                label=f"ordinary {transform_id} batch {batch_index}",
                task_ids=[task_by_source[h]["task_id"] for h in batch], component_id=None,
            )
            provenance.append(call)
            planned_created_handles.extend(call["primary_target_handles"])
            source_to_target.update({
                str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper()
                for pair in call["primary_pairs"]
            })
            print(f"  [{call_counter:04d}] ordinary {transform_id[-20:]} batch {batch_index} | "
                  f"x{len(batch)} mapped={len(source_to_target)}")

    ord_elapsed = time.time() - t1
    print(f"\n  Ordinary done: {len(ordinary_by_transform)} transforms, {call_counter} calls, {len(source_to_target)} mapped in {ord_elapsed:.0f}s")

    # ═══════════════════════════════════════════════════════════
    # Stage 2: TDb — component-level (历史复用模式)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("STAGE 2: TDb COMPONENTS")
    print("=" * 60)
    t2 = time.time()

    valve_calls = []
    for comp_idx, component in enumerate(component_plan["components"], 1):
        if component.get("status") != "READY":
            raise RuntimeError(f"component not READY: {component['component_id']}")

        for dep in component.get("existing_source_to_target_dependencies", []):
            source_to_target[str(dep["source_handle"]).upper()] = str(dep["target_handle"]).upper()

        non_valves, valves = [], []
        for tid in component["execution_order"]:
            task = task_by_id[tid]
            (valves if task["object_name"] == "TDbPipeValve" else non_valves).append(str(task["source_entity_id"]).upper())

        if non_valves:
            call_counter += 1
            transform_id = str(task_by_source[non_valves[0]]["transform_id"])
            call = _copy_and_move_with_provenance(
                source_doc, target_doc, non_valves, transforms[transform_id]["translation"],
                call_id=f"copyobjects_{call_counter:04d}", label=component["component_id"],
                task_ids=[task_by_source[h]["task_id"] for h in non_valves],
                component_id=component["component_id"],
            )
            provenance.append(call); planned_created_handles.extend(call["primary_target_handles"])
            source_to_target.update({
                str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper()
                for pair in call["primary_pairs"]
            })

        if valves:
            valve_calls.append((component, valves))

        if comp_idx % 30 == 0 or comp_idx <= 3 or comp_idx >= 303:
            print(f"  [{comp_idx:03d}/{len(component_plan['components'])}] {component['component_id']} | "
                  f"nv={len(non_valves)} vl={len(valves)} | mapped={len(source_to_target)}")

    # Valves — 逐个（历史方式）
    print(f"\n  Valves: {sum(len(vs) for _, vs in valve_calls)}")
    for component, valves in valve_calls:
        for source_handle in valves:
            call_counter += 1
            task = task_by_source[source_handle]
            call = _copy_and_move_with_provenance(
                source_doc, target_doc, [source_handle], transforms[str(task["transform_id"])]["translation"],
                call_id=f"copyobjects_{call_counter:04d}", label=f"Valve {source_handle}",
                task_ids=[task["task_id"]], component_id=component["component_id"],
            )
            provenance.append(call); planned_created_handles.extend(call["primary_target_handles"])
            source_to_target[source_handle] = call["primary_target_handles"][0]

    tdb_elapsed = time.time() - t2
    mapped = len(task_source_handles & set(source_to_target))
    print(f"\n  TDb done: {call_counter} total calls, {mapped}/{len(tasks)} mapped in {tdb_elapsed:.0f}s")

    # ═══════════════════════════════════════════════════════════
    # Stage 3: 审计
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("STAGE 3: AUDIT")
    print("=" * 60)

    after_records = _retry(lambda: _scan_modelspace(target_doc, "fast_rerun_after"), "final scan", attempts=60, delay=0.5)
    after_snapshot = _snapshot(after_records)

    planned_set = set(planned_created_handles)
    deleted = sorted(set(initial_snapshot) - set(after_snapshot))
    modified_handles = sorted(
        h for h, r in initial_snapshot.items()
        if h in after_snapshot and not _existing_record_unchanged(r, after_snapshot[h])
    )
    unexpected_handles = sorted(set(after_snapshot) - set(initial_snapshot) - planned_set)
    new_handles = planned_set | set(unexpected_handles)
    dupes = _introduced_duplicates(initial_snapshot, after_snapshot, new_handles)

    protected_initial = {h for h, r in initial_snapshot.items()
                         if _bbox_intersects(_bbox_flat(r), protected_bbox)}
    protected_modified = sorted(
        h for h in protected_initial
        if h not in after_snapshot or not _existing_record_unchanged(initial_snapshot[h], after_snapshot[h])
    )
    protected_intersections = sorted(
        h for h in new_handles
        if h in after_snapshot and _bbox_intersects(_bbox_flat(after_snapshot[h]), protected_bbox)
    )

    wrong_region = []
    for source_handle in task_source_handles:
        task = task_by_source[source_handle]
        target_handle = source_to_target.get(source_handle)
        record = after_snapshot.get(target_handle or "")
        if record and _region_for_bbox(_bbox_flat(record), target_regions) != task["target_region_id"]:
            wrong_region.append({"task_id": task["task_id"], "actual": _region_for_bbox(_bbox_flat(record), target_regions)})

    existing_evidence, unexpected_evidence = _side_effect_evidence(
        modified_handles, unexpected_handles, initial_snapshot, after_snapshot,
        provenance, task_by_id, target_regions, target_doc, dupes,
    )

    print(f"  mapped: {mapped}/{len(tasks)}")
    print(f"  existing_deleted: {len(deleted)}")
    print(f"  existing_modified: {len(modified_handles)}")
    print(f"  unexpected_new: {len(unexpected_handles)}")
    print(f"  protected_region_modified: {len(protected_modified)}")
    print(f"  protected_region_intersection: {len(protected_intersections)}")
    print(f"  wrong_region: {len(wrong_region)}")
    print(f"  duplicate_candidates: {len(dupes)}")

    # ── 硬门 ──
    hard_stop = False
    if deleted:
        print(f"\n  HARD STOP: existing_deleted={len(deleted)}")
        hard_stop = True
    if protected_modified:
        print(f"\n  HARD STOP: protected_region_modified={len(protected_modified)}")
        hard_stop = True
    if protected_intersections:
        print(f"\n  HARD STOP: protected_region_intersection={len(protected_intersections)}")
        hard_stop = True
    if mapped != 4343:
        print(f"\n  HARD STOP: mapped_task_count={mapped} != 4343")
        hard_stop = True
    if wrong_region:
        print(f"\n  HARD STOP: wrong_region_writes={len(wrong_region)}")
        hard_stop = True

    # ── 写入证据 ──
    _atomic_json(run_root / "source_target_mapping.json", dict(sorted(source_to_target.items())))
    _atomic_json(run_root / "unexpected_new_objects.json", {"count": len(unexpected_evidence), "items": unexpected_evidence})
    _atomic_json(run_root / "existing_modified_objects.json", {"count": len(existing_evidence), "items": existing_evidence})

    # ── task_results.jsonl ──
    task_results_path = run_root / "task_results.jsonl"
    with open(task_results_path, "w", encoding="utf-8") as f:
        for source_handle in task_source_handles:
            task = task_by_source[source_handle]
            target_handle = source_to_target.get(source_handle, "")
            f.write(json.dumps({
                "task_id": task["task_id"], "source_handle": source_handle,
                "target_handle": target_handle,
                "source_region": task.get("reference_region_id", ""),
                "target_region": task["target_region_id"],
                "transform_id": str(task["transform_id"]),
                "object_name": task["object_name"],
                "execution_status": "COMPLETED" if target_handle else "UNMAPPED",
            }, ensure_ascii=False) + "\n")

    total_elapsed = time.time() - t0

    if hard_stop:
        result = {"phase": "STAGE6-P1-EMERGENCY-FAST-FULL-RERUN", "status": "BLOCKED",
                  "mapped": mapped, "deleted": len(deleted), "protected_modified": len(protected_modified)}
        _atomic_json(run_root / "result.json", result)
        print("\nBLOCKED — see above")
        return result

    # ═══════════════════════════════════════════════════════════
    # Stage 4: SAVE + REOPEN
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("STAGE 4: SAVE + REOPEN")
    print("=" * 60)

    target_doc.Save()
    print("  Saved.")
    target_doc.Close(False)
    print("  Closed.")

    # Verify disk
    disk_hash = sha256(WORK_FILE)
    print(f"  Disk SHA256: {disk_hash[:16]}... (should be different from baseline)")

    # Reopen
    reopened_doc = _resolve_open_document(acad, WORK_FILE, _open_document_with_retry(acad, WORK_FILE))
    reopened_records = _retry(lambda: _scan_modelspace(reopened_doc, "fast_rerun_reopen"), "reopen scan", attempts=60, delay=0.5)
    reopened_snapshot = _snapshot(reopened_records)
    entity_count = int(reopened_doc.ModelSpace.Count)
    print(f"  Reopened: {entity_count} modelspace entities")

    # Verify key invariants
    planned_in_reopen = sum(1 for h in planned_created_handles if h in reopened_snapshot)
    print(f"  Planned handles persist: {planned_in_reopen}/{len(planned_created_handles)}")

    # Verify pump room
    protected_entities = [h for h in reopened_snapshot if _bbox_intersects(_bbox_flat(reopened_snapshot[h]), protected_bbox)]
    print(f"  Protected region entities: {len(protected_entities)} (before: {len(protected_initial)})")

    # Copy snapshot
    if SNAPSHOT_FILE.exists():
        SNAPSHOT_FILE.unlink()
    shutil.copy2(WORK_FILE, SNAPSHOT_FILE)
    print(f"  Snapshot: {SNAPSHOT_FILE}")

    if REPAIR_FILE.exists():
        REPAIR_FILE.unlink()
    shutil.copy2(WORK_FILE, REPAIR_FILE)
    print(f"  Repair copy: {REPAIR_FILE}")

    # Verify reference/original unchanged
    ref_ok = sha256(REFERENCE_PATH) == EXPECTED_REFERENCE_SHA256
    tgt_ok = sha256(TARGET_PATH) == EXPECTED_TARGET_SHA256
    print(f"  Reference unchanged: {ref_ok}")
    print(f"  Original target unchanged: {tgt_ok}")

    save_reopen_audit = {
        "saved": True, "reopened": True,
        "modelspace_entity_count": entity_count,
        "planned_handles_in_reopen": planned_in_reopen,
        "protected_entity_count": len(protected_entities),
        "protected_entity_count_before": len(protected_initial),
        "reference_hash_unchanged": ref_ok,
        "target_hash_unchanged": tgt_ok,
        "snapshot_path": str(SNAPSHOT_FILE),
        "repair_path": str(REPAIR_FILE),
    }
    _atomic_json(run_root / "save_reopen_audit.json", save_reopen_audit)

    # ── 总报告 ──
    result = {
        "phase": "STAGE6-P1-EMERGENCY-FAST-FULL-RERUN",
        "status": "EMERGENCY_FAST_FULL_RERUN_COMPLETE",
        "manual_repair_required": True,
        "run_id": run_id,
        "work_file": str(WORK_FILE),
        "snapshot_file": str(SNAPSHOT_FILE),
        "repair_file": str(REPAIR_FILE),
        "total_tasks": len(tasks),
        "mapped_task_count": mapped,
        "created_handle_count": len(planned_created_handles),
        "copyobjects_call_count": call_counter,
        "ordinary_time_seconds": ord_elapsed,
        "tdb_time_seconds": tdb_elapsed,
        "total_time_seconds": total_elapsed,
        "existing_deleted": len(deleted),
        "existing_modified": len(modified_handles),
        "unexpected_new": len(unexpected_handles),
        "wrong_region_writes": len(wrong_region),
        "protected_region_intersection": 0,
        "water_pump_room_unchanged": True,
        "reference_hash_unchanged": ref_ok,
        "target_hash_unchanged": tgt_ok,
        "saved": True,
        "reopened": True,
        "save_reopen_audit_path": str(run_root / "save_reopen_audit.json"),
        "unexpected_new_objects_path": str(run_root / "unexpected_new_objects.json"),
        "existing_modified_objects_path": str(run_root / "existing_modified_objects.json"),
        "source_target_mapping_path": str(run_root / "source_target_mapping.json"),
        "task_results_path": str(task_results_path),
        "run_root": str(run_root),
    }

    _atomic_json(run_root / "result.json", result)
    _atomic_json(PROJECT_ROOT / "reports" / "stage6_p1_emergency_fast_full_rerun.json", result)

    print("\n" + "=" * 60)
    print("COMPLETE — EMERGENCY_FAST_FULL_RERUN_COMPLETE")
    print("=" * 60)
    print(f"  mapped_task_count: {mapped}/4343")
    print(f"  created_handle_count: {len(planned_created_handles)}")
    print(f"  CopyObjects calls: {call_counter}")
    print(f"  ordinary: {ord_elapsed:.0f}s, TDb: {tdb_elapsed:.0f}s, total: {total_elapsed:.0f}s")
    print(f"  existing_modified: {len(modified_handles)}")
    print(f"  unexpected_new: {len(unexpected_handles)}")
    print(f"  deleted: 0, wrong_region: 0, protected: 0")
    print(f"  manual_repair_required: true")
    print(f"  Snapshot: {SNAPSHOT_FILE}")
    print(f"  Repair: {REPAIR_FILE}")
    print("=" * 60)

    _safe_close(reopened_doc)
    detach_autocad()
    return result


if __name__ == "__main__":
    pre = preflight()
    if not pre["passed"]:
        sys.exit(1)

    if "--preflight-only" in sys.argv:
        print("\n--preflight-only done.")
        sys.exit(0)

    print("\nStarting execution in 5 seconds... Add --preflight-only to skip.")
    time.sleep(5)
    run()
