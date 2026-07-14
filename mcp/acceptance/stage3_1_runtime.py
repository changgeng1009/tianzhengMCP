from __future__ import annotations

import hashlib
import json
import math
import shutil
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np


PROG_ID = "AutoCAD.Application.25.1"
PUMP_TEXT_MARKERS = ("泵房", "水泵房", "泵房大样")
TITLE_NOISE_MARKERS = ("图号", "设计", "审核", "校对", "日期", "比例", "学校", "工程名称")
TDB_PREFIX = "TDb"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_source(path: Path) -> dict[str, Any]:
    absolute = path.resolve(strict=True)
    if not absolute.is_file():
        raise ValueError(f"not a file: {absolute}")
    if absolute.suffix.lower() != ".dwg":
        raise ValueError(f"not a DWG: {absolute}")
    if "?" in str(absolute):
        raise ValueError(f"path contains ASCII replacement character: {absolute}")
    before_stat = absolute.stat()
    first_hash = sha256_file(absolute)
    second_hash = sha256_file(absolute)
    after_stat = absolute.stat()
    stable = (
        first_hash == second_hash
        and before_stat.st_size == after_stat.st_size
        and before_stat.st_mtime_ns == after_stat.st_mtime_ns
    )
    if not stable:
        raise RuntimeError(f"source changed during baseline: {absolute}")
    return {
        "exists": True,
        "is_file": True,
        "absolute_path": str(absolute),
        "file_size": before_stat.st_size,
        "modified_time": datetime.fromtimestamp(before_stat.st_mtime).astimezone().isoformat(),
        "modified_time_ns": before_stat.st_mtime_ns,
        "sha256": first_hash,
        "repeat_sha256": second_hash,
        "hash_repeatable": True,
        "baseline_stable": True,
    }


def attach_existing_autocad() -> Any:
    """只附着现有 AutoCAD；禁止 Dispatch 或创建新实例。"""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        active = win32com.client.GetActiveObject(PROG_ID)
        # 仅包装已附着对象以获得 Documents.Open 的动态方法；绝不以 ProgID Dispatch 新实例。
        return win32com.client.Dispatch(active)
    except Exception:
        pythoncom.CoUninitialize()
        raise


def detach_autocad() -> None:
    try:
        import pythoncom

        pythoncom.CoUninitialize()
    except Exception:
        pass


def enumerate_live_documents(acad: Any, source_paths: Iterable[Path]) -> dict[str, Any]:
    normalized_sources = {_norm_path(path) for path in source_paths}
    documents: list[dict[str, Any]] = []
    source_conflicts: list[dict[str, Any]] = []
    for index in range(int(acad.Documents.Count)):
        document = acad.Documents.Item(index)
        record = {
            "name": _read_string(document, "Name"),
            "full_name": _read_string(document, "FullName"),
            "saved": _read_bool(document, "Saved"),
            "read_only": _read_bool(document, "ReadOnly"),
        }
        record["modified"] = None if record["saved"] is None else not record["saved"]
        documents.append(record)
        if record["full_name"] and _norm_path(Path(record["full_name"])) in normalized_sources:
            if record["saved"] is False:
                source_conflicts.append(record)
    return {
        "documents": documents,
        "live_document_diverges_from_disk": bool(source_conflicts),
        "source_conflicts": source_conflicts,
    }


def create_verified_copy(source: Path, destination: Path, expected_hash: str) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _norm_path(source) == _norm_path(destination):
        raise ValueError("source and copy paths must differ")
    shutil.copyfile(source, destination)
    copied_hash = sha256_file(destination)
    result = {
        "source_path": str(source.resolve()),
        "copy_path": str(destination.resolve()),
        "source_size": source.stat().st_size,
        "copy_size": destination.stat().st_size,
        "source_sha256": expected_hash,
        "copy_sha256": copied_hash,
        "hash_matches": copied_hash == expected_hash,
        "size_matches": source.stat().st_size == destination.stat().st_size,
        "paths_differ": _norm_path(source) != _norm_path(destination),
    }
    if not all((result["hash_matches"], result["size_matches"], result["paths_differ"])):
        raise RuntimeError(f"copy verification failed: {destination}")
    return result


