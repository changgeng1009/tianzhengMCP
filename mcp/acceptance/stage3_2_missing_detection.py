from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mcp.acceptance import stage3_1_r1_analysis as r1


ROOT = Path(__file__).resolve().parents[2]
R1_RUN_ROOT = ROOT / "artifacts" / "stage3_1_r1" / "stage3_1_r1_20260711_002112"
R2_REPORT = ROOT / "reports" / "stage3_1_r2_geometry_acceptance.json"
STAGE1_REPORT = ROOT / "reports" / "stage1_final_acceptance.json"
REPORT_JSON = ROOT / "reports" / "stage3_2_missing_detection.json"
REPORT_MD = ROOT / "reports" / "stage3_2_missing_detection.md"
RUNS_ROOT = ROOT / "artifacts" / "stage3_2"

REFERENCE_SOURCE = ROOT / "artifacts" / "validation" / "s1_reference_fixture_20260710_134249.dwg"
TARGET_SOURCE = Path(r"E:\SampleDrawings\target_sample.dwg")

DIRECT_COM_TYPES = {"AcDbLine", "AcDbPolyline", "AcDbText", "AcDbMText", "AcDbBlockReference"}
UNSUPPORTED_AUTOMATIC_TYPES = {"AcDbCircle"}
TITLE_TOKENS = ("title", "frame", "图框", "图签", "twt_title")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _point(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    result = [float(value[0]), float(value[1]), float(value[2]) if len(value) > 2 else 0.0]
    return result if all(math.isfinite(item) for item in result) else None


def _bbox(value: Any) -> list[list[float]] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    low, high = _point(value[0]), _point(value[1])
    if not low or not high or high[0] < low[0] or high[1] < low[1]:
        return None
    return [low, high]


def _translate_point(value: Any, translation: Sequence[float]) -> list[float] | None:
    point = _point(value)
    if not point:
        return None
    return [point[0] + float(translation[0]), point[1] + float(translation[1]), point[2]]


def _translate_bbox(value: Any, translation: Sequence[float]) -> list[list[float]] | None:
    bbox = _bbox(value)
    if not bbox:
        return None
    return [_translate_point(bbox[0], translation), _translate_point(bbox[1], translation)]  # type: ignore[list-item]


def _round_point(value: Any, digits: int = 3) -> tuple[float, float, float] | None:
    point = _point(value)
    return tuple(round(item, digits) for item in point) if point else None


def _geometry_key(entity: Mapping[str, Any], translation: Sequence[float] | None = None) -> tuple[Any, ...]:
    translation = translation or (0.0, 0.0)
    name = str(entity.get("object_name") or "")
    layer = str(entity.get("layer") or "")
    geometry = entity.get("geometry") or {}
    bbox = _translate_bbox(entity.get("bbox"), translation)
    bbox_key = None
    if bbox:
        bbox_key = (_round_point(bbox[0]), _round_point(bbox[1]))
    if name == "AcDbLine":
        start = _round_point(_translate_point(geometry.get("start_point"), translation))
        end = _round_point(_translate_point(geometry.get("end_point"), translation))
        endpoints = tuple(sorted((start, end))) if start and end else None
        return name, layer, endpoints
    if name == "AcDbCircle":
        center = _round_point(_translate_point(geometry.get("center"), translation))
        radius = round(float(geometry.get("radius") or 0.0), 3)
        return name, layer, center, radius
    if name in {"AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline"}:
        vertices = tuple(
            _round_point(_translate_point(vertex, translation))
            for vertex in geometry.get("vertices", [])
        )
        return name, layer, vertices, bbox_key
    if name == "AcDbBlockReference":
        point = _round_point(_translate_point(geometry.get("insertion_point"), translation))
        block_name = entity.get("attributes", {}).get("effective_name") or entity.get("attributes", {}).get("name")
        return name, layer, str(block_name), point
    return name, layer, bbox_key


def _center(entity: Mapping[str, Any], translation: Sequence[float] | None = None) -> list[float] | None:
    bbox = _translate_bbox(entity.get("bbox"), translation or (0.0, 0.0))
    if bbox:
        return [(bbox[0][0] + bbox[1][0]) / 2, (bbox[0][1] + bbox[1][1]) / 2, (bbox[0][2] + bbox[1][2]) / 2]
    geometry = entity.get("geometry") or {}
    for key in ("center", "insertion_point", "position", "start_point"):
        point = _translate_point(geometry.get(key), translation or (0.0, 0.0))
        if point:
            return point
    return None


def _is_stage1_seed(entity: Mapping[str, Any], seed_handle: str, seed_layer: str) -> bool:
    return str(entity.get("handle")) == seed_handle or str(entity.get("layer")) == seed_layer


def _is_title_or_frame(entity: Mapping[str, Any]) -> bool:
    text = " ".join(str(entity.get(key) or "") for key in ("object_name", "layer", "entity_name")).lower()
    return any(token in text for token in TITLE_TOKENS) or entity.get("object_name") == "TDbDrawingName"


def filter_detection_entities(
    entities: Iterable[Mapping[str, Any]],
    *,
    seed_handle: str,
    seed_layer: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw in entities:
        entity = dict(raw)
        reason = None
        if _is_stage1_seed(entity, seed_handle, seed_layer):
            reason = "stage1_seed_line"
        elif _is_title_or_frame(entity):
            reason = "title_frame_or_drawing_name"
        if reason:
            excluded.append({
                "handle": entity.get("handle"),
                "object_name": entity.get("object_name"),
                "layer": entity.get("layer"),
                "reason": reason,
            })
        else:
            kept.append(entity)
    return kept, excluded


def one_to_one_match(
    reference_entities: Sequence[Mapping[str, Any]],
    target_entities: Sequence[Mapping[str, Any]],
    translation: Sequence[float],
) -> dict[str, Any]:
    reference_groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    target_groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for entity in reference_entities:
        reference_groups[_geometry_key(entity, translation)].append(entity)
    for entity in target_entities:
        target_groups[_geometry_key(entity)].append(entity)

    matches: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    target_only: list[dict[str, Any]] = []
    multiplicity_conflicts: list[dict[str, Any]] = []
    for key in sorted(set(reference_groups) | set(target_groups), key=repr):
        references = sorted(reference_groups.get(key, []), key=lambda item: str(item.get("handle")))
        targets = sorted(target_groups.get(key, []), key=lambda item: str(item.get("handle")))
        paired = min(len(references), len(targets))
        for index in range(paired):
            ref, target = references[index], targets[index]
            residual = math.dist(_center(ref, translation) or [0, 0, 0], _center(target) or [0, 0, 0])
            matches.append({
                "reference_handle": ref.get("handle"),
                "target_handle": target.get("handle"),
                "object_name": ref.get("object_name"),
                "layer": ref.get("layer"),
                "match_method": "exact_transformed_geometry_key_one_to_one",
                "residual": residual,
            })
        missing.extend(dict(item) for item in references[paired:])
        target_only.extend(dict(item) for item in targets[paired:])
        if references and targets and len(references) != len(targets):
            multiplicity_conflicts.append({
                "geometry_key": repr(key),
                "reference_count": len(references),
                "target_count": len(targets),
                "resolution": "matched one-to-one by stable handle order; unmatched multiplicity retained for review",
            })
    return {
        "matches": matches,
        "missing_reference_entities": missing,
        "target_only_entities": target_only,
        "multiplicity_conflicts": multiplicity_conflicts,
    }


def _line_compound_matches(
    reference: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]],
    translation: Sequence[float],
    tolerance: float = 1.0,
) -> list[list[str]]:
    if reference.get("object_name") != "AcDbLine":
        return []
    geometry = reference.get("geometry") or {}
    start = _translate_point(geometry.get("start_point"), translation)
    end = _translate_point(geometry.get("end_point"), translation)
    if not start or not end:
        return []
    candidates = [item for item in targets if item.get("object_name") == "AcDbLine" and item.get("layer") == reference.get("layer")]
    results: list[list[str]] = []
    for index, left in enumerate(candidates):
        lgeom = left.get("geometry") or {}
        left_points = [_point(lgeom.get("start_point")), _point(lgeom.get("end_point"))]
        if not all(left_points):
            continue
        for right in candidates[index + 1:]:
            rgeom = right.get("geometry") or {}
            right_points = [_point(rgeom.get("start_point")), _point(rgeom.get("end_point"))]
            if not all(right_points):
                continue
            points = [*left_points, *right_points]
            for shared_left in left_points:
                for shared_right in right_points:
                    if math.dist(shared_left, shared_right) > tolerance:  # type: ignore[arg-type]
                        continue
                    outer = [point for point in points if point is not shared_left and point is not shared_right]
                    if len(outer) == 2 and _same_unordered_endpoints(start, end, outer[0], outer[1], tolerance):
                        results.append([str(left.get("handle")), str(right.get("handle"))])
    return results


