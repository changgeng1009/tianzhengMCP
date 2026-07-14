from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "artifacts" / "stage6_p1"
CONFIG_PATH = ROOT / "config" / "mvp3_samples.yaml"
REPORT_JSON = ROOT / "reports" / "stage6_p1_multi_region_pilot.json"
REPORT_MD = ROOT / "reports" / "stage6_p1_multi_region_pilot.md"
AUTHORIZED_WRITE_MODE = "AUTHORIZED_TARGET_IN_PLACE"
FINAL_MANUAL_MAPPING_REVISION = "stage6_p1_user_final_mapping_20260712_r2"
FINAL_MANUAL_REGION_PAIRS = (
    ("reference_region_0001", "target_region_0007", "user_final_manual_confirmation"),
    ("reference_region_0002_upper", "target_region_0001", "user_final_manual_confirmation"),
    ("reference_region_0002_lower", "target_region_0002", "user_final_manual_confirmation"),
    ("reference_region_0003", "target_region_0004", "user_final_manual_confirmation"),
    ("reference_region_0004", "target_region_0005", "user_final_manual_confirmation"),
    ("reference_region_0005", "target_region_0003", "user_final_manual_confirmation"),
    ("reference_region_0006", "target_region_0006", "user_final_manual_confirmation"),
)
SUPERSEDED_MANUAL_REGION_PAIRS = (
    ("reference_region_0002_lower", "target_region_0006"),
    ("reference_region_0006", "target_region_0002"),
)


