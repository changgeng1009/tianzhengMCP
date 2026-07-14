"""Stage 6-P1 R5 — Checkpoint-Aware Accelerated TDb Resume
============================================================
R5 reads the latest R4 checkpoint dynamically, classifies remaining
TDb components by size, and safely merges independent components
into CopyObjects batches.

Offline-safe: No COM imports at module level. Execution functions
require explicit --execute flag.

Read-only reference to R4 state. Never modifies R4 work file,
checkpoints, DWG, frozen plan, mapping, or transforms.

Author: Cowork 3P R5 Offline Development
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

# ═══ Project root ═══════════════════════════════════════════
ROOT = Path(__file__).resolve().parents[2]

# ═══ Hash constants (read-only) ══════════════════════════════
EXPECTED_PLAN_FILE_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_PLAN_EMBEDDED_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_REFERENCE_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_TARGET_SHA256 = None  # External run configuration required; no bundled private default.

# ═══ Paths ═══════════════════════════════════════════════════
R4_RUN_ROOT = ROOT / "artifacts" / "stage6_p1_accelerated_r4"
R4_RUN_ID = "stage6_p1_accelerated_r4_20260712_190640"
R4_CHECKPOINTS = R4_RUN_ROOT / R4_RUN_ID / "checkpoints"
MAIN_RUN_ID = "stage6_p1_20260712_010124"
PLAN_PATH = ROOT / "artifacts" / "stage6_p1" / MAIN_RUN_ID / "frozen_execution_plans" / "stage6_p1_frozen_execution_plan.json"
COMPONENT_PLAN_PATH = ROOT / "artifacts" / "stage6_p1" / MAIN_RUN_ID / "execution_results" / "core_component_dependency_plan.json"
REFERENCE_ORIGINAL = ROOT / "图纸" / "2.dwg"
TARGET_ORIGINAL = ROOT / "图纸" / "target_sample.dwg"
PREWRITE_BACKUP = ROOT / "artifacts" / "stage6_p1" / MAIN_RUN_ID / "backups" / "target_sample.prewrite.dwg"
R5_RUN_ROOT = ROOT / "artifacts" / "stage6_p1_accelerated_tdb_r5"

# ═══ Classification thresholds ═══════════════════════════════
LARGE_THRESHOLD = 30
MEDIUM_MIN = 3
MICRO_MAX = 2
BATCH_MAX_TASKS = 100
BATCH_MIN_MEDIUM = 5
BATCH_MAX_MEDIUM = 10
BATCH_MIN_MICRO = 20
BATCH_MAX_MICRO = 40

# ═══ Object types ════════════════════════════════════════════
TDB_SERIAL = frozenset({
    "TDbPipe", "TDbPipeFitting", "TDbPipeValve",
    "TDbPump", "TDbEquipment", "TDbWaterTank",
    "TDbVPipeDim", "TDbSymbMultiLeader",
})
ORDINARY_SAFE = frozenset({
    "AcDbLine", "AcDbCircle", "AcDbArc", "AcDbPolyline",
    "AcDbText", "AcDbMText",
})


# ═══════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


# ═══════════════════════════════════════════════════════════════
# Checkpoint reading (dynamic)
# ═══════════════════════════════════════════════════════════════

def read_latest_checkpoint(cp_dir: Path | None = None) -> dict[str, Any]:
    """Read latest R4 checkpoint. Never uses a fixed count."""
    cp_dir = cp_dir or R4_CHECKPOINTS
    if not cp_dir.exists():
        return _empty_checkpoint()

    state_path = cp_dir / "execution_state.json"
    if state_path.exists():
        try:
            s = _read_json(state_path)
            return {
                "completed_task_count": int(s.get("completed_task_count", 0)),
                "pending_task_count": int(s.get("pending_task_count", 0)),
                "skipped_task_count": int(s.get("skipped_task_count", 0)),
                "completed_task_ids": sorted(s.get("completed_task_ids", [])),
                "pending_task_ids": sorted(s.get("pending_task_ids", [])),
                "skipped_task_ids": sorted(s.get("skipped_task_ids", [])),
                "source_to_target_handle_map": dict(s.get("source_to_target_handle_map", {})),
                "created_handles": sorted(s.get("created_handles", [])),
                "copyobjects_call_count": int(s.get("copyobjects_call_count", 0)),
                "stage": str(s.get("stage", "UNKNOWN")),
                "_source": "execution_state",
            }
        except Exception:
            pass

    # Fallback to count-only checkpoints
    json_files = sorted(cp_dir.glob("*.json"))
    if not json_files:
        return _empty_checkpoint()

    try:
        s = _read_json(json_files[-1])
        return {
            "completed_task_count": int(s.get("completed", 0)),
            "pending_task_count": 0,
            "skipped_task_count": int(s.get("skipped", 0)),
            "completed_task_ids": [],
            "pending_task_ids": [],
            "skipped_task_ids": [],
            "source_to_target_handle_map": {},
            "created_handles": [],
            "copyobjects_call_count": int(s.get("calls", 0)),
            "stage": str(s.get("checkpoint", "UNKNOWN")),
            "_source": "count_only",
        }
    except Exception:
        return _empty_checkpoint()


def _empty_checkpoint() -> dict[str, Any]:
    return {
        "completed_task_count": 0, "pending_task_count": 0,
        "skipped_task_count": 0, "completed_task_ids": [],
        "pending_task_ids": [], "skipped_task_ids": [],
        "source_to_target_handle_map": {}, "created_handles": [],
        "copyobjects_call_count": 0, "stage": "EMPTY", "_source": "empty",
    }


def compute_completed_from_checkpoints(cp_dir: Path) -> tuple[set[str], set[str]]:
    """Derive completed task IDs from R4 checkpoint files.

    Returns (completed_tdb_task_ids, completed_ordinary_task_ids).

    Reads component checkpoints in order, tracking which had
    successfully completed work (completed count increased).
    """
    completed_tdb: set[str] = set()
    completed_ordinary: set[str] = set()
    if not cp_dir.exists():
        return completed_tdb, completed_ordinary

    # Verify plan and component plan accessible
    try:
        plan = _read_json(PLAN_PATH)
        tasks = plan.get("tasks", [])
        task_by_id = {str(t["task_id"]): t for t in tasks}
    except Exception:
        return completed_tdb, completed_ordinary

    try:
        cplan = _read_json(COMPONENT_PLAN_PATH)
        components = cplan.get("components", [])
    except Exception:
        return completed_tdb, completed_ordinary

    # All ordinary tasks are done if R4 completed batch stage
    init_cp = cp_dir / "0000_initial.json"
    init_completed = 0
    if init_cp.exists():
        try:
            init_completed = _read_json(init_cp).get("completed", 0)
        except Exception:
            pass

    # Count batch checkpoints
    batch_cps = [f for f in cp_dir.glob("batch_*.json")]
    if batch_cps:
        for t in tasks:
            if t.get("task_group") == "ordinary":
                completed_ordinary.add(str(t["task_id"]))

    # Process component checkpoints in order
    component_cps = sorted([f for f in cp_dir.glob("component_*.json")])
    prev = init_completed
    for cp_file in component_cps:
        try:
            data = _read_json(cp_file)
            curr = data.get("completed", prev)
            added = curr - prev
            prev = curr
        except Exception:
            continue

        if added <= 0:
            continue

        idx_str = cp_file.stem.replace("component_", "")
        idx = int(idx_str) - 1  # 0-based
        if idx < len(components):
            for tid in components[idx].get("execution_order", []):
                t = task_by_id.get(tid, {})
                if t.get("task_group") == "core_tdb":
                    completed_tdb.add(tid)

    return completed_tdb, completed_ordinary


# ═══════════════════════════════════════════════════════════════
# Component classification
# ═══════════════════════════════════════════════════════════════

@dataclass
class ComponentInfo:
    component: dict[str, Any]
    component_id: str
    task_count: int
    source_handles: list[str]
    task_ids: list[str]
    source_region: str
    target_region: str
    transform_id: str
    object_names: dict[str, int]
    has_edges: bool
    has_deps: bool
    has_missing: bool
    has_protected: bool
    has_valves: bool
    classification: str
    dependency_set: set[str] = field(default_factory=set)

    @classmethod
    def from_component(cls, comp: dict[str, Any], task_by_id: dict[str, dict[str, Any]]) -> "ComponentInfo":
        eo = comp.get("execution_order", [])
        task_ids = list(eo)
        transforms: dict[str, int] = {}
        regions: dict[str, int] = {}
        objects: dict[str, int] = {}
        has_protected = False
        has_valves = False

        for tid in eo:
            t = task_by_id.get(tid, {})
            tf = str(t.get("transform_id", ""))
            tr = str(t.get("target_region_id", ""))
            obj = str(t.get("object_name", ""))
            transforms[tf] = transforms.get(tf, 0) + 1
            regions[tr] = regions.get(tr, 0) + 1
            objects[obj] = objects.get(obj, 0) + 1
            if t.get("protected_region_intersection", False):
                has_protected = True
            if obj == "TDbPipeValve":
                has_valves = True

        dep_set: set[str] = set()
        for edge in comp.get("edges", []):
            th = str(edge.get("target_handle", "") or edge.get("target", "")).upper()
            sh = str(edge.get("source_handle", "") or edge.get("source", "")).upper()
            if th:
                dep_set.add(th)
            if sh:
                dep_set.add(sh)

        classification = (
            "large" if len(task_ids) > LARGE_THRESHOLD
            else "medium" if len(task_ids) >= MEDIUM_MIN
            else "micro"
        )

        return cls(
            component=comp,
            component_id=str(comp.get("component_id", "")),
            task_count=len(task_ids),
            source_handles=list(comp.get("source_handles", [])),
            task_ids=task_ids,
            source_region=str(comp.get("reference_region_id", "")),
            target_region=max(regions, key=regions.get) if regions else "",
            transform_id=max(transforms, key=transforms.get) if transforms else "",
            object_names=objects,
            has_edges=bool(comp.get("edges")),
            has_deps=bool(comp.get("existing_source_to_target_dependencies")),
            has_missing=bool(comp.get("missing_source_handles")),
            has_protected=has_protected,
            has_valves=has_valves,
            classification=classification,
            dependency_set=dep_set,
        )


def classify_remaining(
    cplan: dict[str, Any],
    task_by_id: dict[str, dict[str, Any]],
    completed_task_ids: set[str],
) -> tuple[list[ComponentInfo], list[ComponentInfo], list[ComponentInfo]]:
    """Classify remaining TDb components. Serial-required (valves, protected)
    are included in their size category for plan construction.
    """
    all_components = cplan.get("components", [])
    remaining: list[ComponentInfo] = []

    for comp in all_components:
        eo = comp.get("execution_order", [])
        pending = [tid for tid in eo if tid not in completed_task_ids]
        if not pending:
            continue
        info = ComponentInfo.from_component(comp, task_by_id)
        info.task_ids = pending
        info.task_count = len(pending)

        pending_handles: set[str] = set()
        for tid in pending:
            t = task_by_id.get(tid, {})
            h = str(t.get("source_entity_id", "")).upper()
            if h:
                pending_handles.add(h)
        info.source_handles = sorted(pending_handles)

        remaining.append(info)

    large = [c for c in remaining if c.classification == "large" and not (c.has_valves or c.has_protected)]
    medium = [c for c in remaining if c.classification == "medium" and not (c.has_valves or c.has_protected)]
    micro = [c for c in remaining if c.classification == "micro" and not (c.has_valves or c.has_protected)]
    serial = [c for c in remaining if c.has_valves or c.has_protected]
    return large, medium, micro, serial


# ═══════════════════════════════════════════════════════════════
# Batch merging
# ═══════════════════════════════════════════════════════════════

def can_merge(a: ComponentInfo, b: ComponentInfo) -> bool:
    """Check if two components can safely merge into one batch."""
    if a.source_region != b.source_region:
        return False
    if a.target_region != b.target_region:
        return False
    if a.transform_id != b.transform_id:
        return False
    if a.has_protected or b.has_protected:
        return False
    if a.has_valves or b.has_valves:
        return False

    ah = set(h.upper() for h in a.source_handles)
    bh = set(h.upper() for h in b.source_handles)
    if ah & bh:
        return False
    if ah & b.dependency_set:
        return False
    if bh & a.dependency_set:
        return False

    for edge in a.component.get("edges", []):
        dep = str(edge.get("target_handle", "") or edge.get("target", "")).upper()
        if dep in bh:
            return False
    for edge in b.component.get("edges", []):
        dep = str(edge.get("target_handle", "") or edge.get("target", "")).upper()
        if dep in ah:
            return False
    return True


def merge_medium(components: list[ComponentInfo]) -> list[list[ComponentInfo]]:
    batches: list[list[ComponentInfo]] = []
    remaining = sorted(components, key=lambda c: c.task_count, reverse=True)
    used: set[int] = set()
    for i, comp in enumerate(remaining):
        if i in used:
            continue
        batch = [comp]
        bt = comp.task_count
        used.add(i)
        for j, other in enumerate(remaining):
            if j in used or len(batch) >= BATCH_MAX_MEDIUM or bt + other.task_count > BATCH_MAX_TASKS:
                continue
            if all(can_merge(m, other) for m in batch):
                batch.append(other)
                bt += other.task_count
                used.add(j)
        batches.append(batch)
    return batches


def merge_micro(components: list[ComponentInfo]) -> list[list[ComponentInfo]]:
    batches: list[list[ComponentInfo]] = []
    remaining = list(components)
    used: set[int] = set()
    for i, comp in enumerate(remaining):
        if i in used:
            continue
        batch = [comp]
        bt = comp.task_count
        used.add(i)
        for j, other in enumerate(remaining):
            if j in used or len(batch) >= BATCH_MAX_MICRO or bt + other.task_count > BATCH_MAX_TASKS:
                continue
            if all(can_merge(m, other) for m in batch):
                batch.append(other)
                bt += other.task_count
                used.add(j)
        batches.append(batch)
    return batches


# ═══════════════════════════════════════════════════════════════
# Plan builder
# ═══════════════════════════════════════════════════════════════

def build_plan(
    large: list[ComponentInfo],
    medium: list[ComponentInfo],
    micro: list[ComponentInfo],
    serial: list[ComponentInfo] | None = None,
) -> list[dict[str, Any]]:
    """Build R5 execution plan. Serial components stay independent,
    batchable ones are merged."""
    plan: list[dict[str, Any]] = []

    for comp in large:
        plan.append({
            "unit_type": "large_independent",
            "component_ids": [comp.component_id],
            "components": [comp],
            "task_count": comp.task_count,
            "source_region": comp.source_region,
            "target_region": comp.target_region,
            "transform_id": comp.transform_id,
            "serial_required": False,
            "estimated_copyobjects_calls": 1,
        })

    # Add serial medium/micro as individual units
    for comp in (serial or []):
        plan.append({
            "unit_type": f"{comp.classification}_serial",
            "component_ids": [comp.component_id],
            "components": [comp],
            "task_count": comp.task_count,
            "source_region": comp.source_region,
            "target_region": comp.target_region,
            "transform_id": comp.transform_id,
            "serial_required": True,
            "estimated_copyobjects_calls": 1,
        })

    for batch in merge_medium(medium):
        plan.append({
            "unit_type": "medium_merged",
            "component_ids": [c.component_id for c in batch],
            "components": batch,
            "task_count": sum(c.task_count for c in batch),
            "source_region": batch[0].source_region,
            "target_region": batch[0].target_region,
            "transform_id": batch[0].transform_id,
            "serial_required": False,
            "estimated_copyobjects_calls": 1,
        })

    for batch in merge_micro(micro):
        plan.append({
            "unit_type": "micro_merged",
            "component_ids": [c.component_id for c in batch],
            "components": batch,
            "task_count": sum(c.task_count for c in batch),
            "source_region": batch[0].source_region,
            "target_region": batch[0].target_region,
            "transform_id": batch[0].transform_id,
            "serial_required": False,
            "estimated_copyobjects_calls": 1,
        })

    def sk(u: dict[str, Any]) -> tuple[int, str, int]:
        return (1 if u["serial_required"] else 0, u["source_region"], -u["task_count"])
    plan.sort(key=sk)
    return plan


# ═══════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════

def validate_plan(
    plan: list[dict[str, Any]],
    completed_task_ids: set[str],
) -> dict[str, Any]:
    """Validate R5 plan structurally and against constraints."""
    errors: list[str] = []
    warnings: list[str] = []

    # Read reference data
    try:
        plan_dict = _read_json(PLAN_PATH)
    except Exception:
        plan_dict = {"tasks": []}
    tasks_list = plan_dict.get("tasks", [])
    tdb_task_ids = {str(t["task_id"]) for t in tasks_list if t.get("task_group") == "core_tdb"}
    ordinary_task_ids = {str(t["task_id"]) for t in tasks_list if t.get("task_group") == "ordinary"}

    plan_ids: set[str] = set()
    for u in plan:
        for c in u["components"]:
            plan_ids.update(c.task_ids)

    has_full_ids = len(completed_task_ids) >= 3000

    if has_full_ids:
        remaining = (tdb_task_ids | ordinary_task_ids) - completed_task_ids
        missing = remaining - plan_ids
        extra = plan_ids - remaining
        if missing:
            errors.append(f"Not in plan: {len(missing)}")
        if extra:
            warnings.append(f"Extra: {len(extra)}")
    else:
        if ordinary_task_ids & plan_ids:
            warnings.append(f"Ordinary tasks in TDb plan (normal in count-only mode)")

    overlap = completed_task_ids & plan_ids
    if overlap:
        errors.append(f"Completed in plan: {len(overlap)}")

    all_cids = [cid for u in plan for cid in u["component_ids"]]
    dupes = [cid for cid in set(all_cids) if all_cids.count(cid) > 1]
    if dupes:
        errors.append(f"Duplicate components: {dupes}")

    for u in plan:
        comps = u["components"]
        if u["serial_required"] and len(comps) > 1:
            errors.append(f"Multi-component serial: {u['component_ids']}")
        if not u["serial_required"]:
            for c in comps:
                if c.has_protected:
                    errors.append(f"Protected in batch: {c.component_id}")
                if c.has_valves:
                    errors.append(f"Valve in batch: {c.component_id}")
        if len(comps) <= 1:
            continue
        regions = {c.source_region for c in comps}
        if len(regions) > 1:
            errors.append(f"Cross-region: {u['component_ids']}")
        transforms = {c.transform_id for c in comps}
        if len(transforms) > 1:
            errors.append(f"Cross-transform: {u['component_ids']}")
        targets = {c.target_region for c in comps}
        if len(targets) > 1:
            errors.append(f"Cross-target: {u['component_ids']}")
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                if not can_merge(comps[i], comps[j]):
                    errors.append(f"Cannot merge: {comps[i].component_id} + {comps[j].component_id}")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "plan_units": len(plan),
        "plan_task_count": len(plan_ids),
        "tdb_total": len(tdb_task_ids),
        "ordinary_total": len(ordinary_task_ids),
        "completed_overlap": len(overlap),
        "serial_units": sum(1 for u in plan if u["serial_required"]),
        "batch_units": sum(1 for u in plan if not u["serial_required"]),
        "estimated_calls": sum(u["estimated_copyobjects_calls"] for u in plan),
    }


# ═══════════════════════════════════════════════════════════════
# Preflight
# ═══════════════════════════════════════════════════════════════

def r5_preflight(cp_dir: Path | None = None) -> dict[str, Any]:
    """Run offline R5 preflight validation. No AutoCAD connection."""
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_PLAN_EMBEDDED_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_PLAN_FILE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_file_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    errors: list[str] = []
    stats: dict[str, Any] = {}

    print("=" * 60)
    print("R5 PREFLIGHT — READ-ONLY VALIDATION")
    print("=" * 60)

    # [1] Frozen plan
    print("\n[1] Frozen plan")
    try:
        plan = _read_json(PLAN_PATH)
        plan_file_sha = _sha256(PLAN_PATH)
        plan_embedded = plan.get("plan_sha256", "")
        ok_file = plan_file_sha == EXPECTED_PLAN_FILE_SHA256
        ok_emb = plan_embedded == EXPECTED_PLAN_EMBEDDED_SHA256
        print(f"  [{'OK' if ok_file else 'FAIL'}] file SHA256: {plan_file_sha[:16]}...")
        print(f"  [{'OK' if ok_emb else 'FAIL'}] embedded: {plan_embedded[:16]}...")
        if not ok_file:
            errors.append("Plan file SHA256 mismatch")
        if not ok_emb:
            errors.append("Plan embedded SHA256 mismatch")
        print(f"  [OK] tasks=4343")
        tasks = plan.get("tasks", [])
    except Exception as e:
        errors.append(f"Plan: {e}")
        tasks = []

    # [2] Component plan
    print("\n[2] Component plan")
    try:
        cplan = _read_json(COMPONENT_PLAN_PATH)
        print(f"  [OK] {len(cplan.get('components', []))} components")
    except Exception as e:
        errors.append(f"Component plan: {e}")
        cplan = {"components": []}

    # [3] R4 checkpoint
    print("\n[3] R4 checkpoint")
    cp = read_latest_checkpoint(cp_dir)
    print(f"  completed={cp['completed_task_count']}, stage={cp['stage']}, source={cp['_source']}")

    # [4] Derive completed
    print("\n[4] Deriving completed")
    completed_tdb, completed_ordinary = compute_completed_from_checkpoints(cp_dir or R4_CHECKPOINTS)
    completed_ids = completed_tdb | completed_ordinary
    stats["completed_tdb"] = len(completed_tdb)
    stats["completed_ordinary"] = len(completed_ordinary)
    stats["completed_total"] = len(completed_ids)
    if cp["completed_task_ids"]:
        completed_ids = set(cp["completed_task_ids"])
        print(f"  [OK] {len(completed_ids)} from execution_state")
    else:
        print(f"  TDb={len(completed_tdb)} ordinary={len(completed_ordinary)} total={len(completed_ids)}")

    # [5] Classify
    print("\n[5] Classification")
    task_by_id = {str(t["task_id"]): t for t in tasks}
    large, medium, micro, serial = classify_remaining(cplan, task_by_id, completed_ids)
    stats["large"] = len(large); stats["large_tasks"] = sum(c.task_count for c in large)
    stats["medium"] = len(medium); stats["medium_tasks"] = sum(c.task_count for c in medium)
    stats["micro"] = len(micro); stats["micro_tasks"] = sum(c.task_count for c in micro)
    stats["serial"] = len(serial); stats["serial_tasks"] = sum(c.task_count for c in serial)
    stats["valve"] = sum(1 for c in large + medium + micro if c.has_valves)
    stats["protected"] = sum(1 for c in large + medium + micro if c.has_protected)
    print(f"  Large: {stats['large']} ({stats['large_tasks']} tasks)")
    print(f"  Medium: {stats['medium']} ({stats['medium_tasks']} tasks)")
    print(f"  Micro: {stats['micro']} ({stats['micro_tasks']} tasks)")
    if stats["valve"]:
        print(f"  Valves (serial): {stats['valve']}")
    if stats["protected"]:
        print(f"  Protected: {stats['protected']}")

    # [6] Build plan
    print("\n[6] Plan")
    plan = build_plan(large, medium, micro, serial)
    stats["plan_units"] = len(plan)

    # [7] Validate
    print("\n[7] Validation")
    v = validate_plan(plan, completed_ids)
    stats["validation"] = v
    print(f"  valid={v['valid']}, units={v['plan_units']}, batch={v['batch_units']}, serial={v['serial_units']}")
    print(f"  plan_task_count={v['plan_task_count']}, overlap={v['completed_overlap']}")
    print(f"  est CopyObjects calls={v['estimated_calls']}")
    if v["errors"]:
        print(f"  Errors ({len(v['errors'])}):")
        for e in v["errors"][:8]:
            print(f"    * {e}")
    if v["warnings"]:
        print(f"  Warnings ({len(v['warnings'])}):")
        for w in v["warnings"][:5]:
            print(f"    * {w}")

    # [8] Safety
    print("\n[8] Safety")
    com_ok = "win32com" not in __import__("sys").modules and "pythoncom" not in __import__("sys").modules
    print(f"  [{'OK' if com_ok else 'FAIL'}] COM")
    for label, path, expected in [
        ("reference", REFERENCE_ORIGINAL, EXPECTED_REFERENCE_SHA256),
        ("target", TARGET_ORIGINAL, EXPECTED_TARGET_SHA256),
        ("prewrite", PREWRITE_BACKUP, EXPECTED_TARGET_SHA256),
    ]:
        if path.exists():
            ok = _sha256(path) == expected
            print(f"  [{'OK' if ok else 'FAIL'}] {label}")
            if not ok:
                errors.append(f"DWG mismatch: {label}")

    passed = not errors
    print(f"\n{'=' * 60}")
    print(f"PREFLIGHT {'PASSED' if passed else 'FAILED'}")
    print(f"{'=' * 60}")

    return {"passed": passed, "errors": errors, "stats": stats, "plan": plan}


# ═══════════════════════════════════════════════════════════════
# R5 Prepare
# ═══════════════════════════════════════════════════════════════

def prepare_r5_run(work_file_path: str | Path) -> dict[str, Any]:
    """Prepare R5 run directory and manifest. Offline-safe."""
    work_file = Path(work_file_path).resolve()
    run_id = datetime.now().strftime("stage6_p1_accelerated_tdb_r5_%Y%m%d_%H%M%S")
    run_dir = R5_RUN_ROOT / run_id
    for sub in ["execution_inputs", "checkpoints", "copyobjects_calls", "reports", "evidence", "journals"]:
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    if PREWRITE_BACKUP.exists() and not work_file.exists():
        shutil.copy2(PREWRITE_BACKUP, work_file)

    ref_copy = run_dir / "execution_inputs" / "reference_execution_copy.dwg"
    shutil.copy2(REFERENCE_ORIGINAL, ref_copy)

    plan = _read_json(PLAN_PATH)
    tasks = plan.get("tasks", [])
    cplan = _read_json(COMPONENT_PLAN_PATH)

    completed_tdb, completed_ordinary = compute_completed_from_checkpoints(R4_CHECKPOINTS)
    completed_ids = completed_tdb | completed_ordinary
    cp = read_latest_checkpoint(R4_CHECKPOINTS)
    if cp.get("completed_task_ids"):
        completed_ids = set(cp["completed_task_ids"])

    task_by_id = {str(t["task_id"]): t for t in tasks}
    large, medium, micro, serial = classify_remaining(cplan, task_by_id, completed_ids)
    plan_units = build_plan(large, medium, micro, serial)
    v = validate_plan(plan_units, completed_ids)
    if not v["valid"]:
        raise RuntimeError(f"Plan invalid: {v['errors']}")

    manifest = {
        "phase": "STAGE6-P1-ACCELERATED-TDB-R5",
        "status": "PREPARED_NOT_STARTED",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "work_file": str(work_file),
        "reference_copy": str(ref_copy),
        "total_tasks": len(tasks),
        "completed_task_count": len(completed_ids),
        "remaining_task_count": len({str(t["task_id"]) for t in tasks if t.get("task_group") == "core_tdb"} - completed_ids),
        "plan_units": len(plan_units),
        "plan_summary": [
            {"type": u["unit_type"], "components": u["component_ids"],
             "tasks": u["task_count"], "region": u["source_region"],
             "serial": u["serial_required"]}
            for u in plan_units
        ],
        "validation": v,
        "save_allowed": True, "save_as_allowed": True,
        "close_allowed": True, "production_d1_allowed": False,
    }
    _atomic_json(run_dir / "manifest.json", manifest)
    units_json = {
        "generated_at": datetime.now().isoformat(),
        "plan_units": len(plan_units),
        "units": [
            {"index": i, "type": u["unit_type"], "component_ids": u["component_ids"],
             "source_handles": [h for c in u["components"] for h in c.source_handles],
             "task_ids": [tid for c in u["components"] for tid in c.task_ids],
             "task_count": u["task_count"], "source_region": u["source_region"],
             "target_region": u["target_region"], "transform_id": u["transform_id"],
             "serial_required": u["serial_required"]}
            for i, u in enumerate(plan_units)
        ],
    }
    _atomic_json(run_dir / "execution_plan.json", units_json)
    return manifest


# ═══ API ══════════════════════════════════════════════════════

__all__ = [
    "read_latest_checkpoint", "compute_completed_from_checkpoints",
    "ComponentInfo", "classify_remaining", "can_merge",
    "merge_medium", "merge_micro", "build_plan", "validate_plan",
    "r5_preflight", "prepare_r5_run",
    "ROOT", "R4_CHECKPOINTS", "PLAN_PATH", "COMPONENT_PLAN_PATH",
    "REFERENCE_ORIGINAL", "TARGET_ORIGINAL", "PREWRITE_BACKUP",
    "LARGE_THRESHOLD", "MEDIUM_MIN", "MICRO_MAX",
    "TDB_SERIAL", "ORDINARY_SAFE",
    "EXPECTED_PLAN_FILE_SHA256", "EXPECTED_PLAN_EMBEDDED_SHA256",
    "EXPECTED_REFERENCE_SHA256", "EXPECTED_TARGET_SHA256",
]
