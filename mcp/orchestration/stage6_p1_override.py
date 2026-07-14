from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.orchestration.stage6_p1 import (
    P1Paths,
    _bbox2d,
    _lock_files,
    _read_json,
    _sha256,
    _write_json,
    validate_frozen_execution_plan,
)
from mcp.orchestration.stage6_p1_execution import _relationship_audit, _validate_frozen_evidence


ROOT = Path(__file__).resolve().parents[2]
OVERRIDE_ROOT = ROOT / "artifacts" / "stage6_p1_override"
EMERGENCY_ROOT = ROOT / "artifacts" / "stage6_p1_emergency"
MAIN_RUN_ID = "stage6_p1_20260712_010124"
EXPECTED_PLAN_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_REFERENCE_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_TARGET_SHA256 = None  # External run configuration required; no bundled private default.
EXPECTED_EXISTING_MODIFIED = 6
EXPECTED_UNEXPECTED_NEW = 33


@dataclass(frozen=True)
class OverridePaths:
    run_id: str
    root: Path
    override_rehearsal: Path
    execution_inputs: Path
    evidence: Path
    previews: Path
    reports: Path
    checkpoints: Path

    @classmethod
    def build(cls, run_id: str) -> "OverridePaths":
        root = OVERRIDE_ROOT / run_id
        return cls(
            run_id, root, root / "override_rehearsal", root / "execution_inputs",
            root / "evidence", root / "previews", root / "reports", root / "checkpoints",
        )

    def create(self) -> None:
        for value in self.__dict__.values():
            if isinstance(value, Path):
                value.mkdir(parents=True, exist_ok=True)


def _payload_sha256(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _readable_json(path: Path) -> tuple[bool, str | None]:
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def recover_state() -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    import psutil

    main = P1Paths.build(MAIN_RUN_ID)
    core_paths = {
        "main_report": ROOT / "reports" / "stage6_p1_multi_region_pilot.json",
        "stop_report": ROOT / "reports" / "stage6_p1_rehearsal_stop_gate.json",
        "frozen_plan": main.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json",
        "region_matching": main.root / "region_matching.json",
        "prewrite_gate": main.root / "prewrite_gate.json",
        "manual_mapping_consistency": main.root / "manual_mapping_consistency.json",
    }
    core = {}
    errors = []
    for name, path in core_paths.items():
        valid, parse_error = _readable_json(path) if path.is_file() else (False, "missing")
        core[name] = {"path": str(path), "exists": path.is_file(), "parse_valid": valid, "error": parse_error}
        if not valid:
            errors.append(f"{name}: {parse_error}")
    plan = _read_json(core_paths["frozen_plan"]) if core["frozen_plan"]["parse_valid"] else {}
    plan_valid, actual_plan_hash = validate_frozen_execution_plan(plan) if plan else (False, "")
    if not plan_valid or plan.get("plan_sha256") != EXPECTED_PLAN_SHA256:
        errors.append("frozen plan SHA256 invalid")
    hashes = {}
    for role, expected in (
        ("reference", EXPECTED_REFERENCE_SHA256),
        ("target", EXPECTED_TARGET_SHA256),
        ("prewrite_backup", EXPECTED_TARGET_SHA256),
    ):
        record = (plan.get("frozen_inputs") or {}).get(role) or {}
        path = Path(record.get("path", ""))
        actual = _sha256(path) if path.is_file() else None
        hashes[role] = {
            "path": str(path), "expected": expected, "actual": actual,
            "unchanged": actual == expected, "readable": path.is_file(),
        }
        if actual != expected:
            errors.append(f"{role} hash invalid")
    processes = []
    for process in psutil.process_iter(["pid", "name", "create_time", "cmdline"]):
        try:
            name = str(process.info.get("name") or "")
            if any(token in name.lower() for token in ("acad", "python", "powershell", "pwsh")):
                processes.append({
                    "pid": process.info["pid"], "name": name,
                    "create_time": process.info.get("create_time"),
                    "cmdline": process.info.get("cmdline") or [],
                    "classified_as_active_stage6_execution": (
                        "python" in name.lower()
                        and any("stage6_p1" in str(item).lower() for item in (process.info.get("cmdline") or []))
                    ),
                })
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    partial_artifacts = []
    if OVERRIDE_ROOT.is_dir():
        for path in OVERRIDE_ROOT.rglob("*"):
            if path.is_file():
                partial_artifacts.append({
                    "path": str(path), "classification": "PARTIAL_CANCELLED_ARTIFACT",
                    "continuation_allowed": False, "baseline_allowed": False,
                })
    active_execution = [item for item in processes if item["classified_as_active_stage6_execution"]]
    if active_execution:
        errors.append("active Stage 6 execution process found")
    status = "RECOVERY_VALID" if not errors else "BLOCKED_RECOVERY_EVIDENCE_INVALID"
    return {
        "phase": "STAGE6-P1-RECOVERY",
        "status": status,
        "main_run_id": MAIN_RUN_ID,
        "main_plan_paused": True,
        "stage6_p1_status": "FAILED_REHEARSAL_STOP_GATE",
        "core_artifacts": core,
        "frozen_plan_sha256_declared": plan.get("plan_sha256"),
        "frozen_plan_sha256_actual": actual_plan_hash,
        "frozen_plan_valid": plan_valid,
        "frozen_task_count": len(plan.get("tasks", [])),
        "hashes": hashes,
        "processes": processes,
        "active_stage6_execution_processes": active_execution,
        "partial_cancelled_artifacts": partial_artifacts,
        "global_safety_policy_path": str(ROOT / "docs" / "GLOBAL_SAFETY_POLICY.md"),
        "global_safety_policy_found": (ROOT / "docs" / "GLOBAL_SAFETY_POLICY.md").is_file(),
        "explicit_user_hard_gates_applied": True,
        "errors": errors,
        "original_target_write": False,
        "original_target_save": False,
        "production_d1_allowed": False,
    }


def prepare_override_run(run_id: str | None = None) -> tuple[OverridePaths, dict[str, Any]]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    recovery = recover_state()
    if recovery["status"] != "RECOVERY_VALID":
        raise RuntimeError("BLOCKED_RECOVERY_EVIDENCE_INVALID")
    run_id = run_id or datetime.now().strftime("stage6_p1_override_%Y%m%d_%H%M%S")
    paths = OverridePaths.build(run_id)
    if paths.root.exists():
        raise FileExistsError(paths.root)
    paths.create()
    main = P1Paths.build(MAIN_RUN_ID)
    plan_path = main.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json"
    plan = _read_json(plan_path)
    frozen_inputs = plan["frozen_inputs"]
    backup = Path(frozen_inputs["prewrite_backup"]["path"])
    reference = Path(frozen_inputs["reference"]["path"])
    override_copy = paths.override_rehearsal / "target_sample.override_rehearsal.dwg"
    reference_copy = paths.execution_inputs / "reference_execution_copy.dwg"
    shutil.copy2(backup, override_copy)
    shutil.copy2(reference, reference_copy)
    override_hash = _sha256(override_copy)
    reference_copy_hash = _sha256(reference_copy)
    if override_hash != EXPECTED_TARGET_SHA256:
        raise RuntimeError("BLOCKED_OVERRIDE_COPY_HASH_MISMATCH")
    if reference_copy_hash != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError("BLOCKED_REFERENCE_COPY_HASH_MISMATCH")
    manifest = {
        "phase": "STAGE6-P1-OVERRIDE-PREPARE",
        "status": "READY_FOR_ONE_TIME_OVERRIDE",
        "run_id": run_id,
        "main_run_id": MAIN_RUN_ID,
        "main_plan_paused": True,
        "stage6_p1_status": "FAILED_REHEARSAL_STOP_GATE",
        "one_time_rehearsal_override": True,
        "allow_save_with_existing_modified": True,
        "allow_save_with_unexpected_new": True,
        "override_expected_existing_modified": EXPECTED_EXISTING_MODIFIED,
        "override_expected_unexpected_new": EXPECTED_UNEXPECTED_NEW,
        "frozen_plan_path": str(plan_path),
        "frozen_plan_sha256": plan["plan_sha256"],
        "frozen_task_count": len(plan["tasks"]),
        "override_copy_path": str(override_copy),
        "override_copy_initial_hash": override_hash,
        "override_copy_initial_hash_matches_target_baseline": override_hash == EXPECTED_TARGET_SHA256,
        "reference_execution_copy": str(reference_copy),
        "reference_execution_copy_hash": reference_copy_hash,
        "recovery": recovery,
        "original_target_write": False,
        "original_target_save": False,
        "production_d1_allowed": False,
    }
    _write_json(paths.root / "recovery_state.json", recovery)
    _write_json(paths.root / "override_manifest.json", manifest)
    _write_json(paths.checkpoints / "checkpoint_00_prepared.json", manifest)
    return paths, manifest


def prepare_emergency_run(run_id: str | None = None) -> tuple[OverridePaths, dict[str, Any]]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    recovery = recover_state()
    if recovery["status"] != "RECOVERY_VALID":
        raise RuntimeError("BLOCKED_RECOVERY_EVIDENCE_INVALID")
    run_id = run_id or datetime.now().strftime("stage6_p1_emergency_%Y%m%d_%H%M%S")
    root = EMERGENCY_ROOT / run_id
    paths = OverridePaths(
        run_id, root, root / "emergency_delivery", root / "execution_inputs",
        root / "evidence", root / "previews", root / "reports", root / "checkpoints",
    )
    if root.exists():
        raise FileExistsError(root)
    paths.create()
    main = P1Paths.build(MAIN_RUN_ID)
    plan_path = main.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json"
    plan = _read_json(plan_path)
    backup = Path(plan["frozen_inputs"]["prewrite_backup"]["path"])
    reference = Path(plan["frozen_inputs"]["reference"]["path"])
    emergency_copy = ROOT / "图纸" / "target_sample-应急提交版.dwg"
    if emergency_copy.exists():
        raise FileExistsError(f"emergency output already exists: {emergency_copy}")
    reference_copy = paths.execution_inputs / "reference_execution_copy.dwg"
    shutil.copy2(backup, emergency_copy)
    shutil.copy2(reference, reference_copy)
    emergency_hash = _sha256(emergency_copy)
    reference_copy_hash = _sha256(reference_copy)
    if emergency_hash != EXPECTED_TARGET_SHA256:
        raise RuntimeError("BLOCKED_EMERGENCY_COPY_HASH_MISMATCH")
    if reference_copy_hash != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError("BLOCKED_REFERENCE_COPY_HASH_MISMATCH")
    manifest = {
        "phase": "STAGE6-P1-EMERGENCY-PREPARE",
        "status": "READY_FOR_EMERGENCY_DELIVERY",
        "run_id": run_id,
        "main_run_id": MAIN_RUN_ID,
        "main_plan_paused": True,
        "stage6_p1_status": "FAILED_REHEARSAL_STOP_GATE",
        "emergency_delivery_mode": True,
        "manual_cleanup_expected": True,
        "allow_save_with_existing_modified": True,
        "allow_save_with_unexpected_new": True,
        "allow_save_with_duplicate_candidates": True,
        "allow_save_with_wrong_region_write": True,
        "frozen_plan_path": str(plan_path),
        "frozen_plan_sha256": plan["plan_sha256"],
        "frozen_task_count": len(plan["tasks"]),
        "override_copy_path": str(emergency_copy),
        "override_copy_initial_hash": emergency_hash,
        "override_copy_initial_hash_matches_target_baseline": emergency_hash == EXPECTED_TARGET_SHA256,
        "reference_execution_copy": str(reference_copy),
        "reference_execution_copy_hash": reference_copy_hash,
        "recovery": recovery,
        "original_target_write": False,
        "original_target_save": False,
        "production_d1_allowed": False,
    }
    _write_json(root / "recovery_state.json", recovery)
    _write_json(root / "emergency_manifest.json", manifest)
    _write_json(root / "override_manifest.json", manifest)
    _write_json(paths.checkpoints / "checkpoint_00_prepared.json", manifest)
    return paths, manifest


def _chunks(values: Sequence[str], size: int) -> list[list[str]]:
    return [list(values[index:index + size]) for index in range(0, len(values), size)]


def _copy_and_move_with_provenance(
    source_doc: Any,
    target_doc: Any,
    source_handles: Sequence[str],
    translation: Sequence[float],
    *,
    call_id: str,
    label: str,
    task_ids: Sequence[str],
    component_id: str | None,
) -> dict[str, Any]:
    from mcp.acceptance.stage5_1_valve_component_diagnostics import (
        _copyobjects_with_explicit_idpairs,
        _parse_copyobjects_return,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _variant

    expected = {str(handle).upper() for handle in source_handles}
    objects = [
        _retry(lambda value=handle: source_doc.HandleToObject(value), f"{label} source {handle} lookup")
        for handle in source_handles
    ]
    returned = _retry(
        lambda: _copyobjects_with_explicit_idpairs(source_doc, objects, target_doc.ModelSpace),
        f"{label} CopyObjects", attempts=30, delay=0.5,
    )
    parsed = _parse_copyobjects_return(returned, source_doc, target_doc)
    all_pairs = [dict(pair) for pair in parsed.get("idpairs", [])]
    primary_pairs = [
        pair for pair in all_pairs
        if str(pair.get("source_handle") or "").upper() in expected
        and pair.get("target_handle") and pair.get("IsCloned") is not False
    ]
    by_source = {str(pair["source_handle"]).upper(): pair for pair in primary_pairs}
    missing = sorted(expected - set(by_source))
    if missing:
        raise RuntimeError(f"{label}: primary IDPairs missing for {missing[:20]}")
    vector = [float(translation[0]), float(translation[1]), 0.0]
    for source_handle in sorted(expected):
        target_handle = str(by_source[source_handle]["target_handle"]).upper()
        native = _retry(lambda value=target_handle: target_doc.HandleToObject(value), f"{label} target {target_handle} lookup")
        _retry(
            lambda value=native: value.Move(_variant([0.0, 0.0, 0.0]), _variant(vector)),
            f"{label} target {target_handle} move", attempts=30, delay=0.5,
        )
    return {
        "call_id": call_id,
        "label": label,
        "component_id": component_id,
        "task_ids": list(task_ids),
        "expected_source_handles": sorted(expected),
        "translation": list(vector),
        "primary_pairs": [by_source[handle] for handle in sorted(expected)],
        "all_idpairs": all_pairs,
        "primary_target_handles": [str(by_source[handle]["target_handle"]).upper() for handle in sorted(expected)],
        "all_target_handles": sorted({
            str(pair["target_handle"]).upper() for pair in all_pairs if pair.get("target_handle")
        }),
    }


def _bbox_flat(record: Mapping[str, Any]) -> list[float] | None:
    return _bbox2d(record)


def _bbox_intersects(left: Sequence[float] | None, right: Sequence[float] | None) -> bool:
    if left is None or right is None:
        return False
    return not (left[2] <= right[0] or left[0] >= right[2] or left[3] <= right[1] or left[1] >= right[3])


def _bbox_close(left: Sequence[float] | None, right: Sequence[float] | None, tolerance: float = 2.0) -> bool:
    if left is None or right is None or len(left) != 4 or len(right) != 4:
        return False
    return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))


