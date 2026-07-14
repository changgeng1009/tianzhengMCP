"""Stage 6-P2.4：读取人工命名锚点并离线消除竞争平移簇。"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from mcp.orchestration.stage6_p2_3_alignment_evidence_adjudication import (
    _bbox_intersects,
    holdout_validation,
)


ANCHOR_GROUPS = {
    "basement": ["B1_FIX_01", "B1_FIX_02", "B1_FIX_03"],
    "floors_6_16": ["F6_16_FIX_01", "F6_16_FIX_02", "F6_16_FIX_03"],
}
PAIR_REGIONS = {
    "basement": ("reference_region_0000", "target_region_0001"),
    "floors_6_16": ("reference_region_0002", "target_region_0002"),
}
ANCHOR_TOLERANCE = 1.0
HOLDOUT_TOLERANCE = 20.0


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


def normalize_anchor_id(text: Any) -> str:
    return str(text or "").strip().upper()


def _safe_get(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def parse_anchor_entity(entity: Any) -> dict[str, Any] | None:
    """仅解析 MCP_ANCHOR 图层的 Text 或 MCP_ANCHOR_POINT 块。"""
    layer = str(_safe_get(entity, "Layer", ""))
    if layer.upper() != "MCP_ANCHOR":
        return None
    object_name = str(_safe_get(entity, "ObjectName", ""))
    anchor_id, point, source = None, None, None
    if object_name == "AcDbText":
        anchor_id = normalize_anchor_id(_safe_get(entity, "TextString", ""))
        point = _safe_get(entity, "InsertionPoint")
        source = "TEXT"
    elif object_name == "AcDbBlockReference":
        effective = normalize_anchor_id(_safe_get(entity, "EffectiveName", _safe_get(entity, "Name", "")))
        if effective != "MCP_ANCHOR_POINT":
            return None
        try:
            attributes = list(entity.GetAttributes())
        except Exception:
            attributes = []
        for attribute in attributes:
            if normalize_anchor_id(_safe_get(attribute, "TagString", "")) == "ANCHOR_ID":
                anchor_id = normalize_anchor_id(_safe_get(attribute, "TextString", ""))
                break
        point = _safe_get(entity, "InsertionPoint")
        source = "BLOCK_ATTRIBUTE"
    if not anchor_id or point is None:
        return None
    values = list(point)
    if len(values) < 2:
        return None
    return {
        "anchor_id": anchor_id,
        "handle": str(_safe_get(entity, "Handle", "")),
        "point": [float(values[0]), float(values[1]), float(values[2]) if len(values) > 2 else 0.0],
        "layer": layer, "object_name": object_name, "source": source,
    }


def scan_anchor_layer_readonly(acad: Any, path: Path, role: str) -> dict[str, Any]:
    """只读取 ModelSpace 中 MCP_ANCHOR 图层，不读取其他实体几何。"""
    from mcp.acceptance.stage3_1_runtime import _close_document_without_save, _open_document_with_retry, _resolve_open_document
    from mcp.acceptance.stage5_2_native_clone_poc import _retry

    before = _sha256(path); document = None; anchors = []
    try:
        returned = _open_document_with_retry(acad, path)
        document = _resolve_open_document(acad, path, returned)
        count = int(_retry(lambda: document.ModelSpace.Count, f"{role} ModelSpace.Count", attempts=40, delay=0.25))
        for index in range(count):
            entity = _retry(lambda value=index: document.ModelSpace.Item(value), f"{role} anchor item {index}", attempts=40, delay=0.2)
            if str(_safe_get(entity, "Layer", "")).upper() != "MCP_ANCHOR":
                continue
            parsed = parse_anchor_entity(entity)
            if parsed:
                anchors.append(parsed)
        after = _sha256(path)
        return {
            "role": role, "path": str(path), "hash_before": before, "hash_after": after,
            "hash_unchanged": before == after, "modelspace_count": count,
            "anchor_layer": "MCP_ANCHOR", "anchors": anchors,
            "non_anchor_geometry_read": False, "write": False, "save": False,
        }
    finally:
        if document is not None:
            _close_document_without_save(document)


def pair_named_anchors(reference: list[dict[str, Any]], target: list[dict[str, Any]],
                       expected_ids: list[str]) -> dict[str, Any]:
    by_ref, by_tgt = {}, {}
    for item in reference: by_ref.setdefault(item["anchor_id"], []).append(item)
    for item in target: by_tgt.setdefault(item["anchor_id"], []).append(item)
    pairs, errors = [], []
    for anchor_id in expected_ids:
        ritems, titems = by_ref.get(anchor_id, []), by_tgt.get(anchor_id, [])
        status = "VALID"
        if not ritems or not titems: status = "MISSING"; errors.append(f"{anchor_id}:MISSING")
        elif len(ritems) != 1 or len(titems) != 1: status = "DUPLICATE"; errors.append(f"{anchor_id}:DUPLICATE")
        row = {
            "anchor_id": anchor_id,
            "reference_handle": ritems[0]["handle"] if ritems else None,
            "target_handle": titems[0]["handle"] if titems else None,
            "reference_point": ritems[0]["point"] if ritems else None,
            "target_point": titems[0]["point"] if titems else None,
            "dx": None, "dy": None,
            "layer": "MCP_ANCHOR",
            "object_name": {"reference": ritems[0]["object_name"] if ritems else None,
                            "target": titems[0]["object_name"] if titems else None},
            "duplicate_count": {"reference": len(ritems), "target": len(titems)}, "status": status,
        }
        if status == "VALID":
            row["dx"] = row["target_point"][0] - row["reference_point"][0]
            row["dy"] = row["target_point"][1] - row["reference_point"][1]
        pairs.append(row)
    valid = [p for p in pairs if p["status"] == "VALID"]
    ref_points = np.asarray([p["reference_point"][:2] for p in valid], dtype=float) if valid else np.empty((0,2))
    tgt_points = np.asarray([p["target_point"][:2] for p in valid], dtype=float) if valid else np.empty((0,2))
    non_collinear = len(valid) >= 3 and np.linalg.matrix_rank(ref_points-ref_points.mean(axis=0)) >= 2 and np.linalg.matrix_rank(tgt_points-tgt_points.mean(axis=0)) >= 2
    return {"pairs": pairs, "valid_count": len(valid), "errors": errors,
            "missing": any("MISSING" in e for e in errors), "duplicate": any("DUPLICATE" in e for e in errors),
            "non_collinear": bool(non_collinear)}


def _candidate_residuals(pairs: list[dict[str, Any]], tx: float, ty: float) -> dict[str, Any]:
    residuals = [math.hypot(float(p["dx"])-tx, float(p["dy"])-ty) for p in pairs if p["status"] == "VALID"]
    return {"manual_anchor_residuals": residuals,
            "manual_anchor_rms": math.sqrt(sum(x*x for x in residuals)/max(len(residuals),1)),
            "manual_anchor_max_error": max(residuals, default=float("inf")),
            "supported_anchor_count": sum(x <= ANCHOR_TOLERANCE for x in residuals)}


def _bbox_inside(inner: list[float], outer: list[float], tolerance: float = 1.0) -> bool:
    return inner[0]>=outer[0]-tolerance and inner[1]>=outer[1]-tolerance and inner[2]<=outer[2]+tolerance and inner[3]<=outer[3]+tolerance


def _point_inside(point: list[float], bbox: list[float], tolerance: float = 1.0) -> bool:
    return bbox[0]-tolerance <= point[0] <= bbox[2]+tolerance and bbox[1]-tolerance <= point[1] <= bbox[3]+tolerance


def validate_anchor_region_locations(paired: dict[str, Any], reference_bbox: list[float], target_bbox: list[float]) -> dict[str, Any]:
    errors=[]
    for item in paired["pairs"]:
        if item["status"] != "VALID": continue
        if not _point_inside(item["reference_point"], reference_bbox): errors.append(f"{item['anchor_id']}:REFERENCE_POINT_OUTSIDE_EXPECTED_REGION")
        if not _point_inside(item["target_point"], target_bbox): errors.append(f"{item['anchor_id']}:TARGET_POINT_OUTSIDE_EXPECTED_REGION")
    paired["region_location_valid"] = not errors
    paired["region_location_errors"] = errors
    return paired


def score_candidates(candidates: list[dict[str, Any]], pairs: list[dict[str, Any]],
                     holdout_factory: Any, ref_clipped_bbox: list[float], target_region_bbox: list[float],
                     protected_bboxes: list[list[float]]) -> list[dict[str, Any]]:
    rows=[]
    for index,candidate in enumerate(candidates):
        tx,ty=float(candidate["translation_x"]),float(candidate["translation_y"])
        residual=_candidate_residuals(pairs,tx,ty); hold=holdout_factory(tx,ty)
        transformed=[ref_clipped_bbox[0]+tx,ref_clipped_bbox[1]+ty,ref_clipped_bbox[2]+tx,ref_clipped_bbox[3]+ty]
        protected=sum(_bbox_intersects(transformed,b) for b in protected_bboxes)
        bbox_inside=_bbox_inside(transformed,target_region_bbox)
        score=(max(0,100-residual["manual_anchor_rms"])*0.65 + hold["holdout_match_ratio"]*20 +
               (10 if bbox_inside else 0)+(5 if protected==0 else 0))
        rows.append({"cluster_id":candidate.get("cluster_id",f"cluster_{index+1:02d}"),"translation_x":tx,"translation_y":ty,
                     **residual,"holdout_match_ratio":hold["holdout_match_ratio"],"holdout_rms":hold["holdout_rms"],
                     "bbox_inside_target":bbox_inside,"transformed_clipped_bbox":transformed,
                     "protected_region_intersection":protected,"score":round(score,6),
                     "source":candidate.get("source","existing_cluster")})
    return sorted(rows,key=lambda x:(x["manual_anchor_rms"],-x["holdout_match_ratio"],-x["score"]))


def decide_region(pair_id: str, paired: dict[str, Any], scores: list[dict[str, Any]]) -> dict[str, Any]:
    if paired["duplicate"]: return {"pair_id":pair_id,"status":"MANUAL_ANCHOR_DUPLICATE"}
    if paired["missing"] or paired["valid_count"]<2: return {"pair_id":pair_id,"status":"MANUAL_ANCHOR_INSUFFICIENT"}
    if not paired.get("region_location_valid", True): return {"pair_id":pair_id,"status":"MANUAL_ANCHOR_CONFLICT","reason":"人工锚点不在对应冻结区域内","location_errors":paired.get("region_location_errors",[])}
    if paired["valid_count"]>=3 and not paired["non_collinear"]: return {"pair_id":pair_id,"status":"MANUAL_ANCHOR_CONFLICT","reason":"人工锚点共线"}
    winner=scores[0]; runner=scores[1] if len(scores)>1 else None
    margin=(runner["manual_anchor_rms"]-winner["manual_anchor_rms"]) if runner else float("inf")
    passed=(winner["manual_anchor_max_error"]<=ANCHOR_TOLERANCE and winner["supported_anchor_count"]==paired["valid_count"] and
            margin>=5.0 and winner["holdout_match_ratio"]>=0.90 and winner["holdout_rms"] is not None and winner["holdout_rms"]<=HOLDOUT_TOLERANCE and
            winner["bbox_inside_target"] and winner["protected_region_intersection"]==0)
    return {"pair_id":pair_id,"status":"VERIFIED_BY_MANUAL_CLUSTER_DISAMBIGUATION" if passed else "ALIGNMENT_STILL_BLOCKED",
            "selected_translation":[winner["translation_x"],winner["translation_y"]],"manual_anchor_count":paired["valid_count"],
            "manual_anchor_rms":winner["manual_anchor_rms"],"manual_anchor_max_error":winner["manual_anchor_max_error"],
            "runner_up_translation":[runner["translation_x"],runner["translation_y"]] if runner else None,
            "runner_up_error":runner["manual_anchor_rms"] if runner else None,"cluster_separation_margin":margin,
            "holdout_match_ratio":winner["holdout_match_ratio"],"holdout_rms":winner["holdout_rms"],
            "transformed_bbox_inside_target":winner["bbox_inside_target"],"protected_region_intersection":winner["protected_region_intersection"]}


def run_disambiguation(run_dir: Path, reference_scan: dict[str, Any], target_scan: dict[str, Any]) -> dict[str, Any]:
    out=run_dir/"manual_cluster_disambiguation"; out.mkdir(parents=True,exist_ok=True)
    audit=run_dir/"block_xref_audit"; adjud=run_dir/"alignment_evidence_adjudication"
    clusters={x["pair_id"]:x for x in _read(adjud/"translation_cluster_analysis.json")["pairs"]}
    cross={x["pair_id"]:x for x in _read(adjud/"cross_frame_geometry_audit.json")["pairs"]}
    fingerprint_matches={x["pair_id"]:x for x in _read(audit/"fingerprint_matches.json")["pairs"]}
    fps={}
    rows=[]
    for line in (audit/"local_geometry_fingerprints.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            item=json.loads(line); rows.append(item); fps.setdefault((item["role"],item["region_id"]),[]).append(item)
    structures={}
    for fn in ("reference_region_structure.json","target_region_structure.json"):
        for item in _read(audit/fn)["regions"]: structures[item["region_id"]]=item
    protected=[x["frame_bbox"] for x in _read(run_dir/"protected_regions.json").get("regions",[])]
    all_pairs=[]; all_scores=[]; decisions=[]
    for pair_id,expected in ANCHOR_GROUPS.items():
        rid,tid=PAIR_REGIONS[pair_id]
        paired=pair_named_anchors(reference_scan["anchors"],target_scan["anchors"],expected)
        paired=validate_anchor_region_locations(paired,structures[rid]["region_bbox"],structures[tid]["region_bbox"])
        all_pairs.append({"pair_id":pair_id,**paired})
        if paired["missing"] or paired["duplicate"] or paired["valid_count"] < 2:
            all_scores.append({"pair_id":pair_id,"candidates":[]})
            decisions.append(decide_region(pair_id,paired,[]))
            continue
        candidates=[]
        for index,c in enumerate(clusters[pair_id]["clusters"]):
            candidates.append({"cluster_id":f"existing_cluster_{index+1:02d}","translation_x":c["dx_median"],"translation_y":c["dy_median"],"source":"existing_fingerprint_cluster"})
        valid=[p for p in paired["pairs"] if p["status"]=="VALID"]
        if valid:
            mx=float(np.median([p["dx"] for p in valid])); my=float(np.median([p["dy"] for p in valid]))
            if not any(math.hypot(c["translation_x"]-mx,c["translation_y"]-my)<=ANCHOR_TOLERANCE for c in candidates):
                candidates.append({"cluster_id":"manual_anchor_median","translation_x":mx,"translation_y":my,"source":"manual_anchor_median"})
        used_ids={m["reference"]["fingerprint_id"] for m in fingerprint_matches[pair_id]["matches"]}
        def holdout_factory(tx:float,ty:float):
            return holdout_validation(fps[("reference",rid)],fps[("target",tid)],used_ids,tx,ty,
                                      cross[pair_id]["reference"]["clipped_building_bbox"],cross[pair_id]["target"]["clipped_building_bbox"])
        scores=score_candidates(candidates,paired["pairs"],holdout_factory,cross[pair_id]["reference"]["clipped_building_bbox"],structures[tid]["region_bbox"],protected)
        all_scores.append({"pair_id":pair_id,"candidates":scores}); decisions.append(decide_region(pair_id,paired,scores))
    _write(out/"manual_anchor_scan.json",{"reference":reference_scan,"target":target_scan})
    _write(out/"manual_anchor_pairs.json",{"groups":all_pairs}); _write(out/"candidate_cluster_scores.json",{"groups":all_scores})
    complete=all(x["status"]=="VERIFIED_BY_MANUAL_CLUSTER_DISAMBIGUATION" for x in decisions)
    success=sum(x["status"]=="VERIFIED_BY_MANUAL_CLUSTER_DISAMBIGUATION" for x in decisions)
    status="MANUAL_CLUSTER_DISAMBIGUATION_COMPLETE" if complete else ("MANUAL_CLUSTER_DISAMBIGUATION_PARTIAL" if success else "MANUAL_CLUSTER_DISAMBIGUATION_BLOCKED")
    result={"phase":"STAGE6-P2.4","status":status,"decisions":decisions,"reference_calibration_hash_unchanged":reference_scan["hash_unchanged"],
            "target_calibration_hash_unchanged":target_scan["hash_unchanged"],"target_write":False,"target_save":False,
            "missing_detection_executed":False,"frozen_plan_created":False,"final_manifest_created":False}
    _write(out/"selected_coordinate_transforms.json",result)
    if complete:
        original=_read(run_dir/"coordinate_transforms.json")["transforms"]
        by_ref={x["reference_region_id"]:dict(x) for x in original}
        p22={x["pair_id"]:x for x in _read(audit/"retry_alignment_results.json")["results"]}
        for decision in decisions:
            rid,tid=PAIR_REGIONS[decision["pair_id"]]; tx,ty=decision["selected_translation"]
            by_ref[rid].update({"target_region_id":tid,"model_type":"translation_only","scale_x":1.0,"scale_y":1.0,"rotation_deg":0.0,
                                "translate_x":tx,"translate_y":ty,"matrix_3x3":[[1,0,tx],[0,1,ty],[0,0,1]],"status":"VERIFIED_BY_MANUAL_CLUSTER_DISAMBIGUATION"})
        ground=p22["first_floor"]; by_ref["reference_region_0001"].update({k:ground[k] for k in ("model_type","translate_x","translate_y","matrix_3x3")}); by_ref["reference_region_0001"]["status"]="ALIGNMENT_VERIFIED"
        by_ref["reference_region_0006"]["status"]="VERIFIED_BY_SHARED_FRAME_TRANSFORM"
        final={"phase":"STAGE6-P2.4","count":7,"all_verified":True,"transforms":[by_ref[f"reference_region_{i:04d}"] for i in (0,1,2,5,6,4,3)],
               "historical_coordinate_transforms_overwritten":False,"missing_detection_executed":False,"frozen_plan_created":False}
        _write(run_dir/"alignment_repair"/"final_verified_coordinate_transforms.json",final); result["final_manifest_created"]=True
        _write(out/"selected_coordinate_transforms.json",result)
    lines=["# Stage 6-P2.4 人工平移簇裁决报告","",f"- 最终状态：`{status}`",f"- 七组最终坐标清单：{'已生成' if complete else '未生成'}","","| 区域 | 有效锚点 | 选择平移 | RMS/Max | Runner-up margin | Hold-out | 状态 |","|---|---:|---|---:|---:|---:|---|"]
    for pair,decision in zip(all_pairs,decisions):
        lines.append(f"| {pair['pair_id']} | {pair['valid_count']} | {decision.get('selected_translation')} | {decision.get('manual_anchor_rms')}/{decision.get('manual_anchor_max_error')} | {decision.get('cluster_separation_margin')} | {decision.get('holdout_match_ratio')} | {decision['status']} |")
    (out/"manual_cluster_disambiguation_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return result
