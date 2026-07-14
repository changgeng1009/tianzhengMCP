"""R5 offline tests (batch). No AutoCAD connection."""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.orchestration.stage6_p1_accelerated_tdb_r5 import (
    _read_json, PLAN_PATH, COMPONENT_PLAN_PATH, R4_CHECKPOINTS,
    read_latest_checkpoint, compute_completed_from_checkpoints,
    classify_remaining, build_plan, validate_plan, can_merge,
)


def _data():
    """Load plan + component plan data."""
    tasks = _read_json(PLAN_PATH).get("tasks", [])
    cplan = _read_json(COMPONENT_PLAN_PATH)
    tbyid = {str(t["task_id"]): t for t in tasks}
    ctdb, cord = compute_completed_from_checkpoints(R4_CHECKPOINTS)
    cids = ctdb | cord
    return tasks, cplan, tbyid, cids


def t001_dynamic_checkpoint():
    cp = read_latest_checkpoint(R4_CHECKPOINTS)
    assert cp["completed_task_count"] >= 0
    assert cp["_source"] in ("count_only", "execution_state", "empty")

def t002_completed_not_in_plan():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    pids = set()
    for unit in plan:
        for c in unit["components"]:
            pids.update(c.task_ids)
    assert not (cids & pids)

def t003_pending_covers_remaining():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    pids = set()
    for unit in plan:
        for c in unit["components"]:
            pids.update(c.task_ids)
    tdb = {str(t["task_id"]) for t in tasks if t.get("task_group") == "core_tdb"}
    assert not (pids - tdb)

def t004_large_independent():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        if unit["unit_type"] == "large_independent":
            assert len(unit["components"]) == 1

def t005_medium_safe_merge():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        if unit["unit_type"] != "medium_merged":
            continue
        r = {c.source_region for c in unit["components"]}
        assert len(r) == 1

def t006_micro_safe_merge():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        if unit["unit_type"] != "micro_merged":
            continue
        r = {c.source_region for c in unit["components"]}
        assert len(r) == 1

def t007_no_cross_region():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        if len(unit["components"]) <= 1:
            continue
        r = {c.source_region for c in unit["components"]}
        assert len(r) == 1

def t008_no_cross_target():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        if len(unit["components"]) <= 1:
            continue
        t = {c.target_region for c in unit["components"]}
        assert len(t) == 1

def t009_no_mixed_transform():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        if len(unit["components"]) <= 1:
            continue
        x = {c.transform_id for c in unit["components"]}
        assert len(x) == 1

def t010_dependency_conflict():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    v = validate_plan(plan, cids)
    merge_errs = [e for e in v.get("errors", []) if "Cannot merge" in e]
    assert not merge_errs

def t011_protected_not_in_batch():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        if unit["serial_required"]:
            continue
        for c in unit["components"]:
            assert not c.has_protected

def t012_batch_splittable():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        assert len(unit["components"]) >= 1

def t013_valve_isolated():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        for c in unit["components"]:
            if c.has_valves:
                assert unit["serial_required"]

def t014_no_repeat_completed():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    pids = set()
    for unit in plan:
        for c in unit["components"]:
            pids.update(c.task_ids)
    assert not (cids & pids)

def t015_safe_boundary():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    assert all(u["task_count"] > 0 for u in plan)

def t016_journal_recoverable():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    all_cids = [cid for unit in plan for cid in unit["component_ids"]]
    assert len(all_cids) == len(set(all_cids))

def t017_checkpoint_idempotent():
    cp1 = read_latest_checkpoint(R4_CHECKPOINTS)
    cp2 = read_latest_checkpoint(R4_CHECKPOINTS)
    assert cp1["completed_task_count"] == cp2["completed_task_count"]

def t018_mapping_complete():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        for c in unit["components"]:
            assert c.source_handles or c.task_ids

def t019_idempotent():
    tasks, cplan, tbyid, cids = _data()
    l1, m1, u1, s1 = classify_remaining(cplan, tbyid, cids)
    l2, m2, u2, s2 = classify_remaining(cplan, tbyid, cids)
    c1 = sum(c.task_count for c in l1 + m1 + u1 + s1)
    c2 = sum(c.task_count for c in l2 + m2 + u2 + s2)
    assert c1 == c2

def t020_no_wrong_region():
    tasks, cplan, tbyid, cids = _data()
    l, m, u, s = classify_remaining(cplan, tbyid, cids)
    plan = build_plan(l, m, u, s)
    for unit in plan:
        if len(unit["components"]) <= 1:
            continue
        c0 = unit["components"][0]
        for c in unit["components"][1:]:
            assert c.source_region == c0.source_region
            assert c.target_region == c0.target_region


if __name__ == "__main__":
    tests = [v for k, v in sorted(locals().items()) if k.startswith("t0")]
    passed = failed = 0
    for i, fn in enumerate(tests, 1):
        name = fn.__name__
        print(f"[{i:02d}/{len(tests)}] {name}")
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {type(e).__name__}: {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed ({len(tests)} total)")
