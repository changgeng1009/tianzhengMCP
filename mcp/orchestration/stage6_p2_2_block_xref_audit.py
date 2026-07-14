"""Stage 6-P2.2：三个失败区域的块、Xref 与隐藏建筑几何只读审计。"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np


MAX_NESTING_DEPTH = 8
PAIR_SPECS = (
    ("basement", "reference_region_0000", "target_region_0001", "地下一层"),
    ("first_floor", "reference_region_0001", "target_region_0000", "一层"),
    ("floors_6_16", "reference_region_0002", "target_region_0002", "六至十六层"),
)
LINE_NAMES = {"AcDbLine"}
POLYLINE_NAMES = {"AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline"}
ARC_NAMES = {"AcDbArc"}
CIRCLE_NAMES = {"AcDbCircle"}
BLOCK_NAMES = {"AcDbBlockReference"}
ALLOWED_TRANSFORMS = {"translation_only", "similarity_transform"}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def block_matrix(insertion: Iterable[float], rotation: float, scale_x: float,
                 scale_y: float, scale_z: float = 1.0) -> np.ndarray:
    """构造二维块实例矩阵；保留非统一比例只读展开能力。"""
    x, y = list(insertion)[:2]
    c, s = math.cos(float(rotation)), math.sin(float(rotation))
    return np.asarray([
        [c * float(scale_x), -s * float(scale_y), float(x)],
        [s * float(scale_x), c * float(scale_y), float(y)],
        [0.0, 0.0, 1.0],
    ])


def transform_point(matrix: np.ndarray, point: Iterable[float]) -> list[float]:
    x, y = list(point)[:2]
    result = matrix @ np.asarray([float(x), float(y), 1.0])
    return [float(result[0]), float(result[1])]


def compose_nested(parent: np.ndarray, child: np.ndarray) -> np.ndarray:
    return parent @ child


def _inside(bbox: list[float], point: Iterable[float], padding: float = 1.0) -> bool:
    x, y = list(point)[:2]
    return bbox[0] - padding <= x <= bbox[2] + padding and bbox[1] - padding <= y <= bbox[3] + padding


def _bbox(points: list[list[float]]) -> list[float] | None:
    if not points:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def bbox_audit(region_bbox: list[float], geometry_bbox: list[float] | None) -> dict[str, Any]:
    if not geometry_bbox:
        return {"building_bbox_inside_region": False, "intersection_ratio": 0.0, "coverage_ratio": 0.0}
    rx1, ry1, rx2, ry2 = region_bbox
    gx1, gy1, gx2, gy2 = geometry_bbox
    intersection = max(0.0, min(rx2, gx2) - max(rx1, gx1)) * max(0.0, min(ry2, gy2) - max(ry1, gy1))
    ga = max((gx2 - gx1) * (gy2 - gy1), 1e-9)
    ra = max((rx2 - rx1) * (ry2 - ry1), 1e-9)
    return {
        "building_bbox_inside_region": gx1 >= rx1 - 1 and gy1 >= ry1 - 1 and gx2 <= rx2 + 1 and gy2 <= ry2 + 1,
        "intersection_ratio": round(intersection / ga, 6),
        "coverage_ratio": round(intersection / ra, 6),
    }


def normalize_xref_status(is_xref: bool, status: Any, path: str | None) -> str:
    if not is_xref:
        return "NOT_XREF"
    text = str(status or "").upper()
    if "UNLOAD" in text or text in {"1", "UNLOADED"}:
        return "XREF_UNLOADED"
    if "UNRESOL" in text or text in {"2", "UNRESOLVED"}:
        return "XREF_UNRESOLVED"
    if path and not Path(path).exists():
        return "XREF_PATH_MISSING"
    return "LOADED"


def _safe_get(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _object_name(obj: Any) -> str:
    return str(_safe_get(obj, "ObjectName", ""))


def _coords(value: Any, stride: int = 2) -> list[list[float]]:
    raw = list(value or [])
    return [[float(raw[i]), float(raw[i + 1])] for i in range(0, len(raw) - 1, stride)]


def _light_geometry(entity: Any, matrix: np.ndarray, source: str, layer_override: str | None = None) -> list[dict[str, Any]]:
    name = _object_name(entity)
    layer = str(layer_override or _safe_get(entity, "Layer", ""))
    handle = str(_safe_get(entity, "Handle", ""))
    records: list[dict[str, Any]] = []
    if name in LINE_NAMES:
        start, end = _safe_get(entity, "StartPoint"), _safe_get(entity, "EndPoint")
        if start is not None and end is not None:
            records.append({"type": "line", "object_name": name, "layer": layer, "handle": handle,
                            "points": [transform_point(matrix, start), transform_point(matrix, end)], "source": source})
    elif name in POLYLINE_NAMES:
        raw = _safe_get(entity, "Coordinates", [])
        stride = 3 if name == "AcDb3dPolyline" else 2
        points = [transform_point(matrix, p) for p in _coords(raw, stride)]
        if len(points) >= 2:
            records.append({"type": "polyline", "object_name": name, "layer": layer, "handle": handle,
                            "points": points, "source": source})
    elif name in ARC_NAMES | CIRCLE_NAMES:
        center = _safe_get(entity, "Center")
        radius = _safe_get(entity, "Radius")
        if center is not None and radius is not None:
            c = transform_point(matrix, center)
            sx = math.hypot(matrix[0, 0], matrix[1, 0])
            sy = math.hypot(matrix[0, 1], matrix[1, 1])
            records.append({"type": "circle" if name in CIRCLE_NAMES else "arc", "object_name": name,
                            "layer": layer, "handle": handle, "center": c,
                            "radius_x": float(radius) * sx, "radius_y": float(radius) * sy,
                            "source": source})
    return records


def _block_metadata(entity: Any, matrix: np.ndarray, depth: int, definition: Any | None) -> dict[str, Any]:
    name = str(_safe_get(entity, "Name", ""))
    effective = str(_safe_get(entity, "EffectiveName", name))
    insertion = list(_safe_get(entity, "InsertionPoint", (0.0, 0.0, 0.0)))
    is_xref = bool(_safe_get(definition, "IsXRef", False)) if definition is not None else False
    xref_path = str(_safe_get(definition, "Path", "") or "") if definition is not None else ""
    status = _safe_get(entity, "XRefStatus", _safe_get(definition, "XRefStatus", ""))
    world_insert = transform_point(matrix, insertion)
    return {
        "handle": str(_safe_get(entity, "Handle", "")), "name": name, "effective_name": effective,
        "anonymous_name": name if name.startswith("*") else None,
        "insertion_point": insertion, "world_insertion_point": world_insert,
        "rotation": float(_safe_get(entity, "Rotation", 0.0) or 0.0),
        "scale_x": float(_safe_get(entity, "XScaleFactor", 1.0) or 1.0),
        "scale_y": float(_safe_get(entity, "YScaleFactor", 1.0) or 1.0),
        "scale_z": float(_safe_get(entity, "ZScaleFactor", 1.0) or 1.0),
        "normal": list(_safe_get(entity, "Normal", (0.0, 0.0, 1.0))),
        "is_dynamic": bool(_safe_get(entity, "IsDynamicBlock", False)), "is_xref": is_xref,
        "is_nested": depth > 0, "nesting_depth": depth,
        "block_definition_entity_count": int(_safe_get(definition, "Count", 0) or 0) if definition is not None else 0,
        "world_bbox": None, "inside_region_bbox": None,
        "layer": str(_safe_get(entity, "Layer", "")), "visibility": bool(_safe_get(entity, "Visible", True)),
        "xref_status": normalize_xref_status(is_xref, status, xref_path), "xref_path": xref_path or None,
        "xref_type": "overlay_or_attachment_unknown_readonly" if is_xref else None,
    }


def expand_block_instance(
    block_ref: Any,
    document: Any,
    parent_matrix: np.ndarray | None = None,
    depth: int = 0,
    path_stack: tuple[str, ...] = (),
    max_depth: int = MAX_NESTING_DEPTH,
) -> dict[str, Any]:
    """只读递归展开块定义；不调用 AutoCAD Explode。"""
    parent = np.eye(3) if parent_matrix is None else parent_matrix
    name = str(_safe_get(block_ref, "Name", ""))
    insertion = _safe_get(block_ref, "InsertionPoint", (0.0, 0.0, 0.0))
    local = block_matrix(insertion, _safe_get(block_ref, "Rotation", 0.0) or 0.0,
                         _safe_get(block_ref, "XScaleFactor", 1.0) or 1.0,
                         _safe_get(block_ref, "YScaleFactor", 1.0) or 1.0,
                         _safe_get(block_ref, "ZScaleFactor", 1.0) or 1.0)
    cumulative = compose_nested(parent, local)
    try:
        definition = document.Blocks.Item(name)
    except Exception:
        definition = None
    metadata = _block_metadata(block_ref, parent, depth, definition)
    result = {"instance": metadata, "geometry": [], "children": [], "truncated": [], "max_depth": depth}
    if depth >= max_depth:
        result["truncated"].append({"name": name, "reason": "MAX_DEPTH_REACHED", "depth": depth})
        return result
    if name in path_stack:
        result["truncated"].append({"name": name, "reason": "RECURSION_CYCLE", "depth": depth})
        return result
    if definition is None:
        result["truncated"].append({"name": name, "reason": "BLOCK_DEFINITION_UNAVAILABLE", "depth": depth})
        return result
    for index in range(int(_safe_get(definition, "Count", 0) or 0)):
        try:
            child = definition.Item(index)
        except Exception:
            continue
        child_name = _object_name(child)
        if child_name in BLOCK_NAMES:
            nested = expand_block_instance(child, document, cumulative, depth + 1, (*path_stack, name), max_depth)
            result["children"].append(nested["instance"])
            result["geometry"].extend(nested["geometry"])
            result["children"].extend(nested["children"])
            result["truncated"].extend(nested["truncated"])
            result["max_depth"] = max(result["max_depth"], nested["max_depth"])
        else:
            source = "xref" if metadata["is_xref"] else "block"
            result["geometry"].extend(_light_geometry(child, cumulative, source))
    points = [p for g in result["geometry"] for p in g.get("points", [])]
    metadata["world_bbox"] = _bbox(points)
    return result


def _layer_statistics(geometry: list[dict[str, Any]], region_bbox: list[float]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in geometry:
        grouped[str(item.get("layer") or "")].append(item)
    result = []
    for layer, items in grouped.items():
        counts = Counter(item["type"] for item in items)
        points = [p for item in items for p in item.get("points", [])]
        lengths, angles = [], Counter()
        for item in items:
            pts = item.get("points", [])
            for a, b in zip(pts, pts[1:]):
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = math.hypot(dx, dy)
                if length > 1e-6:
                    lengths.append(length)
                    angles[str(int(round(math.degrees(math.atan2(dy, dx)) % 180 / 15) * 15) % 180)] += 1
        bb = _bbox(points)
        audit = bbox_audit(region_bbox, bb)
        result.append({
            "layer_name": layer, "line_count": counts["line"], "polyline_count": counts["polyline"],
            "arc_count": counts["arc"], "circle_count": counts["circle"], "bbox": bb,
            "total_length": round(sum(lengths), 3), "orientation_histogram": dict(angles),
            "spatial_coverage": audit["coverage_ratio"],
            "building_candidate_score": round(min(1.0, (counts["line"] + counts["polyline"] * 2) / 100) * min(1.0, audit["coverage_ratio"] / 0.12), 4),
        })
    return sorted(result, key=lambda item: (-item["building_candidate_score"], -item["total_length"]))


def local_fingerprints(geometry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """生成平移无关的线段局部指纹。"""
    segments = []
    endpoint_degree: Counter[tuple[int, int]] = Counter()
    for item in geometry:
        if item["type"] not in {"line", "polyline"}:
            continue
        for a, b in zip(item["points"], item["points"][1:]):
            length = math.dist(a, b)
            if length < 5.0:
                continue
            angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
            qa, qb = (round(a[0] / 5), round(a[1] / 5)), (round(b[0] / 5), round(b[1] / 5))
            endpoint_degree[qa] += 1; endpoint_degree[qb] += 1
            segments.append((item, a, b, length, angle, qa, qb))
    output = []
    for index, (item, a, b, length, angle, qa, qb) in enumerate(segments):
        key = f"{item['type']}|L{round(length / 5)}|A{round(angle / 2)}|D{min(endpoint_degree[qa], endpoint_degree[qb])}-{max(endpoint_degree[qa], endpoint_degree[qb])}"
        output.append({
            "fingerprint_id": f"fp_{index:06d}", "fingerprint": key, "type": item["type"],
            "layer": item.get("layer"), "length": round(length, 4), "angle_deg": round(angle, 4),
            "endpoint_degree": [endpoint_degree[qa], endpoint_degree[qb]],
            "midpoint": [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], "source": item.get("source"),
        })
    return output


def match_unique_fingerprints(reference: list[dict[str, Any]], target: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ref_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tgt_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in reference: ref_groups[item["fingerprint"]].append(item)
    for item in target: tgt_groups[item["fingerprint"]].append(item)
    matches = []
    for key in sorted(set(ref_groups) & set(tgt_groups)):
        if len(ref_groups[key]) == len(tgt_groups[key]) == 1:
            r, t = ref_groups[key][0], tgt_groups[key][0]
            matches.append({"fingerprint": key, "reference": r, "target": t,
                            "reference_point": r["midpoint"], "target_point": t["midpoint"]})
    return matches


def _fit_similarity(ref: np.ndarray, tgt: np.ndarray) -> np.ndarray:
    rc, tc = ref.mean(axis=0), tgt.mean(axis=0)
    r0, t0 = ref - rc, tgt - tc
    u, singular, vt = np.linalg.svd(r0.T @ t0)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    scale = float(singular.sum() / max((r0 * r0).sum(), 1e-12))
    matrix = np.eye(3); matrix[:2, :2] = scale * rotation; matrix[:2, 2] = tc - scale * rotation @ rc
    return matrix


def fit_allowed_transform(matches: list[dict[str, Any]], threshold: float = 20.0) -> dict[str, Any]:
    if len(matches) < 3:
        return {"status": "ALIGNMENT_STILL_BLOCKED", "blocking_reason": "少于 3 个唯一指纹匹配", "anchor_pair_count": len(matches)}
    ref = np.asarray([m["reference_point"] for m in matches], dtype=float)
    tgt = np.asarray([m["target_point"] for m in matches], dtype=float)
    if np.linalg.matrix_rank(ref - ref.mean(axis=0)) < 2:
        return {"status": "ALIGNMENT_STILL_BLOCKED", "blocking_reason": "唯一指纹锚点共线", "anchor_pair_count": len(matches)}
    candidates = []
    delta = np.median(tgt - ref, axis=0)
    translation = np.asarray([[1.0, 0.0, delta[0]], [0.0, 1.0, delta[1]], [0.0, 0.0, 1.0]])
    for model, matrix in (("translation_only", translation), ("similarity_transform", _fit_similarity(ref, tgt))):
        predicted = np.c_[ref, np.ones(len(ref))] @ matrix.T
        errors = np.linalg.norm(predicted[:, :2] - tgt, axis=1)
        inliers = errors <= threshold
        inlier_errors = errors[inliers]
        scale = math.hypot(matrix[0, 0], matrix[1, 0]); rotation = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))
        candidates.append({"model_type": model, "matrix_3x3": matrix.tolist(), "scale": scale, "rotation_deg": rotation,
                           "translate_x": float(matrix[0, 2]), "translate_y": float(matrix[1, 2]),
                           "inlier_count": int(inliers.sum()), "inlier_ratio": float(inliers.mean()),
                           "rms_error": float(np.sqrt(np.mean(inlier_errors ** 2))) if len(inlier_errors) else None,
                           "median_error": float(np.median(inlier_errors)) if len(inlier_errors) else None,
                           "max_error": float(inlier_errors.max()) if len(inlier_errors) else None,
                           "all_candidate_rms_error": float(np.sqrt(np.mean(errors ** 2))),
                           "all_candidate_median_error": float(np.median(errors)),
                           "all_candidate_max_error": float(errors.max())})
    valid = [c for c in candidates if 0.98 <= c["scale"] <= 1.02 and abs(c["rotation_deg"]) <= 1.0 and c["inlier_count"] >= 3]
    if not valid:
        return {"status": "ALIGNMENT_STILL_BLOCKED", "blocking_reason": "translation/similarity 均未满足合理尺度、旋转和 inlier 门", "anchor_pair_count": len(matches), "candidates": candidates}
    best = sorted(valid, key=lambda c: (0 if c["model_type"] == "translation_only" else 1, -c["inlier_count"], c["rms_error"]))[0]
    confidence = min(0.99, best["inlier_count"] / max(len(matches), 1))
    return {**best, "status": "ALIGNMENT_VERIFIED" if confidence >= 0.9 and (best["rms_error"] or 0.0) <= threshold else "ALIGNMENT_STILL_BLOCKED",
            "confidence": round(confidence, 4), "anchor_pair_count": len(matches), "allowed_models_only": True,
            "affine_used": False, "non_uniform_scale_used": False}


def audit_region_selection(document: Any, selection: Any, region: Mapping[str, Any], role: str) -> dict[str, Any]:
    from mcp.acceptance.stage5_2_native_clone_poc import _retry
    top_counts = Counter(); geometry = []; blocks = []; xrefs = []; truncated = []
    count = int(_retry(lambda: selection.Count, f"{role} selection count", attempts=20, delay=0.2))
    for index in range(count):
        entity = _retry(lambda value=index: selection.Item(value), f"{role} selected item {index}", attempts=30, delay=0.2)
        name = _object_name(entity); top_counts[name] += 1
        if name in BLOCK_NAMES:
            expanded = expand_block_instance(entity, document)
            instance = expanded["instance"]
            instance_records = [instance, *expanded["children"]]
            for record in instance_records:
                world_bbox = record.get("world_bbox")
                record["inside_region_bbox"] = bbox_audit(list(region["frame_bbox"]), world_bbox)["building_bbox_inside_region"] if world_bbox else None
            blocks.extend(instance_records); geometry.extend(expanded["geometry"]); truncated.extend(expanded["truncated"])
            if instance["is_xref"]: xrefs.append(instance)
        else:
            geometry.extend(_light_geometry(entity, np.eye(3), "top_level"))
    points = [p for item in geometry for p in item.get("points", [])]
    bb = _bbox(points); bb_check = bbox_audit(list(region["frame_bbox"]), bb)
    layers = _layer_statistics(geometry, list(region["frame_bbox"]))
    expanded = [g for g in geometry if g["source"] in {"block", "xref"}]
    return {
        "region_id": region["region_id"], "role": role, "region_bbox": region["frame_bbox"],
        "top_level_entity_count": count, "top_level_line_count": top_counts["AcDbLine"],
        "top_level_polyline_count": sum(top_counts[n] for n in POLYLINE_NAMES),
        "top_level_arc_count": top_counts["AcDbArc"], "top_level_circle_count": top_counts["AcDbCircle"],
        "block_reference_count": top_counts["AcDbBlockReference"],
        "dynamic_block_count": sum(1 for b in blocks if b["is_dynamic"]),
        "anonymous_block_count": sum(1 for b in blocks if b["anonymous_name"]),
        "nested_block_count": sum(1 for b in blocks if b["is_nested"]),
        "max_nesting_depth": max([b["nesting_depth"] for b in blocks] or [0]),
        "xref_count": len(xrefs), "xref_names": [b["name"] for b in xrefs],
        "xref_paths": [b["xref_path"] for b in xrefs], "xref_statuses": [b["xref_status"] for b in xrefs],
        "block_definition_line_count": sum(1 for g in expanded if g["type"] == "line"),
        "block_definition_polyline_count": sum(1 for g in expanded if g["type"] == "polyline"),
        "expanded_line_count": sum(1 for g in expanded if g["type"] == "line"),
        "expanded_polyline_count": sum(1 for g in expanded if g["type"] == "polyline"),
        "expanded_architecture_corner_count": sum(len(g.get("points", [])) for g in expanded if g["type"] in {"line", "polyline"}),
        "combined_building_bbox": bb, **bb_check,
        "building_layer_candidates": layers[:10], "geometry": geometry,
        "block_instances": blocks, "xref_instances": xrefs, "truncated_blocks": truncated,
    }


def scan_document_regions(acad: Any, path: Path, role: str, regions: list[dict[str, Any]]) -> dict[str, Any]:
    from mcp.acceptance.stage3_1_runtime import _close_document_without_save, _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage5_2_native_clone_poc import _retry
    before = _sha256(path); document = None; audits = []
    try:
        returned = _open_document_with_retry(acad, path); document = _resolve_open_document(acad, path, returned)
        modelspace = _retry(lambda: document.ModelSpace, f"{role} ModelSpace", attempts=20, delay=0.2)
        grouped: dict[str, list[Any]] = {str(region["region_id"]): [] for region in regions}
        count = int(_retry(lambda: modelspace.Count, f"{role} ModelSpace.Count", attempts=20, delay=0.2))
        for index in range(count):
            entity = _retry(lambda value=index: modelspace.Item(value), f"{role} ModelSpace.Item {index}", attempts=30, delay=0.2)
            try:
                lower, upper = entity.GetBoundingBox()
                center = ((float(lower[0]) + float(upper[0])) / 2, (float(lower[1]) + float(upper[1])) / 2)
            except Exception:
                continue
            for region in regions:
                if _inside(list(region["frame_bbox"]), center):
                    grouped[str(region["region_id"])].append(entity)

        class _EntityList:
            def __init__(self, entities: list[Any]): self.entities = entities
            @property
            def Count(self) -> int: return len(self.entities)
            def Item(self, index: int) -> Any: return self.entities[index]

        for region in regions:
            audits.append(audit_region_selection(document, _EntityList(grouped[str(region["region_id"])]), region, role))
        after = _sha256(path)
        return {"role": role, "path": str(path), "regions": audits, "hash_before": before, "hash_after": after,
                "hash_unchanged": before == after, "scan_method": "single_lightweight_modelspace_bbox_filter_plus_block_definition_read",
                "full_drawing_cartesian_match": False, "write": False, "save": False}
    finally:
        if document is not None: _close_document_without_save(document)


def run_block_xref_audit(run_dir: Path, reference_scan: dict[str, Any], target_scan: dict[str, Any]) -> dict[str, Any]:
    output = run_dir / "block_xref_audit"; output.mkdir(parents=True, exist_ok=True)
    ref_by_id = {r["region_id"]: r for r in reference_scan["regions"]}; tgt_by_id = {r["region_id"]: r for r in target_scan["regions"]}
    block_rows, xref_rows, fingerprints_rows, matches_payload, alignment = [], [], [], [], []
    for role_scan in (reference_scan, target_scan):
        for region in role_scan["regions"]:
            for item in region.pop("block_instances", []): block_rows.append({"role": role_scan["role"], "region_id": region["region_id"], **item})
            for item in region.pop("xref_instances", []): xref_rows.append({"role": role_scan["role"], "region_id": region["region_id"], **item})
    for basename, rid, tid, semantic in PAIR_SPECS:
        r, t = ref_by_id[rid], tgt_by_id[tid]
        rfp, tfp = local_fingerprints(r["geometry"]), local_fingerprints(t["geometry"])
        matches = match_unique_fingerprints(rfp, tfp); fit = fit_allowed_transform(matches)
        for item in rfp: fingerprints_rows.append({"role": "reference", "region_id": rid, **item})
        for item in tfp: fingerprints_rows.append({"role": "target", "region_id": tid, **item})
        matches_payload.append({"pair_id": basename, "reference_region_id": rid, "target_region_id": tid,
                                "unique_fingerprint_matches": len(matches), "matches": matches})
        hidden = (r["expanded_line_count"] + r["expanded_polyline_count"] + t["expanded_line_count"] + t["expanded_polyline_count"]) > 0
        final_status = fit["status"]
        if final_status != "ALIGNMENT_VERIFIED": final_status = "ALIGNMENT_STILL_BLOCKED"
        alignment.append({"pair_id": basename, "semantic_name": semantic, "reference_region_id": rid, "target_region_id": tid,
                          "hidden_geometry_found": hidden, "unique_fingerprint_matches": len(matches), **fit, "final_status": final_status})
    for role_scan in (reference_scan, target_scan):
        for region in role_scan["regions"]: region.pop("geometry", None)
    _write(output / "reference_region_structure.json", reference_scan); _write(output / "target_region_structure.json", target_scan)
    (output / "block_instances.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False)+"\n" for x in block_rows), encoding="utf-8")
    (output / "xref_instances.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False)+"\n" for x in xref_rows), encoding="utf-8")
    (output / "local_geometry_fingerprints.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False)+"\n" for x in fingerprints_rows), encoding="utf-8")
    _write(output / "fingerprint_matches.json", {"pairs": matches_payload})
    _write(output / "retry_alignment_results.json", {"allowed_models": sorted(ALLOWED_TRANSFORMS), "results": alignment})
    structures = reference_scan["regions"] + target_scan["regions"]
    _write(output / "expanded_geometry_statistics.json", {"regions": [{k:v for k,v in r.items() if k in {"region_id","role","top_level_line_count","top_level_polyline_count","block_reference_count","xref_count","expanded_line_count","expanded_polyline_count","max_nesting_depth"}} for r in structures]})
    _write(output / "building_layer_candidates.json", {"regions": [{"region_id":r["region_id"],"role":r["role"],"candidates":r["building_layer_candidates"]} for r in structures]})
    _write(output / "region_bbox_audit.json", {"regions": [{k:v for k,v in r.items() if k in {"region_id","role","region_bbox","combined_building_bbox","building_bbox_inside_region","intersection_ratio","coverage_ratio"}} for r in structures]})
    verified = sum(1 for r in alignment if r["final_status"] == "ALIGNMENT_VERIFIED")
    status = "BLOCK_XREF_ALIGNMENT_REPAIR_COMPLETE" if verified == 3 else ("BLOCK_XREF_ALIGNMENT_REPAIR_PARTIAL" if verified else "BLOCK_XREF_ALIGNMENT_REPAIR_BLOCKED")
    summary = {"phase":"STAGE6-P2.2","status":status,"verified_region_count":verified,"blocked_region_count":3-verified,
               "reference_hash_unchanged":reference_scan["hash_unchanged"],"target_hash_unchanged":target_scan["hash_unchanged"],
               "target_write":False,"target_save":False,"missing_detection_executed":False,"frozen_plan_created":False,
               "regions":alignment,"artifact_directory":str(output)}
    _write(output / "block_xref_audit_summary.json", summary)
    lines=["# Stage 6-P2.2 块、Xref 与隐藏建筑几何审计","",f"- 最终状态：`{status}`","- DWG 写入：否；保存：否。","- 未执行 missing detection，未生成 frozen plan。","","## 区域结果","","| 区域 | 顶层 L/PL | 块 | Xref | 展开 L/PL | 唯一指纹 | 状态 |","|---|---:|---:|---:|---:|---:|---|"]
    for _,rid,tid,semantic in PAIR_SPECS:
        rr,tt=ref_by_id[rid],tgt_by_id[tid]; ar=next(x for x in alignment if x["reference_region_id"]==rid)
        lines.append(f"| {semantic} {rid}→{tid} | R {rr['top_level_line_count']}/{rr['top_level_polyline_count']}；T {tt['top_level_line_count']}/{tt['top_level_polyline_count']} | R {rr['block_reference_count']}；T {tt['block_reference_count']} | R {rr['xref_count']}；T {tt['xref_count']} | R {rr['expanded_line_count']}/{rr['expanded_polyline_count']}；T {tt['expanded_line_count']}/{tt['expanded_polyline_count']} | {ar['unique_fingerprint_matches']} | {ar['final_status']} |")
    (output/"block_xref_audit_summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return summary