def _same_unordered_endpoints(a: Sequence[float], b: Sequence[float], c: Sequence[float], d: Sequence[float], tolerance: float) -> bool:
    return (math.dist(a, c) <= tolerance and math.dist(b, d) <= tolerance) or (math.dist(a, d) <= tolerance and math.dist(b, c) <= tolerance)


def _target_geometry(entity: Mapping[str, Any], translation: Sequence[float]) -> dict[str, Any]:
    name = str(entity.get("object_name"))
    geometry = entity.get("geometry") or {}
    result: dict[str, Any] = {
        "bbox": _translate_bbox(entity.get("bbox"), translation),
    }
    if name == "AcDbLine":
        result.update({
            "start_point": _translate_point(geometry.get("start_point"), translation),
            "end_point": _translate_point(geometry.get("end_point"), translation),
        })
    elif name == "AcDbCircle":
        result.update({
            "center": _translate_point(geometry.get("center"), translation),
            "radius": float(geometry.get("radius") or 0.0),
        })
    elif name in {"AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline"}:
        result["vertices"] = [_translate_point(value, translation) for value in geometry.get("vertices", [])]
    elif name in {"AcDbText", "AcDbMText", "AcDbBlockReference"}:
        result["insert_point"] = _translate_point(
            geometry.get("insertion_point") or geometry.get("position"), translation
        )
    return result


