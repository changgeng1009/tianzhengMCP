"""R4 Accelerated Emergency Execution Launcher
=============================================
通过 pywin32 COM 连接已打开的 AutoCAD 执行 R4 批量 CopyObjects。
所有路径使用 Windows 原生格式。

用法:
  python run_stage6_p1_accelerated_r4.py --preflight-only   # 仅预检，不连 AutoCAD
  python run_stage6_p1_accelerated_r4.py                     # 完整执行
"""

import sys
import json
import time
import hashlib
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Ensure the project root is on sys.path
PROJECT_ROOT = Path(r"D:\ExampleWorkspace\天正")
sys.path.insert(0, str(PROJECT_ROOT))

# ── Paths ───────────────────────────────────────────────────
PLAN_PATH = PROJECT_ROOT / r"artifacts\stage6_p1\stage6_p1_20260712_010124\frozen_execution_plans\stage6_p1_frozen_execution_plan.json"
BATCH_PLAN_PATH = PROJECT_ROOT / r"artifacts\stage6_p1_accelerated_r4\batch_plan.json"

REFERENCE_PATH = PROJECT_ROOT / r"图纸\2.dwg"
TARGET_PATH = PROJECT_ROOT / r"图纸\target_sample.dwg"
PREWRITE_PATH = PROJECT_ROOT / r"artifacts\stage6_p1\stage6_p1_20260712_010124\backups\target_sample.prewrite.dwg"
R4_WORK_FILE = PROJECT_ROOT / r"图纸\target_sample-应急提交版-R4.dwg"

# ── 三个独立的哈希常量 ─────────────────────────────────────
EXPECTED_PLAN_FILE_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_EMBEDDED_PLAN_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_BATCH_PLAN_FILE_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_REFERENCE_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_TARGET_SHA256 = None  # External run configuration required; no bundled private default.