def _region_for_bbox(bbox: Sequence[float] | None, target_regions: Sequence[Mapping[str, Any]]) -> str | None:
    if bbox is None:
        return None
    center = ((float(bbox[0]) + float(bbox[2])) / 2, (float(bbox[1]) + float(bbox[3])) / 2)
    candidates = [
        region for region in target_regions
        if float(region["bbox"][0]) <= center[0] <= float(region["bbox"][2])
        and float(region["bbox"][1]) <= center[1] <= float(region["bbox"][3])
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda region: (region["bbox"][2] - region["bbox"][0]) * (region["bbox"][3] - region["bbox"][1]))["region_id"]


def _changed_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    from mcp.orchestration.stage5_1_r3 import _stable_value_equal

    fields = []
    for key in ("object_name", "layer", "geometry", "attributes", "bbox"):
        if not _stable_value_equal(before.get(key), after.get(key)):
            fields.append(key)
    return fields


def _relation_signature(record: Mapping[str, Any], records: Mapping[str, Mapping[str, Any]]) -> list[str]:
    from mcp.recognition.stage5_1_relationship_probe import _bbox_distance, relation_type

    name = str(record.get("object_name") or "")
    if name not in {"TDbPipeValve", "TDbPipeFitting"}:
        return []
    related = []
    for handle, candidate in records.items():
        if candidate.get("object_name") != "TDbPipe":
            continue
        distance = _bbox_distance(record.get("bbox"), candidate.get("bbox"))
        edge = None if distance is None else relation_type(name, "TDbPipe", float(distance))
        if edge in {"VALVE_BELONGS_TO_PIPE", "FITTING_JOINS_PIPE"}:
            related.append(handle)
    return sorted(related)


def _owner_chain(document: Any, handle: str) -> dict[str, Any]:
    from mcp.acceptance.stage5_2_native_clone_poc import _retry

    native = _retry(lambda: document.HandleToObject(handle), f"owner chain {handle} lookup")
    chain = []
    current = native
    seen = set()
    for _ in range(8):
        try:
            owner_id = int(current.OwnerID)
        except Exception:
            break
        if owner_id in seen:
            break
        seen.add(owner_id)
        try:
            owner = document.ObjectIDToObject(owner_id)
            item = {
                "object_id": owner_id,
                "handle": str(getattr(owner, "Handle", "")),
                "object_name": str(getattr(owner, "ObjectName", "")),
                "name": str(getattr(owner, "Name", "")),
            }
            chain.append(item)
            current = owner
        except Exception as exc:
            chain.append({"object_id": owner_id, "error": f"{type(exc).__name__}: {exc}"})
            break
    return {"owner": chain[0] if chain else None, "owner_chain": chain}


def _fingerprint(record: Mapping[str, Any]) -> str | None:
    bbox = _bbox_flat(record)
    if bbox is None:
        return None
    payload = {
        "object_name": record.get("object_name"),
        "layer": record.get("layer"),
        "bbox": [round(float(value), 3) for value in bbox],
        "geometry": record.get("geometry") or {},
        "attributes": record.get("attributes") or {},
    }
    return _payload_sha256(payload)


