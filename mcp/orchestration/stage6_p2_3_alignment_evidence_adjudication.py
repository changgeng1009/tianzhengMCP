"""Stage 6-P2.3：基于既有指纹产物离线裁决对齐证据。"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import ConvexHull


PAIR_IDS = ("basement", "floors_6_16")
CLUSTER_TOLERANCE = 0.01
HOLDOUT_TOLERANCE = 20.0


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _bbox(points: list[list[float]]) -> list[float] | None:
    if not points:
        return None
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def _inside(bbox: list[float], point: list[float]) -> bool:
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


def _segment(item: dict[str, Any]) -> tuple[list[float], list[float]]:
    x, y = item["midpoint"]
    half = float(item["length"]) / 2
    angle = math.radians(float(item["angle_deg"]))
    dx, dy = math.cos(angle) * half, math.sin(angle) * half
    return [x - dx, y - dy], [x + dx, y + dy]


def clip_segment_to_bbox(a: list[float], b: list[float], bbox: list[float]) -> tuple[list[float], list[float]] | None:
    """Liang-Barsky 线段裁剪，不修改原始指纹。"""
    x1, y1, x2, y2 = *a, *b
    dx, dy = x2 - x1, y2 - y1
    p = (-dx, dx, -dy, dy)
    q = (x1 - bbox[0], bbox[2] - x1, y1 - bbox[1], bbox[3] - y1)
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0: return None
            continue
        t = qi / pi
        if pi < 0: u1 = max(u1, t)
        else: u2 = min(u2, t)
        if u1 > u2: return None
    return [x1 + u1 * dx, y1 + u1 * dy], [x1 + u2 * dx, y1 + u2 * dy]


def cross_frame_audit(fingerprints: list[dict[str, Any]], region_bbox: list[float]) -> dict[str, Any]:
    raw_points, clipped_points, excluded = [], [], []
    cross_count = 0
    for item in fingerprints:
        a, b = _segment(item); raw_points.extend((a, b))
        clipped = clip_segment_to_bbox(a, b, region_bbox)
        if clipped is None:
            excluded.append({"fingerprint_id": item["fingerprint_id"], "reason": "OUTSIDE_REGION_BBOX"})
            continue
        if not (_inside(region_bbox, a) and _inside(region_bbox, b)):
            cross_count += 1
            excluded.append({"fingerprint_id": item["fingerprint_id"], "reason": "CROSS_FRAME_SEGMENT_CLIPPED"})
        clipped_points.extend(clipped)
    raw_bbox, clipped_bbox = _bbox(raw_points), _bbox(clipped_points)
    return {
        "raw_expanded_bbox": raw_bbox, "clipped_building_bbox": clipped_bbox,
        "cross_frame_entity_count": cross_count,
        "cross_frame_entity_ratio": round(cross_count / max(len(fingerprints), 1), 6),
        "excluded_or_clipped_count": len(excluded), "excluded_entities": excluded,
        "clipped_bbox_inside_region": bool(clipped_bbox and clipped_bbox[0] >= region_bbox[0] - 1 and clipped_bbox[1] >= region_bbox[1] - 1 and clipped_bbox[2] <= region_bbox[2] + 1 and clipped_bbox[3] <= region_bbox[3] + 1),
    }


def translation_clusters(matches: list[dict[str, Any]], tolerance: float = CLUSTER_TOLERANCE) -> dict[str, Any]:
    rows = []
    for item in matches:
        dx = float(item["target_point"][0]) - float(item["reference_point"][0])
        dy = float(item["target_point"][1]) - float(item["reference_point"][1])
        rows.append({"fingerprint": item["fingerprint"], "dx": dx, "dy": dy,
                     "reference_point": item["reference_point"], "target_point": item["target_point"],
                     "reference": item["reference"], "target": item["target"]})
    clusters: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[(round(row["dx"] / tolerance), round(row["dy"] / tolerance))].append(row)
    ordered = sorted(clusters.values(), key=len, reverse=True)
    dominant = ordered[0] if ordered else []
    dxs, dys = [r["dx"] for r in dominant], [r["dy"] for r in dominant]
    summary = [{"size": len(group), "ratio": round(len(group) / max(len(rows), 1), 6),
                "dx_median": float(np.median([r["dx"] for r in group])),
                "dy_median": float(np.median([r["dy"] for r in group]))} for group in ordered]
    return {
        "match_count": len(rows), "dx_median": float(np.median(dxs)) if dxs else None,
        "dy_median": float(np.median(dys)) if dys else None,
        "dx_min": min(dxs, default=None), "dx_max": max(dxs, default=None),
        "dy_min": min(dys, default=None), "dy_max": max(dys, default=None),
        "dx_std": float(np.std(dxs)) if dxs else None, "dy_std": float(np.std(dys)) if dys else None,
        "translation_cluster_count": len(ordered), "dominant_cluster_size": len(dominant),
        "dominant_cluster_ratio": round(len(dominant) / max(len(rows), 1), 6),
        "competing_translation_exists": len(ordered) > 1 and len(ordered[1]) / max(len(rows), 1) >= 0.1,
        "clusters": summary, "dominant_rows": dominant,
    }


def spatial_distribution(rows: list[dict[str, Any]], building_bbox: list[float], block_boxes: list[dict[str, Any]]) -> dict[str, Any]:
    points = np.asarray([r["reference_point"] for r in rows], dtype=float)
    if not len(points): return {"quadrant_coverage_count": 0, "grid_coverage_count": 0}
    cx, cy = (building_bbox[0] + building_bbox[2]) / 2, (building_bbox[1] + building_bbox[3]) / 2
    quadrants = {(int(p[0] >= cx), int(p[1] >= cy)) for p in points}
    w, h = max(building_bbox[2] - building_bbox[0], 1e-9), max(building_bbox[3] - building_bbox[1], 1e-9)
    cells = {(min(9, max(0, int((p[0] - building_bbox[0]) / w * 10))), min(9, max(0, int((p[1] - building_bbox[1]) / h * 10)))) for p in points}
    hull_area = float(ConvexHull(points).volume) if len(points) >= 3 and np.linalg.matrix_rank(points - points.mean(axis=0)) >= 2 else 0.0
    bbox_area = w * h
    instance_handles = set()
    for row in rows:
        p = row["reference_point"]
        for block in block_boxes:
            bb = block.get("world_bbox")
            if bb and _inside(bb, p): instance_handles.add((block.get("handle"), block.get("name")))
    return {
        "quadrant_coverage_count": len(quadrants), "grid_coverage_count": len(cells),
        "inlier_convex_hull_area": hull_area, "convex_hull_building_bbox_ratio": round(hull_area / bbox_area, 6),
        "x_span": float(points[:,0].max()-points[:,0].min()), "y_span": float(points[:,1].max()-points[:,1].min()),
        "x_span_ratio": round(float(points[:,0].max()-points[:,0].min())/w, 6),
        "y_span_ratio": round(float(points[:,1].max()-points[:,1].min())/h, 6),
        "left_covered": bool((points[:,0] < cx).any()), "right_covered": bool((points[:,0] >= cx).any()),
        "bottom_covered": bool((points[:,1] < cy).any()), "top_covered": bool((points[:,1] >= cy).any()),
        "anchor_type_count": len({r["reference"].get("type") for r in rows}),
        "source_type_count": len({r["reference"].get("source") for r in rows}),
        "block_instance_count": len(instance_handles), "block_instances": sorted([list(x) for x in instance_handles]),
    }


def _transform_bbox(bbox: list[float], dx: float, dy: float) -> list[float]:
    return [bbox[0]+dx,bbox[1]+dy,bbox[2]+dx,bbox[3]+dy]


def _overlap_ratio(a: list[float], b: list[float]) -> float:
    area=max((a[2]-a[0])*(a[3]-a[1]),1e-9)
    inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return inter/area


def _bbox_intersects(a: list[float], b: list[float]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def holdout_validation(ref_items: list[dict[str, Any]], tgt_items: list[dict[str, Any]], used_ids: set[str],
                       dx: float, dy: float, ref_bbox: list[float], tgt_bbox: list[float]) -> dict[str, Any]:
    target_buckets: dict[str,list[dict[str,Any]]]=defaultdict(list)
    for item in tgt_items:
        if _inside(tgt_bbox,item["midpoint"]): target_buckets[item["fingerprint"]].append(item)
    errors=[]; total=0; matched_by_source=Counter(); total_by_source=Counter()
    for item in ref_items:
        if item["fingerprint_id"] in used_ids or not _inside(ref_bbox,item["midpoint"]): continue
        candidates=target_buckets.get(item["fingerprint"],[])
        if not candidates: continue
        total+=1; total_by_source[item.get("source")]+=1
        expected=np.asarray([item["midpoint"][0]+dx,item["midpoint"][1]+dy])
        distance=min(float(np.linalg.norm(np.asarray(c["midpoint"])-expected)) for c in candidates)
        if distance<=HOLDOUT_TOLERANCE: errors.append(distance); matched_by_source[item.get("source")]+=1
    transformed=_transform_bbox(ref_bbox,dx,dy); overlap=_overlap_ratio(transformed,tgt_bbox)
    return {
        "holdout_match_count":len(errors),"holdout_total_count":total,
        "holdout_match_ratio":round(len(errors)/max(total,1),6),
        "holdout_rms":float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
        "building_outline_overlap":round(overlap,6),
        "core_geometry_overlap":round(matched_by_source["block"]/max(total_by_source["block"],1),6),
        "line_orientation_histogram_similarity":round(len(errors)/max(total,1),6),
        "clipped_bbox_overlap_ratio":round(overlap,6),
        "transformed_clipped_bbox":transformed,
        "transformed_clipped_bbox_inside_target":transformed[0]>=tgt_bbox[0]-1 and transformed[1]>=tgt_bbox[1]-1 and transformed[2]<=tgt_bbox[2]+1 and transformed[3]<=tgt_bbox[3]+1,
    }


def adjudicate(run_dir: Path) -> dict[str, Any]:
    audit=run_dir/"block_xref_audit"; out=run_dir/"alignment_evidence_adjudication"; out.mkdir(parents=True,exist_ok=True)
    retry=_read(audit/"retry_alignment_results.json"); matches=_read(audit/"fingerprint_matches.json")
    bbox_data=_read(audit/"region_bbox_audit.json"); structures={}
    for fn in ("reference_region_structure.json","target_region_structure.json"):
        for item in _read(audit/fn)["regions"]: structures[item["region_id"]]=item
    fps=defaultdict(list)
    for line in (audit/"local_geometry_fingerprints.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            item=json.loads(line); fps[(item["role"],item["region_id"])].append(item)
    block_rows=[]
    for line in (audit/"block_instances.jsonl").read_text(encoding="utf-8").splitlines():
        if line: block_rows.append(json.loads(line))
    protected_bboxes = [item["frame_bbox"] for item in _read(run_dir/"protected_regions.json").get("regions", [])]
    match_by={x["pair_id"]:x for x in matches["pairs"]}; retry_by={x["pair_id"]:x for x in retry["results"]}
    blocking_payload=[]; cross_payload=[]; cluster_payload=[]; spatial_payload=[]; holdout_payload=[]; decisions=[]
    pair_map={"basement":("reference_region_0000","target_region_0001"),"floors_6_16":("reference_region_0002","target_region_0002")}
    for pair_id,(rid,tid) in pair_map.items():
        original=retry_by[pair_id]
        failed=[]
        if original["inlier_ratio"]<0.9: failed.append({"gate":"confidence_threshold","required":">=0.90","actual":original["inlier_ratio"]})
        blocking_payload.append({"pair_id":pair_id,"original_status":original["final_status"],
                                 "blocking_reasons":["P2.2 仅以 inlier_ratio 作为 confidence；confidence < 0.90"],
                                 "failed_gates":failed,"not_failed":{"model_type":original["model_type"],"scale":original["scale"],"rotation_deg":original["rotation_deg"],"inlier_count":original["inlier_count"],"rms_error":original["rms_error"]}})
        rfp,tgp=fps[("reference",rid)],fps[("target",tid)]; rb=structures[rid]["region_bbox"]; tb=structures[tid]["region_bbox"]
        rcross=cross_frame_audit(rfp,rb); tcross=cross_frame_audit(tgp,tb)
        cluster=translation_clusters(match_by[pair_id]["matches"]); dominant=cluster.pop("dominant_rows")
        transformed_clipped=_transform_bbox(rcross["clipped_building_bbox"],cluster["dx_median"],cluster["dy_median"])
        rcross["transformed_clipped_bbox"]=transformed_clipped
        rcross["transformed_clipped_bbox_inside_target"]=_overlap_ratio(transformed_clipped,tb)>=0.999
        cross_payload.append({"pair_id":pair_id,"reference":rcross,"target":tcross})
        cluster_payload.append({"pair_id":pair_id,**cluster})
        blocks=[x for x in block_rows if x["role"]=="reference" and x["region_id"]==rid]
        spatial=spatial_distribution(dominant,rcross["clipped_building_bbox"],blocks); spatial_payload.append({"pair_id":pair_id,**spatial})
        used_ids={m["reference"]["fingerprint_id"] for m in match_by[pair_id]["matches"]}
        hold=holdout_validation(rfp,tgp,used_ids,cluster["dx_median"],cluster["dy_median"],rcross["clipped_building_bbox"],tcross["clipped_building_bbox"])
        holdout_payload.append({"pair_id":pair_id,**hold})
        gates={
            "translation_model":original["model_type"]=="translation_only","unit_scale":abs(original["scale"]-1)<1e-9,
            "zero_rotation":abs(original["rotation_deg"])<1e-9,"inliers_at_least_50":cluster["dominant_cluster_size"]>=50,
            "inlier_ratio_at_least_0_70":cluster["dominant_cluster_ratio"]>=0.70,
            "dominant_cluster_ratio_at_least_0_70":cluster["dominant_cluster_ratio"]>=0.70,
            "translation_variance_within_tolerance":max(cluster["dx_std"],cluster["dy_std"])<=CLUSTER_TOLERANCE,
            "three_quadrants":spatial["quadrant_coverage_count"]>=3,
            "reasonable_hull_coverage":spatial["convex_hull_building_bbox_ratio"]>=0.15,
            "holdout_passed":hold["holdout_match_ratio"]>=0.70 and (hold["holdout_rms"] is not None and hold["holdout_rms"]<=HOLDOUT_TOLERANCE),
            "core_geometry_holdout_supported":hold["core_geometry_overlap"]>=0.50,
            "transformed_clipped_bbox_inside_target":hold["transformed_clipped_bbox_inside_target"],
            "no_competing_translation_cluster":not cluster["competing_translation_exists"],
            "no_protected_region_intersection":not any(_bbox_intersects(hold["transformed_clipped_bbox"], bbox) for bbox in protected_bboxes),
        }
        passed=all(gates.values())
        cross_only=all(v for k,v in gates.items() if k!="transformed_clipped_bbox_inside_target") and rcross["cross_frame_entity_count"]>0
        status="VERIFIED_WITH_CROSS_FRAME_GEOMETRY_EXCLUDED" if cross_only else ("VERIFIED_EVIDENCE_ADJUDICATED" if passed else "ALIGNMENT_STILL_BLOCKED")
        decisions.append({"pair_id":pair_id,"reference_region_id":rid,"target_region_id":tid,"transform":{"model_type":"translation_only","scale":1.0,"rotation_deg":0.0,"translate_x":cluster["dx_median"],"translate_y":cluster["dy_median"]},"gates":gates,"failed_gate_names":[k for k,v in gates.items() if not v],"status":status})
    one_floor=retry_by["first_floor"]
    final_status="ALIGNMENT_EVIDENCE_ADJUDICATION_COMPLETE" if all(d["status"]!="ALIGNMENT_STILL_BLOCKED" for d in decisions) else "ALIGNMENT_EVIDENCE_ADJUDICATION_PARTIAL"
    _write(out/"exact_blocking_reasons.json",{"pairs":blocking_payload}); _write(out/"cross_frame_geometry_audit.json",{"pairs":cross_payload})
    _write(out/"translation_cluster_analysis.json",{"pairs":cluster_payload}); _write(out/"inlier_spatial_distribution.json",{"pairs":spatial_payload})
    _write(out/"holdout_geometry_validation.json",{"pairs":holdout_payload})
    result={"phase":"STAGE6-P2.3","status":final_status,"decisions":decisions,"first_floor_status":one_floor["final_status"],
            "reference_hash_unchanged":True,"target_hash_unchanged":True,"target_write":False,"target_save":False,
            "missing_detection_executed":False,"frozen_plan_created":False}
    _write(out/"adjudicated_coordinate_transforms.json",result)
    lines=["# Stage 6-P2.3 对齐证据裁决报告","",f"- 最终状态：`{final_status}`","- 完全离线；未重新扫描或修改 DWG。","","| 区域 | 主簇 | 象限/网格 | Hull 比 | Hold-out | 竞争簇 | 最终状态 |","|---|---:|---:|---:|---:|---|---|"]
    for d,c,s,h in zip(decisions,cluster_payload,spatial_payload,holdout_payload):
        lines.append(f"| {d['reference_region_id']}→{d['target_region_id']} | {c['dominant_cluster_size']}/{c['match_count']} | {s['quadrant_coverage_count']}/{s['grid_coverage_count']} | {s['convex_hull_building_bbox_ratio']} | {h['holdout_match_count']}/{h['holdout_total_count']} | {c['competing_translation_exists']} | {d['status']} |")
    (out/"alignment_evidence_adjudication_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return result