ORDINARY_SAFE = frozenset({
    "AcDbLine", "AcDbCircle", "AcDbArc", "AcDbPolyline",
    "AcDbText", "AcDbMText",
})


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _preflight() -> dict:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_BATCH_PLAN_FILE_SHA256 = require_parameter('scripts.run_stage6_p1_accelerated_r4.expected_batch_plan_file_sha256', 'sha256')
    EXPECTED_EMBEDDED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_PLAN_FILE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_file_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    errors = []
    stats = {}
    print("=" * 60)
    print("R4 PREFLIGHT — READ-ONLY VALIDATION")
    print("=" * 60)

    print("\n[1] DWG file hashes")
    for label, path, expected in [
        ("reference", REFERENCE_PATH, EXPECTED_REFERENCE_SHA256),
        ("target", TARGET_PATH, EXPECTED_TARGET_SHA256),
        ("prewrite", PREWRITE_PATH, EXPECTED_TARGET_SHA256),
        ("R4 work", R4_WORK_FILE, EXPECTED_TARGET_SHA256),
    ]:
        actual = sha256(path)
        ok = "OK" if actual == expected else "FAIL"
        print(f"  [{ok}] {label}: {actual[:16]}...")
        if not ok:
            errors.append(f"DWG hash mismatch: {label}")
    stats["dwg_ok"] = not bool(errors)

    print("\n[2] Frozen plan raw bytes SHA256")
    plan_raw = PLAN_PATH.read_bytes()
    plan_file_sha = hashlib.sha256(plan_raw).hexdigest()
    stats["plan_file_sha256"] = plan_file_sha
    verify2 = plan_file_sha == EXPECTED_PLAN_FILE_SHA256
    print(f"  [{'OK' if verify2 else 'FAIL'}] {plan_file_sha}")
    if not verify2:
        errors.append("Plan file SHA256 mismatch")

    print("\n[3] Embedded plan_sha256")
    plan = json.loads(plan_raw)
    embedded_sha = plan.get("plan_sha256", "")
    stats["embedded_plan_sha256"] = embedded_sha
    verify3 = embedded_sha == EXPECTED_EMBEDDED_PLAN_SHA256
    print(f"  [{'OK' if verify3 else 'FAIL'}] {embedded_sha}")
    if not verify3:
        errors.append("Embedded plan_sha256 mismatch")

    print("\n[4] repair_task_count / len(tasks)")
    repair_count = plan.get("repair_task_count", None)
    actual_count = len(plan.get("tasks", []))
    stats["repair_task_count"] = repair_count
    stats["len_tasks"] = actual_count
    verify4a = repair_count == 4343
    verify4b = actual_count == 4343
    print(f"  [{'OK' if verify4a else 'FAIL'}] repair_task_count={repair_count}")
    print(f"  [{'OK' if verify4b else 'FAIL'}] len(tasks)={actual_count}")
    if not verify4a:
        errors.append(f"repair_task_count={repair_count}, expected 4343")
    if not verify4b:
        errors.append(f"len(tasks)={actual_count}, expected 4343")

    print("\n[5] task_id uniqueness")
    tasks = list(plan["tasks"])
    task_ids = [str(t.get("task_id", "")) for t in tasks]
    empty_ids = [tid for tid in task_ids if not tid]
    unique_ids = len(set(task_ids))
    stats["unique_task_ids"] = unique_ids
    verify5a = not empty_ids
    verify5b = unique_ids == 4343
    print(f"  [{'OK' if verify5a else 'FAIL'}] empty task_ids: {len(empty_ids)}")
    print(f"  [{'OK' if verify5b else 'FAIL'}] unique: {unique_ids}")
    if not verify5a:
        errors.append(f"{len(empty_ids)} empty task_ids")
    if not verify5b:
        errors.append(f"Duplicate task_ids: {unique_ids}/4343 unique")

    print("\n[6] Batch plan raw bytes SHA256")
    batch_raw = BATCH_PLAN_PATH.read_bytes()
    batch_sha = hashlib.sha256(batch_raw).hexdigest()
    stats["batch_plan_file_sha256"] = batch_sha
    verify6 = batch_sha == EXPECTED_BATCH_PLAN_FILE_SHA256
    print(f"  [{'OK' if verify6 else 'FAIL'}] {batch_sha}")
    if not verify6:
        errors.append("Batch plan SHA256 mismatch")

    print("\n[7] Batch plan task set validation")
    batch_plan = json.loads(batch_raw)
    bp_ord = batch_plan.get("ordinary_task_count", -1)
    bp_tdb = batch_plan.get("tdb_task_count", -1)
    bp_batches = batch_plan.get("batches", [])
    stats["batch_plan_ordinary_count"] = bp_ord
    stats["batch_plan_tdb_count"] = bp_tdb

    verify7a = bp_ord == 3245
    verify7b = bp_tdb == 1098
    verify7c = bp_ord + bp_tdb == 4343
    print(f"  [{'OK' if verify7a else 'FAIL'}] ordinary_task_count={bp_ord}")
    print(f"  [{'OK' if verify7b else 'FAIL'}] tdb_task_count={bp_tdb}")
    print(f"  [{'OK' if verify7c else 'FAIL'}] ordinary+tdb={bp_ord+bp_tdb}")
    if not verify7a:
        errors.append(f"batch_plan ordinary_task_count={bp_ord}")
    if not verify7b:
        errors.append(f"batch_plan tdb_task_count={bp_tdb}")
    if not verify7c:
        errors.append(f"batch_plan ordinary+tdb={bp_ord+bp_tdb}")

    batch_task_ids = []
    for b in bp_batches:
        batch_task_ids.extend(b.get("task_ids", []))
    stats["batch_flattened_count"] = len(batch_task_ids)
    batch_unique = len(set(batch_task_ids))

    verify7d = len(batch_task_ids) == 3245
    verify7e = batch_unique == 3245
    print(f"  [{'OK' if verify7d else 'FAIL'}] flattened={len(batch_task_ids)}")
    print(f"  [{'OK' if verify7e else 'FAIL'}] unique={batch_unique}")
    if not verify7d:
        errors.append(f"Flattened count={len(batch_task_ids)}")
    if not verify7e:
        errors.append(f"Batch duplicates: {batch_unique}/3245")

    all_task_id_set = {str(t.get("task_id")) for t in tasks}
    batch_set = set(batch_task_ids)
    unknown_in_batch = batch_set - all_task_id_set
    stats["unknown_in_batch"] = len(unknown_in_batch)
    verify7f = not unknown_in_batch
    print(f"  [{'OK' if verify7f else 'FAIL'}] unknown in batch: {len(unknown_in_batch)}")
    if not verify7f:
        errors.append(f"{len(unknown_in_batch)} unknown task_ids in batch")

    print("\n[8] R4 classification")
    frozen_ordinary = {str(t["task_id"]) for t in tasks
                       if t.get("task_group") == "ordinary" and t.get("object_name") in ORDINARY_SAFE}
    frozen_serial = {str(t["task_id"]) for t in tasks} - frozen_ordinary
    stats["frozen_ordinary_eligible"] = len(frozen_ordinary)
    stats["frozen_serial"] = len(frozen_serial)

    verify8a = len(frozen_ordinary) == 3245
    verify8b = len(frozen_serial) == 1098
    print(f"  [{'OK' if verify8a else 'FAIL'}] ordinary eligible={len(frozen_ordinary)}")
    print(f"  [{'OK' if verify8b else 'FAIL'}] serial={len(frozen_serial)}")
    if not verify8a:
        errors.append(f"Ordinary eligible={len(frozen_ordinary)}")
    if not verify8b:
        errors.append(f"Serial={len(frozen_serial)}")

    verify8c = batch_set == frozen_ordinary
    if verify8c:
        print(f"  [OK]   batch set == frozen ordinary set (exact)")
    else:
        missing = frozen_ordinary - batch_set
        extra = batch_set - frozen_ordinary
        print(f"  [FAIL] missing={len(missing)}, extra={len(extra)}")
        errors.append("Ordinary set mismatch")

    serial_from_batch = all_task_id_set - batch_set
    verify8d = serial_from_batch == frozen_serial
    verify8e = len(batch_set) + len(serial_from_batch) == 4343
    print(f"  [{'OK' if verify8d else 'FAIL'}] serial residual match: {len(serial_from_batch)}")
    print(f"  [{'OK' if verify8e else 'FAIL'}] batch+serial=4343")
    if not verify8d:
        errors.append("Serial residual mismatch")
    if not verify8e:
        errors.append("batch+serial != 4343")

    print("\n[9] COM check")
    com_ok = "win32com" not in sys.modules and "pythoncom" not in sys.modules
    print(f"  [{'OK' if com_ok else 'FAIL'}] COM not imported")
    if not com_ok:
        errors.append("COM modules unexpectedly loaded")

    print("\n" + "=" * 60)
    if errors:
        print(f"PREFLIGHT FAILED — {len(errors)} error(s)")
        for e in errors:
            print(f"  * {e}")
        return {"passed": False, "errors": errors, "stats": stats}
    else:
        print("PREFLIGHT PASSED — all checks green")
        return {"passed": True, "errors": [], "stats": stats}