def scan_working_copy(acad: Any, path: Path, role: str, forbidden_sources: Iterable[Path]) -> dict[str, Any]:
    if role not in {"reference", "target"}:
        raise ValueError("role must be reference or target")
    forbidden = {_norm_path(item) for item in forbidden_sources}
    resolved = path.resolve(strict=True)
    if _norm_path(resolved) in forbidden:
        raise ValueError("source path cannot be opened")

    hash_before = sha256_file(resolved)
    document = None
    entities: list[dict[str, Any]] = []
    document_errors: list[str] = []
    try:
        returned = _open_document_with_retry(acad, resolved)
        document = _resolve_open_document(acad, resolved, returned)
        modelspace = document.ModelSpace
        paperspace = document.PaperSpace
        for index in range(int(modelspace.Count)):
            entities.append(_scan_entity(modelspace.Item(index), role, "Model"))
        document_info = {
            "full_name": _read_string(document, "FullName"),
            "name": _read_string(document, "Name"),
            "read_only": _read_bool(document, "ReadOnly"),
            "saved": _read_bool(document, "Saved"),
            "modelspace_count": int(modelspace.Count),
            "paperspace_count": int(paperspace.Count),
            "layout_count": int(document.Layouts.Count),
            "layouts": [_layout_record(document.Layouts.Item(i)) for i in range(int(document.Layouts.Count))],
            "insunits": _get_variable(document, "INSUNITS", document_errors),
            "acadver": _get_variable(document, "ACADVER", document_errors),
        }
    finally:
        if document is not None:
            _close_document_without_save(document)

    hash_after = sha256_file(resolved)
    object_counts = Counter(item["object_name"] for item in entities)
    tdb_counts = Counter(item["object_name"] for item in entities if item["object_name"].startswith(TDB_PREFIX))
    return {
        "schema_version": "stage3.1-entity-scan-v1",
        "document_role": role,
        "source_kind": "filesystem_working_copy",
        "document": document_info,
        "entities": entities,
        "entity_count": len(entities),
        "object_type_counts": dict(sorted(object_counts.items())),
        "tdb_object_count": sum(tdb_counts.values()),
        "tdb_object_types": dict(sorted(tdb_counts.items())),
        "read_error_count": sum(bool(item["read_errors"]) for item in entities),
        "document_read_errors": document_errors,
        "copy_sha256_before": hash_before,
        "copy_sha256_after": hash_after,
        "copy_hash_unchanged": hash_before == hash_after,
        "copy_saved": False,
        "closed_with_save": False,
    }


def detect_pump_room_regions(scan: Mapping[str, Any]) -> dict[str, Any]:
    entities = list(scan.get("entities", []))
    role = str(scan.get("document_role"))
    useful = [entity for entity in entities if _entity_center(entity) is not None]
    pump_titles = [
        entity for entity in useful
        if entity.get("attributes", {}).get("text")
        and any(marker in str(entity["attributes"]["text"]) for marker in PUMP_TEXT_MARKERS)
    ]
    candidates: list[dict[str, Any]] = []
    for index, title in enumerate(pump_titles):
        title_center = _entity_center(title)
        assert title_center is not None
        distances = sorted(
            ((math.dist(title_center, center), entity) for entity in useful if (center := _entity_center(entity)) is not None),
            key=lambda item: item[0],
        )
        neighborhood = [entity for _, entity in distances[: min(240, len(distances))]]
        trimmed = _trim_spatial_outliers(neighborhood)
        bbox = _aggregate_bbox(trimmed)
        if bbox is None:
            continue
        candidates.append(_region_record(role, index, bbox, title, trimmed, "pump_title_neighborhood"))

    # 当标题对象不可读时，提供 TDb 密度候选，但不自动宣称泵房。
    if not candidates:
        tdb_entities = [entity for entity in useful if entity["object_name"].startswith(TDB_PREFIX)]
        for index, cluster in enumerate(_spatial_clusters(tdb_entities)[:3]):
            bbox = _aggregate_bbox(cluster)
            if bbox is not None:
                candidates.append(_region_record(role, index, bbox, None, cluster, "tdb_density_cluster"))

    selected = max(candidates, key=lambda item: item["confidence"], default=None)
    return {
        "document_role": role,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "selected_region_id": selected["region_id"] if selected else None,
        "selected_region": selected,
        "pump_room_identified": bool(selected and selected["confidence"] >= 0.65 and selected["text_anchors"]),
        "whole_drawing_extents_used": False,
    }