@dataclass(frozen=True)
class P1Paths:
    run_id: str
    root: Path
    backups: Path
    alignment_reports: Path
    region_diffs: Path
    frozen_execution_plans: Path
    execution_results: Path
    source_to_target_handle_maps: Path
    previews: Path
    completed: Path

    @classmethod
    def build(cls, run_id: str) -> "P1Paths":
        root = RUNS_ROOT / run_id
        return cls(
            run_id,
            root,
            root / "backups",
            root / "alignment_reports",
            root / "region_diffs",
            root / "frozen_execution_plans",
            root / "execution_results",
            root / "source_to_target_handle_maps",
            root / "previews",
            root / "completed",
        )

    def create(self) -> None:
        for value in self.__dict__.values():
            if isinstance(value, Path):
                value.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _payload_sha256(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_frozen_execution_plan(plan: Mapping[str, Any]) -> tuple[bool, str]:
    expected = str(plan.get("plan_sha256") or "")
    unhashed = dict(plan)
    unhashed.pop("plan_sha256", None)
    actual = _payload_sha256(unhashed)
    return bool(expected and expected == actual), actual


def _mapping_pairs(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    return [
        (str(item["reference_region_id"]), str(item["target_region_id"]))
        for item in payload.get("matches", [])
    ]


def _archive_superseded_mapping_outputs(paths: P1Paths) -> dict[str, Any] | None:
    """Archive only mapping-derived evidence when the active mapping is obsolete."""
    matching_path = paths.root / "region_matching.json"
    if not matching_path.exists():
        return None
    previous = _read_json(matching_path)
    previous_pairs = _mapping_pairs(previous)
    final_pairs = [(reference_id, target_id) for reference_id, target_id, _ in FINAL_MANUAL_REGION_PAIRS]
    if previous_pairs == final_pairs:
        return None

    archive_root = paths.root / "superseded" / FINAL_MANUAL_MAPPING_REVISION
    archive_root.mkdir(parents=True, exist_ok=True)
    candidates = [
        *paths.alignment_reports.glob("alignment_reference_region_*.json"),
        *paths.alignment_reports.glob("manual_alignment_*"),
        *paths.region_diffs.glob("diff_reference_region_*.json"),
        *paths.previews.glob("alignment_reference_region_*.png"),
        *paths.previews.glob("consistency_reference_region_*.png"),
        paths.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json",
        paths.root / "region_matching.json",
        paths.root / "manual_mapping_consistency.json",
        paths.root / "manual_mapping_consistency.md",
        paths.root / "prewrite_gate.json",
    ]
    archived = []
    for source in candidates:
        if not source.exists() or not source.is_file():
            continue
        relative = source.relative_to(paths.root)
        destination = archive_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        source.replace(destination)
        archived.append(str(relative))
    record = {
        "mapping_revision": FINAL_MANUAL_MAPPING_REVISION,
        "reason": "user_final_mapping_replaced_swapped_region_pairs",
        "previous_pairs": [list(item) for item in previous_pairs],
        "final_pairs": [list(item) for item in final_pairs],
        "explicitly_superseded_pairs": [list(item) for item in SUPERSEDED_MANUAL_REGION_PAIRS],
        "archived_files": archived,
        "dwg_opened": False,
        "target_write": False,
        "target_save": False,
    }
    _write_json(archive_root / "archive_manifest.json", record)
    return record


def _frozen_plan_gate(
    *, all_alignment_verified: bool, protected_intersection_count: int, hashes_unchanged: bool
) -> bool:
    return bool(all_alignment_verified and protected_intersection_count == 0 and hashes_unchanged)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _lock_files(path: Path) -> list[str]:
    return [str(candidate) for candidate in (path.with_suffix(".dwl"), path.with_suffix(".dwl2")) if candidate.exists()]


def _exclusive_readable(path: Path) -> tuple[bool, str | None]:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        handle = create_file(str(path), 0x80000000, 0, None, 3, 0x80, None)
        invalid = wintypes.HANDLE(-1).value
        if handle == invalid:
            code = ctypes.get_last_error()
            return False, f"CreateFileW exclusive read failed with Windows error {code}"
        kernel32.CloseHandle(handle)
        return True, None
    try:
        with path.open("rb"):
            pass
        return True, None
    except OSError as exc:
        return False, str(exc)


def file_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "size": stat.st_size,
        "modified_time_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def safety_flags() -> dict[str, bool]:
    return {
        "reference_opened": False,
        "reference_saved": False,
        "reference_modified": False,
        "target_opened": False,
        "target_saved": False,
        "target_modified": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "production_d1_allowed": False,
    }


def load_pilot_sample(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    samples = payload.get("samples", [])
    if not isinstance(samples, list) or len(samples) != 1 or not isinstance(samples[0], Mapping):
        raise ValueError("Stage 6-P1 requires exactly one pilot sample")
    return dict(samples[0])


def validate_pilot_authorization(sample: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if sample.get("sample_id") != "sample_multi_region_pilot":
        errors.append("unexpected_sample_id")
    if sample.get("write_mode") != AUTHORIZED_WRITE_MODE:
        errors.append("target_write_mode_not_authorized")
    if sample.get("target_in_place_write_allowed") is not True:
        errors.append("target_in_place_write_not_allowed")
    if sample.get("target_save_allowed") is not True:
        errors.append("target_save_not_allowed")
    if sample.get("reference_write_allowed") is not False or sample.get("reference_save_allowed") is not False:
        errors.append("reference_must_be_read_only")
    if sample.get("dimension2_required") is not False:
        errors.append("dimension2_must_be_allowed_difference")
    protected = sample.get("protected_regions", [])
    if not isinstance(protected, list) or not protected:
        errors.append("protected_regions_missing")
    reference = Path(str(sample.get("reference_path", "")))
    target = Path(str(sample.get("target_path", "")))
    if reference == target:
        errors.append("reference_target_same_path")
    if not reference.is_file():
        errors.append("reference_missing")
    if not target.is_file():
        errors.append("target_missing")
    return errors


def difference_policy() -> dict[str, Any]:
    return {
        "phase": "STAGE6-P1",
        "object_match_priority": [
            "ObjectName", "geometry", "SysType", "DN", "topology",
            "functional_role", "layer_semantics", "text", "color",
        ],
        "classifications": {
            "PROTECTED_COMPLETE_REGION": {"repair_allowed": False, "modification_allowed": False, "style_normalization_allowed": False},
            "EXISTING_WITH_STYLE_DIFFERENCE": {"repair_required": False, "modification_allowed": False},
            "DRAFTING_STYLE_DIFFERENCE": {"repair_required": False, "modification_allowed": False},
            "SAME_REGION_WITH_TITLE_VARIANT": {"title_repair_required": False},
            "PLOT_SCALE_TEXT_DIFFERENCE": {"repair_required": False, "geometry_scale_inference_allowed": False},
            "ALLOWED_DIFFERENCE": {"object_names": ["TDbDimension2"], "required": False},
        },
        "title_aliases": {
            "ROOF_PLUMBING_PLAN": ["屋面平面图", "屋顶平面图", "屋面给排水平面图", "屋顶给排水平面图"],
            "BASEMENT_PLUMBING_PLAN": ["地下一层平面图", "地下一层给排水平面图"],
            "TANK_ROOM_PLUMBING_PLAN": ["水箱间平面图", "水箱间给排水平面图"],
        },
        "new_object_style_sources": ["target_exact_semantic_mapping", "reference_object_style"],
        "color_is_missing_evidence": False,
        "dimension2_required": False,
        "production_d1_allowed": False,
    }


def run_prewrite_preflight(run_id: str | None = None, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    run_id = run_id or datetime.now().strftime("stage6_p1_%Y%m%d_%H%M%S")
    paths = P1Paths.build(run_id)
    paths.create()
    sample = load_pilot_sample(config_path)
    errors = validate_pilot_authorization(sample)
    reference = Path(str(sample.get("reference_path", "")))
    target = Path(str(sample.get("target_path", "")))
    locks = {
        "reference": _lock_files(reference) if reference.exists() else [],
        "target": _lock_files(target) if target.exists() else [],
    }
    exclusive = {}
    for role, path in (("reference", reference), ("target", target)):
        exclusive[role] = _exclusive_readable(path) if path.is_file() else (False, "missing")
        if locks[role] or not exclusive[role][0]:
            errors.append(f"{role}_locked")
    policy = difference_policy()
    _write_json(paths.root / "difference_policy.json", policy)
    _write_json(paths.root / "title_alias_normalization.json", policy["title_aliases"])
    _write_json(paths.root / "protected_regions.json", {
        "regions": sample.get("protected_regions", []),
        "classification": "PROTECTED_COMPLETE_REGION",
        "repair_allowed": False,
        "modification_allowed": False,
        "confirmed_by_geometry": False,
    })
    reference_record = file_record(reference) if reference.is_file() and not errors else None
    target_record = file_record(target) if target.is_file() and not errors else None
    backup_path = paths.backups / f"{target.stem}.prewrite.dwg"
    backup_record = None
    backup_hash_matches = False
    if not errors and target_record:
        shutil.copyfile(target, backup_path)
        backup_record = file_record(backup_path)
        backup_hash_matches = backup_record["sha256"] == target_record["sha256"]
        if not backup_hash_matches:
            errors.append("target_backup_hash_mismatch")
    status = "PASS_P1_PREWRITE_FROZEN" if not errors and backup_hash_matches else (
        "BLOCKED_TARGET_BACKUP_FAILED" if "target_backup_hash_mismatch" in errors else "BLOCKED_P1_PREFLIGHT"
    )
    manifest = {
        "phase": "STAGE6-P1-PREFLIGHT",
        "status": status,
        "run_id": run_id,
        "sample": sample,
        "reference": reference_record,
        "target": target_record,
        "prewrite_backup": backup_record,
        "prewrite_backup_hash_matches": backup_hash_matches,
        "lock_files": locks,
        "exclusive_readable": {key: value[0] for key, value in exclusive.items()},
        "errors": sorted(set(errors)),
        "write_gate_open": status == "PASS_P1_PREWRITE_FROZEN",
        "region_scan_completed": False,
        "region_matching_confirmed": False,
        "protected_region_confirmed": False,
        "target_write_started": False,
        "safety": safety_flags(),
    }
    _write_json(paths.root / "input_manifest.json", manifest)
    _write_json(paths.root / "source_integrity.json", {
        "reference_before": reference_record,
        "target_before": target_record,
        "prewrite_backup": backup_record,
        "reference_hash_unchanged": None,
        "target_rollback_available": backup_hash_matches,
        "safety": safety_flags(),
    })
    _write_json(paths.root / "stage6_p1_manifest.json", manifest)
    return manifest


def write_preflight_report(manifest: Mapping[str, Any]) -> None:
    report = dict(manifest)
    report["pilot_status"] = "PREFLIGHT_ONLY"
    report["pilot_completed"] = False
    report["stage6_final_status"] = "IN_PROGRESS" if manifest.get("status") == "PASS_P1_PREWRITE_FROZEN" else manifest.get("status")
    report["mvp3_completed"] = False
    report["mvp4_allowed"] = False
    report["production_d1_allowed"] = False
    _write_json(REPORT_JSON, report)
    reference = manifest.get("reference") or {}
    target = manifest.get("target") or {}
    backup = manifest.get("prewrite_backup") or {}
    REPORT_MD.write_text(
        "# Stage 6-P1 多区域核心工程复刻 Pilot\n\n"
        f"- status: {manifest.get('status')}\n"
        f"- run_id: {manifest.get('run_id')}\n"
        f"- reference SHA256: {reference.get('sha256')}\n"
        f"- target SHA256: {target.get('sha256')}\n"
        f"- prewrite backup: {backup.get('path')}\n"
        f"- backup hash matches: {str(manifest.get('prewrite_backup_hash_matches', False)).lower()}\n"
        "- region scan completed: false\n"
        "- target write started: false\n"
        "- reference opened/saved/modified: false/false/false\n"
        "- target opened/saved/modified: false/false/false\n"
        "- SendCommand/LISP/NETLOAD/Tianzheng command: false\n"
        "- MVP3 completed: false\n"
        "- MVP4 allowed: false\n"
        "- Production D1 allowed: false\n",
        encoding="utf-8",
    )


def run_readonly_region_scan(run_id: str) -> dict[str, Any]:
    from mcp.acceptance.stage3_1_runtime import (
        attach_existing_autocad,
        detach_autocad,
        enumerate_live_documents,
        scan_working_copy,
    )

    paths = P1Paths.build(run_id)
    manifest_path = paths.root / "input_manifest.json"
    manifest = _read_json(manifest_path)
    if manifest.get("status") != "PASS_P1_PREWRITE_FROZEN":
        raise RuntimeError("Stage 6-P1 prewrite preflight is not passed")
    reference = Path(manifest["reference"]["path"])
    target = Path(manifest["target"]["path"])
    frozen_hashes = {
        "reference": manifest["reference"]["sha256"],
        "target": manifest["target"]["sha256"],
    }
    before_hashes = {"reference": _sha256(reference), "target": _sha256(target)}
    if before_hashes != frozen_hashes:
        raise RuntimeError("Stage 6-P1 input hash changed after preflight")
    if _lock_files(reference) or _lock_files(target):
        raise RuntimeError("Stage 6-P1 input became locked before read-only scan")

    acad = None
    reference_scan = None
    target_scan = None
    live_documents: dict[str, Any] = {}
    status = "BLOCKED_P1_READONLY_SCAN"
    error = None
    try:
        acad = attach_existing_autocad()
        live_documents = enumerate_live_documents(acad, (reference, target))
        normalized_inputs = {str(reference.resolve()).casefold(), str(target.resolve()).casefold()}
        already_open = [
            item for item in live_documents.get("documents", [])
            if item.get("full_name") and str(Path(item["full_name"]).resolve()).casefold() in normalized_inputs
        ]
        if already_open:
            raise RuntimeError("reference or target is already open in AutoCAD")
        reference_scan = scan_working_copy(acad, reference, "reference", ())
        if reference_scan.get("document", {}).get("read_only") is not True:
            raise RuntimeError("reference did not open read-only")
        target_scan = scan_working_copy(acad, target, "target", ())
        if target_scan.get("document", {}).get("read_only") is not True:
            raise RuntimeError("target did not open read-only during region scan")
        if not reference_scan.get("copy_hash_unchanged") or not target_scan.get("copy_hash_unchanged"):
            raise RuntimeError("input hash changed during read-only scan")
        status = "PASS_P1_READONLY_SCAN"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if acad is not None:
            detach_autocad()

    after_hashes = {"reference": _sha256(reference), "target": _sha256(target)}
    hashes_unchanged = before_hashes == after_hashes == frozen_hashes
    if not hashes_unchanged:
        status = "FAILED_P1_INPUT_INTEGRITY"
    if reference_scan is not None:
        _write_json(paths.root / "reference_scan.json", reference_scan)
    if target_scan is not None:
        _write_json(paths.root / "target_scan.json", target_scan)
    result = {
        "phase": "STAGE6-P1-READONLY-SCAN",
        "status": status,
        "run_id": run_id,
        "live_documents_before_scan": live_documents,
        "reference_entity_count": (reference_scan or {}).get("entity_count"),
        "target_entity_count": (target_scan or {}).get("entity_count"),
        "reference_tdb_count": (reference_scan or {}).get("tdb_object_count"),
        "target_tdb_count": (target_scan or {}).get("tdb_object_count"),
        "frozen_hashes": frozen_hashes,
        "hashes_before_scan": before_hashes,
        "hashes_after_scan": after_hashes,
        "hashes_unchanged": hashes_unchanged,
        "error": error,
        "region_scan_completed": status == "PASS_P1_READONLY_SCAN",
        "target_write_started": False,
        "reference_opened_read_only": reference_scan is not None,
        "target_opened_read_only": target_scan is not None,
        "reference_saved": False,
        "target_saved": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "production_d1_allowed": False,
    }
    _write_json(paths.root / "readonly_scan_result.json", result)
    return result


def _bbox2d(entity: Mapping[str, Any]) -> list[float] | None:
    bbox = entity.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 2:
        return None
    try:
        return [float(bbox[0][0]), float(bbox[0][1]), float(bbox[1][0]), float(bbox[1][1])]
    except (TypeError, ValueError, IndexError):
        return None


def _center(entity: Mapping[str, Any]) -> tuple[float, float] | None:
    bbox = _bbox2d(entity)
    return None if bbox is None else ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _contains(bbox: list[float], point: tuple[float, float], padding: float = 0.0) -> bool:
    return bbox[0] - padding <= point[0] <= bbox[2] + padding and bbox[1] - padding <= point[1] <= bbox[3] + padding


def _normalize_title(text: str) -> str | None:
    aliases = difference_policy()["title_aliases"]
    compact = "".join(text.split())
    for normalized, variants in aliases.items():
        if any("".join(variant.split()) in compact for variant in variants):
            return normalized
    if "泵房" in compact and "大样" in compact:
        return "PUMP_ROOM_DETAIL"
    if "喷淋" in compact and ("系统" in compact or "原理" in compact):
        return "SPRINKLER_SYSTEM_DIAGRAM"
    if "消火栓" in compact and ("系统" in compact or "原理" in compact):
        return "HYDRANT_SYSTEM_DIAGRAM"
    if "给水" in compact and ("系统" in compact or "原理" in compact):
        return "WATER_SUPPLY_SYSTEM_DIAGRAM"
    if "排水" in compact and ("系统" in compact or "原理" in compact):
        return "DRAINAGE_SYSTEM_DIAGRAM"
    if "平面图" in compact:
        return "PLUMBING_PLAN"
    return None


def _frame_candidates(scan: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entity in scan.get("entities", []):
        bbox = _bbox2d(entity)
        if bbox is None:
            continue
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        object_name = str(entity.get("object_name", ""))
        layer = str(entity.get("layer", ""))
        is_large_block = object_name == "AcDbBlockReference" and min(width, height) >= 70_000
        is_frame_polyline = object_name in {"AcDbPolyline", "AcDb2dPolyline"} and (
            "图框" in layer or "TITLE" in layer.upper()
        ) and min(width, height) >= 70_000
        if is_large_block or is_frame_polyline:
            candidates.append({
                "evidence_handle": entity.get("handle"),
                "evidence_object_name": object_name,
                "evidence_layer": layer,
                "bbox": bbox,
                "width": width,
                "height": height,
                "frame_evidence": "large_block_reference" if is_large_block else "explicit_frame_polyline",
            })
    # Nested title-frame outlines represent one region. Keep the larger envelope.
    selected: list[dict[str, Any]] = []
    for item in sorted(candidates, key=lambda value: value["width"] * value["height"], reverse=True):
        bbox = item["bbox"]
        center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        duplicate = any(
            _contains(existing["bbox"], center)
            and abs(item["width"] - existing["width"]) / existing["width"] < 0.08
            and abs(item["height"] - existing["height"]) / existing["height"] < 0.08
            for existing in selected
        )
        if not duplicate:
            selected.append(item)
    return sorted(selected, key=lambda value: (value["bbox"][1], value["bbox"][0]))


def _region_record(role: str, index: int, frame: Mapping[str, Any], entities: list[Mapping[str, Any]]) -> dict[str, Any]:
    bbox = list(frame["bbox"])
    members = [entity for entity in entities if (point := _center(entity)) is not None and _contains(bbox, point, 1.0)]
    title_items = []
    for entity in entities:
        text = str((entity.get("attributes") or {}).get("text") or "").strip()
        point = _center(entity)
        normalized = _normalize_title(text) if text else None
        if normalized and point is not None and _contains(bbox, point, 2_000.0):
            title_items.append({"text": text, "normalized_title": normalized, "handle": entity.get("handle"), "bbox": _bbox2d(entity)})
    type_counts = Counter(str(entity.get("object_name")) for entity in members)
    tdb_count = sum(count for name, count in type_counts.items() if name.startswith("TDb"))
    normalized_titles = sorted({item["normalized_title"] for item in title_items})
    return {
        "region_id": f"{role}_region_{index:04d}",
        "source_file_role": role,
        "bbox": bbox,
        "title_items": title_items,
        "normalized_titles": normalized_titles,
        "frame_width": frame["width"],
        "frame_height": frame["height"],
        "frame_evidence": frame["frame_evidence"],
        "frame_evidence_handle": frame["evidence_handle"],
        "ordinary_cad_count": len(members) - tdb_count,
        "tdb_count": tdb_count,
        "entity_count": len(members),
        "object_type_counts": dict(sorted(type_counts.items())),
        "content_density": len(members) / max(frame["width"] * frame["height"], 1.0),
        "completion_status": "UNKNOWN_PENDING_MATCHING",
        "matching_region_id": None,
        "matching_confidence": 0.0,
        "repair_allowed": False,
        "protected": False,
        "reason": "write gate remains closed until unique matching and alignment pass",
    }


def _protected_pump_region(target_scan: Mapping[str, Any]) -> dict[str, Any] | None:
    entities = list(target_scan.get("entities", []))
    titles = [
        entity for entity in entities
        if _normalize_title(str((entity.get("attributes") or {}).get("text") or "")) == "PUMP_ROOM_DETAIL"
    ]
    if len(titles) != 1:
        return None
    title = titles[0]
    title_bbox = _bbox2d(title)
    if title_bbox is None:
        return None
    search = [title_bbox[0] - 35_000, title_bbox[1] - 75_000, title_bbox[2] + 35_000, title_bbox[3] + 20_000]
    nearby = [entity for entity in entities if (point := _center(entity)) is not None and _contains(search, point)]
    evidence_bboxes = [bbox for entity in nearby if (bbox := _bbox2d(entity)) is not None]
    if not evidence_bboxes:
        return None
    envelope = [
        min(item[0] for item in evidence_bboxes), min(item[1] for item in evidence_bboxes),
        max(item[2] for item in evidence_bboxes), max(item[3] for item in evidence_bboxes),
    ]
    # Clamp to the conservative title neighborhood so remote display extents cannot expand protection arbitrarily.
    envelope = [max(envelope[0], search[0]), max(envelope[1], search[1]), min(envelope[2], search[2]), min(envelope[3], search[3])]
    tdb_count = sum(str(entity.get("object_name", "")).startswith("TDb") for entity in nearby)
    return {
        "region_id": "target_protected_pump_room",
        "source_file_role": "target",
        "bbox": envelope,
        "title_items": [{"text": (title.get("attributes") or {}).get("text"), "handle": title.get("handle"), "bbox": title_bbox}],
        "normalized_titles": ["PUMP_ROOM_DETAIL"],
        "entity_count": len(nearby),
        "tdb_count": tdb_count,
        "completion_status": "PROTECTED_COMPLETE_REGION",
        "matching_region_id": None,
        "matching_confidence": 1.0,
        "repair_allowed": False,
        "protected": True,
        "reason": "user-confirmed completed pump room; conservative title-neighborhood geometry envelope",
        "protection_bbox_method": "conservative_title_neighborhood_envelope",
        "title_evidence_unique": True,
    }


def build_region_manifest(run_id: str) -> dict[str, Any]:
    paths = P1Paths.build(run_id)
    scan_result = _read_json(paths.root / "readonly_scan_result.json")
    if scan_result.get("status") != "PASS_P1_READONLY_SCAN":
        raise RuntimeError("read-only scan is not passed")
    reference_scan = _read_json(paths.root / "reference_scan.json")
    target_scan = _read_json(paths.root / "target_scan.json")
    reference_regions = [
        _region_record("reference", index, frame, list(reference_scan["entities"]))
        for index, frame in enumerate(_frame_candidates(reference_scan), 1)
    ]
    target_regions = [
        _region_record("target", index, frame, list(target_scan["entities"]))
        for index, frame in enumerate(_frame_candidates(target_scan), 1)
    ]
    protected = _protected_pump_region(target_scan)
    all_target_regions = [*target_regions, *([protected] if protected else [])]
    manifest = {
        "phase": "STAGE6-P1-REGION-MANIFEST",
        "status": "PASS_P1_REGION_IDENTIFIED" if reference_regions and target_regions and protected else "BLOCKED_P1_REGION_IDENTIFICATION",
        "run_id": run_id,
        "reference_region_count": len(reference_regions),
        "target_frame_region_count": len(target_regions),
        "protected_region_count": int(protected is not None),
        "region_count": len(reference_regions) + len(all_target_regions),
        "reference_regions": reference_regions,
        "target_regions": all_target_regions,
        "protected_pump_room_confirmed": protected is not None,
        "region_matching_confirmed": False,
        "target_write_started": False,
        "production_d1_allowed": False,
    }
    _write_json(paths.root / "region_manifest.json", manifest)
    lines = ["# Stage 6-P1 区域清单", "", f"- status: {manifest['status']}", f"- reference regions: {len(reference_regions)}", f"- target frame regions: {len(target_regions)}", f"- protected pump room: {str(protected is not None).lower()}", ""]
    for region in [*reference_regions, *all_target_regions]:
        lines.append(f"- {region['region_id']}: bbox={region['bbox']}, titles={region.get('normalized_titles', [])}, entities={region.get('entity_count')}, protected={str(region.get('protected', False)).lower()}")
    (paths.root / "region_manifest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def render_region_overview(run_id: str) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    paths = P1Paths.build(run_id)
    manifest = _read_json(paths.root / "region_manifest.json")
    figure, axes = plt.subplots(1, 2, figsize=(18, 8), constrained_layout=True)
    for axis, role, regions in (
        (axes[0], "reference", manifest["reference_regions"]),
        (axes[1], "target", manifest["target_regions"]),
    ):
        for region in regions:
            bbox = region["bbox"]
            color = "#d62728" if region.get("protected") else "#1f77b4"
            axis.add_patch(Rectangle((bbox[0], bbox[1]), bbox[2] - bbox[0], bbox[3] - bbox[1], fill=False, linewidth=2, edgecolor=color))
            axis.text(bbox[0], bbox[3], region["region_id"], fontsize=8, color=color, va="bottom")
        axis.autoscale()
        axis.set_aspect("equal", adjustable="box")
        axis.set_title(role)
        axis.grid(True, linewidth=0.3, alpha=0.4)
    output = paths.previews / "region_overview.png"
    figure.savefig(output, dpi=160)
    plt.close(figure)
    return output


def _draw_entity(axis: Any, entity: Mapping[str, Any], color: str, alpha: float) -> None:
    geometry = entity.get("geometry") or {}
    start, end = geometry.get("start_point"), geometry.get("end_point")
    if isinstance(start, list) and isinstance(end, list) and len(start) >= 2 and len(end) >= 2:
        axis.plot([start[0], end[0]], [start[1], end[1]], color=color, linewidth=0.35, alpha=alpha)
        return
    vertices = geometry.get("vertices")
    if isinstance(vertices, list) and len(vertices) >= 2:
        points = [point for point in vertices if isinstance(point, list) and len(point) >= 2]
        if len(points) >= 2:
            axis.plot([point[0] for point in points], [point[1] for point in points], color=color, linewidth=0.35, alpha=alpha)
            return
    bbox = _bbox2d(entity)
    if bbox is not None:
        axis.plot((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2, marker=".", markersize=0.5, color=color, alpha=alpha)


def render_region_contact_sheet(run_id: str) -> Path:
    import matplotlib.pyplot as plt

    paths = P1Paths.build(run_id)
    manifest = _read_json(paths.root / "region_manifest.json")
    scans = {
        "reference": _read_json(paths.root / "reference_scan.json"),
        "target": _read_json(paths.root / "target_scan.json"),
    }
    regions = [*manifest["reference_regions"], *[item for item in manifest["target_regions"] if not item.get("protected")]]
    columns = 4
    rows = math.ceil(len(regions) / columns)
    figure, axes = plt.subplots(rows, columns, figsize=(20, 5 * rows), constrained_layout=True)
    flat_axes = list(axes.flat) if hasattr(axes, "flat") else [axes]
    for axis, region in zip(flat_axes, regions):
        bbox = region["bbox"]
        role = region["source_file_role"]
        members = [entity for entity in scans[role]["entities"] if (point := _center(entity)) is not None and _contains(bbox, point)]
        for entity in members:
            is_tdb = str(entity.get("object_name", "")).startswith("TDb")
            _draw_entity(axis, entity, "#d62728" if is_tdb else "#222222", 0.55 if is_tdb else 0.35)
        axis.set_xlim(bbox[0], bbox[2])
        axis.set_ylim(bbox[1], bbox[3])
        axis.set_aspect("equal", adjustable="box")
        axis.set_title(f"{region['region_id']} | {region.get('normalized_titles', [])}\nordinary={region.get('ordinary_cad_count')} TDb={region.get('tdb_count')}", fontsize=8)
        axis.set_xticks([])
        axis.set_yticks([])
    for axis in flat_axes[len(regions):]:
        axis.axis("off")
    output = paths.previews / "region_contact_sheet.png"
    figure.savefig(output, dpi=180)
    plt.close(figure)
    return output


_MATCH_TYPES = (
    "TDbWall", "TDbColumn", "TDbOpening", "TDbAxisLabelSet",
    "AcDbBlockReference", "AcDbLine", "AcDbPolyline", "AcDbCircle", "AcDbHatch",
)

ORDINARY_EXECUTION_TYPES = {
    "AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline", "AcDbCircle", "AcDbArc",
}
CORE_TDB_EXECUTION_TYPES = {
    "TDbPipe", "TDbPipeFitting", "TDbPipeValve", "TDbPump", "TDbEquipment",
    "TDbWaterTank", "TDbVPipeDim", "TDbSymbMultiLeader",
}


def _normalized_points(scan: Mapping[str, Any], region: Mapping[str, Any], object_name: str) -> list[list[float]]:
    bbox = region["bbox"]
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    points = []
    for entity in scan.get("entities", []):
        if entity.get("object_name") != object_name:
            continue
        center = _center(entity)
        if center is not None and _contains(bbox, center):
            points.append([(center[0] - bbox[0]) / width, (center[1] - bbox[1]) / height])
    return points


def _geometry_coverage(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
) -> tuple[float, dict[str, Any]]:
    import numpy as np
    from scipy.spatial import cKDTree

    details = {}
    weighted_sum = 0.0
    total_weight = 0
    for object_name in _MATCH_TYPES:
        reference_points = _normalized_points(reference_scan, reference_region, object_name)
        target_points = _normalized_points(target_scan, target_region, object_name)
        if len(reference_points) < 3 or len(target_points) < 3:
            continue
        distances, _ = cKDTree(np.asarray(reference_points)).query(np.asarray(target_points), k=1)
        coverage = float(np.mean(distances < 0.012))
        weight = min(len(reference_points), len(target_points))
        weighted_sum += coverage * weight
        total_weight += weight
        details[object_name] = {
            "reference_count": len(reference_points),
            "target_count": len(target_points),
            "target_to_reference_coverage": round(coverage, 6),
        }
    return (weighted_sum / total_weight if total_weight else 0.0), details


def _count_similarity(reference_region: Mapping[str, Any], target_region: Mapping[str, Any]) -> float:
    left = reference_region.get("object_type_counts") or {}
    right = target_region.get("object_type_counts") or {}
    numerator = sum(float(left.get(name, 0)) * float(right.get(name, 0)) for name in _MATCH_TYPES)
    left_norm = math.sqrt(sum(float(left.get(name, 0)) ** 2 for name in _MATCH_TYPES))
    right_norm = math.sqrt(sum(float(right.get(name, 0)) ** 2 for name in _MATCH_TYPES))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _title_compatibility(reference_region: Mapping[str, Any], target_region: Mapping[str, Any]) -> tuple[float | None, bool]:
    left, right = set(reference_region.get("normalized_titles", [])), set(target_region.get("normalized_titles", []))
    if not left or not right:
        return None, True
    overlap = len(left & right) / len(left | right)
    compatible = overlap > 0
    if compatible and left & right == {"PLUMBING_PLAN"}:
        floor_pattern = re.compile(r"([一二三四五六七八九十百0-9~～\-]+层)")
        left_floors = {
            match.group(1) for item in reference_region.get("title_items", [])
            for match in floor_pattern.finditer(str(item.get("text", "")))
        }
        right_floors = {
            match.group(1) for item in target_region.get("title_items", [])
            for match in floor_pattern.finditer(str(item.get("text", "")))
        }
        if left_floors and right_floors and left_floors.isdisjoint(right_floors):
            compatible = False
    return overlap, compatible


def _region_class(region: Mapping[str, Any]) -> str:
    titles = set(region.get("normalized_titles", []))
    if any("SYSTEM_DIAGRAM" in title for title in titles):
        return "SYSTEM_DIAGRAM"
    if any("PLAN" in title for title in titles):
        return "PLAN"
    counts = region.get("object_type_counts") or {}
    if sum(int(counts.get(name, 0)) for name in ("TDbWall", "TDbColumn", "TDbOpening")) >= 30:
        return "PLAN"
    return "UNKNOWN"


def _pair_score(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
) -> dict[str, Any]:
    geometry, geometry_details = _geometry_coverage(reference_scan, target_scan, reference_region, target_region)
    counts = _count_similarity(reference_region, target_region)
    left_aspect = reference_region["frame_width"] / reference_region["frame_height"]
    right_aspect = target_region["frame_width"] / target_region["frame_height"]
    aspect = min(left_aspect, right_aspect) / max(left_aspect, right_aspect)
    title, title_compatible = _title_compatibility(reference_region, target_region)
    reference_class, target_class = _region_class(reference_region), _region_class(target_region)
    class_compatible = reference_class == target_class or "UNKNOWN" in {reference_class, target_class}
    title_weight = 0.15 if title is not None else 0.0
    base_weight = 1.0 - title_weight
    score = base_weight * (0.58 * geometry + 0.32 * counts + 0.10 * aspect) + title_weight * float(title or 0.0)
    if not title_compatible or not class_compatible:
        score *= 0.15
    return {
        "reference_region_id": reference_region["region_id"],
        "target_region_id": target_region["region_id"],
        "score": round(score, 6),
        "geometry_coverage": round(geometry, 6),
        "count_similarity": round(counts, 6),
        "aspect_similarity": round(aspect, 6),
        "title_similarity": None if title is None else round(title, 6),
        "title_compatible": title_compatible,
        "reference_region_class": reference_class,
        "target_region_class": target_class,
        "region_class_compatible": class_compatible,
        "geometry_details": geometry_details,
    }


def _render_normalized_overlay(
    output: Path,
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
) -> None:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(8, 8), constrained_layout=True)
    for scan, region, color, label in (
        (reference_scan, reference_region, "#1f77b4", "reference"),
        (target_scan, target_region, "#d62728", "target"),
    ):
        first = True
        for object_name in _MATCH_TYPES:
            points = _normalized_points(scan, region, object_name)
            if points:
                axis.scatter([point[0] for point in points], [point[1] for point in points], s=3, alpha=0.35, color=color, label=label if first else None)
                first = False
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.set_aspect("equal", adjustable="box")
    axis.grid(True, linewidth=0.3, alpha=0.4)
    axis.legend()
    axis.set_title(f"{reference_region['region_id']} -> {target_region['region_id']}")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def _members(scan: Mapping[str, Any], region: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    bbox = region["bbox"]
    return [
        entity for entity in scan.get("entities", [])
        if (point := _center(entity)) is not None and _contains(bbox, point)
    ]


def _logical_reference_regions(
    manifest: Mapping[str, Any], reference_scan: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Split the user-confirmed compound frame without inventing CAD geometry."""
    existing_ids = {item["region_id"] for item in manifest["reference_regions"]}
    split_ids = {"reference_region_0002_upper", "reference_region_0002_lower"}
    if split_ids <= existing_ids:
        evidence = dict(manifest.get("logical_split_evidence") or {})
        if not evidence:
            upper = next(item for item in manifest["reference_regions"] if item["region_id"].endswith("_upper"))
            evidence = {
                "parent_region_id": "reference_region_0002",
                "method": "reused_existing_logical_split",
                "split_axis": "y",
                "split_coordinate": upper["bbox"][1],
                "gap": upper.get("logical_split_gap"),
                "evidence_source": "reference_readonly_scan",
            }
        return [dict(item) for item in manifest["reference_regions"]], evidence
    original = next(
        item for item in manifest["reference_regions"]
        if item["region_id"] == "reference_region_0002"
    )
    bbox = list(original["bbox"])
    centers = sorted(
        point[1] for entity in _members(reference_scan, original)
        if (point := _center(entity)) is not None
        and str(entity.get("object_name")) not in {"AcDbBlockReference"}
    )
    lower_bound = bbox[1] + 0.35 * (bbox[3] - bbox[1])
    upper_bound = bbox[1] + 0.65 * (bbox[3] - bbox[1])
    gaps = [
        (right - left, (left + right) / 2.0)
        for left, right in zip(centers, centers[1:])
        if lower_bound <= (left + right) / 2.0 <= upper_bound
    ]
    if not gaps:
        raise RuntimeError("reference_region_0002 has no evidence-backed vertical split")
    gap, split_y = max(gaps)
    if gap < 1_000:
        raise RuntimeError("reference_region_0002 vertical split is not separated by a stable gap")

    logical: list[dict[str, Any]] = []
    for suffix, sub_bbox in (
        ("lower", [bbox[0], bbox[1], bbox[2], split_y]),
        ("upper", [bbox[0], split_y, bbox[2], bbox[3]]),
    ):
        frame = {
            "bbox": sub_bbox,
            "width": sub_bbox[2] - sub_bbox[0],
            "height": sub_bbox[3] - sub_bbox[1],
            "frame_evidence": "user_confirmed_compound_frame_split_with_entity_gap",
            "evidence_handle": original.get("frame_evidence_handle"),
        }
        record = _region_record("reference", 2, frame, list(reference_scan["entities"]))
        record["region_id"] = f"reference_region_0002_{suffix}"
        record["parent_region_id"] = "reference_region_0002"
        record["logical_split_axis"] = "y"
        record["logical_split_coordinate"] = split_y
        record["logical_split_gap"] = gap
        logical.append(record)

    result = []
    for item in manifest["reference_regions"]:
        if item["region_id"] == "reference_region_0002":
            result.extend([logical[1], logical[0]])  # upper then lower, as confirmed by the user
        else:
            result.append(dict(item))
    return result, {
        "parent_region_id": "reference_region_0002",
        "method": "largest_entity_center_gap_within_middle_30_percent",
        "split_axis": "y",
        "split_coordinate": split_y,
        "gap": gap,
        "evidence_source": "reference_readonly_scan",
    }


def _bbox_similarity_transform(reference_bbox: list[float], target_bbox: list[float]) -> dict[str, Any]:
    ref_width, ref_height = reference_bbox[2] - reference_bbox[0], reference_bbox[3] - reference_bbox[1]
    target_width, target_height = target_bbox[2] - target_bbox[0], target_bbox[3] - target_bbox[1]
    scale_x, scale_y = target_width / ref_width, target_height / ref_height
    scale = math.sqrt(scale_x * scale_y)
    ref_center = [(reference_bbox[0] + reference_bbox[2]) / 2, (reference_bbox[1] + reference_bbox[3]) / 2]
    target_center = [(target_bbox[0] + target_bbox[2]) / 2, (target_bbox[1] + target_bbox[3]) / 2]
    translation = [target_center[0] - scale * ref_center[0], target_center[1] - scale * ref_center[1]]
    aspect_residual = abs(math.log(scale_x / scale_y))
    return {
        "method": "independent_region_bbox_similarity_initialization",
        "translation": translation,
        "rotation_degrees": 0.0,
        "uniform_scale": scale,
        "scale_x_evidence": scale_x,
        "scale_y_evidence": scale_y,
        "aspect_log_residual": aspect_residual,
        "reference_bbox": reference_bbox,
        "target_bbox": target_bbox,
        "coordinate_space": "modelspace_cad",
    }


_NATIVE_ALIGNMENT_TYPES = {
    "TDbWall", "TDbColumn", "TDbOpening", "TDbAxisLabelSet",
    "AcDbBlockReference", "AcDbLine", "AcDbPolyline", "AcDbCircle",
    "TDbPipe", "TDbPipeFitting", "TDbPipeValve", "TDbEquipment", "TDbWaterTank",
    "TDbSymbElevation",
}


def _native_alignment_feature(entity: Mapping[str, Any]) -> dict[str, Any] | None:
    if str(entity.get("object_name")) not in _NATIVE_ALIGNMENT_TYPES:
        return None
    if "TWT_TITLE" in str(entity.get("layer", "")).upper():
        return None
    bbox = entity.get("bbox")
    if not (
        isinstance(bbox, list) and len(bbox) == 2
        and all(isinstance(point, list) and len(point) >= 2 for point in bbox)
    ):
        return None
    geometry = entity.get("geometry") or {}
    attributes = entity.get("attributes") or {}
    angle = None
    if (
        entity.get("object_name") == "AcDbLine"
        and isinstance(geometry.get("start_point"), list)
        and isinstance(geometry.get("end_point"), list)
    ):
        start, end = geometry["start_point"], geometry["end_point"]
        angle = math.atan2(float(end[1]) - float(start[1]), float(end[0]) - float(start[0])) % math.pi
    return {
        "handle": str(entity.get("handle")),
        "anchor_type": str(entity.get("object_name")),
        "point": [
            (float(bbox[0][0]) + float(bbox[1][0])) / 2,
            (float(bbox[0][1]) + float(bbox[1][1])) / 2,
        ],
        "dimensions": [
            abs(float(bbox[1][0]) - float(bbox[0][0])),
            abs(float(bbox[1][1]) - float(bbox[0][1])),
        ],
        "length": float(geometry.get("length") or 0.0),
        "area": float(geometry.get("area") or 0.0),
        "angle": angle,
        "dn_diameter": attributes.get("dn_diameter"),
        "sys_type": attributes.get("sys_type"),
        "height": attributes.get("height"),
    }


def _native_alignment_features(
    scan: Mapping[str, Any], region: Mapping[str, Any]
) -> list[dict[str, Any]]:
    result = []
    for entity in scan.get("entities", []):
        feature = _native_alignment_feature(entity)
        if feature is not None and _contains(region["bbox"], feature["point"]):
            result.append(feature)
    return result


def _native_value_close(left: float, right: float) -> bool:
    tolerance = max(0.1, 0.00001 * max(abs(left), abs(right), 1.0))
    return abs(left - right) <= tolerance


def _native_signature_matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if left["anchor_type"] != right["anchor_type"]:
        return False
    if not all(
        _native_value_close(float(a), float(b))
        for a, b in zip(left["dimensions"], right["dimensions"])
    ):
        return False
    if left["length"] and right["length"] and not _native_value_close(left["length"], right["length"]):
        return False
    if left["area"] and right["area"] and not _native_value_close(left["area"], right["area"]):
        return False
    return True


def _ratio_score(left: float, right: float) -> float:
    left, right = abs(float(left)), abs(float(right))
    return min(left, right) / max(left, right, 1e-9) if left or right else 1.0


def _relaxed_feature_similarity(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    if left["anchor_type"] != right["anchor_type"]:
        return 0.0
    name = left["anchor_type"]
    if name == "AcDbLine":
        angle_delta = abs(float(left.get("angle") or 0.0) - float(right.get("angle") or 0.0))
        angle_delta = min(angle_delta, abs(math.pi - angle_delta))
        orientation = 1.0 if angle_delta <= math.radians(1) else 0.0
        return 0.55 * _ratio_score(left["length"], right["length"]) + 0.45 * orientation
    if name == "AcDbPolyline":
        left_width, left_height = left["dimensions"]
        right_width, right_height = right["dimensions"]
        direct = (_ratio_score(left_width, right_width) + _ratio_score(left_height, right_height)) / 2
        swapped = (_ratio_score(left_width, right_height) + _ratio_score(left_height, right_width)) / 2
        return max(direct, swapped)
    if name == "AcDbCircle":
        return _ratio_score(max(left["dimensions"]), max(right["dimensions"]))
    if name in {"TDbWall", "TDbColumn", "TDbOpening"}:
        dimensions = sum(
            _ratio_score(a, b) for a, b in zip(left["dimensions"], right["dimensions"])
        ) / 2
        height = (
            _ratio_score(float(left["height"]), float(right["height"]))
            if left.get("height") is not None and right.get("height") is not None else 1.0
        )
        return 0.70 * dimensions + 0.30 * height
    if name == "TDbPipe":
        dn = 1.0 if left.get("dn_diameter") == right.get("dn_diameter") else 0.0
        system = 1.0 if left.get("sys_type") == right.get("sys_type") else 0.30
        return 0.50 * _ratio_score(left["length"], right["length"]) + 0.30 * dn + 0.20 * system
    if name == "AcDbBlockReference":
        return 0.0
    return 1.0


def _content_spatial_coverage(anchors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not anchors:
        return {
            "occupied_spatial_cells": 0, "total_spatial_cells": 4,
            "spatial_coverage_ratio": 0.0, "maximum_anchor_cluster_ratio": 1.0,
            "cell_counts": {}, "passed": False,
        }
    points = [list(map(float, item["reference_point"][:2])) for item in anchors]
    xmin, ymin = min(point[0] for point in points), min(point[1] for point in points)
    xmax, ymax = max(point[0] for point in points), max(point[1] for point in points)
    if xmax - xmin <= 1e-6 or ymax - ymin <= 1e-6:
        return {
            "content_bbox": [xmin, ymin, xmax, ymax],
            "occupied_spatial_cells": 2 if ymax - ymin > 1e-6 or xmax - xmin > 1e-6 else 1,
            "total_spatial_cells": 4,
            "spatial_coverage_ratio": 0.5 if ymax - ymin > 1e-6 or xmax - xmin > 1e-6 else 0.25,
            "maximum_anchor_cluster_ratio": 1.0,
            "cell_counts": {}, "passed": False,
        }
    xmid, ymid = (xmin + xmax) / 2, (ymin + ymax) / 2
    cells = Counter(f"r{int(y >= ymid)}c{int(x >= xmid)}" for x, y in points)
    maximum_ratio = max(cells.values()) / len(points)
    return {
        "content_bbox": [xmin, ymin, xmax, ymax],
        "occupied_spatial_cells": len(cells), "total_spatial_cells": 4,
        "spatial_coverage_ratio": len(cells) / 4,
        "maximum_anchor_cluster_ratio": round(maximum_ratio, 6),
        "cell_counts": dict(cells),
        "passed": len(cells) >= 3 and maximum_ratio <= 0.70,
    }


def _relaxed_geometry_alignment(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
) -> dict[str, Any]:
    """Find a deterministic scale=1 transform from a stable completed target subset."""
    import numpy as np

    from mcp.acceptance.stage3_1_r2_geometry_acceptance import deterministic_holdouts

    reference_features = _native_alignment_features(reference_scan, reference_region)
    target_features = _native_alignment_features(target_scan, target_region)
    bins: dict[tuple[int, int], list[tuple[dict[str, Any], dict[str, Any], Any, float]]] = {}
    bin_size = 100.0
    for reference in reference_features:
        reference_point = np.asarray(reference["point"], dtype=float)
        for target in target_features:
            similarity = _relaxed_feature_similarity(reference, target)
            if similarity < 0.82:
                continue
            delta = np.asarray(target["point"], dtype=float) - reference_point
            key = tuple(int(value) for value in np.rint(delta / bin_size))
            bins.setdefault(key, []).append((reference, target, delta, similarity))

    records = []
    for raw in bins.values():
        translation = np.median(np.asarray([item[2] for item in raw], dtype=float), axis=0)
        ranked = sorted(raw, key=lambda item: (float(np.linalg.norm(item[2] - translation)), -item[3]))
        used_reference: set[str] = set()
        used_target: set[str] = set()
        selected = []
        for reference, target, delta, similarity in ranked:
            residual = float(np.linalg.norm(delta - translation))
            if residual > 150.0:
                continue
            if reference["handle"] in used_reference or target["handle"] in used_target:
                continue
            used_reference.add(reference["handle"])
            used_target.add(target["handle"])
            selected.append((reference, target, delta, similarity, residual))
        if selected:
            records.append({
                "translation": [float(value) for value in translation],
                "selected": selected,
                "anchor_count": len(selected),
                "anchor_type_count": len({item[0]["anchor_type"] for item in selected}),
                "mean_similarity": sum(item[3] for item in selected) / len(selected),
                "maximum_residual": max(item[4] for item in selected),
            })
    records.sort(
        key=lambda item: (
            item["anchor_count"], item["anchor_type_count"], item["mean_similarity"],
            -item["maximum_residual"], tuple(-value for value in item["translation"]),
        ),
        reverse=True,
    )
    if not records:
        return {
            "mode": "COMPLETED_TARGET_SUBSET",
            "status": "BLOCKED_NO_RELAXED_GEOMETRY_CLUSTER",
            "verified": False, "alignment_confidence": 0.0, "transform": None,
            "blockers": ["no relaxed geometry cluster"],
        }

    primary = records[0]
    second_count = records[1]["anchor_count"] if len(records) > 1 else 0
    dominance = primary["anchor_count"] / max(second_count, 1)
    anchors = [
        {
            "anchor_id": f"relaxed_{reference['handle']}_{target['handle']}",
            "anchor_type": reference["anchor_type"],
            "reference_handles": [reference["handle"]],
            "target_handles": [target["handle"]],
            "reference_point": reference["point"],
            "target_point": target["point"],
        }
        for reference, target, _delta, _similarity, _residual in primary["selected"]
    ]
    content_coverage = _content_spatial_coverage(anchors)
    diagonal = math.hypot(float(reference_region["frame_width"]), float(reference_region["frame_height"]))
    holdouts = deterministic_holdouts(
        anchors, primary["translation"], diagonal, content_coverage.get("content_bbox")
    ) if len(anchors) >= 2 else {"all_valid_holdouts_passed": False, "valid_holdout_count": 0}
    reference_class, target_class = _region_class(reference_region), _region_class(target_region)
    system_mode = reference_class == target_class == "SYSTEM_DIAGRAM"
    y_values = [float(item["reference_point"][1]) for item in anchors]
    vertical_span_ratio = (
        (max(y_values) - min(y_values)) / max(float(reference_region["frame_height"]), 1.0)
        if y_values else 0.0
    )
    type_counts = Counter(item["anchor_type"] for item in anchors)
    common_checks = (
        len(anchors) >= 12
        and dominance >= 1.20
        and bool(holdouts.get("all_valid_holdouts_passed"))
        and primary["mean_similarity"] >= 0.90
        and primary["maximum_residual"] <= 150.0
    )
    subset_verified = common_checks and len(type_counts) >= 3 and content_coverage["passed"]
    riser_verified = (
        common_checks and system_mode and set(type_counts) == {"AcDbLine"}
        and vertical_span_ratio >= 0.50
    )
    verified = subset_verified or riser_verified
    evidence_mode = "SYSTEM_RISER_SEQUENCE" if riser_verified else "COMPLETED_TARGET_SUBSET"
    blockers = []
    if len(anchors) < 12:
        blockers.append("fewer than 12 relaxed anchors")
    if dominance < 1.20:
        blockers.append("primary translation cluster is not unique")
    if not holdouts.get("all_valid_holdouts_passed"):
        blockers.append("relaxed anchor holdout unstable")
    if primary["mean_similarity"] < 0.90:
        blockers.append("mean geometry similarity below 0.90")
    if not subset_verified and not riser_verified:
        if len(type_counts) < 3 and not system_mode:
            blockers.append("fewer than 3 relaxed anchor types")
        if not content_coverage["passed"] and not (system_mode and vertical_span_ratio >= 0.50):
            blockers.append("completed-subset spatial coverage failed")
    confidence = (
        0.20 * min(1.0, len(anchors) / 12)
        + 0.15 * min(1.0, len(type_counts) / 3)
        + 0.15 * min(1.0, dominance / 1.20)
        + 0.20 * float(bool(holdouts.get("all_valid_holdouts_passed")))
        + 0.15 * min(1.0, primary["mean_similarity"] / 0.90)
        + 0.15 * (min(1.0, vertical_span_ratio / 0.50) if system_mode else float(content_coverage["passed"]))
    )
    return {
        "mode": evidence_mode,
        "status": "PASS_TRANSLATION_COMPLETED_TARGET_SUBSET" if verified else "BLOCKED_RELAXED_GEOMETRY_EVIDENCE_INSUFFICIENT",
        "verified": verified,
        "reference_region_class": reference_class,
        "target_region_class": target_class,
        "anchor_count": len(anchors),
        "anchor_type_counts": dict(type_counts),
        "primary_cluster_dominance": round(dominance, 6),
        "mean_similarity": round(primary["mean_similarity"], 6),
        "maximum_residual": primary["maximum_residual"],
        "content_spatial_coverage": content_coverage,
        "vertical_span_ratio": round(vertical_span_ratio, 6),
        "holdout_stable": bool(holdouts.get("all_valid_holdouts_passed")),
        "valid_holdout_count": int(holdouts.get("valid_holdout_count", 0)),
        "alignment_confidence": round(confidence, 6),
        "transform": {
            "method": "completed_target_subset_translation_scale_1",
            "translation": primary["translation"],
            "rotation_degrees": 0.0,
            "uniform_scale": 1.0,
            "coordinate_space": "modelspace_cad",
            "accepted": verified,
        },
        "blockers": [] if verified else blockers,
    }


def _native_geometry_alignment(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a scale=1 CAD translation using native, non-title entity evidence."""
    import numpy as np

    from mcp.acceptance.stage3_1_r2_geometry_acceptance import (
        audit_anchor_independence,
        deterministic_holdouts,
    )

    reference_features = _native_alignment_features(reference_scan, reference_region)
    target_features = _native_alignment_features(target_scan, target_region)
    clusters: dict[tuple[int, int], list[tuple[dict[str, Any], dict[str, Any], Any]]] = {}
    for reference in reference_features:
        reference_point = np.asarray(reference["point"], dtype=float)
        for target in target_features:
            if not _native_signature_matches(reference, target):
                continue
            delta = np.asarray(target["point"], dtype=float) - reference_point
            key = tuple(int(value) for value in np.rint(delta))
            clusters.setdefault(key, []).append((reference, target, delta))

    empty = {
        "mode": "NATIVE_GEOMETRY_TRANSLATION",
        "status": "BLOCKED_NATIVE_GEOMETRY_EVIDENCE_INSUFFICIENT",
        "geometry_dominant_verified": False,
        "reference_feature_count": len(reference_features),
        "target_feature_count": len(target_features),
        "raw_primary_cluster_count": 0,
        "independent_anchor_count": 0,
        "anchor_type_counts": {},
        "spatial_coverage": None,
        "holdout_stable": False,
        "target_to_reference_overlap": 0.0,
        "reference_to_target_overlap": 0.0,
        "alignment_confidence": 0.0,
        "transform": None,
        "blockers": ["no native geometry translation cluster"],
    }
    if not clusters:
        return empty

    primary = max(clusters.values(), key=len)
    translation = np.median(np.asarray([item[2] for item in primary], dtype=float), axis=0)
    ranked = sorted(primary, key=lambda item: float(np.linalg.norm(item[2] - translation)))
    used_reference: set[str] = set()
    used_target: set[str] = set()
    anchors = []
    for reference, target, delta in ranked:
        if float(np.linalg.norm(delta - translation)) > 1.0:
            continue
        if reference["handle"] in used_reference or target["handle"] in used_target:
            continue
        used_reference.add(reference["handle"])
        used_target.add(target["handle"])
        anchors.append({
            "anchor_id": f"native_{reference['handle']}_{target['handle']}",
            "anchor_type": reference["anchor_type"],
            "reference_handles": [reference["handle"]],
            "target_handles": [target["handle"]],
            "reference_point": reference["point"],
            "target_point": target["point"],
        })

    anchor_audit = audit_anchor_independence(anchors, reference_region["bbox"])
    independent = anchor_audit.pop("independent_anchors")
    diagonal = math.hypot(float(reference_region["frame_width"]), float(reference_region["frame_height"]))
    holdouts = (
        deterministic_holdouts(independent, translation.tolist(), diagonal, reference_region["bbox"])
        if len(independent) >= 2 else {"all_valid_holdouts_passed": False, "valid_holdout_count": 0}
    )

    matched_reference: set[int] = set()
    matched_target: set[int] = set()
    directional_pairs = []
    for reference_index, reference in enumerate(reference_features):
        predicted = np.asarray(reference["point"], dtype=float) + translation
        for target_index, target in enumerate(target_features):
            if not _native_signature_matches(reference, target):
                continue
            residual = float(np.linalg.norm(predicted - np.asarray(target["point"], dtype=float)))
            if residual <= 1.0:
                directional_pairs.append((residual, reference_index, target_index))
    directional_pairs.sort()
    for _residual, reference_index, target_index in directional_pairs:
        if reference_index in matched_reference or target_index in matched_target:
            continue
        matched_reference.add(reference_index)
        matched_target.add(target_index)
    target_overlap = len(matched_target) / max(len(target_features), 1)
    reference_overlap = len(matched_reference) / max(len(reference_features), 1)

    independent_count = int(anchor_audit["independent_anchor_count"])
    type_count = len(anchor_audit["anchor_type_counts"])
    spatial_passed = bool(anchor_audit["spatial_coverage"]["passed"])
    holdout_passed = bool(holdouts.get("all_valid_holdouts_passed"))
    blockers = []
    if independent_count < 12:
        blockers.append("fewer than 12 independent native anchors")
    if type_count < 3:
        blockers.append("fewer than 3 native anchor types")
    if not spatial_passed:
        blockers.append("native anchor spatial coverage failed")
    if not holdout_passed:
        blockers.append("native anchor holdout unstable")
    if target_overlap < 0.80:
        blockers.append("directional target-to-reference native overlap below 0.80")
    confidence = (
        0.20 * min(1.0, independent_count / 12)
        + 0.15 * min(1.0, type_count / 3)
        + 0.15 * float(anchor_audit["spatial_coverage"]["spatial_coverage_ratio"])
        + 0.20 * float(holdout_passed)
        + 0.30 * target_overlap
    )
    transform = {
        "method": "native_geometry_translation_scale_1",
        "translation": [float(value) for value in translation],
        "rotation_degrees": 0.0,
        "uniform_scale": 1.0,
        "coordinate_space": "modelspace_cad",
        "accepted": not blockers,
    }
    return {
        "mode": "NATIVE_GEOMETRY_TRANSLATION",
        "status": "PASS_TRANSLATION_GEOMETRY_DOMINANT" if not blockers else "BLOCKED_NATIVE_GEOMETRY_EVIDENCE_INSUFFICIENT",
        "geometry_dominant_verified": not blockers,
        "reference_feature_count": len(reference_features),
        "target_feature_count": len(target_features),
        "raw_primary_cluster_count": len(primary),
        "independent_anchor_count": independent_count,
        "anchor_type_counts": anchor_audit["anchor_type_counts"],
        "spatial_coverage": anchor_audit["spatial_coverage"],
        "holdout_stable": holdout_passed,
        "valid_holdout_count": int(holdouts.get("valid_holdout_count", 0)),
        "target_to_reference_overlap": round(target_overlap, 6),
        "reference_to_target_overlap": round(reference_overlap, 6),
        "alignment_confidence": round(confidence, 6),
        "transform": transform,
        "blockers": blockers,
    }


def _bbox_intersects(left: list[float], right: list[float]) -> bool:
    return not (left[2] <= right[0] or left[0] >= right[2] or left[3] <= right[1] or left[1] >= right[3])


def _transform_bbox(bbox: list[float], transform: Mapping[str, Any]) -> list[float]:
    scale = float(transform["uniform_scale"])
    tx, ty = transform["translation"]
    return [bbox[0] * scale + tx, bbox[1] * scale + ty, bbox[2] * scale + tx, bbox[3] * scale + ty]


def _entity_geometry_compatible(
    source: Mapping[str, Any], target: Mapping[str, Any], scale: float
) -> bool:
    if source.get("object_name") != target.get("object_name"):
        return False
    source_geometry, target_geometry = source.get("geometry") or {}, target.get("geometry") or {}
    source_length, target_length = source_geometry.get("length"), target_geometry.get("length")
    if source_length is not None and target_length is not None:
        if _ratio_score(float(source_length) * scale, float(target_length)) < 0.80:
            return False
    source_attributes, target_attributes = source.get("attributes") or {}, target.get("attributes") or {}
    for key in ("dn_diameter", "sys_type"):
        if (
            source_attributes.get(key) is not None and target_attributes.get(key) is not None
            and source_attributes.get(key) != target_attributes.get(key)
        ):
            return False
    source_bbox, target_bbox = _bbox2d(source), _bbox2d(target)
    if source_bbox is not None and target_bbox is not None:
        source_dimensions = [
            (source_bbox[2] - source_bbox[0]) * scale,
            (source_bbox[3] - source_bbox[1]) * scale,
        ]
        target_dimensions = [target_bbox[2] - target_bbox[0], target_bbox[3] - target_bbox[1]]
        meaningful = [
            _ratio_score(left, right)
            for left, right in zip(source_dimensions, target_dimensions)
            if abs(left) > 1e-6 or abs(right) > 1e-6
        ]
        if meaningful and sum(meaningful) / len(meaningful) < 0.75:
            return False
    return True


def _pair_difference_summary(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any],
    target_region: Mapping[str, Any],
    pair_score: Mapping[str, Any],
    transform: Mapping[str, Any],
    protected_bbox: list[float],
    *,
    geometry_verified_override: bool | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Conservative prewrite diff: low-confidence geometry stays review-only."""
    import numpy as np
    from scipy.spatial import cKDTree

    ignored = {"TDbDimension2"}
    frame_or_annotation = {
        "AcDbText", "AcDbMText", "AcDbDimension", "AcDbHatch", "AcDbTable",
        "AcDbBlockReference", "AcDbAttribute", "AcDbAttributeDefinition",
    }
    reference_members = [e for e in _members(reference_scan, reference_region) if str(e.get("object_name")) not in ignored]
    target_members = [e for e in _members(target_scan, target_region) if str(e.get("object_name")) not in ignored]
    target_points: dict[str, list[tuple[float, float]]] = {}
    target_entities: dict[str, list[Mapping[str, Any]]] = {}
    for entity in target_members:
        name = str(entity.get("object_name"))
        point = _center(entity)
        if point is not None:
            target_points.setdefault(name, []).append(point)
            target_entities.setdefault(name, []).append(entity)
    trees = {name: cKDTree(np.asarray(points)) for name, points in target_points.items() if points}
    used_target_indexes: dict[str, set[int]] = {name: set() for name in target_points}

    counts = Counter()
    tasks: list[dict[str, Any]] = []
    source_to_target_matches: list[dict[str, Any]] = []
    geometry_verified = (
        bool(geometry_verified_override)
        if geometry_verified_override is not None
        else float(pair_score["geometry_coverage"]) >= 0.20
        and float(transform.get("aspect_log_residual", math.inf)) <= 0.45
    )
    tolerance = max(target_region["frame_width"], target_region["frame_height"]) * 0.008
    for entity in reference_members:
        name = str(entity.get("object_name"))
        source_bbox = _bbox2d(entity)
        center = _center(entity)
        if source_bbox is None or center is None:
            counts["review"] += 1
            continue
        scale = float(transform["uniform_scale"])
        tx, ty = transform["translation"]
        mapped_center = np.asarray([center[0] * scale + tx, center[1] * scale + ty])
        tree = trees.get(name)
        matched_target_index = None
        if tree is not None:
            candidate_indexes = tree.query_ball_point(mapped_center, tolerance)
            ranked_candidates = sorted(
                (
                    float(np.linalg.norm(np.asarray(target_points[name][int(index)]) - mapped_center)),
                    int(index),
                )
                for index in candidate_indexes
                if int(index) not in used_target_indexes[name]
                and _entity_geometry_compatible(entity, target_entities[name][int(index)], scale)
            )
            if ranked_candidates:
                _distance, matched_target_index = ranked_candidates[0]
                used_target_indexes[name].add(matched_target_index)
                target_entity = target_entities[name][matched_target_index]
                same_style = (
                    entity.get("color") == target_entity.get("color")
                    and entity.get("layer") == target_entity.get("layer")
                    and entity.get("linetype") == target_entity.get("linetype")
                )
                counts["existing" if same_style else "style_difference"] += 1
                counts["source_to_target_match"] += 1
                source_to_target_matches.append({
                    "source_handle": str(entity.get("handle")),
                    "target_handle": str(target_entity.get("handle")),
                    "object_name": name,
                    "classification": "EXISTING_CONFIRMED" if same_style else "EXISTING_WITH_STYLE_DIFFERENCE",
                    "distance": _distance,
                })
                continue
        mapped_bbox = _transform_bbox(source_bbox, transform)
        if _bbox_intersects(mapped_bbox, protected_bbox):
            counts["protected_excluded"] += 1
            continue
        if not geometry_verified or name in frame_or_annotation:
            counts["review"] += 1
            continue
        if name not in ORDINARY_EXECUTION_TYPES and name not in CORE_TDB_EXECUTION_TYPES:
            counts["review"] += 1
            counts["unsupported_missing_review"] += 1
            continue
        task_group = "ordinary" if name in ORDINARY_EXECUTION_TYPES else "core_tdb"
        task = {
            "task_id": f"stage6_p1_{reference_region['region_id']}_{entity.get('handle')}",
            "reference_region_id": reference_region["region_id"],
            "target_region_id": target_region["region_id"],
            "source_entity_id": entity.get("handle"),
            "object_name": name,
            "task_group": task_group,
            "execution_route": (
                "selective_native_clone" if task_group == "ordinary"
                else "relationship_aware_component_clone"
            ),
            "classification": "REQUIRED_MISSING",
            "target_bbox_evidence": mapped_bbox,
            "transform_id": f"alignment_{reference_region['region_id']}_{target_region['region_id']}",
            "execution_allowed": task_group == "ordinary",
            "component_graph_required": task_group == "core_tdb",
            "protected_region_intersection": False,
        }
        tasks.append(task)
        counts["required_missing"] += 1
        counts[f"required_missing_{task_group}"] += 1
    return {
        "reference_region_id": reference_region["region_id"],
        "target_region_id": target_region["region_id"],
        "alignment_geometry_verified": geometry_verified,
        "existing_count": counts["existing"],
        "existing_with_style_difference_count": counts["style_difference"],
        "required_missing_count": counts["required_missing"],
        "required_missing_ordinary_count": counts["required_missing_ordinary"],
        "required_missing_core_tdb_count": counts["required_missing_core_tdb"],
        "review_count": counts["review"],
        "unsupported_missing_review_count": counts["unsupported_missing_review"],
        "ambiguous_count": 0,
        "allowed_dimension2_difference": True,
        "protected_excluded_count": counts["protected_excluded"],
        "color_used_as_missing_evidence": False,
        "source_to_target_matches": source_to_target_matches,
    }, tasks


def _build_core_component_dependency_plan(
    reference_scan: Mapping[str, Any],
    reference_regions: Sequence[Mapping[str, Any]],
    region_diffs: Sequence[Mapping[str, Any]],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    from mcp.recognition.stage5_1_relationship_probe import _bbox_distance, relation_type

    region_by_id = {item["region_id"]: item for item in reference_regions}
    diff_by_id = {item["reference_region_id"]: item for item in region_diffs}
    core_tasks = [task for task in tasks if task.get("task_group") == "core_tdb"]
    tasks_by_region: dict[str, list[dict[str, Any]]] = {}
    for task in core_tasks:
        tasks_by_region.setdefault(task["reference_region_id"], []).append(task)

    component_records = []
    covered_task_ids: set[str] = set()
    blocked_reasons = []
    for region_id, region_tasks in sorted(tasks_by_region.items()):
        region = region_by_id[region_id]
        entities = [
            entity for entity in _members(reference_scan, region)
            if str(entity.get("object_name")) in CORE_TDB_EXECUTION_TYPES
        ]
        by_handle = {str(entity.get("handle")): entity for entity in entities}
        missing_by_handle = {str(task["source_entity_id"]): task for task in region_tasks}
        matches = {
            str(item["source_handle"]): item
            for item in diff_by_id[region_id].get("source_to_target_matches", [])
            if item.get("object_name") in CORE_TDB_EXECUTION_TYPES
        }
        parent = {handle: handle for handle in by_handle}

        def find(handle: str) -> str:
            while parent[handle] != handle:
                parent[handle] = parent[parent[handle]]
                handle = parent[handle]
            return handle

        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        edges = []
        handles = sorted(by_handle)
        for left_index, left_handle in enumerate(handles):
            left = by_handle[left_handle]
            for right_handle in handles[left_index + 1:]:
                right = by_handle[right_handle]
                distance = _bbox_distance(left.get("bbox"), right.get("bbox"))
                if distance is None:
                    continue
                edge_type = relation_type(
                    str(left.get("object_name")), str(right.get("object_name")), float(distance)
                )
                if edge_type is None:
                    continue
                edges.append({
                    "source_handle": left_handle, "target_handle": right_handle,
                    "edge_type": edge_type, "distance": float(distance),
                    "evidence_source": "reference_readonly_geometry",
                })
                union(left_handle, right_handle)

        annotations = [
            handle for handle, entity in by_handle.items()
            if entity.get("object_name") in {"TDbVPipeDim", "TDbSymbMultiLeader"}
        ]
        design_handles = [handle for handle in handles if handle not in annotations]
        for annotation_handle in annotations:
            candidates = []
            for design_handle in design_handles:
                distance = _bbox_distance(
                    by_handle[annotation_handle].get("bbox"), by_handle[design_handle].get("bbox")
                )
                if distance is not None:
                    candidates.append((float(distance), design_handle))
            if candidates:
                distance, design_handle = min(candidates)
                edges.append({
                    "source_handle": annotation_handle, "target_handle": design_handle,
                    "edge_type": "ANNOTATES_OBJECT", "distance": distance,
                    "evidence_source": "reference_readonly_nearest_design_object",
                })
                union(annotation_handle, design_handle)

        groups: dict[str, list[str]] = {}
        for handle in handles:
            groups.setdefault(find(handle), []).append(handle)
        region_component_index = 0
        for component_handles in sorted(groups.values(), key=lambda value: (-len(value), value[0])):
            missing_handles = [handle for handle in component_handles if handle in missing_by_handle]
            if not missing_handles:
                continue
            region_component_index += 1
            component_id = f"stage6_p1_{region_id}_component_{region_component_index:04d}"
            component_edges = [
                edge for edge in edges
                if edge["source_handle"] in component_handles and edge["target_handle"] in component_handles
            ]
            unresolved_dependencies = [
                handle for handle in component_handles
                if handle not in missing_by_handle and handle not in matches
            ]
            component_blockers = []
            if unresolved_dependencies:
                component_blockers.append("component contains unresolved existing reference dependencies")
            relationship_expectations = []
            for handle in missing_handles:
                name = str(by_handle[handle].get("object_name"))
                if name not in {"TDbPipeValve", "TDbPipeFitting"}:
                    continue
                expected = sorted({
                    edge["target_handle"] if edge["source_handle"] == handle else edge["source_handle"]
                    for edge in component_edges
                    if handle in {edge["source_handle"], edge["target_handle"]}
                    and edge["edge_type"] in {"VALVE_BELONGS_TO_PIPE", "FITTING_JOINS_PIPE"}
                })
                relationship_expectations.append({
                    "source_handle": handle,
                    "object_name": name,
                    "expected_related_pipe_source_handles": expected,
                    "empty_relationship_set_allowed": True,
                    "verification_rule": "persisted relation set must exactly equal the mapped reference set",
                })
            non_valves = [
                missing_by_handle[handle]["task_id"] for handle in missing_handles
                if by_handle[handle].get("object_name") != "TDbPipeValve"
            ]
            valves = [
                missing_by_handle[handle]["task_id"] for handle in missing_handles
                if by_handle[handle].get("object_name") == "TDbPipeValve"
            ]
            for handle in missing_handles:
                task = missing_by_handle[handle]
                task["component_id"] = component_id
                task["execution_allowed"] = not component_blockers
                covered_task_ids.add(task["task_id"])
            component_records.append({
                "component_id": component_id,
                "reference_region_id": region_id,
                "source_handles": component_handles,
                "missing_source_handles": missing_handles,
                "existing_source_to_target_dependencies": [matches[handle] for handle in component_handles if handle in matches],
                "edges": component_edges,
                "relationship_expectations": relationship_expectations,
                "execution_order": [*non_valves, *valves],
                "non_valve_task_count": len(non_valves),
                "valve_task_count": len(valves),
                "status": "READY" if not component_blockers else "BLOCKED",
                "blockers": component_blockers,
            })
            if component_blockers:
                blocked_reasons.append({"component_id": component_id, "reasons": component_blockers})

    uncovered = sorted(task["task_id"] for task in core_tasks if task["task_id"] not in covered_task_ids)
    ready = not blocked_reasons and not uncovered and len(covered_task_ids) == len(core_tasks)
    return {
        "phase": "STAGE6-P1-CORE-COMPONENT-DEPENDENCY-PLAN",
        "status": "PASS_COMPONENT_GRAPH_READY" if ready else "BLOCKED_COMPONENT_GRAPH_INCOMPLETE",
        "core_tdb_task_count": len(core_tasks),
        "covered_core_tdb_task_count": len(covered_task_ids),
        "component_count": len(component_records),
        "ready_component_count": sum(item["status"] == "READY" for item in component_records),
        "blocked_component_count": sum(item["status"] == "BLOCKED" for item in component_records),
        "uncovered_task_ids": uncovered,
        "blocked_reasons": blocked_reasons,
        "components": component_records,
        "component_graph_ready": ready,
        "relationship_evidence_mode": "reference_readonly_geometry_then_IDPairs_and_persistence_validation",
        "target_write": False,
        "target_save": False,
        "production_d1_allowed": False,
    }


def apply_manual_region_confirmation(run_id: str) -> dict[str, Any]:
    """Apply the user's seven-region decision and build a no-write prewrite package."""
    paths = P1Paths.build(run_id)
    paths.create()
    superseded_archive = _archive_superseded_mapping_outputs(paths)
    input_manifest = _read_json(paths.root / "input_manifest.json")
    manifest = _read_json(paths.root / "region_manifest.json")
    reference_scan = _read_json(paths.root / "reference_scan.json")
    target_scan = _read_json(paths.root / "target_scan.json")
    logical_regions, split_evidence = _logical_reference_regions(manifest, reference_scan)
    targets = [item for item in manifest["target_regions"] if not item.get("protected")]
    protected = next(item for item in manifest["target_regions"] if item.get("protected"))
    reference_by_id = {item["region_id"]: item for item in logical_regions}
    target_by_id = {item["region_id"]: item for item in targets}

    confirmed_pairs = list(FINAL_MANUAL_REGION_PAIRS)
    reference_ids = [item[0] for item in confirmed_pairs]
    target_ids = [item[1] for item in confirmed_pairs]
    if len(set(reference_ids)) != 7 or len(set(target_ids)) != 7:
        raise RuntimeError("manual confirmation does not form a seven-by-seven bijection")

    matches, alignment_reports, region_diffs, tasks = [], [], [], []
    all_alignment_verified = True
    for reference_id, target_id, basis in confirmed_pairs:
        reference, target = reference_by_id[reference_id], target_by_id[target_id]
        score = _pair_score(reference_scan, target_scan, reference, target)
        strict_geometry = _native_geometry_alignment(reference_scan, target_scan, reference, target)
        relaxed_geometry = _relaxed_geometry_alignment(reference_scan, target_scan, reference, target)
        if strict_geometry["geometry_dominant_verified"]:
            selected_mode = "NATIVE_GEOMETRY_TRANSLATION"
            selected_evidence = strict_geometry
        else:
            selected_mode = relaxed_geometry["mode"]
            selected_evidence = relaxed_geometry
        transform = selected_evidence["transform"] or _bbox_similarity_transform(reference["bbox"], target["bbox"])
        alignment_verified = bool(
            strict_geometry["geometry_dominant_verified"] or relaxed_geometry["verified"]
        )
        all_alignment_verified = all_alignment_verified and alignment_verified
        alignment = {
            "alignment_id": f"alignment_{reference_id}_{target_id}",
            "reference_region_id": reference_id,
            "target_region_id": target_id,
            "status": "AUTO_ALIGNMENT_VERIFIED" if alignment_verified else "BLOCKED_ALIGNMENT_LOW_CONFIDENCE",
            "matching_basis": basis,
            "mapping_revision": FINAL_MANUAL_MAPPING_REVISION,
            "priority_revalidation": (reference_id, target_id) in {
                ("reference_region_0002_lower", "target_region_0002"),
                ("reference_region_0006", "target_region_0006"),
            },
            "region_correspondence_confirmed": True,
            "alignment_confidence": selected_evidence["alignment_confidence"],
            "alignment_evidence_mode": selected_mode,
            "pair_score": score["score"],
            "spatial_coverage": selected_evidence.get("spatial_coverage") or selected_evidence.get("content_spatial_coverage"),
            "residual": None,
            "transform": transform,
            "geometry_evidence": {
                "selected_mode": selected_mode,
                "strict_native": strict_geometry,
                "completed_target_subset": relaxed_geometry,
            },
            "target_write": False,
            "target_save": False,
        }
        alignment_reports.append(alignment)
        _write_json(paths.alignment_reports / f"{alignment['alignment_id']}.json", alignment)
        overlay = paths.previews / f"alignment_{reference_id}_{target_id}.png"
        _render_normalized_overlay(overlay, reference_scan, target_scan, reference, target)
        diff, pair_tasks = _pair_difference_summary(
            reference_scan, target_scan, reference, target, score, transform, protected["bbox"],
            geometry_verified_override=alignment_verified,
        )
        region_diffs.append(diff)
        _write_json(paths.region_diffs / f"diff_{reference_id}_{target_id}.json", diff)
        tasks.extend(pair_tasks)
        matches.append({
            "reference_region_id": reference_id,
            "target_region_id": target_id,
            "status": "MANUALLY_CONFIRMED_UNIQUE_PAIR",
            "matching_basis": basis,
            "matching_confidence": 1.0,
            "alignment_confidence": selected_evidence["alignment_confidence"],
            "reference_bbox": reference["bbox"],
            "target_bbox": target["bbox"],
            "transform_id": alignment["alignment_id"],
            "overlay_path": str(overlay),
            "required_missing_count": diff["required_missing_count"],
            "review_count": diff["review_count"],
            "ambiguous_count": diff["ambiguous_count"],
        })

    protected_intersections = [task for task in tasks if task.get("protected_region_intersection")]
    core_component_graph_required = any(task.get("component_graph_required") for task in tasks)
    component_plan = _build_core_component_dependency_plan(
        reference_scan, logical_regions, region_diffs, tasks
    )
    _write_json(paths.execution_results / "core_component_dependency_plan.json", component_plan)
    core_component_graph_ready = bool(component_plan["component_graph_ready"])
    reference_path, target_path = Path(input_manifest["reference"]["path"]), Path(input_manifest["target"]["path"])
    hashes = {"reference": _sha256(reference_path), "target": _sha256(target_path)}
    frozen = {"reference": input_manifest["reference"]["sha256"], "target": input_manifest["target"]["sha256"]}
    hashes_unchanged = hashes == frozen
    integrity = _read_json(paths.root / "source_integrity.json")
    integrity.update({
        "reference_hash_after_manual_confirmation": hashes["reference"],
        "target_hash_after_manual_confirmation": hashes["target"],
        "reference_hash_unchanged": hashes["reference"] == frozen["reference"],
        "target_hash_unchanged": hashes["target"] == frozen["target"],
        "target_write_started": False,
        "target_saved": False,
    })
    integrity["safety"] = {
        **integrity.get("safety", {}),
        "reference_saved": False,
        "reference_modified": False,
        "target_saved": False,
        "target_modified": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "production_d1_allowed": False,
    }
    _write_json(paths.root / "source_integrity.json", integrity)

    logical_manifest = dict(manifest)
    logical_manifest.update({
        "status": "PASS_P1_LOGICAL_REGIONS_CONFIRMED",
        "reference_frame_region_count": manifest["reference_region_count"],
        "reference_logical_region_count": len(logical_regions),
        "reference_region_count": len(logical_regions),
        "target_frame_region_count": len(targets),
        "target_region_count": len(targets),
        "region_count": len(logical_regions) + len(targets) + 1,
        "reference_regions": logical_regions,
        "logical_split_evidence": split_evidence,
        "region_matching_confirmed": True,
        "target_write_started": False,
    })
    _write_json(paths.root / "region_manifest.json", logical_manifest)
    manifest_lines = [
        "# Stage 6-P1 逻辑区域清单", "",
        "- reference frame regions: 6",
        "- reference logical regions: 7",
        "- target regions: 7",
        "- protected regions: 1", "",
    ]
    for region in [*logical_regions, *targets, protected]:
        manifest_lines.append(
            f"- {region['region_id']}: bbox={region['bbox']}, "
            f"titles={region.get('normalized_titles', [])}, entities={region.get('entity_count')}, "
            f"protected={str(region.get('protected', False)).lower()}"
        )
    (paths.root / "region_manifest.md").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    _write_json(paths.root / "protected_regions.json", {
        "regions": ["水泵房大样图", "泵房大样"],
        "region_id": protected["region_id"],
        "bbox": protected["bbox"],
        "classification": "PROTECTED_COMPLETE_REGION",
        "repair_allowed": False,
        "modification_allowed": False,
        "style_normalization_allowed": False,
        "target_write_started": False,
        "target_saved": False,
    })

    matching = {
        "phase": "STAGE6-P1-REGION-MATCHING-MANUAL-CLOSURE",
        "status": "PASS_P1_REGION_MATCHING",
        "run_id": run_id,
        "mapping_revision": FINAL_MANUAL_MAPPING_REVISION,
        "manual_mapping_final": True,
        "superseded_pairs": [list(item) for item in SUPERSEDED_MANUAL_REGION_PAIRS],
        "superseded_output_archive": (
            str(paths.root / "superseded" / FINAL_MANUAL_MAPPING_REVISION)
            if superseded_archive else None
        ),
        "reference_logical_region_count": 7,
        "target_region_count": 7,
        "matched_pair_count": 7,
        "ambiguous_region_count": 0,
        "matches": matches,
        "unmatched_reference_region_ids": [],
        "unmatched_target_region_ids": [],
        "protected_target_region_ids": [protected["region_id"]],
        "reference_read_only": True,
        "target_write": False,
        "target_save": False,
        "target_write_started": False,
        "target_saved": False,
        "production_d1_allowed": False,
    }
    _write_json(paths.root / "region_matching.json", matching)

    frozen_path = paths.frozen_execution_plans / "stage6_p1_frozen_execution_plan.json"
    gate_passed = bool(
        len(logical_regions) == len(targets) == len(matches) == 7
        and _frozen_plan_gate(
            all_alignment_verified=all_alignment_verified,
            protected_intersection_count=len(protected_intersections),
            hashes_unchanged=hashes_unchanged,
        )
        and (not core_component_graph_required or core_component_graph_ready)
    )
    for task in tasks:
        task["execution_allowed"] = gate_passed
        if not gate_passed:
            task["block_reason"] = "global prewrite gate blocked by unverified region alignment"

    frozen_plan_created = False
    frozen_plan_path: str | None = None
    if gate_passed:
        component_plan_path = paths.execution_results / "core_component_dependency_plan.json"
        alignment_evidence = [
            {
                "alignment_id": item["alignment_id"],
                "reference_region_id": item["reference_region_id"],
                "target_region_id": item["target_region_id"],
                "alignment_confidence": item["alignment_confidence"],
                "alignment_evidence_mode": item["alignment_evidence_mode"],
                "transform": item["transform"],
                "report_path": str(paths.alignment_reports / f"{item['alignment_id']}.json"),
                "report_sha256": _sha256(paths.alignment_reports / f"{item['alignment_id']}.json"),
            }
            for item in alignment_reports
        ]
        diff_evidence = [
            {
                "reference_region_id": item["reference_region_id"],
                "target_region_id": item["target_region_id"],
                "report_path": str(
                    paths.region_diffs
                    / f"diff_{item['reference_region_id']}_{item['target_region_id']}.json"
                ),
                "report_sha256": _sha256(
                    paths.region_diffs
                    / f"diff_{item['reference_region_id']}_{item['target_region_id']}.json"
                ),
            }
            for item in region_diffs
        ]
        frozen_plan = {
            "phase": "STAGE6-P1-FROZEN-EXECUTION-PLAN",
            "run_id": run_id,
            "mapping_revision": FINAL_MANUAL_MAPPING_REVISION,
            "status": "FROZEN_PREWRITE",
            "created_from_readonly_evidence": True,
            "reference_logical_region_count": 7,
            "target_region_count": 7,
            "matched_pair_count": 7,
            "frozen_inputs": {
                "reference": input_manifest["reference"],
                "target": input_manifest["target"],
                "prewrite_backup": input_manifest["prewrite_backup"],
                "prewrite_backup_hash_matches": input_manifest["prewrite_backup_hash_matches"],
            },
            "alignment_evidence": alignment_evidence,
            "region_diff_evidence": diff_evidence,
            "core_component_dependency_plan": {
                "path": str(component_plan_path),
                "sha256": _sha256(component_plan_path),
                "component_count": component_plan["component_count"],
                "component_graph_ready": component_plan["component_graph_ready"],
            },
            "repair_task_count": len(tasks),
            "tasks": tasks,
            "protected_region": {
                "region_id": protected["region_id"],
                "bbox": protected["bbox"],
                "classification": "PROTECTED_COMPLETE_REGION",
                "repair_allowed": False,
                "modification_allowed": False,
            },
            "protected_region_intersection": 0,
            "target_write_allowed": True,
            "target_write_started": False,
            "target_saved": False,
            "production_d1_allowed": False,
        }
        frozen_plan["plan_sha256"] = _payload_sha256(frozen_plan)
        _write_json(frozen_path, frozen_plan)
        frozen_plan_created = True
        frozen_plan_path = str(frozen_path)
    else:
        if frozen_path.exists():
            frozen_path.unlink()
        _write_json(paths.execution_results / "prewrite_candidate_tasks_not_frozen.json", {
            "phase": "STAGE6-P1-PREWRITE-CANDIDATE-TASKS",
            "mapping_revision": FINAL_MANUAL_MAPPING_REVISION,
            "status": "NOT_FROZEN_ALIGNMENT_UNVERIFIED",
            "candidate_task_count": len(tasks),
            "tasks": tasks,
            "target_write": False,
            "target_save": False,
            "production_d1_allowed": False,
        })
    result = {
        "phase": "STAGE6-P1-PREWRITE-MANUAL-CONFIRMATION-CLOSURE",
        "status": "PASS_P1_PREWRITE_GATE" if gate_passed else "BLOCKED_P1_PREWRITE_GATE",
        "run_id": run_id,
        "mapping_revision": FINAL_MANUAL_MAPPING_REVISION,
        "superseded_pairs": [list(item) for item in SUPERSEDED_MANUAL_REGION_PAIRS],
        "reference_logical_region_count": 7,
        "target_region_count": 7,
        "matched_pair_count": 7,
        "ambiguous_region_count": 0,
        "alignment_verified_pair_count": sum(item["status"] == "AUTO_ALIGNMENT_VERIFIED" for item in alignment_reports),
        "alignment_low_confidence_pair_count": sum(item["status"] != "AUTO_ALIGNMENT_VERIFIED" for item in alignment_reports),
        "protected_region_intersection": len(protected_intersections),
        "protected_bbox": protected["bbox"],
        "protected_classification": "PROTECTED_COMPLETE_REGION",
        "protected_repair_allowed": False,
        "protected_modification_allowed": False,
        "reference_hash": hashes["reference"],
        "target_hash": hashes["target"],
        "reference_hash_unchanged": hashes["reference"] == frozen["reference"],
        "target_hash_unchanged": hashes["target"] == frozen["target"],
        "reference_read_only": True,
        "target_write": False,
        "target_save": False,
        "frozen_execution_plan_created": frozen_plan_created,
        "frozen_execution_plan_path": frozen_plan_path,
        "repair_task_count": len(tasks),
        "ordinary_repair_task_count": sum(task.get("task_group") == "ordinary" for task in tasks),
        "core_tdb_repair_task_count": sum(task.get("task_group") == "core_tdb" for task in tasks),
        "core_component_graph_required": core_component_graph_required,
        "core_component_graph_ready": core_component_graph_ready,
        "core_component_count": component_plan["component_count"],
        "blocked_core_component_count": component_plan["blocked_component_count"],
        "difference_counts": {
            "existing": sum(item["existing_count"] for item in region_diffs),
            "style_difference": sum(item["existing_with_style_difference_count"] for item in region_diffs),
            "required_missing": sum(item["required_missing_count"] for item in region_diffs),
            "review": sum(item["review_count"] for item in region_diffs),
            "ambiguous": 0,
            "unsupported_missing_review": sum(item["unsupported_missing_review_count"] for item in region_diffs),
        },
        "region_matches": matches,
        "alignment_reports": alignment_reports,
        "region_diffs": region_diffs,
        "write_gate_passed": gate_passed,
        "required_action": (
            None if gate_passed else
            "若 alignment 未全通过则继续补充几何证据；若核心 TDb task 存在则必须先生成并验证组件依赖图。不得写入 target。"
        ),
        "production_d1_allowed": False,
    }
    _write_json(paths.root / "prewrite_gate.json", result)
    return result


def write_manual_confirmation_report(run_id: str, result: Mapping[str, Any], tests: Mapping[str, Any]) -> dict[str, Any]:
    paths = P1Paths.build(run_id)
    previous = _read_json(paths.root / "stage6_p1_manifest.json")
    consistency_path = paths.root / "manual_mapping_consistency.json"
    consistency = _read_json(consistency_path) if consistency_path.exists() else None
    report = dict(previous)
    report.update({
        "pilot_status": result["status"],
        "reference_hash_after": result["reference_hash"],
        "target_hash_after": result["target_hash"],
        "source_hashes_unchanged": bool(result["reference_hash_unchanged"] and result["target_hash_unchanged"]),
        "region_summary": {
            "reference_frame_region_count": 6,
            "reference_logical_region_count": result["reference_logical_region_count"],
            "target_region_count": result["target_region_count"],
            "protected_region_count": 1,
            "protected_pump_room_confirmed": True,
        },
        "region_matching": {
            "status": "PASS_P1_REGION_MATCHING",
            "matched_pair_count": result["matched_pair_count"],
            "ambiguous_region_count": result["ambiguous_region_count"],
            "matches": result["region_matches"],
            "unmatched_target_region_ids": [],
        },
        "alignment_reports": result["alignment_reports"],
        "difference_counts": result["difference_counts"],
        "execution": {
            **previous.get("execution", {}),
            "frozen_execution_plan_created": result["frozen_execution_plan_created"],
            "frozen_execution_plan_path": result["frozen_execution_plan_path"],
            "target_write_gate_passed": result["write_gate_passed"],
        },
        "qa": {
            **previous.get("qa", {}),
            "protected_region_intersection": result["protected_region_intersection"],
            "protected_region_modified": 0,
        },
        "target_saved": False,
        "target_reopened": False,
        "pilot_completed": False,
        "mvp3_completed": False,
        "mvp4_allowed": False,
        "production_d1_allowed": False,
        "tests": dict(tests),
        "safety": {
            **previous.get("safety", {}),
            "reference_saved": False,
            "reference_modified": False,
            "target_saved": False,
            "target_modified": False,
            "sendcommand_used": False,
            "lisp_executed": False,
            "netload_used": False,
            "tianzheng_command_executed": False,
            "production_d1_allowed": False,
        },
        "required_user_action": result["required_action"],
        "prewrite_gate": {
            key: result[key] for key in (
                "reference_logical_region_count", "target_region_count", "matched_pair_count",
                "ambiguous_region_count", "alignment_verified_pair_count",
                "alignment_low_confidence_pair_count", "protected_region_intersection",
                "reference_hash_unchanged", "target_hash_unchanged", "target_write",
                "target_save", "write_gate_passed",
            )
        },
    })
    report["evidence_paths"] = {
        **previous.get("evidence_paths", {}),
        "prewrite_gate": str(paths.root / "prewrite_gate.json"),
        "frozen_execution_plan": result["frozen_execution_plan_path"],
        "alignment_reports": str(paths.alignment_reports),
        "region_diffs": str(paths.region_diffs),
    }
    if consistency is not None:
        report["manual_mapping_consistency"] = {
            "status": consistency["status"],
            "low_confidence_pair_count": consistency["low_confidence_pair_count"],
            "pair_with_consistency_warning_count": consistency["pair_with_consistency_warning_count"],
            "anchor_template_path": consistency["anchor_template_path"],
            "anchor_capture_instructions_path": consistency["anchor_capture_instructions_path"],
        }
        low_count = consistency["low_confidence_pair_count"]
        report["required_user_action"] = None if low_count == 0 else (
            f"最终 7 对 7 映射已冻结；请为 {low_count} 个低置信 pair 在 "
            "manual_alignment_anchor_input_template.json 中提供至少两组对应 CAD 锚点。"
        )
        report["evidence_paths"]["manual_mapping_consistency"] = str(consistency_path)
        report["evidence_paths"]["manual_alignment_anchor_template"] = consistency["anchor_template_path"]
        report["evidence_paths"]["manual_alignment_anchor_capture_instructions"] = consistency["anchor_capture_instructions_path"]
    _write_json(paths.root / "stage6_p1_manifest.json", report)
    _write_json(REPORT_JSON, report)

    lines = [
        "# Stage 6-P1 多区域核心工程复刻 Pilot", "",
        "## 人工区域确认闭包", "",
        f"- Pilot status: {report['pilot_status']}",
        f"- run_id: {run_id}",
        f"- reference logical regions: {result['reference_logical_region_count']}",
        f"- target regions: {result['target_region_count']}",
        f"- matched pairs: {result['matched_pair_count']}",
        f"- ambiguous regions: {result['ambiguous_region_count']}",
        f"- alignment verified/low confidence: {result['alignment_verified_pair_count']}/{result['alignment_low_confidence_pair_count']}",
        f"- protected region intersection: {result['protected_region_intersection']}",
        f"- reference hash unchanged: {str(result['reference_hash_unchanged']).lower()}",
        "- target write/save: false/false", "",
        "## 7 对 7 区域映射", "",
    ]
    for item in result["region_matches"]:
        lines.append(
            f"- {item['reference_region_id']} -> {item['target_region_id']}: "
            f"{item['status']}; basis={item['matching_basis']}; "
            f"alignment_confidence={item['alignment_confidence']}; "
            f"missing/review/ambiguous={item['required_missing_count']}/{item['review_count']}/{item['ambiguous_count']}"
        )
    lines.extend([
        "", "## 水泵房保护", "",
        f"- bbox: {result['protected_bbox']}",
        "- classification: PROTECTED_COMPLETE_REGION",
        "- repair_allowed: false",
        "- modification_allowed: false", "",
        "## 写前门", "",
        f"- write_gate_passed: {str(result['write_gate_passed']).lower()}",
        f"- required_action: {report['required_user_action']}",
        "- target_write: false",
        "- target_save: false",
        "- production_d1_allowed: false", "",
        "## 测试", "",
        f"- status: {tests.get('status')}",
        f"- result: {tests.get('result')}", "",
    ])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    return report


def solve_similarity_from_anchor_points(
    reference_points: Sequence[Sequence[float]],
    target_points: Sequence[Sequence[float]],
) -> dict[str, Any]:
    """Solve a 2D rotation + uniform scale + translation from verified CAD anchors."""
    import numpy as np

    source = np.asarray(reference_points, dtype=float)
    target = np.asarray(target_points, dtype=float)
    if source.ndim != 2 or target.ndim != 2 or source.shape != target.shape or source.shape[1] != 2:
        raise ValueError("anchor points must be matching Nx2 arrays")
    if len(source) < 2:
        raise ValueError("at least two anchor pairs are required")
    source_center, target_center = source.mean(axis=0), target.mean(axis=0)
    source_zero, target_zero = source - source_center, target - target_center
    source_energy = float(np.sum(source_zero ** 2))
    if source_energy <= 1e-9:
        raise ValueError("reference anchors are degenerate")
    covariance = source_zero.T @ target_zero
    left, singular, right_transpose = np.linalg.svd(covariance)
    rotation = right_transpose.T @ left.T
    if np.linalg.det(rotation) < 0:
        right_transpose[-1, :] *= -1
        rotation = right_transpose.T @ left.T
    scale = float(np.sum(singular) / source_energy)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("anchor transform has invalid scale")
    translation = target_center - scale * (rotation @ source_center)
    predicted = (scale * (rotation @ source.T)).T + translation
    residuals = np.linalg.norm(predicted - target, axis=1)
    rotation_degrees = math.degrees(math.atan2(rotation[1, 0], rotation[0, 0]))
    return {
        "method": "user_verified_cad_anchor_similarity",
        "translation": translation.tolist(),
        "rotation_degrees": rotation_degrees,
        "uniform_scale": scale,
        "anchor_pair_count": len(source),
        "anchor_rmse": float(math.sqrt(float(np.mean(residuals ** 2)))),
        "anchor_max_residual": float(np.max(residuals)),
        "reference_anchor_points": source.tolist(),
        "target_anchor_points": target.tolist(),
        "coordinate_space": "modelspace_cad",
    }


def build_manual_mapping_consistency_audit(run_id: str) -> dict[str, Any]:
    paths = P1Paths.build(run_id)
    manifest = _read_json(paths.root / "region_manifest.json")
    matching = _read_json(paths.root / "region_matching.json")
    gate = _read_json(paths.root / "prewrite_gate.json")
    reference_scan = _read_json(paths.root / "reference_scan.json")
    target_scan = _read_json(paths.root / "target_scan.json")
    reference_by_id = {item["region_id"]: item for item in manifest["reference_regions"]}
    targets = [item for item in manifest["target_regions"] if not item.get("protected")]
    target_by_id = {item["region_id"]: item for item in targets}
    alignment_by_pair = {
        (item["reference_region_id"], item["target_region_id"]): item
        for item in gate["alignment_reports"]
    }
    selected_types = (
        "TDbWall", "TDbColumn", "TDbOpening", "TDbAxisLabelSet",
        "AcDbBlockReference", "AcDbLine", "AcDbPolyline",
        "TDbPipe", "TDbPipeFitting", "TDbPipeValve",
    )
    pair_audits = []
    low_confidence_pairs = []
    contradiction_count = 0
    for match in matching["matches"]:
        reference_id, target_id = match["reference_region_id"], match["target_region_id"]
        reference, assigned_target = reference_by_id[reference_id], target_by_id[target_id]
        candidates = sorted(
            [_pair_score(reference_scan, target_scan, reference, target) for target in targets],
            key=lambda item: item["score"], reverse=True,
        )
        assigned = next(item for item in candidates if item["target_region_id"] == target_id)
        class_compatible_candidates = [item for item in candidates if item["region_class_compatible"]]
        strongest = (class_compatible_candidates or candidates)[0]
        alignment = alignment_by_pair[(reference_id, target_id)]
        reasons = []
        if alignment["status"] != "AUTO_ALIGNMENT_VERIFIED":
            reasons.append("alignment_low_confidence")
        if not assigned["title_compatible"]:
            reasons.append("extracted_title_semantics_conflict")
        if "aspect_log_residual" in alignment["transform"] and alignment["transform"]["aspect_log_residual"] > 0.45:
            reasons.append("logical_bbox_aspect_incompatible_with_uniform_scale")
        if strongest["target_region_id"] != target_id and strongest["score"] - assigned["score"] >= 0.08:
            reasons.append("stronger_unassigned_geometric_candidate")
        semantic_counts = {
            name: {
                "reference": int((reference.get("object_type_counts") or {}).get(name, 0)),
                "assigned_target": int((assigned_target.get("object_type_counts") or {}).get(name, 0)),
                "strongest_candidate": int((target_by_id[strongest["target_region_id"]].get("object_type_counts") or {}).get(name, 0)),
            }
            for name in selected_types
        }
        item = {
            "reference_region_id": reference_id,
            "assigned_target_region_id": target_id,
            "matching_basis": match["matching_basis"],
            "assigned_pair_score": assigned["score"],
            "assigned_geometry_coverage": assigned["geometry_coverage"],
            "assigned_count_similarity": assigned["count_similarity"],
            "assigned_title_compatible": assigned["title_compatible"],
            "assigned_alignment_status": alignment["status"],
            "assigned_alignment_confidence": alignment["alignment_confidence"],
            "assigned_aspect_log_residual": alignment["transform"].get("aspect_log_residual"),
            "native_geometry_evidence": alignment.get("geometry_evidence"),
            "strongest_candidate_target_region_id": strongest["target_region_id"],
            "strongest_candidate_score": strongest["score"],
            "strongest_candidate_geometry_coverage": strongest["geometry_coverage"],
            "strongest_candidate_count_similarity": strongest["count_similarity"],
            "consistency_reasons": reasons,
            "semantic_count_evidence": semantic_counts,
            "requires_anchor_confirmation": alignment["status"] != "AUTO_ALIGNMENT_VERIFIED",
        }
        item["assigned_overlay_path"] = str(
            paths.previews / f"alignment_{reference_id}_{target_id}.png"
        )
        alternative_overlay = paths.previews / f"consistency_{reference_id}_{strongest['target_region_id']}.png"
        if strongest["target_region_id"] != target_id:
            _render_normalized_overlay(
                alternative_overlay,
                reference_scan,
                target_scan,
                reference,
                target_by_id[strongest["target_region_id"]],
            )
            item["strongest_candidate_overlay_path"] = str(alternative_overlay)
        else:
            item["strongest_candidate_overlay_path"] = item["assigned_overlay_path"]
        pair_audits.append(item)
        if reasons:
            contradiction_count += 1
        if item["requires_anchor_confirmation"]:
            low_confidence_pairs.append(item)

    anchor_template = {
        "phase": "STAGE6-P1-MANUAL-ALIGNMENT-ANCHORS",
        "run_id": run_id,
        "coordinate_space": "modelspace_cad",
        "instructions": (
            "For each listed pair, provide at least two distinct corresponding CAD points. "
            "Use the frozen reference and authorized target coordinates; do not modify either drawing while capturing anchors."
        ),
        "pairs": [
            {
                "reference_region_id": item["reference_region_id"],
                "target_region_id": item["assigned_target_region_id"],
                "pair_mapping_confirmed": None,
                "reference_anchor_points": [],
                "target_anchor_points": [],
                "anchor_description": [],
                "provided_by_user": True,
            }
            for item in low_confidence_pairs
        ],
        "mapping_revision": FINAL_MANUAL_MAPPING_REVISION,
        "manual_mapping_final": True,
        "mapping_conflicts": [],
        "target_write": False,
        "target_save": False,
    }
    anchor_template_path = paths.alignment_reports / "manual_alignment_anchor_input_template.json"
    _write_json(anchor_template_path, anchor_template)
    capture_instructions_path = paths.alignment_reports / "manual_alignment_anchor_capture_instructions.md"
    capture_lines = [
        "# Stage 6-P1 CAD Alignment Anchor Capture", "",
        "Operate read-only. Do not save or modify the reference or target DWG.", "",
        "## Final Mapping", "",
        f"The seven-by-seven mapping is frozen by user confirmation: `{FINAL_MANUAL_MAPPING_REVISION}`.",
        "Do not remap a pair from automatic candidate scores; anchors are only for transform verification.", "",
        "## CAD Anchors", "",
        "For every entry in `pairs`, capture at least two distinct corresponding model-space CAD points.",
        "Use stable engineering geometry such as grid intersections, pipe centerline intersections, or equipment insertion points.",
        "Do not use PDF coordinates, screenshot pixels, guessed points, or default origin.",
        "Keep anchor pairs well separated; for split regions, do not use parent frame corners as content anchors.",
        "Set `pair_mapping_confirmed=true` only after visually verifying the same logical feature in both regions.", "",
        f"Fill: `{anchor_template_path}`", "",
    ]
    capture_instructions_path.write_text("\n".join(capture_lines), encoding="utf-8")
    audit = {
        "phase": "STAGE6-P1-MANUAL-MAPPING-CONSISTENCY-AUDIT",
        "status": "HUMAN_TRANSFORM_CONFIRMATION_REQUIRED" if low_confidence_pairs else "PASS_MAPPING_AND_ALIGNMENT_CONSISTENCY",
        "run_id": run_id,
        "mapping_revision": FINAL_MANUAL_MAPPING_REVISION,
        "manual_mapping_final": True,
        "matched_pair_count": len(pair_audits),
        "low_confidence_pair_count": len(low_confidence_pairs),
        "pair_with_consistency_warning_count": contradiction_count,
        "pair_audits": pair_audits,
        "anchor_template_path": str(anchor_template_path),
        "anchor_capture_instructions_path": str(capture_instructions_path),
        "target_write": False,
        "target_save": False,
        "reference_read_only": True,
        "reference_hash_unchanged": gate["reference_hash_unchanged"],
        "target_hash_unchanged": gate["target_hash_unchanged"],
        "production_d1_allowed": False,
    }
    audit_path = paths.root / "manual_mapping_consistency.json"
    _write_json(audit_path, audit)
    lines = [
        "# Stage 6-P1 人工映射一致性审计", "",
        f"- status: {audit['status']}",
        f"- matched pairs: {audit['matched_pair_count']}",
        f"- low-confidence pairs: {audit['low_confidence_pair_count']}",
        f"- warning pairs: {audit['pair_with_consistency_warning_count']}",
        "- target write/save: false/false", "",
        "## Pair Evidence", "",
    ]
    for item in pair_audits:
        lines.append(
            f"- {item['reference_region_id']} -> {item['assigned_target_region_id']}: "
            f"alignment={item['assigned_alignment_status']}, coverage={item['assigned_alignment_confidence']}, "
            f"strongest={item['strongest_candidate_target_region_id']}, reasons={item['consistency_reasons']}"
        )
    lines.extend([
        "", "## Required Input", "",
        f"Fill `{anchor_template_path}` with at least two corresponding CAD anchor pairs for every low-confidence mapping.",
        "Do not write or save either DWG while capturing coordinates.", "",
    ])
    (paths.root / "manual_mapping_consistency.md").write_text("\n".join(lines), encoding="utf-8")
    return audit


def build_region_matching(run_id: str) -> dict[str, Any]:
    from scipy.optimize import linear_sum_assignment
    import numpy as np

    paths = P1Paths.build(run_id)
    manifest = _read_json(paths.root / "region_manifest.json")
    reference_scan = _read_json(paths.root / "reference_scan.json")
    target_scan = _read_json(paths.root / "target_scan.json")
    reference_regions = list(manifest["reference_regions"])
    target_regions = [item for item in manifest["target_regions"] if not item.get("protected")]
    pairs = [
        _pair_score(reference_scan, target_scan, reference_region, target_region)
        for reference_region in reference_regions for target_region in target_regions
    ]
    pair_map = {(item["reference_region_id"], item["target_region_id"]): item for item in pairs}
    matrix = np.asarray([
        [-pair_map[(reference["region_id"], target["region_id"])]["score"] for target in target_regions]
        for reference in reference_regions
    ])
    rows, columns = linear_sum_assignment(matrix)
    assigned = {reference_regions[row]["region_id"]: target_regions[column]["region_id"] for row, column in zip(rows, columns)}
    matches = []
    ambiguous = []
    for reference in reference_regions:
        candidates = sorted(
            [
                pair_map[(reference["region_id"], target["region_id"])]
                for target in target_regions
                if pair_map[(reference["region_id"], target["region_id"])]["title_compatible"]
                and pair_map[(reference["region_id"], target["region_id"])]["region_class_compatible"]
            ],
            key=lambda item: item["score"], reverse=True,
        )
        assigned_target = assigned.get(reference["region_id"])
        assigned_pair = pair_map[(reference["region_id"], assigned_target)] if assigned_target else None
        best_score = candidates[0]["score"] if candidates else 0.0
        second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
        margin = best_score - second_score
        assigned_is_best = bool(assigned_pair and candidates and assigned_pair["target_region_id"] == candidates[0]["target_region_id"])
        unique = bool(assigned_pair and assigned_is_best and assigned_pair["score"] >= 0.38 and margin >= 0.06)
        status = "UNIQUE_CANDIDATE" if unique else (
            "BLOCKED_NO_CORRESPONDING_REGION" if not candidates or best_score < 0.20 else "HUMAN_REGION_CONFIRMATION_REQUIRED"
        )
        item = {
            "reference_region_id": reference["region_id"],
            "assigned_target_region_id": assigned_target,
            "status": status,
            "matching_confidence": assigned_pair["score"] if assigned_pair else 0.0,
            "best_candidate_score": best_score,
            "second_candidate_score": second_score,
            "uniqueness_margin": round(margin, 6),
            "assigned_pair": assigned_pair,
            "ranked_candidates": candidates,
        }
        matches.append(item)
        if status != "UNIQUE_CANDIDATE":
            ambiguous.append(item)
            raw_candidates = sorted(
                [pair_map[(reference["region_id"], target["region_id"])] for target in target_regions],
                key=lambda value: value["score"], reverse=True,
            )
            overlay_candidates = candidates[:2] if candidates else raw_candidates[:2]
            for candidate in overlay_candidates:
                target_region = next(region for region in target_regions if region["region_id"] == candidate["target_region_id"])
                output = paths.previews / f"matching_{reference['region_id']}_{target_region['region_id']}.png"
                _render_normalized_overlay(output, reference_scan, target_scan, reference, target_region)
    used_targets = {item["assigned_target_region_id"] for item in matches if item["status"] == "UNIQUE_CANDIDATE"}
    unmatched_targets = [region["region_id"] for region in target_regions if region["region_id"] not in used_targets]
    status = "PASS_P1_REGION_MATCHING" if not ambiguous else "HUMAN_REGION_CONFIRMATION_REQUIRED"
    report = {
        "phase": "STAGE6-P1-REGION-MATCHING",
        "status": status,
        "run_id": run_id,
        "matches": matches,
        "pair_score_matrix": pairs,
        "unique_match_count": sum(item["status"] == "UNIQUE_CANDIDATE" for item in matches),
        "human_confirmation_required_count": sum(item["status"] == "HUMAN_REGION_CONFIRMATION_REQUIRED" for item in matches),
        "blocked_no_corresponding_count": sum(item["status"] == "BLOCKED_NO_CORRESPONDING_REGION" for item in matches),
        "unmatched_target_region_ids": unmatched_targets,
        "protected_target_region_ids": [item["region_id"] for item in manifest["target_regions"] if item.get("protected")],
        "target_write_started": False,
        "target_saved": False,
        "production_d1_allowed": False,
    }
    _write_json(paths.root / "region_matching.json", report)
    return report


def finalize_prewrite_stop(run_id: str, tests: Mapping[str, Any] | None = None) -> dict[str, Any]:
    paths = P1Paths.build(run_id)
    input_manifest = _read_json(paths.root / "input_manifest.json")
    scan = _read_json(paths.root / "readonly_scan_result.json")
    regions = _read_json(paths.root / "region_manifest.json")
    matching = _read_json(paths.root / "region_matching.json")
    reference_path = Path(input_manifest["reference"]["path"])
    target_path = Path(input_manifest["target"]["path"])
    final_hashes = {"reference": _sha256(reference_path), "target": _sha256(target_path)}
    frozen_hashes = {"reference": input_manifest["reference"]["sha256"], "target": input_manifest["target"]["sha256"]}
    source_hashes_unchanged = final_hashes == frozen_hashes
    downstream = {
        "property_qa.json": "NOT_RUN_REGION_MATCHING_STOP_GATE",
        "topology_qa.json": "NOT_RUN_REGION_MATCHING_STOP_GATE",
        "persistence_qa.json": "NOT_RUN_REGION_MATCHING_STOP_GATE",
        "idempotency_qa.json": "NOT_RUN_REGION_MATCHING_STOP_GATE",
        "protected_region_qa.json": "PASS_PREWRITE_PROTECTION_FROZEN_NO_WRITE",
        "style_mapping.json": "NOT_RUN_REGION_MATCHING_STOP_GATE",
    }
    for name, status in downstream.items():
        _write_json(paths.root / name, {
            "phase": "STAGE6-P1", "status": status, "run_id": run_id,
            "target_write_started": False, "target_saved": False,
            "reference_hash_unchanged": source_hashes_unchanged,
            "target_hash_unchanged": source_hashes_unchanged,
            "production_d1_allowed": False,
        })
    stop_status = matching["status"]
    report = {
        "phase": "STAGE6-P1-MULTI-REGION-CORE-RECONSTRUCTION-PILOT",
        "pilot_status": stop_status,
        "stage6_final_status": "PARTIAL_SAMPLE_COVERAGE",
        "run_id": run_id,
        "reference": input_manifest["reference"],
        "target": input_manifest["target"],
        "prewrite_backup": input_manifest["prewrite_backup"],
        "prewrite_backup_hash_matches": input_manifest["prewrite_backup_hash_matches"],
        "reference_hash_after": final_hashes["reference"],
        "target_hash_after": final_hashes["target"],
        "source_hashes_unchanged": source_hashes_unchanged,
        "readonly_scan": {
            "status": scan["status"],
            "reference_entity_count": scan["reference_entity_count"],
            "target_entity_count": scan["target_entity_count"],
            "reference_tdb_count": scan["reference_tdb_count"],
            "target_tdb_count": scan["target_tdb_count"],
        },
        "region_summary": {
            "reference_region_count": regions["reference_region_count"],
            "target_frame_region_count": regions["target_frame_region_count"],
            "protected_region_count": regions["protected_region_count"],
            "protected_pump_room_confirmed": regions["protected_pump_room_confirmed"],
        },
        "region_matching": {
            "status": matching["status"],
            "unique_match_count": matching["unique_match_count"],
            "human_confirmation_required_count": matching["human_confirmation_required_count"],
            "blocked_no_corresponding_count": matching["blocked_no_corresponding_count"],
            "matches": matching["matches"],
            "unmatched_target_region_ids": matching["unmatched_target_region_ids"],
        },
        "processed_region_ids": [],
        "protected_region_ids": matching["protected_target_region_ids"],
        "alignment_reports": [],
        "difference_counts": {"existing": None, "style_difference": None, "required_missing": None, "review": None},
        "execution": {
            "ordinary_attempted": 0, "ordinary_successful": 0,
            "core_tdb_attempted": 0, "core_tdb_successful": 0,
            "new_object_types": [], "frozen_execution_plan_created": False,
        },
        "qa": {
            "property": "NOT_RUN_STOP_GATE", "relationship": "NOT_RUN_STOP_GATE",
            "topology": "NOT_RUN_STOP_GATE", "persistence": "NOT_RUN_STOP_GATE",
            "idempotency": "NOT_RUN_STOP_GATE", "existing_modified": 0,
            "existing_deleted": 0, "protected_region_modified": 0,
            "duplicate": 0, "unexpected_new": 0,
        },
        "target_saved": False,
        "target_reopened": False,
        "rollback_used": False,
        "pilot_completed": False,
        "valid_sample_count": 1,
        "pilot_sample_count": 1,
        "blind_sample_count": 0,
        "additional_valid_samples_required": 2,
        "additional_blind_samples_required": 2,
        "dimension2_required": False,
        "mvp3_completed": False,
        "mvp4_allowed": False,
        "production_d1_allowed": False,
        "tests": dict(tests or {"status": "NOT_RUN"}),
        "safety": {
            "reference_opened_read_only": True, "reference_saved": False, "reference_modified": False,
            "target_opened_read_only": True, "target_saved": False, "target_modified": False,
            "sendcommand_used": False, "lisp_executed": False, "netload_used": False,
            "tianzheng_command_executed": False, "production_d1_allowed": False,
        },
        "required_user_action": (
            "确认 reference_region_0002 在 target_region_0002/0003 中的唯一对应；"
            "确认 reference_region_0004 在 target_region_0004/0005 中的唯一对应；"
            "说明 reference_region_0003（生活给水/排水系统原理图）是否有 target 对应区域。"
        ),
        "evidence_paths": {
            "run_root": str(paths.root),
            "region_overview": str(paths.previews / "region_overview.png"),
            "region_contact_sheet": str(paths.previews / "region_contact_sheet.png"),
            "region_matching": str(paths.root / "region_matching.json"),
            "prewrite_backup": input_manifest["prewrite_backup"]["path"],
        },
    }
    _write_json(paths.root / "stage6_p1_manifest.json", report)
    _write_json(REPORT_JSON, report)
    lines = [
        "# Stage 6-P1 多区域核心工程复刻 Pilot", "",
        f"- Pilot status: {report['pilot_status']}",
        f"- run_id: {run_id}",
        f"- reference SHA256: {report['reference']['sha256']}",
        f"- target SHA256: {report['target']['sha256']}",
        f"- prewrite backup hash matches: {str(report['prewrite_backup_hash_matches']).lower()}",
        f"- reference/target regions: {regions['reference_region_count']}/{regions['target_frame_region_count']}",
        f"- unique/human/no-corresponding: {matching['unique_match_count']}/{matching['human_confirmation_required_count']}/{matching['blocked_no_corresponding_count']}",
        "- processed regions: 0", "- target saved/reopened: false/false",
        "- existing modified/deleted: 0/0", "- protected region modified: 0",
        f"- source hashes unchanged: {str(source_hashes_unchanged).lower()}",
        "- Pilot completed: false", "- MVP3 completed: false", "- MVP4 allowed: false",
        "- Production D1 allowed: false", "", "## Region Matching", "",
    ]
    for item in matching["matches"]:
        lines.append(f"- {item['reference_region_id']} -> {item['assigned_target_region_id']}: {item['status']} (confidence={item['matching_confidence']})")
    lines.extend(["", "## Required User Action", "", report["required_user_action"], ""])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run_prewrite_preflight()
    write_preflight_report(result)
    print(json.dumps({"status": result["status"], "run_id": result["run_id"]}, ensure_ascii=False))