def _run_execution():
    import shutil
    from mcp.acceptance.stage3_1_runtime import attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage5_1_valve_component_diagnostics import (
        _copyobjects_with_explicit_idpairs, _parse_copyobjects_return)
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _scan_native, _variant
    from mcp.orchestration.stage5_1_r3 import _existing_record_unchanged, _scan_modelspace, _snapshot
    from mcp.orchestration.stage6_p1_override import _bbox_intersects, _introduced_duplicates
    from mcp.orchestration.stage6_p1 import _bbox2d

    print("=" * 60)
    print("R4 EXECUTION — PREPARING")
    print("=" * 60)

    with open(PLAN_PATH, "r", encoding="utf-8") as f:
        plan = json.load(f)
    tasks = list(plan["tasks"])
    task_by_id = {str(t["task_id"]): t for t in tasks}
    task_by_source = {str(t["source_entity_id"]).upper(): t for t in tasks}
    transforms = {item["alignment_id"]: item["transform"] for item in plan["alignment_evidence"]}
    protected_bbox = plan["protected_region"]["bbox"]
    component_plan_path = Path(plan["core_component_dependency_plan"]["path"])

    ordinary = [t for t in tasks if t["task_group"] == "ordinary" and t["object_name"] in ORDINARY_SAFE]
    groups = defaultdict(list)
    for t in ordinary:
        groups[(t["target_region_id"], str(t["transform_id"]), t["object_name"])].append(t)

    batches = []
    for (rid, tid, oname), group in sorted(groups.items()):
        gs = sorted(group, key=lambda t: str(t["source_entity_id"]).upper())
        for idx in range(0, len(gs), 200):
            chunk = gs[idx:idx + 200]
            batches.append({"batch_id": f"batch_{len(batches)+1:04d}", "region_id": rid,
                           "transform_id": tid, "object_name": oname,
                           "source_handles": [str(t["source_entity_id"]).upper() for t in chunk],
                           "task_ids": [t["task_id"] for t in chunk], "size": len(chunk)})

    print(f"  Batches: {len(batches)}")

    run_id = datetime.now().strftime("stage6_p1_accelerated_r4_%Y%m%d_%H%M%S")
    run_root = PROJECT_ROOT / "artifacts" / "stage6_p1_accelerated_r4" / run_id
    for sub in ["execution_inputs", "checkpoints", "copyobjects_calls", "reports", "evidence"]:
        (run_root / sub).mkdir(parents=True, exist_ok=True)

    ref_copy = run_root / "execution_inputs" / "reference_execution_copy.dwg"
    shutil.copy2(REFERENCE_PATH, ref_copy)

    with open(run_root / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({"phase": "STAGE6-P1-ACCELERATED-R4", "run_id": run_id,
                    "work_file": str(R4_WORK_FILE), "total_tasks": len(tasks),
                    "batch_count": len(batches)}, f, ensure_ascii=False, indent=2)
    print(f"  Run dir: {run_root}")

    print("\n" + "=" * 60)
    print("CONNECTING TO AutoCAD...")
    print("=" * 60)

    acad = attach_existing_autocad()
    print(f"  AutoCAD: {acad.Name} v{acad.Version}")
    live = enumerate_live_documents(acad, (REFERENCE_PATH, TARGET_PATH, ref_copy, R4_WORK_FILE))
    if live.get("documents"):
        print(f"  Note: documents open: {live['documents']}")

    source_doc = None
    target_doc = None
    try:
        source_doc = _resolve_open_document(acad, ref_copy, _open_document_with_retry(acad, ref_copy))
        target_doc = _resolve_open_document(acad, R4_WORK_FILE, _open_document_with_retry(acad, R4_WORK_FILE))
        print(f"  Reference: {source_doc.Name} ({int(source_doc.ModelSpace.Count)} handles)")
        print(f"  Target R4: {target_doc.Name} ({int(target_doc.ModelSpace.Count)} handles)")

        initial_rec = _retry(lambda: _scan_modelspace(target_doc, "R4_init"), "Init scan", attempts=60, delay=0.5)
        initial_snap = _snapshot(initial_rec)
        print(f"  Initial entities: {len(initial_snap)}")

        completed = set()
        skipped = set()
        manual = []
        s2t = {}
        created = set()
        calls = 0

        def ckpt(name, **kw):
            p = run_root / "checkpoints" / f"{name}.json"
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"checkpoint": name, "ts": datetime.now().isoformat(),
                           "completed": len(completed), "skipped": len(skipped),
                           "calls": calls, **kw}, f, ensure_ascii=False, indent=2)

        ckpt("0000_initial")

        print("\n" + "=" * 60)
        print("STAGE 1: ORDINARY BATCHES")
        print("=" * 60)
        t0 = time.time()

        for bi, batch in enumerate(batches, 1):
            bt = time.time()
            calls += 1
            shandles = batch["source_handles"]
            tf = batch["transform_id"]

            before = set()
            for i in range(int(target_doc.ModelSpace.Count)):
                try:
                    before.add(str(target_doc.ModelSpace.Item(i).Handle).upper())
                except Exception:
                    pass

            objs = []
            for h in shandles:
                try:
                    objs.append(_retry(lambda hh=h: source_doc.HandleToObject(hh), f"src {h}"))
                except Exception as e:
                    skipped.add(str(task_by_source.get(h, {}).get("task_id", "")))
                    manual.append({"handle": h, "reason": f"src: {e}"})
            if not objs:
                continue

            try:
                ret = _retry(lambda: _copyobjects_with_explicit_idpairs(source_doc, objs, target_doc.ModelSpace),
                            f"Batch {bi}/{len(batches)} x{len(objs)}", attempts=30, delay=0.5)
                parsed = _parse_copyobjects_return(ret, source_doc, target_doc)
            except Exception as e:
                print(f"  FATAL batch {bi}: {e}")
                ckpt(f"failed_batch_{bi:04d}", error=str(e))
                raise

            after = set()
            for i in range(int(target_doc.ModelSpace.Count)):
                try:
                    after.add(str(target_doc.ModelSpace.Item(i).Handle).upper())
                except Exception:
                    pass

            new = sorted(after - before)
            pairs = [dict(p) for p in parsed.get("idpairs", [])]
            exp = set(shandles)
            primary = [p for p in pairs if str(p.get("source_handle", "")).upper() in exp
                      and p.get("target_handle") and p.get("IsCloned") is not False]
            bs = {str(p["source_handle"]).upper(): str(p["target_handle"]).upper() for p in primary}

            vec = [float(transforms[tf]["translation"][0]),
                  float(transforms[tf]["translation"][1]), 0.0]
            for sh in sorted(bs):
                th = bs[sh]
                try:
                    ntv = _retry(lambda hh=th: target_doc.HandleToObject(hh), f"tgt {th}")
                    _retry(lambda n=ntv: n.Move(_variant([0.0, 0.0, 0.0]), _variant(vec)),
                           f"move {th}", attempts=30, delay=0.5)
                    s2t[sh] = th
                    created.add(th)
                    completed.add(str(task_by_source.get(sh, {}).get("task_id", "")))
                except Exception as e:
                    skipped.add(str(task_by_source.get(sh, {}).get("task_id", "")))
                    manual.append({"handle": sh, "reason": f"move: {e}"})

            el = time.time() - bt
            print(f"  [{bi:03d}/{len(batches)}] {batch['object_name']:20s} {batch['region_id']} | "
                  f"in={len(shandles)} out={len(new)} mapped={len(bs)} | {el:.1f}s | {len(completed)}/{len(tasks)}")
            ckpt(f"batch_{bi:04d}")

        print(f"\n  Batches done: {len(completed)} ordinary in {time.time()-t0:.1f}s")

        # Stage 2: TDb
        print("\n" + "=" * 60)
        print("STAGE 2: SERIAL TDb COMPONENTS")
        print("=" * 60)

        with open(component_plan_path, "r", encoding="utf-8") as f:
            cplan = json.load(f)

        vq = []
        ct0 = time.time()
        for ci, comp in enumerate(cplan.get("components", []), 1):
            cstat = comp.get("status", "UNKNOWN")
            cid = comp.get("component_id", f"c_{ci}")
            if cstat != "READY":
                for tid in comp.get("execution_order", []):
                    skipped.add(tid)
                ckpt(f"component_{ci:04d}")
                continue

            for dep in comp.get("existing_source_to_target_dependencies", []):
                s2t[str(dep["source_handle"]).upper()] = str(dep["target_handle"]).upper()

            nv, vl = [], []
            for tid in comp.get("execution_order", []):
                t = task_by_id.get(tid)
                if not t:
                    continue
                h = str(t["source_entity_id"]).upper()
                if t.get("object_name") == "TDbPipeValve":
                    vl.append(h)
                else:
                    nv.append(h)

            if nv:
                calls += 1
                before = set()
                for i in range(int(target_doc.ModelSpace.Count)):
                    try:
                        before.add(str(target_doc.ModelSpace.Item(i).Handle).upper())
                    except Exception:
                        pass
                objs = []
                for h in nv:
                    try:
                        objs.append(_retry(lambda hh=h: source_doc.HandleToObject(hh), f"tdb {h}"))
                    except Exception:
                        skipped.add(str(task_by_source.get(h, {}).get("task_id", "")))

                if objs:
                    try:
                        ret = _retry(lambda: _copyobjects_with_explicit_idpairs(source_doc, objs, target_doc.ModelSpace),
                                    f"TDb {cid}", attempts=30, delay=0.5)
                        parsed = _parse_copyobjects_return(ret, source_doc, target_doc)
                    except Exception:
                        for h in nv + vl:
                            skipped.add(str(task_by_source.get(h, {}).get("task_id", "")))
                        ckpt(f"component_{ci:04d}")
                        continue

                    after = set()
                    for i in range(int(target_doc.ModelSpace.Count)):
                        try:
                            after.add(str(target_doc.ModelSpace.Item(i).Handle).upper())
                        except Exception:
                            pass
                    pairs = [dict(p) for p in parsed.get("idpairs", [])]
                    exp = set(nv)
                    primary = [p for p in pairs if str(p.get("source_handle", "")).upper() in exp
                              and p.get("target_handle") and p.get("IsCloned") is not False]
                    bs = {str(p["source_handle"]).upper(): str(p["target_handle"]).upper() for p in primary}

                    ttf = comp.get("transform_id", "")
                    v = [0.0, 0.0, 0.0]
                    if ttf and ttf in transforms:
                        v = [float(transforms[ttf]["translation"][0]),
                            float(transforms[ttf]["translation"][1]), 0.0]

                    rf = False
                    for sh in sorted(bs):
                        th = bs[sh]
                        try:
                            ntv = _retry(lambda hh=th: target_doc.HandleToObject(hh), f"tdb tgt {th}")
                            _retry(lambda n=ntv: n.Move(_variant([0.0, 0.0, 0.0]), _variant(v)),
                                   f"tdb move {th}", attempts=30, delay=0.5)
                            s2t[sh] = th
                            created.add(th)
                            completed.add(str(task_by_source.get(sh, {}).get("task_id", "")))
                        except Exception:
                            rf = True
                            skipped.add(str(task_by_source.get(sh, {}).get("task_id", "")))

                    if rf:
                        for h in vl:
                            skipped.add(str(task_by_source.get(h, {}).get("task_id", "")))
                    else:
                        vq.append((comp, vl))
                else:
                    vq.append((comp, vl))
            else:
                vq.append((comp, vl))
            ckpt(f"component_{ci:04d}")
            if ci % 10 == 0:
                print(f"  [{ci:03d}/{len(cplan['components'])}] {cid} | done={len(completed)}")

        # Valves
        print(f"\n  Processing {sum(len(vs) for _, vs in vq)} valves...")
        for comp, valves in vq:
            for sh in valves:
                calls += 1
                before = set()
                for i in range(int(target_doc.ModelSpace.Count)):
                    try:
                        before.add(str(target_doc.ModelSpace.Item(i).Handle).upper())
                    except Exception:
                        pass
                try:
                    sobj = _retry(lambda hh=sh: source_doc.HandleToObject(hh), f"valve {sh}")
                    ret = _retry(lambda: _copyobjects_with_explicit_idpairs(source_doc, [sobj], target_doc.ModelSpace),
                                f"Valve {sh}", attempts=30, delay=0.5)
                    parsed = _parse_copyobjects_return(ret, source_doc, target_doc)
                    after = set()
                    for i in range(int(target_doc.ModelSpace.Count)):
                        try:
                            after.add(str(target_doc.ModelSpace.Item(i).Handle).upper())
                        except Exception:
                            pass
                    pairs = [dict(p) for p in parsed.get("idpairs", [])]
                    primary = [p for p in pairs if p.get("target_handle") and p.get("IsCloned") is not False]
                    if primary:
                        th = str(primary[0]["target_handle"]).upper()
                        ttf = comp.get("transform_id", "")
                        v = [0.0, 0.0, 0.0]
                        if ttf and ttf in transforms:
                            v = [float(transforms[ttf]["translation"][0]),
                                float(transforms[ttf]["translation"][1]), 0.0]
                        ntv = _retry(lambda hh=th: target_doc.HandleToObject(hh), f"valve tgt {th}")
                        _retry(lambda n=ntv: n.Move(_variant([0.0, 0.0, 0.0]), _variant(v)), f"valve move {th}")
                        s2t[sh] = th
                        created.add(th)
                        completed.add(str(task_by_source.get(sh, {}).get("task_id", "")))
                    else:
                        skipped.add(str(task_by_source.get(sh, {}).get("task_id", "")))
                except Exception:
                    skipped.add(str(task_by_source.get(sh, {}).get("task_id", "")))

        print(f"\n  TDb done: {time.time()-ct0:.1f}s")

        # Stage 3: Final Audit
        print("\n" + "=" * 60)
        print("STAGE 3: FINAL AUDIT")
        print("=" * 60)

        after_rec = _retry(lambda: _scan_modelspace(target_doc, "R4_final"), "Final scan", attempts=60, delay=0.5)
        after_snap = _snapshot(after_rec)

        ed = sorted(set(initial_snap) - set(after_snap))
        em = sorted(h for h, r in initial_snap.items()
                   if h in after_snap and not _existing_record_unchanged(r, after_snap[h]))
        un = len(set(after_snap) - set(initial_snap) - created)
        pm = sorted(h for h in initial_snap
                   if _bbox_intersects(_bbox2d(initial_snap[h]), protected_bbox)
                   and (h not in after_snap or not _existing_record_unchanged(initial_snap[h], after_snap[h])))
        pi = sorted(h for h in created
                   if h in after_snap and _bbox_intersects(_bbox2d(after_snap[h]), protected_bbox))
        dc = _introduced_duplicates(initial_snap, after_snap, created)

        print(f"  existing_deleted: {len(ed)}")
        print(f"  existing_modified: {len(em)}")
        print(f"  unexpected_new: {un}")
        print(f"  protected_modified: {len(pm)}")
        print(f"  protected_intersection: {len(pi)}")

        if ed:
            raise RuntimeError(f"existing_deleted={len(ed)}")
        if pm:
            raise RuntimeError(f"protected_region_modified={len(pm)}")
        if pi:
            raise RuntimeError(f"protected_region_intersection={len(pi)}")

        target_doc.Activate()
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(acad.HWND))
        except Exception:
            pass

        total_t = time.time() - t0
        status = ("EMERGENCY_ACCELERATED_R4_HANDOFF_READY_WITH_MANUAL_TASKS" if manual
                  else "EMERGENCY_ACCELERATED_R4_HANDOFF_READY")

        result = {
            "phase": "STAGE6-P1-ACCELERATED-R4", "status": status, "run_id": run_id,
            "work_file": str(R4_WORK_FILE), "total_tasks": len(tasks),
            "completed_task_count": len(completed),
            "uncompleted_task_count": len(tasks) - len(completed),
            "skipped_task_count": len(skipped),
            "manual_completion_required": len(manual),
            "copyobjects_call_count": calls,
            "execution_time_seconds": total_t,
            "existing_deleted": 0, "existing_modified": len(em),
            "unexpected_new": un, "duplicate_candidates": len(dc),
            "protected_region_modified": 0, "protected_region_intersection": 0,
            "water_pump_room_unchanged": True,
            "save_called": False, "save_as_called": False, "close_called": False,
            "document_modified": bool(not target_doc.Saved), "document_open": True,
        }
        with open(run_root / "reports" / "result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        (PROJECT_ROOT / "reports").mkdir(parents=True, exist_ok=True)
        with open(PROJECT_ROOT / "reports" / "stage6_p1_accelerated_r4.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 60)
        print(f"R4 COMPLETE — {status}")
        print("=" * 60)
        print(f"  Completed: {len(completed)}/{len(tasks)}")
        print(f"  CopyObjects calls: {calls}")
        print(f"  Time: {total_t:.1f}s")
        print(f"  R4 is OPEN, MODIFIED, NOT SAVED")
    except Exception:
        import traceback
        traceback.print_exc()
        try:
            if target_doc:
                target_doc.Close(False)
        except Exception:
            pass
        try:
            if source_doc:
                source_doc.Close(False)
        except Exception:
            pass
        raise
    finally:
        if acad:
            detach_autocad()


if __name__ == "__main__":
    preflight_only = "--preflight-only" in sys.argv
    result = _preflight()
    if not result["passed"]:
        sys.exit(1)
    if preflight_only:
        print("\n--preflight-only mode: exiting without connecting to AutoCAD.")
        sys.exit(0)
    print("\n" + "=" * 60)
    print("PREFLIGHT PASSED — STARTING R4 EXECUTION")
    print("=" * 60)
    _run_execution()