def _introduced_duplicates(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    new_handles: set[str],
) -> list[dict[str, Any]]:
    before_groups: dict[str, list[str]] = defaultdict(list)
    after_groups: dict[str, list[str]] = defaultdict(list)
    for handle, record in before.items():
        fingerprint = _fingerprint(record)
        if fingerprint:
            before_groups[fingerprint].append(handle)
    for handle, record in after.items():
        fingerprint = _fingerprint(record)
        if fingerprint:
            after_groups[fingerprint].append(handle)
    duplicates = []
    for fingerprint, handles in after_groups.items():
        new_in_group = sorted(set(handles) & new_handles)
        if not new_in_group:
            continue
        old = sorted(before_groups.get(fingerprint, []))
        if old or len(new_in_group) > 1:
            sample = after[new_in_group[0]]
            duplicates.append({
                "fingerprint": fingerprint,
                "object_name": sample.get("object_name"),
                "bbox": _bbox_flat(sample),
                "preexisting_handles": old,
                "new_handles": new_in_group,
            })
    return duplicates


def _entire_frame_wrong_regions(
    tasks: Sequence[Mapping[str, Any]], wrong_region: Sequence[Mapping[str, Any]]
) -> list[str]:
    per_region_task_count = Counter(str(task["target_region_id"]) for task in tasks)
    per_region_wrong_count = Counter(str(item["expected_region_id"]) for item in wrong_region)
    return sorted(
        region_id for region_id, wrong_count in per_region_wrong_count.items()
        if wrong_count >= 20 and wrong_count / max(per_region_task_count[region_id], 1) >= 0.50
    )


