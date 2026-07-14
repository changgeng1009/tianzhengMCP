"""Stage 6-P2.5：基于既有区域与人工锚点离线审计区域绑定。"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


EXPECTED = {
    "basement": {
        "anchor_ids": ["B1_FIX_01", "B1_FIX_02", "B1_FIX_03"],
        "semantic": "地下一层平面图",
        "reference_region_id": "reference_region_0000",
        "target_region_id": "target_region_0001",
    },
    "floors_6_16": {
        "anchor_ids": ["F6_16_FIX_01", "F6_16_FIX_02", "F6_16_FIX_03"],
        "semantic": "六～十五层平面图、十六层平面图",
        "reference_region_id": "reference_region_0002",
        "target_region_id": "target_region_0002",
    },
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()


def point_in_bbox(point: list[float], bbox: list[float], tolerance: float = 1.0) -> bool:
    return bbox[0]-tolerance <= point[0] <= bbox[2]+tolerance and bbox[1]-tolerance <= point[1] <= bbox[3]+tolerance


def point_bbox_distance(point: list[float], bbox: list[float]) -> float:
    dx=max(bbox[0]-point[0],0.0,point[0]-bbox[2])
    dy=max(bbox[1]-point[1],0.0,point[1]-bbox[3])
    return math.hypot(dx,dy)


def audit_point_membership(anchor_id: str, point: list[float], original_region_id: str,
                           regions: list[dict[str, Any]], building_bboxes: dict[str,list[float]]) -> dict[str, Any]:
    frame=[r["region_id"] for r in regions if point_in_bbox(point,r["frame_bbox"])]
    content=[r["region_id"] for r in regions if point_in_bbox(point,r["content_bbox"])]
    building=[rid for rid,bbox in building_bboxes.items() if point_in_bbox(point,bbox)]
    distances=sorted([(point_bbox_distance(point,r["frame_bbox"]),r["region_id"]) for r in regions])
    actual=frame[0] if len(frame)==1 else (content[0] if len(content)==1 else None)
    region_by={r["region_id"]:r for r in regions}
    semantic=region_by[actual]["semantic_name"] if actual else None
    return {
        "anchor_id":anchor_id,"point":point,"original_bound_region_id":original_region_id,
        "frame_bbox_containing_regions":frame,"content_bbox_containing_regions":content,
        "building_bbox_containing_regions":building,"nearest_region_id":distances[0][1],
        "nearest_region_distance":round(distances[0][0],6),"actual_region_id":actual,
        "semantic_name":semantic,"binding_consistent":actual==original_region_id,
        "conflict_reason":None if actual==original_region_id else ("ANCHOR_IN_DIFFERENT_SEMANTIC_REGION" if actual else "NO_UNIQUE_CONTAINING_REGION"),
    }


def classify_group(pair_id: str, reference_rows: list[dict[str,Any]], target_rows: list[dict[str,Any]],
                   region_by_id: dict[str,dict[str,Any]]) -> dict[str,Any]:
    expected=EXPECTED[pair_id]
    ref_ids={r["actual_region_id"] for r in reference_rows}; tgt_ids={r["actual_region_id"] for r in target_rows}
    ref_same=len(ref_ids)==1 and None not in ref_ids; tgt_same=len(tgt_ids)==1 and None not in tgt_ids
    actual_ref=next(iter(ref_ids)) if ref_same else None; actual_tgt=next(iter(tgt_ids)) if tgt_same else None
    ref_sem=region_by_id[actual_ref]["semantic_name"] if actual_ref else None
    tgt_sem=region_by_id[actual_tgt]["semantic_name"] if actual_tgt else None
    semantic_correct=ref_sem==expected["semantic"] and tgt_sem==expected["semantic"]
    if ref_same and tgt_same and semantic_correct:
        classification="REGION_BINDING_ERROR" if (actual_ref!=expected["reference_region_id"] or actual_tgt!=expected["target_region_id"]) else "BINDING_CONSISTENT"
    elif ref_same and tgt_same:
        classification="ANCHOR_PLACEMENT_WRONG"
    else:
        classification="REGION_BBOX_ERROR"
    return {
        "pair_id":pair_id,"anchor_ids":expected["anchor_ids"],
        "reference_same_frame":ref_same,"target_same_frame":tgt_same,
        "old_reference_region_id":expected["reference_region_id"],"old_target_region_id":expected["target_region_id"],
        "actual_reference_region_id":actual_ref,"actual_target_region_id":actual_tgt,
        "expected_semantic_name":expected["semantic"],"actual_reference_semantic_name":ref_sem,
        "actual_target_semantic_name":tgt_sem,"semantic_correct":semantic_correct,
        "classification":classification,
        "binding_reason":"三个锚点均落在同一但语义错误的图框" if classification=="ANCHOR_PLACEMENT_WRONG" else "",
    }


def run_region_rebinding_audit(run_dir: Path) -> dict[str,Any]:
    out=run_dir/"manual_anchor_region_rebinding"; out.mkdir(parents=True,exist_ok=True)
    ref_regions=_read(run_dir/"reference_regions.json")["regions"]
    tgt_regions=_read(run_dir/"target_regions.json")["regions"]
    scan=_read(run_dir/"manual_cluster_disambiguation"/"manual_anchor_scan.json")
    pairs=_read(run_dir/"manual_cluster_disambiguation"/"manual_anchor_pairs.json")
    structure_regions=[]
    for fn in ("reference_region_structure.json","target_region_structure.json"):
        structure_regions.extend(_read(run_dir/"block_xref_audit"/fn)["regions"])
    ref_build={r["region_id"]:r["combined_building_bbox"] for r in structure_regions if r["role"]=="reference" and r.get("combined_building_bbox")}
    tgt_build={r["region_id"]:r["combined_building_bbox"] for r in structure_regions if r["role"]=="target" and r.get("combined_building_bbox")}
    region_by_id={r["region_id"]:r for r in [*ref_regions,*tgt_regions]}
    pair_by={g["pair_id"]:g for g in pairs["groups"]}
    memberships=[]; groups=[]
    for pair_id,expected in EXPECTED.items():
        source=pair_by[pair_id]["pairs"]
        ref_rows=[]; tgt_rows=[]
        for item in source:
            rr=audit_point_membership(item["anchor_id"],item["reference_point"],expected["reference_region_id"],ref_regions,ref_build)
            tr=audit_point_membership(item["anchor_id"],item["target_point"],expected["target_region_id"],tgt_regions,tgt_build)
            ref_rows.append(rr); tgt_rows.append(tr)
            memberships.extend([{"role":"reference",**rr},{"role":"target",**tr}])
        groups.append(classify_group(pair_id,ref_rows,tgt_rows,region_by_id))

    conflicts=[]; corrections=[]; holdout=[]; transforms=[]
    for group in groups:
        if group["classification"]=="REGION_BINDING_ERROR":
            corrections.append({"semantic_name":group["expected_semantic_name"],"old_reference_region_id":group["old_reference_region_id"],
                                "actual_reference_region_id":group["actual_reference_region_id"],"old_target_region_id":group["old_target_region_id"],
                                "actual_target_region_id":group["actual_target_region_id"],"binding_reason":group["binding_reason"],"anchor_ids":group["anchor_ids"],
                                "frame_bbox":{"reference":region_by_id[group["actual_reference_region_id"]]["frame_bbox"],"target":region_by_id[group["actual_target_region_id"]]["frame_bbox"]},
                                "content_bbox":{"reference":region_by_id[group["actual_reference_region_id"]]["content_bbox"],"target":region_by_id[group["actual_target_region_id"]]["content_bbox"]}})
        else:
            conflicts.append({**group,"anchors_to_move":group["anchor_ids"],"move_to_semantic_region":group["expected_semantic_name"],"dwg_modified":False})
        if group["classification"]=="ANCHOR_PLACEMENT_WRONG":
            holdout.append({"pair_id":group["pair_id"],"status":"NOT_EXECUTED_ANCHOR_PLACEMENT_WRONG",
                            "reason":"实际区域语义与锚点 ID 目标语义不一致；不得使用错误图框几何验证目标平移",
                            "holdout_total":0,"holdout_match_count":0,"holdout_match_ratio":None,"holdout_rms":None,
                            "transformed_building_bbox":None,"target_building_bbox":None,"bbox_overlap_ratio":None,
                            "transformed_bbox_inside_actual_target_region":None,"protected_region_intersection":0})
            transforms.append({"pair_id":group["pair_id"],"status":"ANCHOR_PLACEMENT_WRONG","transform":None})

    _write(out/"anchor_region_membership.json",{"anchors":memberships})
    _write(out/"region_binding_conflicts.json",{"groups":groups,"conflicts":conflicts})
    _write(out/"corrected_region_binding.json",{"correction_count":len(corrections),"corrections":corrections,
                                                 "historical_region_files_overwritten":False})
    _write(out/"rebound_holdout_validation.json",{"groups":holdout})
    _write(out/"rebound_coordinate_transforms.json",{"groups":transforms,"final_manifest_created":False})
    ref_path=Path(scan["reference"]["path"]); tgt_path=Path(scan["target"]["path"])
    ref_unchanged=_sha256(ref_path)==scan["reference"]["hash_before"]
    tgt_unchanged=_sha256(tgt_path)==scan["target"]["hash_before"]
    if all(g["classification"]=="ANCHOR_PLACEMENT_WRONG" for g in groups): status="ANCHOR_PLACEMENT_WRONG"
    elif corrections: status="VERIFIED_AFTER_REGION_REBINDING"
    else: status="REGION_REBINDING_BLOCKED"
    result={"phase":"STAGE6-P2.5","status":status,"groups":groups,"region_bbox_error":any(g["classification"]=="REGION_BBOX_ERROR" for g in groups),
            "final_manifest_created":False,"reference_calibration_hash_unchanged":ref_unchanged,
            "target_calibration_hash_unchanged":tgt_unchanged,"target_write":False,"target_save":False,
            "missing_detection_executed":False,"frozen_plan_created":False}
    lines=["# Stage 6-P2.5 人工锚点区域重绑定审计","",f"- 最终状态：`{status}`","- 完全离线；未扫描、修改或保存 DWG。","","| 组 | 原绑定 R/T | 实际 R/T | 实际语义 | 裁决 |","|---|---|---|---|---|"]
    for g in groups:
        lines.append(f"| {g['pair_id']} | {g['old_reference_region_id']}/{g['old_target_region_id']} | {g['actual_reference_region_id']}/{g['actual_target_region_id']} | {g['actual_reference_semantic_name']} / {g['actual_target_semantic_name']} | {g['classification']} |")
    (out/"manual_anchor_region_rebinding_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return result