def align_selected_regions(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_region: Mapping[str, Any] | None,
    target_region: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not reference_region or not target_region:
        return _blocked_alignment("BLOCKED_NO_CORRESPONDING_REGION", "pump-room region missing")
    reference_entities = _entities_in_bbox(reference_scan.get("entities", []), reference_region["bbox"])
    target_entities = _entities_in_bbox(target_scan.get("entities", []), target_region["bbox"])
    anchors = _match_text_anchors(reference_entities, target_entities)
    if len(anchors) < 3 or _points_collinear([item["reference_point"] for item in anchors]):
        return _blocked_alignment(
            "PARTIAL_LOW_CONFIDENCE",
            "fewer than three non-collinear unique text anchors",
            anchors,
        )

    reference_points = np.array([item["reference_point"] for item in anchors], dtype=float)
    target_points = np.array([item["target_point"] for item in anchors], dtype=float)
    region_diag = max(_bbox_diagonal(reference_region["bbox"]), _bbox_diagonal(target_region["bbox"]), 1.0)
    threshold = max(region_diag * 0.005, 1e-6)
    candidates = [
        _evaluate_transform("identity", np.eye(3), reference_points, target_points, threshold),
        _evaluate_transform("translation", _translation_matrix(reference_points, target_points), reference_points, target_points, threshold),
        _evaluate_transform("rigid", _procrustes_matrix(reference_points, target_points, allow_scale=False), reference_points, target_points, threshold),
        _evaluate_transform("similarity", _procrustes_matrix(reference_points, target_points, allow_scale=True), reference_points, target_points, threshold),
    ]
    supported = [item for item in candidates if item["inlier_count"] >= 3]
    if not supported:
        result = _blocked_alignment("PARTIAL_LOW_CONFIDENCE", "no transform has at least three inliers", anchors)
        result["transform_candidates"] = candidates
        return result
    selected = min(supported, key=lambda item: (item["median_residual"], _transform_complexity(item["transform_type"])))
    inlier_indexes = selected["inlier_indexes"]
    inlier_reference = reference_points[inlier_indexes]
    inlier_target = target_points[inlier_indexes]
    if selected["transform_type"] == "translation":
        refined_matrix = _translation_matrix(inlier_reference, inlier_target)
    elif selected["transform_type"] == "rigid":
        refined_matrix = _procrustes_matrix(inlier_reference, inlier_target, allow_scale=False)
    elif selected["transform_type"] == "similarity":
        refined_matrix = _procrustes_matrix(inlier_reference, inlier_target, allow_scale=True)
    else:
        refined_matrix = np.eye(3)
    selected = _evaluate_transform(selected["transform_type"], refined_matrix, reference_points, target_points, threshold)
    normalized = {key: value / region_diag for key, value in selected["residual_statistics"].items()}
    inlier_values = [selected["residuals"][index] for index in selected["inlier_indexes"]]
    inlier_stats = _residual_statistics(inlier_values)
    inlier_normalized = {key: value / region_diag for key, value in inlier_stats.items()}
    confidence = max(
        0.0,
        min(
            1.0,
            (selected["inlier_count"] / len(anchors))
            * (1.0 - min(inlier_normalized["max"] / 0.01, 1.0)),
        ),
    )
    status_map = {
        "identity": "PASS_IDENTITY",
        "translation": "PASS_TRANSLATION",
        "rigid": "PASS_RIGID",
        "similarity": "PASS_SIMILARITY",
    }
    status = status_map[selected["transform_type"]] if confidence >= 0.70 else "PARTIAL_LOW_CONFIDENCE"
    inlier_index_set = set(selected["inlier_indexes"])
    matched = [dict(item, inlier=index in inlier_index_set) for index, item in enumerate(anchors)]
    return {
        "alignment_status": status,
        "alignment_type": selected["transform_type"],
        "anchor_candidates": anchors,
        "matched_anchors": matched,
        "anchor_count": len(anchors),
        "inlier_count": selected["inlier_count"],
        "outlier_count": len(anchors) - selected["inlier_count"],
        "transform_candidates": candidates,
        "selected_transform": selected,
        "residual_statistics": selected["residual_statistics"],
        "normalized_residual_statistics": normalized,
        "inlier_residual_statistics": inlier_stats,
        "inlier_normalized_residual_statistics": inlier_normalized,
        "alignment_confidence": round(confidence, 6),
        "residual_threshold_absolute": threshold,
        "residual_threshold_normalized": threshold / region_diag,
        "region_diagonal": region_diag,
        "selection_reason": "lowest median residual among supported transforms with at least three inliers",
        "frame_only_alignment": False,
    }


def correspondence_summary(
    reference_scan: Mapping[str, Any],
    target_scan: Mapping[str, Any],
    reference_regions: Mapping[str, Any],
    target_regions: Mapping[str, Any],
    alignment: Mapping[str, Any],
) -> dict[str, Any]:
    ref_types = Counter(reference_scan.get("object_type_counts", {}))
    target_types = Counter(target_scan.get("object_type_counts", {}))
    common_types = set(ref_types) & set(target_types)
    type_overlap = len(common_types) / max(len(set(ref_types) | set(target_types)), 1)
    ref_region = reference_regions.get("selected_region")
    target_region = target_regions.get("selected_region")
    both_regions = bool(reference_regions.get("pump_room_identified") and target_regions.get("pump_room_identified"))
    enough_anchors = int(alignment.get("inlier_count", 0)) >= 3
    likelihood = min(1.0, 0.35 * type_overlap + 0.35 * float(both_regions) + 0.30 * min(int(alignment.get("inlier_count", 0)) / 5, 1.0))
    status = "CONFIRMED" if both_regions and enough_anchors and likelihood >= 0.65 else "INSUFFICIENT_EVIDENCE"
    return {
        "same_project_likelihood": round(likelihood, 6),
        "same_detail_region_likelihood": round(likelihood if both_regions else likelihood * 0.5, 6),
        "reference_more_complete": int(reference_scan.get("entity_count", 0)) > int(target_scan.get("entity_count", 0)),
        "target_incomplete_evidence": {
            "reference_entity_count": reference_scan.get("entity_count"),
            "target_entity_count": target_scan.get("entity_count"),
            "reference_selected_region_entity_count": ref_region.get("entity_count") if ref_region else None,
            "target_selected_region_entity_count": target_region.get("entity_count") if target_region else None,
        },
        "correspondence_status": status,
        "correspondence_blockers": [] if status == "CONFIRMED" else ["pump-room regions or non-collinear local anchors are insufficient"],
        "common_object_type_ratio": round(type_overlap, 6),
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _scan_entity(entity: Any, role: str, layout: str) -> dict[str, Any]:
    errors: list[str] = []
    object_name = _safe_property(entity, "ObjectName", errors)
    handle = _safe_property(entity, "Handle", errors)
    record: dict[str, Any] = {
        "document_role": role,
        "handle": str(handle) if handle not in (None, "") else None,
        "object_name": str(object_name) if object_name else "UNKNOWN",
        "entity_name": str(object_name) if object_name else "UNKNOWN",
        "layer": _safe_property(entity, "Layer", errors),
        "color": _safe_property(entity, "Color", errors),
        "linetype": _safe_property(entity, "Linetype", errors),
        "visibility": _safe_property(entity, "Visible", errors),
        "owner_layout": layout,
        "bbox": _safe_bbox(entity, errors),
        "geometry": {},
        "attributes": {},
        "read_errors": errors,
        "coordinate_space": "cad_wcs",
    }
    geometry_map = {
        "StartPoint": "start_point", "EndPoint": "end_point", "Center": "center",
        "InsertionPoint": "insertion_point", "Coordinates": "vertices", "Radius": "radius",
        "Rotation": "rotation", "ScaleFactor": "scale", "Length": "length", "Area": "area",
    }
    for source, target in geometry_map.items():
        value = _safe_property(entity, source, errors, record_missing=False)
        if value is not None:
            record["geometry"][target] = _json_value(value)
    for source, target in {
        "TextString": "text", "Contents": "mtext_contents", "Height": "height",
        "EffectiveName": "effective_name", "Name": "name", "DNDiameter": "dn_diameter",
        "SysType": "sys_type", "SElevation": "start_elevation", "EElevation": "end_elevation",
    }.items():
        value = _safe_property(entity, source, errors, record_missing=False)
        if value is not None:
            record["attributes"][target] = _json_value(value)
    if record["handle"] is None:
        errors.append("Handle: unavailable")
    return record


def _safe_bbox(entity: Any, errors: list[str]) -> list[list[float]] | None:
    try:
        raw = entity.GetBoundingBox()
        if isinstance(raw, tuple) and len(raw) == 2:
            minimum, maximum = raw
        else:
            errors.append(f"GetBoundingBox: unexpected result {type(raw).__name__}")
            return None
        minimum = [float(value) for value in minimum]
        maximum = [float(value) for value in maximum]
        if len(minimum) < 2 or len(maximum) < 2 or maximum[0] < minimum[0] or maximum[1] < minimum[1]:
            errors.append("GetBoundingBox: invalid extents")
            return None
        return [minimum[:3], maximum[:3]]
    except Exception as exc:
        errors.append(f"GetBoundingBox: {type(exc).__name__}: {exc}")
        return None


def _safe_property(entity: Any, name: str, errors: list[str], record_missing: bool = True) -> Any:
    try:
        return getattr(entity, name)
    except Exception as exc:
        if record_missing:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
        return None


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    try:
        return float(value)
    except Exception:
        return str(value)


def _resolve_open_document(acad: Any, expected: Path, returned: Any) -> Any:
    # AutoCAD 2026 可能从 Open() 返回 <COMObject Open> 方法代理；始终按 FullName
    # 从 Documents 集合取真实文档对象，避免对方法代理调用 Close。
    last_error: Exception | None = None
    for _attempt in range(30):
        try:
            documents = acad.Documents
            for index in range(int(documents.Count)):
                candidate = documents.Item(index)
                try:
                    if _norm_path(Path(str(candidate.FullName))) == _norm_path(expected):
                        return candidate
                except Exception:
                    continue
        except Exception as exc:
            last_error = exc
        time.sleep(0.2)
    if last_error is not None:
        raise RuntimeError(f"opened document lookup failed: {type(last_error).__name__}: {last_error}")
    raise RuntimeError(f"opened document could not be resolved: {expected}")


def _open_document_with_retry(acad: Any, path: Path) -> Any:
    last_error: Exception | None = None
    for _attempt in range(30):
        try:
            return acad.Documents.Open(str(path), True)
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    assert last_error is not None
    raise RuntimeError(f"read-only copy open failed: {type(last_error).__name__}: {last_error}")


def _close_document_without_save(document: Any) -> None:
    last_error: Exception | None = None
    for _attempt in range(30):
        try:
            document.Close(False)
            time.sleep(0.3)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    assert last_error is not None
    raise RuntimeError(f"Close(False) failed: {type(last_error).__name__}: {last_error}")


def _layout_record(layout: Any) -> dict[str, Any]:
    return {
        "name": _read_string(layout, "Name"),
        "model_type": _read_bool(layout, "ModelType"),
        "tab_order": _read_int(layout, "TabOrder"),
    }


def _get_variable(document: Any, name: str, errors: list[str]) -> Any:
    try:
        return _json_value(document.GetVariable(name))
    except Exception as exc:
        errors.append(f"GetVariable({name}): {type(exc).__name__}: {exc}")
        return None


def _read_string(obj: Any, name: str) -> str | None:
    try:
        value = getattr(obj, name)
        return str(value) if value not in (None, "") else None
    except Exception:
        return None


def _read_bool(obj: Any, name: str) -> bool | None:
    try:
        return bool(getattr(obj, name))
    except Exception:
        return None


def _read_int(obj: Any, name: str) -> int | None:
    try:
        return int(getattr(obj, name))
    except Exception:
        return None


def _norm_path(path: Path) -> str:
    return str(path.resolve()).casefold()


def _entity_center(entity: Mapping[str, Any]) -> list[float] | None:
    bbox = entity.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 2 and len(bbox[0]) >= 2 and len(bbox[1]) >= 2:
        return [(float(bbox[0][0]) + float(bbox[1][0])) / 2, (float(bbox[0][1]) + float(bbox[1][1])) / 2]
    geometry = entity.get("geometry", {})
    for key in ("insertion_point", "center", "start_point", "end_point"):
        point = geometry.get(key)
        if isinstance(point, list) and len(point) >= 2:
            return [float(point[0]), float(point[1])]
    return None


def _aggregate_bbox(entities: Iterable[Mapping[str, Any]]) -> list[float] | None:
    points = [_entity_center(entity) for entity in entities]
    points = [point for point in points if point is not None]
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _trim_spatial_outliers(entities: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if len(entities) < 10:
        return entities
    points = [(_entity_center(entity), entity) for entity in entities]
    valid = [(point, entity) for point, entity in points if point is not None]
    xs = np.array([point[0] for point, _ in valid])
    ys = np.array([point[1] for point, _ in valid])
    x1, x2 = np.quantile(xs, [0.02, 0.98])
    y1, y2 = np.quantile(ys, [0.02, 0.98])
    return [entity for point, entity in valid if x1 <= point[0] <= x2 and y1 <= point[1] <= y2]


def _spatial_clusters(entities: list[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    if not entities:
        return []
    points = [_entity_center(entity) for entity in entities]
    valid = [(point, entity) for point, entity in zip(points, entities) if point is not None]
    if len(valid) < 2:
        return [[entity for _, entity in valid]]
    nearest = []
    for index, (point, _) in enumerate(valid):
        nearest.append(min(math.dist(point, other) for other_index, (other, _) in enumerate(valid) if other_index != index))
    threshold = max(statistics.median(nearest) * 8, 1e-6)
    parent = list(range(len(valid)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(valid)):
        for right in range(left + 1, len(valid)):
            if math.dist(valid[left][0], valid[right][0]) <= threshold:
                union(left, right)
    groups: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for index, (_, entity) in enumerate(valid):
        groups[find(index)].append(entity)
    return sorted(groups.values(), key=len, reverse=True)


def _region_record(
    role: str,
    index: int,
    bbox: list[float],
    title: Mapping[str, Any] | None,
    entities: list[Mapping[str, Any]],
    method: str,
) -> dict[str, Any]:
    tdb_count = sum(str(entity.get("object_name", "")).startswith(TDB_PREFIX) for entity in entities)
    text_anchors = []
    if title:
        title_point = _entity_center(title)
        if title_point is not None:
            bbox = [
                min(bbox[0], title_point[0]), min(bbox[1], title_point[1]),
                max(bbox[2], title_point[0]), max(bbox[3], title_point[1]),
            ]
        text_anchors.append({
            "handle": title.get("handle"),
            "text": title.get("attributes", {}).get("text"),
            "point": title_point,
        })
    ordinary_count = len(entities) - tdb_count
    area = max((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 1e-9)
    confidence = min(0.98, 0.55 + (0.25 if text_anchors else 0.0) + min(tdb_count / 100, 0.15))
    return {
        "region_id": f"{role}_pump_candidate_{index + 1:04d}",
        "bbox": bbox,
        "evidence": [method, "pump_title" if text_anchors else "tdb_density"],
        "text_anchors": text_anchors,
        "entity_density": len(entities) / area,
        "tdb_object_count": tdb_count,
        "ordinary_entity_count": ordinary_count,
        "entity_count": len(entities),
        "excluded_reason": None,
        "confidence": round(confidence, 6),
        "title_frame_noise_excluded": True,
    }


def _entities_in_bbox(entities: Iterable[Mapping[str, Any]], bbox: list[float]) -> list[Mapping[str, Any]]:
    result = []
    for entity in entities:
        center = _entity_center(entity)
        if center and bbox[0] <= center[0] <= bbox[2] and bbox[1] <= center[1] <= bbox[3]:
            result.append(entity)
    return result


def _normalize_text(value: Any) -> str:
    return "".join(str(value or "").split()).casefold()


def _match_text_anchors(reference_entities: list[Mapping[str, Any]], target_entities: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    reference_by_text: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    target_by_text: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for entity in reference_entities:
        text = _normalize_text(entity.get("attributes", {}).get("text") or entity.get("attributes", {}).get("mtext_contents"))
        if len(text) >= 2 and not any(marker in text for marker in TITLE_NOISE_MARKERS):
            reference_by_text[text].append(entity)
    for entity in target_entities:
        text = _normalize_text(entity.get("attributes", {}).get("text") or entity.get("attributes", {}).get("mtext_contents"))
        if len(text) >= 2 and not any(marker in text for marker in TITLE_NOISE_MARKERS):
            target_by_text[text].append(entity)
    anchors = []
    for text in sorted(set(reference_by_text) & set(target_by_text)):
        if len(reference_by_text[text]) != 1 or len(target_by_text[text]) != 1:
            continue
        reference = reference_by_text[text][0]
        target = target_by_text[text][0]
        reference_point = _entity_center(reference)
        target_point = _entity_center(target)
        if reference_point is None or target_point is None:
            continue
        anchors.append({
            "anchor_id": f"text_{len(anchors) + 1:04d}",
            "anchor_type": "unique_exact_text",
            "reference_point": reference_point,
            "target_point": target_point,
            "reference_handle": reference.get("handle"),
            "target_handle": target.get("handle"),
            "confidence": 0.95,
            "text_fingerprint_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
    return anchors


def _points_collinear(points: list[list[float]]) -> bool:
    if len(points) < 3:
        return True
    array = np.array(points, dtype=float)
    centered = array - array.mean(axis=0)
    return np.linalg.matrix_rank(centered, tol=1e-9) < 2


def _translation_matrix(reference: np.ndarray, target: np.ndarray) -> np.ndarray:
    delta = np.median(target - reference, axis=0)
    matrix = np.eye(3)
    matrix[:2, 2] = delta
    return matrix


def _procrustes_matrix(reference: np.ndarray, target: np.ndarray, allow_scale: bool) -> np.ndarray:
    ref_center = reference.mean(axis=0)
    target_center = target.mean(axis=0)
    ref_zero = reference - ref_center
    target_zero = target - target_center
    covariance = ref_zero.T @ target_zero
    u, singular, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    scale = 1.0
    if allow_scale:
        denominator = float(np.sum(ref_zero ** 2))
        scale = float(np.sum(singular) / denominator) if denominator else 1.0
    translation = target_center - scale * (rotation @ ref_center)
    matrix = np.eye(3)
    matrix[:2, :2] = scale * rotation
    matrix[:2, 2] = translation
    return matrix


def _evaluate_transform(
    transform_type: str,
    matrix: np.ndarray,
    reference: np.ndarray,
    target: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    homogeneous = np.column_stack([reference, np.ones(len(reference))])
    predicted = (matrix @ homogeneous.T).T[:, :2]
    residuals = np.linalg.norm(predicted - target, axis=1)
    inliers = [index for index, value in enumerate(residuals) if value <= threshold]
    values = [float(value) for value in residuals]
    stats = _residual_statistics(values)
    return {
        "transform_type": transform_type,
        "matrix": [[float(value) for value in row] for row in matrix],
        "residuals": values,
        "residual_statistics": stats,
        "median_residual": stats["median"],
        "inlier_indexes": inliers,
        "inlier_count": len(inliers),
        "outlier_count": len(values) - len(inliers),
        "scale": math.hypot(float(matrix[0, 0]), float(matrix[1, 0])),
        "rotation_radians": math.atan2(float(matrix[1, 0]), float(matrix[0, 0])),
        "translation": [float(matrix[0, 2]), float(matrix[1, 2])],
    }


def _residual_statistics(values: list[float]) -> dict[str, float]:
    array = np.array(values, dtype=float)
    if not len(array):
        return {"median": math.inf, "mean": math.inf, "max": math.inf, "p95": math.inf}
    return {
        "median": float(np.median(array)),
        "mean": float(np.mean(array)),
        "max": float(np.max(array)),
        "p95": float(np.percentile(array, 95)),
    }


def _transform_complexity(name: str) -> int:
    return {"identity": 0, "translation": 1, "rigid": 2, "similarity": 3}.get(name, 99)


def _bbox_diagonal(bbox: list[float]) -> float:
    return math.hypot(float(bbox[2]) - float(bbox[0]), float(bbox[3]) - float(bbox[1]))


def _blocked_alignment(status: str, reason: str, anchors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    anchors = anchors or []
    return {
        "alignment_status": status,
        "alignment_type": "NOT_SELECTED",
        "anchor_candidates": anchors,
        "matched_anchors": [],
        "anchor_count": len(anchors),
        "inlier_count": 0,
        "outlier_count": len(anchors),
        "transform_candidates": [],
        "selected_transform": None,
        "residual_statistics": None,
        "normalized_residual_statistics": None,
        "alignment_confidence": 0.0,
        "selection_reason": reason,
        "frame_only_alignment": False,
    }