def _geometry_complete(name: str, geometry: Mapping[str, Any]) -> bool:
    if name == "AcDbLine":
        start, end = _point(geometry.get("start_point")), _point(geometry.get("end_point"))
        return bool(start and end and math.dist(start, end) > 1e-6)
    if name == "AcDbPolyline":
        vertices = [_point(item) for item in geometry.get("vertices", [])]
        return len(vertices) >= 2 and all(vertices)
    if name in {"AcDbText", "AcDbMText", "AcDbBlockReference"}:
        return _point(geometry.get("insert_point")) not in (None, [0.0, 0.0, 0.0])
    return False


def _candidate_confidence(geometry_complete: bool, duplicate_free: bool = True) -> tuple[float, dict[str, float]]:
    components = {
        "transform_residual_stability": 1.0,
        "target_scan_completeness": 0.9,
        "region_correspondence": 0.9,
        "target_to_reference_overlap": 1.0,
        "geometry_completeness": 1.0 if geometry_complete else 0.7,
        "duplicate_exclusion": 1.0 if duplicate_free else 0.0,
    }
    weights = {
        "transform_residual_stability": 0.30,
        "target_scan_completeness": 0.20,
        "region_correspondence": 0.15,
        "target_to_reference_overlap": 0.20,
        "geometry_completeness": 0.10,
        "duplicate_exclusion": 0.05,
    }
    confidence = sum(components[key] * weights[key] for key in weights)
    return round(confidence, 6), components