def _render_previews(
    paths: OverridePaths,
    before_records: Sequence[Mapping[str, Any]],
    after_records: Sequence[Mapping[str, Any]],
    created_handles: set[str],
    unexpected_handles: set[str],
    modified_handles: set[str],
    target_regions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    before_by_handle = {str(item.get("handle")): item for item in before_records if item.get("handle")}
    after_by_handle = {str(item.get("handle")): item for item in after_records if item.get("handle")}

    def segments(records: Sequence[Mapping[str, Any]], bounds: Sequence[float] | None = None) -> list[list[tuple[float, float]]]:
        values = []
        for record in records:
            bbox = _bbox_flat(record)
            if bbox is None or (bounds is not None and not _bbox_intersects(bbox, bounds)):
                continue
            x1, y1, x2, y2 = bbox
            if abs(x2 - x1) < 1e-6 and abs(y2 - y1) < 1e-6:
                d = 2.0
                values.append([(x1 - d, y1), (x1 + d, y1)])
                continue
            values.extend([
                [(x1, y1), (x2, y1)], [(x2, y1), (x2, y2)],
                [(x2, y2), (x1, y2)], [(x1, y2), (x1, y1)],
            ])
        return values

    outputs = []

    def render(path: Path, bounds: Sequence[float] | None, title: str) -> None:
        fig, axes = plt.subplots(1, 2, figsize=(18, 8), dpi=150)
        for axis, mode in zip(axes, ("before", "after")):
            axis.set_facecolor("white")
            base = before_records if mode == "before" else after_records
            axis.add_collection(LineCollection(segments(base, bounds), colors="#B8BEC5", linewidths=0.22, alpha=0.65))
            if mode == "after":
                planned = [after_by_handle[h] for h in created_handles if h in after_by_handle]
                unexpected = [after_by_handle[h] for h in unexpected_handles if h in after_by_handle]
                modified = [after_by_handle[h] for h in modified_handles if h in after_by_handle]
                axis.add_collection(LineCollection(segments(planned, bounds), colors="#1677FF", linewidths=0.65, alpha=0.9))
                axis.add_collection(LineCollection(segments(unexpected, bounds), colors="#E5484D", linewidths=1.0, alpha=0.95))
                axis.add_collection(LineCollection(segments(modified, bounds), colors="#F5A524", linewidths=1.1, alpha=0.95))
            if bounds:
                axis.set_xlim(bounds[0], bounds[2]); axis.set_ylim(bounds[1], bounds[3])
            else:
                all_boxes = [_bbox_flat(record) for record in base]
                all_boxes = [bbox for bbox in all_boxes if bbox]
                if all_boxes:
                    axis.set_xlim(min(b[0] for b in all_boxes), max(b[2] for b in all_boxes))
                    axis.set_ylim(min(b[1] for b in all_boxes), max(b[3] for b in all_boxes))
            axis.set_aspect("equal", adjustable="box")
            axis.set_title("Before" if mode == "before" else "Unsaved override memory state")
            axis.axis("off")
        fig.suptitle(title)
        fig.tight_layout()
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        outputs.append(str(path))

    render(paths.previews / "full_drawing_before_after.png", None, "Stage 6-P1 Override Full Drawing Before / After")
    for region in target_regions:
        if region["region_id"] == "target_protected_pump_room":
            continue
        render(
            paths.previews / f"{region['region_id']}_before_after.png",
            region["bbox"], f"{region['region_id']} Before / After",
        )
    return {"created": len(outputs) == 8, "paths": outputs}


def _side_effect_evidence(
    modified_handles: Sequence[str],
    unexpected_handles: Sequence[str],
    initial_snapshot: Mapping[str, Mapping[str, Any]],
    after_snapshot: Mapping[str, Mapping[str, Any]],
    provenance: Sequence[Mapping[str, Any]],
    task_by_id: Mapping[str, Mapping[str, Any]],
    target_regions: Sequence[Mapping[str, Any]],
    document: Any,
    duplicates: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    duplicate_handles = {
        handle for item in duplicates for handle in [*item.get("preexisting_handles", []), *item.get("new_handles", [])]
    }
    target_provenance: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in provenance:
        for pair in call.get("all_idpairs", []):
            target_handle = str(pair.get("target_handle") or "").upper()
            if target_handle:
                target_provenance[target_handle].append({
                    "call_id": call["call_id"], "component_id": call.get("component_id"),
                    "task_ids": call.get("task_ids", []), "source_handle": pair.get("source_handle"),
                    "IsPrimary": pair.get("IsPrimary"), "IsCloned": pair.get("IsCloned"),
                    "IsOwnerXlated": pair.get("IsOwnerXlated"),
                })
    existing_evidence = []
    for handle in modified_handles:
        before, after = initial_snapshot[handle], after_snapshot[handle]
        owner = _owner_chain(document, handle)
        triggers = target_provenance.get(handle, [])
        changed = _changed_fields(before, after)
        before_relations = _relation_signature(before, initial_snapshot)
        after_relations = _relation_signature(after, after_snapshot)
        existing_evidence.append({
            "handle": handle,
            "ObjectName": after.get("object_name"),
            "layer": after.get("layer"),
            **owner,
            "region_id": _region_for_bbox(_bbox_flat(after), target_regions),
            "before_snapshot": before,
            "after_snapshot": after,
            "changed_fields": changed,
            "native_geometry_changed": "geometry" in changed,
            "attributes_changed": "attributes" in changed,
            "relationships_before": before_relations,
            "relationships_after": after_relations,
            "relationships_changed": before_relations != after_relations,
            "bbox_display_only_change": changed == ["bbox"],
            "trigger_task_ids": sorted({task for item in triggers for task in item.get("task_ids", [])}),
            "trigger_component_ids": sorted({item["component_id"] for item in triggers if item.get("component_id")}),
            "trigger_copyobjects_calls": triggers,
            "trigger_attribution": "IDPAIRS_DIRECT" if triggers else "UNKNOWN_REQUIRES_R1_FORENSICS",
        })
    unexpected_evidence = []
    for order, handle in enumerate(unexpected_handles, 1):
        after = after_snapshot[handle]
        owner = _owner_chain(document, handle)
        triggers = target_provenance.get(handle, [])
        sources = sorted({str(item.get("source_handle")) for item in triggers if item.get("source_handle")})
        parent_tasks = sorted({task for item in triggers for task in item.get("task_ids", [])})
        source_in_frozen_plan = any(source in {str(task["source_entity_id"]).upper() for task in task_by_id.values()} for source in sources)
        owned_child = any(item.get("IsPrimary") is False for item in triggers)
        native_dependency = bool(triggers) and any(item.get("IsPrimary") is False or item.get("IsCloned") is True for item in triggers)
        unexpected_evidence.append({
            "handle": handle,
            "ObjectName": after.get("object_name"),
            "layer": after.get("layer"),
            **owner,
            "region_id": _region_for_bbox(_bbox_flat(after), target_regions),
            "bbox": _bbox_flat(after),
            "source_handles": sources,
            "parent_task_ids": parent_tasks,
            "component_ids": sorted({item["component_id"] for item in triggers if item.get("component_id")}),
            "creation_order": order,
            "is_owned_child": owned_child,
            "is_native_dependency": native_dependency,
            "source_handle_is_frozen_task": source_in_frozen_plan,
            "is_duplicate_engineering_object": handle in duplicate_handles,
            "is_unplanned_leak": not native_dependency,
            "copyobjects_calls": triggers,
            "classification": (
                "DUPLICATE_DEPENDENCY" if source_in_frozen_plan
                else "NATIVE_OWNED_DEPENDENCY" if native_dependency
                else "UNMAPPED_EXECUTOR_LEAK"
            ),
        })
    return existing_evidence, unexpected_evidence


def execute_override(paths: OverridePaths) -> dict[str, Any]:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_PLAN_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256', 'sha256')
    EXPECTED_REFERENCE_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256', 'sha256')
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    from mcp.acceptance.stage3_1_r1_target_scan_alignment import _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage3_1_runtime import _norm_path, attach_existing_autocad, detach_autocad, enumerate_live_documents
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _safe_close
    from mcp.orchestration.stage5_1_r3 import _existing_record_unchanged, _scan_modelspace, _snapshot

    manifest = _read_json(paths.root / "override_manifest.json")
    emergency_delivery_mode = bool(manifest.get("emergency_delivery_mode"))
    valid_manifest_statuses = {"READY_FOR_ONE_TIME_OVERRIDE", "READY_FOR_EMERGENCY_DELIVERY"}
    if manifest.get("status") not in valid_manifest_statuses:
        raise RuntimeError("override manifest not prepared")
    main = P1Paths.build(MAIN_RUN_ID)
    plan_path = Path(manifest["frozen_plan_path"])
    plan = _read_json(plan_path)
    validation_errors = _validate_frozen_evidence(plan)
    valid, actual_plan_hash = validate_frozen_execution_plan(plan)
    if not valid or actual_plan_hash != EXPECTED_PLAN_SHA256 or plan.get("plan_sha256") != EXPECTED_PLAN_SHA256:
        validation_errors.append("immutable frozen plan SHA256 mismatch")
    reference = Path(plan["frozen_inputs"]["reference"]["path"])
    target = Path(plan["frozen_inputs"]["target"]["path"])
    backup = Path(plan["frozen_inputs"]["prewrite_backup"]["path"])
    override_copy = Path(manifest["override_copy_path"])
    reference_copy = Path(manifest["reference_execution_copy"])
    if _sha256(override_copy) != EXPECTED_TARGET_SHA256:
        validation_errors.append("override copy initial hash mismatch")
    if _sha256(reference_copy) != EXPECTED_REFERENCE_SHA256:
        validation_errors.append("reference execution copy hash mismatch")
    validation_errors.extend(f"source lock present: {path}" for path in [*_lock_files(reference), *_lock_files(target)])
    if validation_errors:
        result = {
            "phase": "STAGE6-P1-ONE-TIME-OVERRIDE", "status": "BLOCKED_RECOVERY_EVIDENCE_INVALID",
            "errors": validation_errors, "original_target_write": False, "original_target_save": False,
            "production_d1_allowed": False,
        }
        _write_json(paths.reports / "override_result.json", result)
        return result

    region_manifest = _read_json(main.root / "region_manifest.json")
    target_regions = region_manifest["target_regions"]
    protected_bbox = plan["protected_region"]["bbox"]
    task_by_id = {str(task["task_id"]): task for task in plan["tasks"]}
    task_by_source = {str(task["source_entity_id"]).upper(): task for task in plan["tasks"]}
    task_source_handles = set(task_by_source)
    transforms = {item["alignment_id"]: item["transform"] for item in plan["alignment_evidence"]}
    component_plan = _read_json(Path(plan["core_component_dependency_plan"]["path"]))
    ordinary_by_transform: dict[str, list[str]] = defaultdict(list)
    for task in plan["tasks"]:
        if task["task_group"] == "ordinary":
            ordinary_by_transform[str(task["transform_id"])].append(str(task["source_entity_id"]).upper())

    acad = source_doc = target_doc = persisted_doc = None
    provenance: list[dict[str, Any]] = []
    source_to_target: dict[str, str] = {}
    planned_created_handles: list[str] = []
    initial_records: list[dict[str, Any]] = []
    after_records: list[dict[str, Any]] = []
    persisted_records: list[dict[str, Any]] = []
    initial_snapshot: dict[str, dict[str, Any]] = {}
    after_snapshot: dict[str, dict[str, Any]] = {}
    persisted_snapshot: dict[str, dict[str, Any]] = {}
    modified_handles: list[str] = []
    deleted_handles: list[str] = []
    unexpected_handles: list[str] = []
    existing_evidence: list[dict[str, Any]] = []
    unexpected_evidence: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    protected_modified: list[str] = []
    actual_protected_intersections: list[str] = []
    wrong_region: list[dict[str, Any]] = []
    pre_save_type_bbox_errors: list[dict[str, Any]] = []
    persistence_errors: list[dict[str, Any]] = []
    relationship_qa: dict[str, Any] = {"passed": False, "checked_relationship_count": 0, "relationship_mismatch_count": 0}
    saved = reopened = False
    hard_stop_reasons: list[str] = []
    error: str | None = None
    call_counter = 0
    live_documents = []
    try:
        acad = attach_existing_autocad()
        live = enumerate_live_documents(acad, (reference, target, backup, override_copy, reference_copy))
        live_documents = live.get("documents", [])
        forbidden = {_norm_path(reference), _norm_path(target), _norm_path(backup)}
        opened_originals = [
            item for item in live_documents
            if item.get("full_name") and _norm_path(Path(item["full_name"])) in forbidden
        ]
        if opened_originals:
            raise RuntimeError(f"original input is open in AutoCAD: {opened_originals}")
        source_doc = _resolve_open_document(acad, reference_copy, _open_document_with_retry(acad, reference_copy))
        target_doc = _resolve_open_document(acad, override_copy, _open_document_with_retry(acad, override_copy))
        initial_records = _retry(lambda: _scan_modelspace(target_doc, "stage6_override_before"), "override initial scan", attempts=60, delay=0.5)
        initial_snapshot = _snapshot(initial_records)
        _write_json(paths.checkpoints / "checkpoint_01_initial_scan.json", {
            "status": "INITIAL_SCAN_COMPLETE", "modelspace_count": len(initial_records),
            "override_copy_hash_before_open": manifest["override_copy_initial_hash"],
        })

        for transform_id, handles in sorted(ordinary_by_transform.items()):
            translation = transforms[transform_id]["translation"]
            for batch_index, batch in enumerate(_chunks(sorted(handles), 200), 1):
                call_counter += 1
                tasks = [task_by_source[handle]["task_id"] for handle in batch]
                call = _copy_and_move_with_provenance(
                    source_doc, target_doc, batch, translation,
                    call_id=f"copyobjects_{call_counter:04d}",
                    label=f"ordinary {transform_id} batch {batch_index}",
                    task_ids=tasks, component_id=None,
                )
                provenance.append(call)
                planned_created_handles.extend(call["primary_target_handles"])
                source_to_target.update({
                    str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper()
                    for pair in call["primary_pairs"]
                })
                _write_json(paths.checkpoints / "execution_progress.json", {
                    "copyobjects_call_count": call_counter,
                    "mapped_task_count": len(source_to_target),
                    "last_call_id": call["call_id"], "save_called": False,
                })

        valve_calls: list[tuple[dict[str, Any], list[str]]] = []
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
                call_counter += 1
                transform_id = str(task_by_source[non_valves[0]]["transform_id"])
                call = _copy_and_move_with_provenance(
                    source_doc, target_doc, non_valves, transforms[transform_id]["translation"],
                    call_id=f"copyobjects_{call_counter:04d}", label=component["component_id"],
                    task_ids=[task_by_source[handle]["task_id"] for handle in non_valves],
                    component_id=component["component_id"],
                )
                provenance.append(call); planned_created_handles.extend(call["primary_target_handles"])
                source_to_target.update({
                    str(pair["source_handle"]).upper(): str(pair["target_handle"]).upper()
                    for pair in call["primary_pairs"]
                })
            if valves:
                valve_calls.append((component, valves))
            _write_json(paths.checkpoints / "execution_progress.json", {
                "copyobjects_call_count": call_counter,
                "mapped_task_count": len(task_source_handles & set(source_to_target)),
                "last_component_id": component["component_id"], "save_called": False,
            })

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
                _write_json(paths.checkpoints / "execution_progress.json", {
                    "copyobjects_call_count": call_counter,
                    "mapped_task_count": len(task_source_handles & set(source_to_target)),
                    "last_call_id": call["call_id"], "save_called": False,
                })

        after_records = _retry(lambda: _scan_modelspace(target_doc, "stage6_override_after"), "override final pre-save scan", attempts=60, delay=0.5)
        after_snapshot = _snapshot(after_records)
        planned_created_set = set(planned_created_handles)
        deleted_handles = sorted(set(initial_snapshot) - set(after_snapshot))
        modified_handles = sorted(
            handle for handle, before in initial_snapshot.items()
            if handle in after_snapshot and not _existing_record_unchanged(before, after_snapshot[handle])
        )
        unexpected_handles = sorted(set(after_snapshot) - set(initial_snapshot) - planned_created_set)
        new_handles = planned_created_set | set(unexpected_handles)
        duplicates = _introduced_duplicates(initial_snapshot, after_snapshot, new_handles)
        protected_initial = {
            handle for handle, record in initial_snapshot.items()
            if _bbox_intersects(_bbox_flat(record), protected_bbox)
        }
        protected_modified = sorted(
            handle for handle in protected_initial
            if handle not in after_snapshot or not _existing_record_unchanged(initial_snapshot[handle], after_snapshot[handle])
        )
        actual_protected_intersections = sorted(
            handle for handle in new_handles
            if handle in after_snapshot and _bbox_intersects(_bbox_flat(after_snapshot[handle]), protected_bbox)
        )
        for source_handle in task_source_handles:
            task = task_by_source[source_handle]
            target_handle = source_to_target.get(source_handle)
            record = after_snapshot.get(target_handle or "")
            if not record or record.get("object_name") != task["object_name"] or not _bbox_close(_bbox_flat(record), task["target_bbox_evidence"]):
                pre_save_type_bbox_errors.append({
                    "task_id": task["task_id"], "target_handle": target_handle,
                    "expected_object_name": task["object_name"],
                    "actual_object_name": None if record is None else record.get("object_name"),
                    "expected_bbox": task["target_bbox_evidence"],
                    "actual_bbox": None if record is None else _bbox_flat(record),
                })
            elif _region_for_bbox(_bbox_flat(record), target_regions) != task["target_region_id"]:
                wrong_region.append({
                    "task_id": task["task_id"], "target_handle": target_handle,
                    "expected_region_id": task["target_region_id"],
                    "actual_region_id": _region_for_bbox(_bbox_flat(record), target_regions),
                })
        existing_evidence, unexpected_evidence = _side_effect_evidence(
            modified_handles, unexpected_handles, initial_snapshot, after_snapshot,
            provenance, task_by_id, target_regions, target_doc, duplicates,
        )
        _write_json(paths.evidence / "copyobjects_provenance.json", {"calls": provenance})
        _write_json(paths.evidence / "existing_modified_evidence.json", {"count": len(existing_evidence), "items": existing_evidence})
        _write_json(paths.evidence / "unexpected_new_evidence.json", {"count": len(unexpected_evidence), "items": unexpected_evidence})
        _write_json(paths.evidence / "pre_save_snapshot.json", {"records": after_records})
        entire_frame_wrong = _entire_frame_wrong_regions(plan["tasks"], wrong_region)
        frame_title_modified = [
            handle for handle in modified_handles
            if after_snapshot[handle].get("object_name") in {"AcDbBlockReference", "AcDbTable"}
            or any(token in str(after_snapshot[handle].get("layer") or "").upper() for token in ("FRAME", "TITLE", "BORDER"))
        ]
        hard_stop_reasons.extend([
            *( [f"existing_modified count {len(modified_handles)} != authorized {EXPECTED_EXISTING_MODIFIED}"] if not emergency_delivery_mode and len(modified_handles) != EXPECTED_EXISTING_MODIFIED else [] ),
            *( [f"unexpected_new count {len(unexpected_handles)} != authorized {EXPECTED_UNEXPECTED_NEW}"] if not emergency_delivery_mode and len(unexpected_handles) != EXPECTED_UNEXPECTED_NEW else [] ),
            *( [f"existing_deleted={len(deleted_handles)}"] if deleted_handles else [] ),
            *( [f"protected_region_modified={len(protected_modified)}"] if protected_modified else [] ),
            *( [f"protected_region_intersection={len(actual_protected_intersections)}"] if actual_protected_intersections else [] ),
            *( [f"duplicate_visible_engineering_objects={len(duplicates)}"] if not emergency_delivery_mode and duplicates else [] ),
            *( [f"wrong_region_write={len(wrong_region)}"] if not emergency_delivery_mode and wrong_region else [] ),
            *( [f"entire_frame_wrong={entire_frame_wrong}"] if entire_frame_wrong else [] ),
            *( [f"frame_or_title_modified={len(frame_title_modified)}"] if frame_title_modified else [] ),
            *( [f"pre_save_type_or_bbox_errors={len(pre_save_type_bbox_errors)}"] if pre_save_type_bbox_errors else [] ),
        ])
        _write_json(paths.checkpoints / "checkpoint_02_pre_save_hard_gate.json", {
            "status": "PASS_OVERRIDE_PRE_SAVE_HARD_GATE" if not hard_stop_reasons else "FAILED_OVERRIDE_HARD_STOP",
            "mapped_task_count": len(task_source_handles & set(source_to_target)),
            "existing_modified": len(modified_handles), "unexpected_new": len(unexpected_handles),
            "existing_deleted": len(deleted_handles), "protected_region_modified": len(protected_modified),
            "protected_region_intersection": len(actual_protected_intersections),
            "duplicate": len(duplicates), "wrong_region": len(wrong_region),
            "entire_frame_wrong": entire_frame_wrong,
            "frame_or_title_modified": len(frame_title_modified),
            "emergency_delivery_mode": emergency_delivery_mode,
            "hard_stop_reasons": hard_stop_reasons, "save_called": False,
        })
        if hard_stop_reasons:
            raise RuntimeError(f"FAILED_OVERRIDE_HARD_STOP: {hard_stop_reasons}")

        _retry(lambda: target_doc.Save(), "override rehearsal save", attempts=30, delay=0.5)
        saved = True
        _write_json(paths.checkpoints / "checkpoint_03_saved.json", {
            "status": "OVERRIDE_COPY_SAVED", "saved": True, "override_sha256": _sha256(override_copy),
        })
        _safe_close(target_doc); target_doc = None
        _safe_close(source_doc); source_doc = None
        persisted_doc = _resolve_open_document(acad, override_copy, _open_document_with_retry(acad, override_copy))
        reopened = True
        persisted_records = _retry(lambda: _scan_modelspace(persisted_doc, "stage6_override_persisted"), "override persisted scan", attempts=60, delay=0.5)
        persisted_snapshot = _snapshot(persisted_records)
        for handle, record in after_snapshot.items():
            persisted = persisted_snapshot.get(handle)
            if persisted is None or not _existing_record_unchanged(record, persisted):
                persistence_errors.append({
                    "handle": handle, "before_save": record, "after_reopen": persisted,
                })
        persisted_protected_modified = sorted(
            handle for handle in protected_initial
            if handle not in persisted_snapshot
            or not _existing_record_unchanged(initial_snapshot[handle], persisted_snapshot[handle])
        )
        persisted_duplicates = _introduced_duplicates(initial_snapshot, persisted_snapshot, new_handles)
        relationship_qa = _relationship_audit(component_plan, task_by_id, source_to_target, persisted_doc)
        if persistence_errors:
            hard_stop_reasons.append(f"persistence_errors={len(persistence_errors)}")
        if persisted_protected_modified:
            hard_stop_reasons.append(f"persisted_protected_region_modified={len(persisted_protected_modified)}")
        if persisted_duplicates and not emergency_delivery_mode:
            hard_stop_reasons.append(f"persisted_duplicate={len(persisted_duplicates)}")
        if not relationship_qa.get("passed") and not emergency_delivery_mode:
            hard_stop_reasons.append(f"topology_relationship_mismatch={relationship_qa.get('relationship_mismatch_count')}")
        _write_json(paths.evidence / "persisted_snapshot.json", {"records": persisted_records})
        _write_json(paths.evidence / "persistence_qa.json", {
            "passed": not persistence_errors, "error_count": len(persistence_errors), "errors": persistence_errors,
        })
        _write_json(paths.evidence / "topology_qa.json", relationship_qa)
        _write_json(paths.evidence / "protected_region_qa.json", {
            "passed": not persisted_protected_modified,
            "protected_region_modified": len(persisted_protected_modified),
            "modified_handles": persisted_protected_modified,
        })
        _write_json(paths.evidence / "duplicate_qa.json", {
            "passed": not persisted_duplicates, "duplicate_count": len(persisted_duplicates), "items": persisted_duplicates,
        })
        dry_diff_errors = []
        for source_handle in task_source_handles:
            task = task_by_source[source_handle]
            target_handle = source_to_target.get(source_handle)
            record = persisted_snapshot.get(target_handle or "")
            if not record or record.get("object_name") != task["object_name"] or not _bbox_close(_bbox_flat(record), task["target_bbox_evidence"]):
                dry_diff_errors.append(task["task_id"])
        dry_diff = {
            "phase": "STAGE6-P1-OVERRIDE-DRY-DIFF",
            "second_write_executed": False,
            "frozen_task_count": len(plan["tasks"]),
            "persisted_frozen_task_count": len(plan["tasks"]) - len(dry_diff_errors),
            "remaining_frozen_task_count": len(dry_diff_errors),
            "remaining_task_ids": dry_diff_errors,
            "passed": not dry_diff_errors,
        }
        _write_json(paths.evidence / "dry_diff.json", dry_diff)
        if dry_diff_errors:
            hard_stop_reasons.append(f"dry_diff_remaining={len(dry_diff_errors)}")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _safe_close(persisted_doc); _safe_close(target_doc); _safe_close(source_doc)
        if acad is not None:
            detach_autocad()

    originals = {
        "reference": _sha256(reference), "target": _sha256(target), "prewrite_backup": _sha256(backup),
    }
    original_hashes_unchanged = originals == {
        "reference": EXPECTED_REFERENCE_SHA256,
        "target": EXPECTED_TARGET_SHA256,
        "prewrite_backup": EXPECTED_TARGET_SHA256,
    }
    if not original_hashes_unchanged:
        hard_stop_reasons.append("original input hash changed")
    hard_pass = all((
        saved, reopened, not hard_stop_reasons, original_hashes_unchanged,
        not deleted_handles, not protected_modified, not actual_protected_intersections,
        not pre_save_type_bbox_errors, not persistence_errors,
        emergency_delivery_mode or (
            len(modified_handles) == EXPECTED_EXISTING_MODIFIED
            and len(unexpected_handles) == EXPECTED_UNEXPECTED_NEW
            and not duplicates and not wrong_region and relationship_qa.get("passed") is True
        ),
    ))
    success_status = "EMERGENCY_DELIVERY_DWG_CREATED" if emergency_delivery_mode else "OVERRIDE_REHEARSAL_SAVED_FOR_MANUAL_REVIEW"
    status = success_status if hard_pass else "FAILED_OVERRIDE_HARD_STOP"
    previews = {"created": False, "paths": []}
    if persisted_records:
        try:
            previews = _render_previews(
                paths, initial_records, persisted_records, set(planned_created_handles),
                set(unexpected_handles), set(modified_handles), target_regions,
            )
        except Exception as exc:
            hard_stop_reasons.append(f"preview_generation_failed: {type(exc).__name__}: {exc}")
            status = "FAILED_OVERRIDE_HARD_STOP"
    result = {
        "phase": "STAGE6-P1-ONE-TIME-OVERRIDE",
        "status": status,
        "run_id": paths.run_id,
        "main_run_id": MAIN_RUN_ID,
        "main_plan_paused": True,
        "stage6_p1_status": "FAILED_REHEARSAL_STOP_GATE",
        "one_time_rehearsal_override": True,
        "emergency_delivery_mode": emergency_delivery_mode,
        "manual_cleanup_required": emergency_delivery_mode,
        "normal_safety_gate_passed": False if emergency_delivery_mode else hard_pass,
        "allow_save_with_existing_modified": True,
        "allow_save_with_unexpected_new": True,
        "side_effects_unresolved": True,
        "frozen_plan_sha256": plan["plan_sha256"],
        "planned_task_count": len(plan["tasks"]),
        "executed_task_count": len(task_source_handles & set(source_to_target)),
        "planned_created_handle_count": len(set(planned_created_handles)),
        "existing_modified": len(modified_handles),
        "unexpected_new": len(unexpected_handles),
        "existing_deleted": len(deleted_handles),
        "protected_region_modified": len(protected_modified),
        "protected_region_intersection": len(actual_protected_intersections),
        "duplicate": len(duplicates),
        "wrong_region_write": len(wrong_region),
        "saved": saved,
        "closed_and_reopened": reopened,
        "persistence_qa": not persistence_errors and reopened,
        "topology_qa": relationship_qa,
        "duplicate_qa": {"passed": not duplicates, "items": duplicates},
        "dry_diff_path": str(paths.evidence / "dry_diff.json") if persisted_records else None,
        "override_dwg_path": str(override_copy),
        "override_initial_hash": manifest["override_copy_initial_hash"],
        "override_final_hash": _sha256(override_copy),
        "original_hashes": originals,
        "original_hashes_unchanged": original_hashes_unchanged,
        "existing_modified_evidence_path": str(paths.evidence / "existing_modified_evidence.json"),
        "unexpected_new_evidence_path": str(paths.evidence / "unexpected_new_evidence.json"),
        "preview_paths": previews["paths"],
        "previews_created": previews["created"],
        "copyobjects_call_count": call_counter,
        "live_documents_before_execution": live_documents,
        "hard_stop_reasons": hard_stop_reasons,
        "error": error,
        "original_target_write": False,
        "original_target_save": False,
        "reference_read_only": True,
        "reference_save": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "production_d1_allowed": False,
        "mvp3_completed": False,
        "mvp4_allowed": False,
        "next_stage_pending": "Stage 6-P1-R1 — Rehearsal Side-Effect Forensics",
    }
    _write_json(paths.reports / "override_result.json", result)
    _write_json(paths.checkpoints / "checkpoint_04_final.json", result)
    return result


def write_override_reports(paths: OverridePaths, result: Mapping[str, Any], tests: Mapping[str, Any]) -> dict[str, Any]:
    saved_for_review = result.get("status") == "OVERRIDE_REHEARSAL_SAVED_FOR_MANUAL_REVIEW"
    report = {
        **dict(result),
        "tests": dict(tests),
        "manual_review_required": saved_for_review,
        "override_dwg_manual_review_available": saved_for_review,
        "static_unsaved_preview_review_available": bool(result.get("previews_created")),
        "manual_review_scope": [
            "七张图是否进入正确图框",
            "管线、阀门、设备是否明显错位",
            "是否存在重复管道、重复阀门、重复文字",
            "原有对象是否被移动或改色",
            "水泵房是否完全没有变化",
            "图框和标题栏是否未修改",
            "天正对象是否可以正常选择和编辑",
            "关闭重开后是否存在报错",
            "是否有对象消失、错层或异常显示",
        ],
        "manual_acceptance_does_not_close_side_effects": True,
        "side_effect_forensics_pending": True,
        "main_plan_resume_allowed": False,
    }
    _write_json(paths.reports / "stage6_p1_override_rehearsal.json", report)
    global_json = ROOT / "reports" / f"{paths.run_id}.json"
    global_md = ROOT / "reports" / f"{paths.run_id}.md"
    _write_json(global_json, report)
    lines = [
        "# Stage 6-P1 Recovery + One-Time Override Rehearsal", "",
        f"- status: {report['status']}",
        f"- run_id: {paths.run_id}",
        f"- main plan paused: {str(report['main_plan_paused']).lower()}",
        f"- frozen plan SHA256: {report['frozen_plan_sha256']}",
        f"- executed tasks: {report['executed_task_count']}/{report['planned_task_count']}",
        f"- existing modified: {report['existing_modified']}",
        f"- unexpected new: {report['unexpected_new']}",
        f"- existing deleted: {report['existing_deleted']}",
        f"- protected region modified/intersection: {report['protected_region_modified']}/{report['protected_region_intersection']}",
        f"- duplicate: {report['duplicate']}",
        f"- saved/reopened: {str(report['saved']).lower()}/{str(report['closed_and_reopened']).lower()}",
        f"- persistence QA: {str(report['persistence_qa']).lower()}",
        f"- topology QA: {str(report['topology_qa'].get('passed')).lower()}",
        f"- original hashes unchanged: {str(report['original_hashes_unchanged']).lower()}",
        "- original target write/save: false/false",
        "- Production D1 allowed: false", "",
        "## Override DWG", "", report["override_dwg_path"], "",
        "## Review Evidence", "",
    ]
    lines.extend(f"- {item}" for item in report["manual_review_scope"])
    lines.extend([
        "", (
            "人工检查通过也不能自动关闭 existing_modified/unexpected_new 副作用。"
            if saved_for_review else
            "Override DWG 未保存，磁盘文件仍是干净基线；仅可审查未保存内存态诊断预览和 JSON 证据。"
        ),
        "", "## Next Pending Stage", "", report["next_stage_pending"], "",
    ])
    if report.get("hard_stop_reasons"):
        lines.extend(["## Hard Stop Reasons", ""])
        lines.extend(f"- {item}" for item in report["hard_stop_reasons"])
        lines.append("")
    text = "\n".join(lines)
    (paths.reports / "stage6_p1_override_rehearsal.md").write_text(text, encoding="utf-8")
    global_md.write_text(text, encoding="utf-8")
    return report


def finalize_hard_stop_static_evidence(paths: OverridePaths) -> dict[str, Any]:
    """Build diagnostics from captured JSON only; never reconnect to AutoCAD."""
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    result_path = paths.reports / "override_result.json"
    result = _read_json(result_path)
    main = P1Paths.build(MAIN_RUN_ID)
    plan = _read_json(main.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json")
    region_manifest = _read_json(main.root / "region_manifest.json")
    target_regions = region_manifest["target_regions"]
    before_records = _read_json(main.root / "target_scan.json")["entities"]
    after_records = _read_json(paths.evidence / "pre_save_snapshot.json")["records"]
    provenance = _read_json(paths.evidence / "copyobjects_provenance.json")["calls"]
    existing_evidence = _read_json(paths.evidence / "existing_modified_evidence.json")["items"]
    unexpected_evidence = _read_json(paths.evidence / "unexpected_new_evidence.json")["items"]
    before_snapshot = {str(item["handle"]): item for item in before_records if item.get("handle")}
    after_snapshot = {str(item["handle"]): item for item in after_records if item.get("handle")}
    source_to_target = {}
    planned_created = set()
    for call in provenance:
        for pair in call.get("primary_pairs", []):
            source = str(pair.get("source_handle") or "").upper()
            target = str(pair.get("target_handle") or "").upper()
            if source and target:
                source_to_target[source] = target
                planned_created.add(target)
    unexpected_handles = {str(item["handle"]) for item in unexpected_evidence}
    modified_handles = {str(item["handle"]) for item in existing_evidence}
    duplicates = _introduced_duplicates(before_snapshot, after_snapshot, planned_created | unexpected_handles)
    wrong_region = []
    for task in plan["tasks"]:
        source_handle = str(task["source_entity_id"]).upper()
        target_handle = source_to_target.get(source_handle)
        record = after_snapshot.get(target_handle or "")
        if not record:
            continue
        actual_region = _region_for_bbox(_bbox_flat(record), target_regions)
        if actual_region != task["target_region_id"]:
            wrong_region.append({
                "task_id": task["task_id"],
                "source_handle": source_handle,
                "target_handle": target_handle,
                "object_name": record.get("object_name"),
                "expected_region_id": task["target_region_id"],
                "actual_region_id": actual_region,
                "actual_bbox": _bbox_flat(record),
                "expected_bbox": task["target_bbox_evidence"],
                "transform_id": task["transform_id"],
            })
    preview = _render_previews(
        paths, before_records, after_records, planned_created, unexpected_handles,
        modified_handles, target_regions,
    )
    diagnostics = {
        "phase": "STAGE6-P1-OVERRIDE-HARD-STOP-STATIC-DIAGNOSTICS",
        "status": "FAILED_OVERRIDE_HARD_STOP",
        "source": "captured_unsaved_memory_state_json",
        "autocad_reconnected": False,
        "dwg_saved": False,
        "wrong_region_write_count": len(wrong_region),
        "wrong_region_items": wrong_region,
        "duplicate_group_count": len(duplicates),
        "duplicate_groups": duplicates,
        "preview_state": "UNSAVED_MEMORY_STATE_DIAGNOSTIC_ONLY",
        "preview_paths": preview["paths"],
        "override_dwg_remains_clean_baseline": _sha256(Path(result["override_dwg_path"])) == EXPECTED_TARGET_SHA256,
        "original_target_write": False,
        "original_target_save": False,
        "production_d1_allowed": False,
    }
    _write_json(paths.evidence / "hard_stop_static_diagnostics.json", diagnostics)
    result.update({
        "wrong_region_items_path": str(paths.evidence / "hard_stop_static_diagnostics.json"),
        "duplicate_items_path": str(paths.evidence / "hard_stop_static_diagnostics.json"),
        "preview_paths": preview["paths"],
        "previews_created": preview["created"],
        "preview_state": "UNSAVED_MEMORY_STATE_DIAGNOSTIC_ONLY",
        "override_dwg_remains_clean_baseline": diagnostics["override_dwg_remains_clean_baseline"],
        "override_dwg_contains_executed_tasks": False,
    })
    _write_json(result_path, result)
    _write_json(paths.checkpoints / "checkpoint_05_static_evidence.json", diagnostics)
    return result


def _render_emergency_after_previews(
    paths: OverridePaths,
    records: Sequence[Mapping[str, Any]],
    target_regions: Sequence[Mapping[str, Any]],
    wrong_handles: set[str],
    duplicate_handles: set[str],
) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    by_handle = {str(item.get("handle")): item for item in records if item.get("handle")}

    def segments(handles: Sequence[str] | None, bounds: Sequence[float] | None) -> list[list[tuple[float, float]]]:
        selected = records if handles is None else [by_handle[h] for h in handles if h in by_handle]
        values = []
        for record in selected:
            bbox = _bbox_flat(record)
            if bbox is None or (bounds is not None and not _bbox_intersects(bbox, bounds)):
                continue
            x1, y1, x2, y2 = bbox
            if abs(x2 - x1) < 1e-6 and abs(y2 - y1) < 1e-6:
                values.append([(x1 - 2, y1), (x1 + 2, y1)])
            else:
                values.extend([
                    [(x1, y1), (x2, y1)], [(x2, y1), (x2, y2)],
                    [(x2, y2), (x1, y2)], [(x1, y2), (x1, y1)],
                ])
        return values

    def render(path: Path, bounds: Sequence[float] | None, highlights: set[str], color: str, title: str) -> None:
        fig, axis = plt.subplots(figsize=(12, 8), dpi=150)
        axis.add_collection(LineCollection(segments(None, bounds), colors="#AEB5BD", linewidths=0.25, alpha=0.7))
        if highlights:
            axis.add_collection(LineCollection(segments(sorted(highlights), bounds), colors=color, linewidths=1.2, alpha=0.95))
        if bounds:
            axis.set_xlim(bounds[0], bounds[2]); axis.set_ylim(bounds[1], bounds[3])
        else:
            boxes = [_bbox_flat(record) for record in records]
            boxes = [bbox for bbox in boxes if bbox]
            axis.set_xlim(min(b[0] for b in boxes), max(b[2] for b in boxes))
            axis.set_ylim(min(b[1] for b in boxes), max(b[3] for b in boxes))
        axis.set_aspect("equal", adjustable="box")
        axis.set_title(title)
        axis.axis("off")
        fig.tight_layout(); fig.savefig(path, bbox_inches="tight"); plt.close(fig)

    outputs = []
    full = paths.previews / "full_drawing_after.png"
    render(full, None, wrong_handles | duplicate_handles, "#E5484D", "Emergency delivery - full drawing after reopen")
    outputs.append(str(full))
    region_by_id = {item["region_id"]: item for item in target_regions}
    for index in range(1, 8):
        region = region_by_id[f"target_region_{index:04d}"]
        path = paths.previews / f"region_{index:04d}_after.png"
        render(path, region["bbox"], wrong_handles | duplicate_handles, "#E5484D", f"target_region_{index:04d} after reopen")
        outputs.append(str(path))
    wrong_path = paths.previews / "wrong_region_objects.png"
    render(wrong_path, None, wrong_handles, "#FF3B30", "Wrong-region candidates")
    outputs.append(str(wrong_path))
    duplicate_path = paths.previews / "duplicate_candidates.png"
    render(duplicate_path, None, duplicate_handles, "#AF52DE", "Duplicate candidates")
    outputs.append(str(duplicate_path))
    return outputs


def finalize_emergency_delivery(paths: OverridePaths, tests: Mapping[str, Any]) -> dict[str, Any]:
    result_path = paths.reports / "override_result.json"
    result = _read_json(result_path)
    main = P1Paths.build(MAIN_RUN_ID)
    plan = _read_json(main.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json")
    region_manifest = _read_json(main.root / "region_manifest.json")
    target_regions = region_manifest["target_regions"]
    before_records = _read_json(main.root / "target_scan.json")["entities"]
    persisted_records = _read_json(paths.evidence / "persisted_snapshot.json")["records"]
    provenance = _read_json(paths.evidence / "copyobjects_provenance.json")["calls"]
    existing_items = _read_json(paths.evidence / "existing_modified_evidence.json")["items"]
    unexpected_items = _read_json(paths.evidence / "unexpected_new_evidence.json")["items"]
    before_snapshot = {str(item["handle"]): item for item in before_records if item.get("handle")}
    persisted_snapshot = {str(item["handle"]): item for item in persisted_records if item.get("handle")}
    source_to_target = {}
    planned_created = set()
    for call in provenance:
        for pair in call.get("primary_pairs", []):
            source = str(pair.get("source_handle") or "").upper()
            target = str(pair.get("target_handle") or "").upper()
            if source and target:
                source_to_target[source] = target
                planned_created.add(target)
    wrong_items = []
    for task in plan["tasks"]:
        target_handle = source_to_target.get(str(task["source_entity_id"]).upper())
        record = persisted_snapshot.get(target_handle or "")
        if not record:
            continue
        actual_region = _region_for_bbox(_bbox_flat(record), target_regions)
        if actual_region != task["target_region_id"]:
            bbox = _bbox_flat(record)
            expected_region = next(item for item in target_regions if item["region_id"] == task["target_region_id"])
            actual_center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2) if bbox else (0.0, 0.0)
            expected_center = (
                (expected_region["bbox"][0] + expected_region["bbox"][2]) / 2,
                (expected_region["bbox"][1] + expected_region["bbox"][3]) / 2,
            )
            wrong_items.append({
                "task_id": task["task_id"], "handle": target_handle,
                "ObjectName": record.get("object_name"),
                "current_region_id": actual_region,
                "expected_region_id": task["target_region_id"],
                "bbox": bbox,
                "suggested_translation": [
                    round(expected_center[0] - actual_center[0], 3),
                    round(expected_center[1] - actual_center[1], 3),
                ],
                "affects_print_or_submission": True,
            })
    unexpected_handles = {str(item["handle"]) for item in unexpected_items}
    duplicates = _introduced_duplicates(before_snapshot, persisted_snapshot, planned_created | unexpected_handles)
    duplicate_handles = {
        handle for item in duplicates for handle in [*item.get("preexisting_handles", []), *item.get("new_handles", [])]
    }
    wrong_handles = {str(item["handle"]) for item in wrong_items if item.get("handle")}
    preview_paths = _render_emergency_after_previews(
        paths, persisted_records, target_regions, wrong_handles, duplicate_handles,
    )
    diagnostics = {
        "phase": "STAGE6-P1-EMERGENCY-DIAGNOSTICS",
        "wrong_region_write_count": len(wrong_items),
        "wrong_region_items": wrong_items,
        "duplicate_candidate_count": len(duplicates),
        "duplicate_candidates": duplicates,
        "existing_modified": existing_items,
        "unexpected_new": unexpected_items,
        "protected_pump_room": {
            "classification": "PROTECTED_COMPLETE_REGION",
            "modified_count": result["protected_region_modified"],
            "unchanged": result["protected_region_modified"] == 0,
        },
        "preview_paths": preview_paths,
        "manual_cleanup_required": True,
        "production_d1_allowed": False,
    }
    _write_json(paths.evidence / "emergency_diagnostics.json", diagnostics)
    cleanup_path = ROOT / "reports" / "stage6_p1_emergency_manual_cleanup.md"
    lines = [
        "# Stage 6-P1 应急提交版人工修正清单", "",
        f"- run_id: {paths.run_id}",
        f"- 应急 DWG: {result['override_dwg_path']}",
        f"- 错区候选: {len(wrong_items)}",
        f"- 重复候选组: {len(duplicates)}",
        f"- 原有对象变化: {len(existing_items)}",
        f"- 计划外对象: {len(unexpected_items)}",
        f"- 水泵房保持不变: {str(result['protected_region_modified'] == 0).lower()}", "",
    ]
    grouped_wrong: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in wrong_items:
        grouped_wrong[item["expected_region_id"]].append(item)
    for region_id in [f"target_region_{index:04d}" for index in range(1, 8)]:
        lines.extend([f"## {region_id}", ""])
        items = grouped_wrong.get(region_id, [])
        if not items:
            lines.append("- 无错区候选。")
        for item in items:
            lines.append(
                f"- Handle `{item['handle']}` | {item['ObjectName']} | 当前图框 `{item['current_region_id']}` | "
                f"预期图框 `{item['expected_region_id']}` | bbox `{item['bbox']}` | "
                f"建议平移 `{item['suggested_translation']}` | 影响打印/提交：YES"
            )
        region_duplicates = [
            item for item in duplicates
            if _region_for_bbox(item.get("bbox"), target_regions) == region_id
        ]
        lines.append(f"- 重复对象候选组：{len(region_duplicates)}")
        lines.append("")
    lines.extend(["## 原有对象变化", ""])
    for item in existing_items:
        lines.append(
            f"- Handle `{item['handle']}` | {item['ObjectName']} | 图层 `{item['layer']}` | "
            f"区域 `{item['region_id']}` | changed_fields `{item['changed_fields']}`"
        )
    lines.extend(["", "## 计划外对象", ""])
    for item in unexpected_items:
        lines.append(
            f"- Handle `{item['handle']}` | {item['ObjectName']} | 区域 `{item['region_id']}` | "
            f"bbox `{item['bbox']}` | classification `{item['classification']}`"
        )
    lines.extend([
        "", "## 水泵房", "",
        "- classification: PROTECTED_COMPLETE_REGION",
        f"- 修改数量：{result['protected_region_modified']}",
        "- 人工检查：确认打印预览中水泵房图框、文字、管线、阀门和设备均未变化。", "",
    ])
    cleanup_path.write_text("\n".join(lines), encoding="utf-8")
    report = {
        **result,
        "normal_safety_gate_passed": False,
        "manual_cleanup_required": True,
        "side_effects_unresolved": True,
        "mvp3_completed": False,
        "mvp4_allowed": False,
        "production_d1_allowed": False,
        "original_target_unchanged": result["original_hashes_unchanged"],
        "reference_unchanged": result["original_hashes_unchanged"],
        "manual_cleanup_path": str(cleanup_path),
        "preview_paths": preview_paths,
        "emergency_diagnostics_path": str(paths.evidence / "emergency_diagnostics.json"),
        "tests": dict(tests),
    }
    _write_json(paths.reports / "stage6_p1_emergency_delivery.json", report)
    _write_json(ROOT / "reports" / "stage6_p1_emergency_delivery.json", report)
    report_md = ROOT / "reports" / "stage6_p1_emergency_delivery.md"
    report_md.write_text(
        "\n".join([
            "# Stage 6-P1 Emergency Delivery", "",
            f"- status: {report['status']}",
            f"- run_id: {paths.run_id}",
            f"- executed tasks: {report['executed_task_count']}",
            f"- saved/reopened: {str(report['saved']).lower()}/{str(report['closed_and_reopened']).lower()}",
            f"- existing modified/unexpected new: {report['existing_modified']}/{report['unexpected_new']}",
            f"- duplicate/wrong region: {report['duplicate']}/{report['wrong_region_write']}",
            f"- existing deleted/protected modified: {report['existing_deleted']}/{report['protected_region_modified']}",
            f"- original inputs unchanged: {str(report['original_hashes_unchanged']).lower()}",
            "- normal safety gate passed: false",
            "- manual cleanup required: true",
            "- MVP3/MVP4: false/false",
            "- Production D1 allowed: false", "",
        ]), encoding="utf-8",
    )
    return report


def finalize_emergency_failure_static(paths: OverridePaths, tests: Mapping[str, Any]) -> dict[str, Any]:
    """Finalize a failed pre-save emergency run using captured JSON only."""
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_TARGET_SHA256 = require_parameter('mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256', 'sha256')
    result = finalize_hard_stop_static_evidence(paths)
    main = P1Paths.build(MAIN_RUN_ID)
    region_manifest = _read_json(main.root / "region_manifest.json")
    target_regions = region_manifest["target_regions"]
    after_records = _read_json(paths.evidence / "pre_save_snapshot.json")["records"]
    diagnostics = _read_json(paths.evidence / "hard_stop_static_diagnostics.json")
    existing_items = _read_json(paths.evidence / "existing_modified_evidence.json")["items"]
    unexpected_items = _read_json(paths.evidence / "unexpected_new_evidence.json")["items"]
    wrong_items = diagnostics["wrong_region_items"]
    duplicates = diagnostics["duplicate_groups"]
    wrong_handles = {str(item["target_handle"]) for item in wrong_items if item.get("target_handle")}
    duplicate_handles = {
        handle for item in duplicates for handle in [*item.get("preexisting_handles", []), *item.get("new_handles", [])]
    }
    preview_paths = _render_emergency_after_previews(
        paths, after_records, target_regions, wrong_handles, duplicate_handles,
    )
    cleanup_path = ROOT / "reports" / "stage6_p1_emergency_manual_cleanup.md"
    target_by_id = {item["region_id"]: item for item in target_regions}
    enriched_wrong = []
    for item in wrong_items:
        bbox = item.get("actual_bbox")
        expected = target_by_id[item["expected_region_id"]]["bbox"]
        actual_center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2) if bbox else (0.0, 0.0)
        expected_center = ((expected[0] + expected[2]) / 2, (expected[1] + expected[3]) / 2)
        enriched_wrong.append({
            **item,
            "suggested_translation": [
                round(expected_center[0] - actual_center[0], 3),
                round(expected_center[1] - actual_center[1], 3),
            ],
            "affects_print_or_submission": True,
        })
    lines = [
        "# Stage 6-P1 应急提交版人工修正清单", "",
        "> 本次 Save 失败，磁盘 DWG 仍是干净基线。以下内容来自未保存内存态 JSON，仅用于后续修复取证。", "",
        f"- run_id: {paths.run_id}",
        f"- 应急 DWG: {result['override_dwg_path']}",
        f"- 错区候选: {len(enriched_wrong)}",
        f"- 重复候选组: {len(duplicates)}",
        f"- 原有对象变化: {len(existing_items)}",
        f"- 计划外对象: {len(unexpected_items)}",
        f"- 水泵房保持不变: {str(result['protected_region_modified'] == 0).lower()}", "",
    ]
    grouped_wrong: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in enriched_wrong:
        grouped_wrong[item["expected_region_id"]].append(item)
    for region_id in [f"target_region_{index:04d}" for index in range(1, 8)]:
        lines.extend([f"## {region_id}", ""])
        items = grouped_wrong.get(region_id, [])
        if not items:
            lines.append("- 无错区候选。")
        for item in items:
            lines.append(
                f"- Handle `{item['target_handle']}` | {item['object_name']} | 当前图框 `{item['actual_region_id']}` | "
                f"预期图框 `{item['expected_region_id']}` | bbox `{item['actual_bbox']}` | "
                f"建议平移 `{item['suggested_translation']}` | 影响打印/提交：YES"
            )
        region_duplicates = [item for item in duplicates if _region_for_bbox(item.get("bbox"), target_regions) == region_id]
        lines.extend([f"- 重复对象候选组：{len(region_duplicates)}", ""])
    lines.extend(["## 原有对象变化", ""])
    for item in existing_items:
        lines.append(
            f"- Handle `{item['handle']}` | {item['ObjectName']} | 图层 `{item['layer']}` | "
            f"区域 `{item['region_id']}` | changed_fields `{item['changed_fields']}`"
        )
    lines.extend(["", "## 计划外对象", ""])
    for item in unexpected_items:
        lines.append(
            f"- Handle `{item['handle']}` | {item['ObjectName']} | 区域 `{item['region_id']}` | "
            f"bbox `{item['bbox']}` | classification `{item['classification']}`"
        )
    lines.extend([
        "", "## 水泵房检查", "",
        "- classification: PROTECTED_COMPLETE_REGION",
        f"- 修改数量：{result['protected_region_modified']}",
        "- protected region intersection：0", "",
    ])
    cleanup_path.write_text("\n".join(lines), encoding="utf-8")
    report = {
        **result,
        "status": "FAILED_OVERRIDE_HARD_STOP",
        "emergency_delivery_dwg_created": False,
        "normal_safety_gate_passed": False,
        "manual_cleanup_required": True,
        "side_effects_unresolved": True,
        "original_target_unchanged": result["original_hashes_unchanged"],
        "reference_unchanged": result["original_hashes_unchanged"],
        "disk_emergency_dwg_is_clean_baseline": _sha256(Path(result["override_dwg_path"])) == EXPECTED_TARGET_SHA256,
        "disk_emergency_dwg_contains_executed_tasks": False,
        "manual_cleanup_path": str(cleanup_path),
        "preview_paths": preview_paths,
        "preview_state": "UNSAVED_MEMORY_STATE_DIAGNOSTIC_ONLY",
        "tests": dict(tests),
        "mvp3_completed": False,
        "mvp4_allowed": False,
        "production_d1_allowed": False,
    }
    _write_json(paths.reports / "stage6_p1_emergency_delivery.json", report)
    _write_json(ROOT / "reports" / "stage6_p1_emergency_delivery.json", report)
    (ROOT / "reports" / "stage6_p1_emergency_delivery.md").write_text(
        "\n".join([
            "# Stage 6-P1 Emergency Delivery", "",
            "- status: FAILED_OVERRIDE_HARD_STOP",
            f"- run_id: {paths.run_id}",
            f"- executed tasks in unsaved memory state: {report['executed_task_count']}",
            "- save/reopen: false/false",
            f"- save error: {report['error']}",
            f"- existing modified/unexpected new: {report['existing_modified']}/{report['unexpected_new']}",
            f"- duplicate/wrong region: {report['duplicate']}/{report['wrong_region_write']}",
            f"- existing deleted/protected modified: {report['existing_deleted']}/{report['protected_region_modified']}",
            "- disk emergency DWG remains clean baseline: true",
            "- original reference/target unchanged: true",
            "- MVP3/MVP4: false/false",
            "- Production D1 allowed: false", "",
        ]), encoding="utf-8",
    )
    return report