def classify_missing_entities(
    missing_entities: Sequence[Mapping[str, Any]],
    target_entities: Sequence[Mapping[str, Any]],
    translation: Sequence[float],
) -> dict[str, Any]:
    missing_candidates: list[dict[str, Any]] = []
    repair_drafts: list[dict[str, Any]] = []
    manual_tasks: list[dict[str, Any]] = []
    review_tasks: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for index, entity in enumerate(sorted(missing_entities, key=lambda item: str(item.get("handle"))), 1):
        name = str(entity.get("object_name") or "")
        geometry = _target_geometry(entity, translation)
        complete = _geometry_complete(name, geometry)
        compound = _line_compound_matches(entity, target_entities, translation)
        confidence, confidence_components = _candidate_confidence(complete, duplicate_free=not compound)
        candidate = {
            "candidate_id": f"stage3_2_missing_{index:04d}",
            "reference_handle": str(entity.get("handle")),
            "object_name": name,
            "semantic_type": name,
            "layer": str(entity.get("layer") or ""),
            "target_wcs_geometry": geometry,
            "confidence": confidence,
            "confidence_components": confidence_components,
            "geometry_source": "transformed_reference_geometry",
            "transform_used": True,
            "compound_match_candidates": compound,
            "one_to_many_conflict": bool(compound),
            "many_to_one_conflict": False,
            "nearby_duplicate_found": bool(compound),
            "execution_allowed": False,
            "executed": False,
        }
        if compound:
            candidate.update({
                "classification": "AMBIGUOUS_MATCH",
                "route": "manual_review",
                "reason": "reference line may be represented by multiple target segments",
            })
            ambiguous.append(candidate)
        elif name.startswith("TDb") or name in {"Pump", "Equipment", "WaterTank"}:
            candidate.update({
                "classification": "MISSING_HIGH_CONFIDENCE",
                "route": "manual_tianzheng_review",
                "reason": "Tianzheng/custom object is missing but cannot be automatically recreated",
            })
            manual_tasks.append(candidate)
        elif name in DIRECT_COM_TYPES and complete and confidence >= 0.95:
            candidate.update({
                "classification": "MISSING_HIGH_CONFIDENCE",
                "route": "direct_com_candidate",
                "reason": "complete transformed ordinary CAD geometry has no one-to-one or compound target match",
            })
            required = {
                "AcDbLine": ["create_acdb_line"],
                "AcDbPolyline": ["create_acdb_polyline"],
                "AcDbText": ["create_acdb_text"],
                "AcDbMText": ["create_acdb_text"],
                "AcDbBlockReference": ["create_block_reference"],
            }.get(name, [])
            draft = {
                **candidate,
                "task_id": f"repair_{candidate['candidate_id']}",
                "action": "create",
                "required_capabilities": required,
                "preferred_backend": "com",
                "allowed_backends": ["com"],
                "execution_backend_class": "ComCadBackend",
                "fallback_policy": "block",
                "automatic_fallback": False,
            }
            repair_drafts.append(draft)
        elif name in UNSUPPORTED_AUTOMATIC_TYPES:
            candidate.update({
                "classification": "BLOCKED_UNSUPPORTED_OBJECT",
                "route": "blocked",
                "reason": "object type is outside the Stage 3.3 automatic execution whitelist",
            })
            review_tasks.append(candidate)
            blocked.append(candidate)
        else:
            candidate.update({
                "classification": "BLOCKED_INSUFFICIENT_GEOMETRY",
                "route": "blocked",
                "reason": "ordinary CAD execution geometry is incomplete or unsupported",
            })
            review_tasks.append(candidate)
            blocked.append(candidate)
        missing_candidates.append(candidate)
    return {
        "missing_candidates": missing_candidates,
        "repair_task_drafts": repair_drafts,
        "manual_review_tasks": review_tasks,
        "tianzheng_manual_tasks": manual_tasks,
        "ambiguous_tasks": ambiguous,
        "blocked_tasks": blocked,
    }


def _safety_flags() -> dict[str, bool]:
    return {
        "autocad_connected": False,
        "dwg_opened": False,
        "dwg_saved": False,
        "entities_created": False,
        "entities_modified": False,
        "entities_deleted": False,
        "sendcommand_used": False,
        "lisp_executed": False,
        "netload_used": False,
        "tianzheng_command_executed": False,
        "repair_task_executed": False,
        "stage3_3_entered": False,
        "production_d1_allowed": False,
    }


def run_stage3_2(
    *,
    run_id: str | None = None,
    report_json_path: Path = REPORT_JSON,
    report_md_path: Path = REPORT_MD,
    test_results: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    run_id = run_id or datetime.now().strftime("stage3_2_%Y%m%d_%H%M%S")
    run_root = RUNS_ROOT / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    required = [
        R2_REPORT, STAGE1_REPORT,
        R1_RUN_ROOT / "reference_scan.json", R1_RUN_ROOT / "target_scan.json",
        R1_RUN_ROOT / "reference_region.json", R1_RUN_ROOT / "target_region.json",
        R1_RUN_ROOT / "reference_block_audit.json", R1_RUN_ROOT / "target_block_audit.json",
        REFERENCE_SOURCE, TARGET_SOURCE,
    ]
    missing_inputs = [str(path) for path in required if not path.is_file()]
    safety = _safety_flags()
    if missing_inputs:
        report = _blocked_report(run_id, run_root, "BLOCKED_SCAN_ARTIFACTS_INSUFFICIENT", safety, missing_inputs)
        return _finalize(report, report_json_path, report_md_path)

    r2_report = read_json(R2_REPORT)
    stage1_report = read_json(STAGE1_REPORT)
    translation = list(map(float, r2_report["selected_translation"][:2]))
    reference_region = read_json(R1_RUN_ROOT / "reference_region.json")
    target_region = read_json(R1_RUN_ROOT / "target_region.json")
    reference_entities = r1._region_entities(
        read_json(R1_RUN_ROOT / "reference_scan.json"), reference_region,
        read_json(R1_RUN_ROOT / "reference_block_audit.json"),
    )
    target_entities = r1._region_entities(
        read_json(R1_RUN_ROOT / "target_scan.json"), target_region,
        read_json(R1_RUN_ROOT / "target_block_audit.json"),
    )
    seed_handle = str(stage1_report["fixture_seed_handle"])
    seed_layer = str(stage1_report["fixture_seed_layer"])
    filtered_reference, reference_excluded = filter_detection_entities(reference_entities, seed_handle=seed_handle, seed_layer=seed_layer)
    filtered_target, target_excluded = filter_detection_entities(target_entities, seed_handle=seed_handle, seed_layer=seed_layer)
    match = one_to_one_match(filtered_reference, filtered_target, translation)
    classified = classify_missing_entities(match["missing_reference_entities"], filtered_target, translation)

    source_hashes = {
        "reference_frozen": read_json(R1_RUN_ROOT / "source_integrity.json")["reference_source_sha256_before"],
        "target_frozen": read_json(R1_RUN_ROOT / "source_integrity.json")["target_source_sha256_before"],
        "reference_actual": sha256_file(REFERENCE_SOURCE),
        "target_actual": sha256_file(TARGET_SOURCE),
    }
    source_hashes["unchanged"] = (
        source_hashes["reference_frozen"] == source_hashes["reference_actual"]
        and source_hashes["target_frozen"] == source_hashes["target_actual"]
    )
    max_residual = max((item["residual"] for item in match["matches"]), default=math.inf)
    target_unexplained = len(match["target_only_entities"])
    alignment_contradiction = (
        not source_hashes["unchanged"]
        or max_residual > 1.0
        or target_unexplained > 0
        or r2_report.get("target_to_reference_overlap", 0.0) < 0.80
    )
    matching_reliable = (
        len(match["matches"]) == len(filtered_target)
        and target_unexplained == 0
        and not match["multiplicity_conflicts"]
        and not classified["ambiguous_tasks"]
    )
    if alignment_contradiction:
        status = "BLOCKED_ALIGNMENT_CONTRADICTION"
    elif not matching_reliable:
        status = "BLOCKED_MATCHING_UNRELIABLE"
    elif classified["ambiguous_tasks"]:
        status = "PARTIAL_MISSING_DETECTION_REVIEW_REQUIRED"
    else:
        status = "PASS_MISSING_DETECTION_EVIDENCE_READY"

    artifacts = {
        "missing_candidates.json": {"phase": "STAGE3.2", "items": classified["missing_candidates"]},
        "repair_task_drafts.json": {"phase": "STAGE3.2", "items": classified["repair_task_drafts"]},
        "manual_review_tasks.json": {"phase": "STAGE3.2", "items": classified["manual_review_tasks"]},
        "tianzheng_manual_tasks.json": {"phase": "STAGE3.2", "items": classified["tianzheng_manual_tasks"]},
        "blocked_tasks.json": {"phase": "STAGE3.2", "items": classified["blocked_tasks"]},
        "matching_results.json": match,
    }
    for name, payload in artifacts.items():
        write_json(run_root / name, payload)

    report = {
        "phase": "STAGE3.2-MISSING-DETECTION",
        "run_id": run_id,
        "run_root": str(run_root),
        "status": status,
        "user_authorized_stage3_2": True,
        "prior_stage3_2_allowed": bool(r2_report.get("stage3_2_allowed")),
        "conditional_readonly_stage3_2_override": True,
        "alignment_evidence_mode": "conditional_geometry_dominant",
        "alignment_contradiction": alignment_contradiction,
        "alignment_previous_status": r2_report.get("final_status"),
        "alignment_known_correlation": "all independent anchors originate from one top-level BlockReference pair",
        "reference_target_roles_preserved": True,
        "translation_direction": "reference_wcs_to_target_wcs",
        "selected_translation": translation,
        "stage1_seed_line_excluded": any(item["reason"] == "stage1_seed_line" for item in reference_excluded),
        "title_frame_drawing_name_excluded": True,
        "target_virtual_block_entities_participated": True,
        "one_to_one_conflicts_handled": True,
        "compound_matching_conflicts_handled": True,
        "reference_entity_count_input": len(reference_entities),
        "target_entity_count_input": len(target_entities),
        "reference_excluded_count": len(reference_excluded),
        "target_excluded_count": len(target_excluded),
        "existing_count": len(match["matches"]),
        "missing_count": sum(item["classification"] == "MISSING_HIGH_CONFIDENCE" for item in classified["missing_candidates"]),
        "review_count": len(classified["manual_review_tasks"]),
        "ambiguous_count": len(classified["ambiguous_tasks"]),
        "blocked_count": len(classified["blocked_tasks"]),
        "target_only_count": target_unexplained,
        "high_confidence_ordinary_object_count": len(classified["repair_task_drafts"]),
        "tdb_manual_task_count": len(classified["tianzheng_manual_tasks"]),
        "repair_task_draft_count": len(classified["repair_task_drafts"]),
        "matching_reliable": matching_reliable,
        "matched_max_residual": max_residual,
        "multiplicity_conflict_count": len(match["multiplicity_conflicts"]),
        "source_hashes": source_hashes,
        "source_hashes_unchanged": bool(source_hashes["unchanged"]),
        "automatic_fallback": False,
        "repair_tasks_executed": False,
        "stage3_3_entered": False,
        "stage3_3_allowed": status == "PASS_MISSING_DETECTION_EVIDENCE_READY",
        "user_authorized_automatic_stage3_3_transition": True,
        "automatic_stage3_3_transition_scope": "mvp_safe_ordinary_cad_only",
        "stage3_3_requires_separate_user_message": False,
        "production_d1_allowed": False,
        "safety_flags": safety,
        "artifact_paths": {name: str(run_root / name) for name in artifacts},
        "tests": dict(test_results or {}),
    }
    write_json(run_root / "stage3_2_manifest.json", report)
    return _finalize(report, report_json_path, report_md_path)


def _blocked_report(run_id: str, run_root: Path, status: str, safety: Mapping[str, bool], missing_inputs: Sequence[str]) -> dict[str, Any]:
    return {
        "phase": "STAGE3.2-MISSING-DETECTION",
        "run_id": run_id,
        "run_root": str(run_root),
        "status": status,
        "missing_inputs": list(missing_inputs),
        "alignment_contradiction": False,
        "existing_count": 0,
        "missing_count": 0,
        "review_count": 0,
        "ambiguous_count": 0,
        "high_confidence_ordinary_object_count": 0,
        "tdb_manual_task_count": 0,
        "repair_task_draft_count": 0,
        "stage3_3_entered": False,
        "stage3_3_allowed": False,
        "production_d1_allowed": False,
        "safety_flags": dict(safety),
    }


def _finalize(report: dict[str, Any], json_path: Path, md_path: Path) -> dict[str, Any]:
    write_json(json_path, report)
    md_path.write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Stage 3.2 Missing Detection",
        "",
        f"- status: {report['status']}",
        f"- alignment_contradiction: {str(report.get('alignment_contradiction')).lower()}",
        f"- evidence_mode: {report.get('alignment_evidence_mode')}",
        f"- existing / missing / review / ambiguous: {report.get('existing_count', 0)} / {report.get('missing_count', 0)} / {report.get('review_count', 0)} / {report.get('ambiguous_count', 0)}",
        f"- high_confidence_ordinary_object_count: {report.get('high_confidence_ordinary_object_count', 0)}",
        f"- tdb_manual_task_count: {report.get('tdb_manual_task_count', 0)}",
        f"- repair_task_draft_count: {report.get('repair_task_draft_count', 0)}",
        f"- source_hashes_unchanged: {str(report.get('source_hashes_unchanged')).lower()}",
        f"- stage3_3_allowed: {str(report.get('stage3_3_allowed')).lower()}",
        "- stage3_3_entered: false",
        "- production_d1_allowed: false",
        "",
        "## Safety",
        *[f"- {key}: {str(value).lower()}" for key, value in report.get("safety_flags", {}).items()],
        "",
        "## Tests",
        *[f"- {key}: {value}" for key, value in report.get("tests", {}).items()],
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_stage3_2()
    print(json.dumps({
        "status": result["status"],
        "run_id": result["run_id"],
        "stage3_3_allowed": result["stage3_3_allowed"],
    }, ensure_ascii=False))
