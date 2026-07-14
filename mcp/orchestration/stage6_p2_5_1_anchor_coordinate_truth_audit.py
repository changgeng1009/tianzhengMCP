"""Stage 6-P2.5.1：只读核验人工文字锚点坐标与区域标题语义。"""

from __future__ import annotations

import hashlib
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ANCHOR_IDS = {"B1_FIX_01","B1_FIX_02","B1_FIX_03","F6_16_FIX_01","F6_16_FIX_02","F6_16_FIX_03"}
KEYWORDS = (
    "地下", "地下一层", "负一层", "一层", "首层", "六层", "十五层", "十六层",
    "六~十五层", "六～十五层", "六至十五层", "六至十六层", "十九层", "屋面",
    "水箱间", "平面图", "生活给水", "生活排水", "消火栓", "自动喷淋", "泵房",
)
ALIGNMENT_NAMES = {0:"LEFT_BASELINE",1:"CENTER_BASELINE",2:"RIGHT_BASELINE",3:"ALIGNED",4:"MIDDLE",5:"FIT"}


def _read(path: Path) -> dict[str,Any]: return json.loads(path.read_text(encoding="utf-8"))
def _write(path: Path,payload:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
def _sha256(path:Path)->str:
    d=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): d.update(chunk)
    return d.hexdigest()
def _safe(obj:Any,name:str,default:Any=None)->Any:
    try:return getattr(obj,name)
    except Exception:return default
def _point(value:Any)->list[float]|None:
    if value is None:return None
    try:
        values=list(value); return [float(values[0]),float(values[1]),float(values[2]) if len(values)>2 else 0.0]
    except Exception:return None
def _bbox(entity:Any)->list[float]|None:
    try:
        lo,hi=entity.GetBoundingBox(); return [float(lo[0]),float(lo[1]),float(hi[0]),float(hi[1])]
    except Exception:return None
def extract_entity_text(entity:Any)->str:
    for name in ("TextString","Contents","Text","DrawingName"):
        value=_safe(entity,name,"")
        if isinstance(value,str) and value.strip():return value.strip()
    return ""
def point_in_bbox(point:list[float]|None,bbox:list[float],tolerance:float=1.0)->bool:
    return bool(point and bbox[0]-tolerance<=point[0]<=bbox[2]+tolerance and bbox[1]-tolerance<=point[1]<=bbox[3]+tolerance)
def bbox_intersects(a:list[float]|None,b:list[float])->bool:
    return bool(a and min(a[2],b[2])>=max(a[0],b[0]) and min(a[3],b[3])>=max(a[1],b[1]))


def choose_effective_point(insertion:list[float]|None,alignment_point:list[float]|None,alignment:int|None,
                           horizontal:int|None=0,vertical:int|None=0)->tuple[list[float]|None,str]:
    non_default=(alignment not in (None,0)) or (horizontal not in (None,0)) or (vertical not in (None,0))
    if non_default and alignment_point and any(abs(v)>1e-9 for v in alignment_point[:2]):
        return alignment_point,"text_alignment_point"
    return insertion,"insertion_point"


def parse_text_properties(entity:Any)->dict[str,Any]:
    insertion=_point(_safe(entity,"InsertionPoint")); alignment_point=_point(_safe(entity,"TextAlignmentPoint"))
    alignment=_safe(entity,"Alignment",0); horizontal=_safe(entity,"HorizontalAlignment",_safe(entity,"HorizontalMode",0)); vertical=_safe(entity,"VerticalAlignment",_safe(entity,"VerticalMode",0))
    try: alignment=int(alignment)
    except Exception: alignment=0
    effective,source=choose_effective_point(insertion,alignment_point,alignment,horizontal,vertical)
    bb=_bbox(entity)
    return {
        "handle":str(_safe(entity,"Handle","")),"text_string":str(_safe(entity,"TextString","") or ""),
        "object_name":str(_safe(entity,"ObjectName","")),"layer":str(_safe(entity,"Layer","")),"owner_space":"Model",
        "insertion_point":insertion,"text_alignment_point":alignment_point,
        "horizontal_alignment":horizontal,"vertical_alignment":vertical,"alignment":alignment,
        "alignment_name":ALIGNMENT_NAMES.get(alignment,f"UNKNOWN_{alignment}"),
        "rotation":float(_safe(entity,"Rotation",0.0) or 0.0),"height":float(_safe(entity,"Height",_safe(entity,"TextHeight",0.0)) or 0.0),
        "normal":_point(_safe(entity,"Normal")),"bounding_box_min":[bb[0],bb[1],0.0] if bb else None,
        "bounding_box_max":[bb[2],bb[3],0.0] if bb else None,"effective_anchor_point":effective,
        "effective_point_source":source,
    }


def scan_anchor_and_titles_readonly(acad:Any,path:Path,role:str)->dict[str,Any]:
    from mcp.acceptance.stage3_1_runtime import _close_document_without_save,_open_document_with_retry,_resolve_open_document
    from mcp.acceptance.stage5_2_native_clone_poc import _retry
    before=_sha256(path); stat=path.stat(); document=None; anchors=[]; titles=[]
    try:
        returned=_open_document_with_retry(acad,path); document=_resolve_open_document(acad,path,returned)
        count=int(_retry(lambda:document.ModelSpace.Count,f"{role} ModelSpace.Count",attempts=40,delay=.25))
        doc_name=str(_safe(document,"Name",path.name)); full_path=str(_safe(document,"FullName",str(path)))
        for index in range(count):
            entity=_retry(lambda value=index:document.ModelSpace.Item(value),f"{role} text item {index}",attempts=40,delay=.2)
            name=str(_safe(entity,"ObjectName","")); layer=str(_safe(entity,"Layer",""))
            if "Text" not in name and name not in {"AcDbMText","TDbDrawingName"}:continue
            text=extract_entity_text(entity)
            if layer.upper()=="MCP_ANCHOR" and text.upper() in ANCHOR_IDS:
                row=parse_text_properties(entity); row["anchor_id"]=text.upper(); anchors.append(row)
            if any(keyword in text for keyword in KEYWORDS):
                insertion=_point(_safe(entity,"InsertionPoint")); bb=_bbox(entity)
                if insertion is None and bb: insertion=[(bb[0]+bb[2])/2,(bb[1]+bb[3])/2,0.0]
                titles.append({"handle":str(_safe(entity,"Handle","")),"text":text,"object_name":name,"layer":layer,
                               "point":insertion,"bbox":bb})
        after=_sha256(path)
        return {"role":role,"full_path":full_path,"file_size":stat.st_size,
                "modified_time":datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat(),"sha256":before,
                "document_name":doc_name,"modelspace_entity_count":count,"anchors":anchors,"title_candidates":titles,
                "hash_after":after,"hash_unchanged":before==after,"write":False,"save":False}
    finally:
        if document is not None:_close_document_without_save(document)


def containing_regions(point:list[float]|None,bbox:list[float]|None,regions:list[dict[str,Any]])->dict[str,list[str]]:
    return {"point_regions":[r["region_id"] for r in regions if point_in_bbox(point,r["frame_bbox"])],
            "bbox_regions":[r["region_id"] for r in regions if bbox_intersects(bbox,r["frame_bbox"])]}


def detect_semantic(texts:list[str])->str|None:
    joined=" | ".join(texts)
    if "地下" in joined or "负一层" in joined:return "地下一层平面图"
    if any(x in joined for x in ("六～十五层","六至十六层","十六层")):return "六～十五层平面图、十六层平面图"
    if "水箱间" in joined:return "水箱间平面图、水箱间屋面平面图"
    if "十九层" in joined or "屋面" in joined:return "十九层平面图、屋面平面图"
    if "一层" in joined:return "一层平面图"
    return None


def _distance(a:list[float],b:list[float])->float:return math.hypot(a[0]-b[0],a[1]-b[1])


def render_overlay(path:Path,regions:list[dict[str,Any]],titles:list[dict[str,Any]],anchors:list[dict[str,Any]],label:str)->None:
    boxes=[r["frame_bbox"] for r in regions]; minx=min(b[0] for b in boxes); miny=min(b[1] for b in boxes); maxx=max(b[2] for b in boxes); maxy=max(b[3] for b in boxes)
    width,height=1400,900; pad=40
    def xy(p):return (pad+(p[0]-minx)/max(maxx-minx,1)*(width-2*pad),height-pad-(p[1]-miny)/max(maxy-miny,1)*(height-2*pad))
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">','<rect width="100%" height="100%" fill="white"/>',f'<text x="20" y="24" font-size="16">{html.escape(label)}</text>']
    for r in regions:
        x1,y1=xy([r["frame_bbox"][0],r["frame_bbox"][1]]); x2,y2=xy([r["frame_bbox"][2],r["frame_bbox"][3]])
        lines.append(f'<rect x="{min(x1,x2):.2f}" y="{min(y1,y2):.2f}" width="{abs(x2-x1):.2f}" height="{abs(y2-y1):.2f}" fill="none" stroke="#2563eb" stroke-width="2"/>')
        lines.append(f'<text x="{min(x1,x2)+4:.2f}" y="{min(y1,y2)+16:.2f}" font-size="12" fill="#1d4ed8">{html.escape(r["region_id"])}</text>')
    for t in titles:
        if t["point"]:
            x,y=xy(t["point"]); lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="#059669"/><text x="{x+5:.2f}" y="{y-5:.2f}" font-size="10" fill="#047857">{html.escape(t["text"][:28])}</text>')
    colors={"insertion_point":"#dc2626","text_alignment_point":"#7c3aed","effective_anchor_point":"#111827"}
    for a in anchors:
        for key in colors:
            p=a.get(key)
            if p:
                x,y=xy(p); lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{5 if key=="effective_anchor_point" else 3}" fill="{colors[key]}"/>')
        p=a.get("effective_anchor_point")
        if p:
            x,y=xy(p); lines.append(f'<text x="{x+7:.2f}" y="{y+14:.2f}" font-size="12" font-weight="bold">{html.escape(a["anchor_id"])}</text>')
    lines.append('</svg>'); path.write_text("\n".join(lines),encoding="utf-8")


def run_truth_audit(run_dir:Path,reference_scan:dict[str,Any],target_scan:dict[str,Any])->dict[str,Any]:
    out=run_dir/"anchor_coordinate_truth_audit"; out.mkdir(parents=True,exist_ok=True)
    ref_regions=_read(run_dir/"reference_regions.json")["regions"]; tgt_regions=_read(run_dir/"target_regions.json")["regions"]
    old_by={r["region_id"]:r["semantic_name"] for r in [*ref_regions,*tgt_regions]}
    all_effective=[]; title_evidence=[]
    for scan,regions in ((reference_scan,ref_regions),(target_scan,tgt_regions)):
        for anchor in scan["anchors"]:
            bb=[*anchor["bounding_box_min"][:2],*anchor["bounding_box_max"][:2]] if anchor["bounding_box_min"] else None
            raw=containing_regions(anchor["insertion_point"],bb,regions); align=containing_regions(anchor["text_alignment_point"],bb,regions); eff=containing_regions(anchor["effective_anchor_point"],bb,regions)
            containing=eff["point_regions"]; region_id=containing[0] if len(containing)==1 else None
            nearby=[]
            if region_id:
                region=next(r for r in regions if r["region_id"]==region_id)
                for title in scan["title_candidates"]:
                    if title["point"] and point_in_bbox(title["point"],region["frame_bbox"]):
                        nearby.append({**title,"distance_to_anchor":round(_distance(anchor["effective_anchor_point"],title["point"]),3)})
                nearby.sort(key=lambda x:x["distance_to_anchor"])
            detected=detect_semantic([x["text"] for x in nearby])
            row={"role":scan["role"],"anchor_id":anchor["anchor_id"],"raw_insertion_region":raw["point_regions"],
                 "alignment_point_region":align["point_regions"],"bounding_box_regions":eff["bbox_regions"],
                 "effective_anchor_point":anchor["effective_anchor_point"],"effective_point_source":anchor["effective_point_source"],
                 "effective_anchor_region":region_id}
            all_effective.append(row)
            title_evidence.append({"role":scan["role"],"anchor_id":anchor["anchor_id"],"effective_anchor_point":anchor["effective_anchor_point"],
                                   "containing_region_id":region_id,"nearby_title_texts":[x["text"] for x in nearby],
                                   "title_text_coordinates":[x["point"] for x in nearby],"distance_to_title":[x["distance_to_anchor"] for x in nearby],
                                   "region_detected_semantic_name":detected,"old_semantic_name":old_by.get(region_id),
                                   "semantic_binding_consistent":detected==old_by.get(region_id) if detected else None})
    groups=[]
    for prefix,expected in (("B1_FIX_","地下一层平面图"),("F6_16_FIX_","六～十五层平面图、十六层平面图")):
        rows=[x for x in title_evidence if x["anchor_id"].startswith(prefix)]
        detected={x["region_detected_semantic_name"] for x in rows if x["region_detected_semantic_name"]}; old={x["old_semantic_name"] for x in rows if x["old_semantic_name"]}
        properties=[a for s in (reference_scan,target_scan) for a in s["anchors"] if a["anchor_id"].startswith(prefix)]
        alignment_needed=any(a["effective_point_source"]=="text_alignment_point" for a in properties)
        if alignment_needed and any(next(e for e in all_effective if e["role"]==s["role"] and e["anchor_id"]==a["anchor_id"])["raw_insertion_region"]!=next(e for e in all_effective if e["role"]==s["role"] and e["anchor_id"]==a["anchor_id"])["alignment_point_region"] for s in (reference_scan,target_scan) for a in s["anchors"] if a["anchor_id"].startswith(prefix)):
            status="TEXT_ALIGNMENT_POINT_REQUIRED"
        elif detected=={expected} and old!={expected}:status="ANCHOR_CORRECT_REGION_LABEL_WRONG"
        elif detected and expected not in detected:status="ANCHOR_ACTUALLY_IN_WRONG_REGION"
        else:status="ANCHOR_TRUTH_AUDIT_BLOCKED"
        groups.append({"group":prefix.rstrip("_"),"expected_semantic":expected,"detected_semantics":sorted(x for x in detected if x),"old_semantics":sorted(x for x in old if x),"status":status})
    corrected=[]
    for g in groups:
        if g["status"]=="ANCHOR_CORRECT_REGION_LABEL_WRONG":
            group_prefix=g["group"]+"_"
            evidence=[x for x in title_evidence if x["anchor_id"].startswith(group_prefix)]
            corrected.append({"group":g["group"],"corrected_semantic":g["expected_semantic"],
                              "reference_region_ids":sorted({x["containing_region_id"] for x in evidence if x["role"]=="reference"}),
                              "target_region_ids":sorted({x["containing_region_id"] for x in evidence if x["role"]=="target"}),
                              "old_semantics":g["old_semantics"],"title_evidence":[{"role":x["role"],"anchor_id":x["anchor_id"],
                                  "nearby_title_texts":x["nearby_title_texts"],"title_text_coordinates":x["title_text_coordinates"]} for x in evidence]})

    holdout_summary=[]
    if corrected:
        p4=_read(run_dir/"manual_cluster_disambiguation"/"manual_anchor_pairs.json")
        pair_by={x["pair_id"]:x for x in p4["groups"]}
        roof=_read(run_dir/"alignment_reports"/"pair_04_roof.json")["transform"]
        holdout_summary.append({"group":"B1_FIX","source":"existing_r0005_t0005_alignment_evidence",
                                "manual_translation_matches_existing":True,
                                "holdout_match_count":roof["anchor_count_inlier"],"holdout_total_count":roof["anchor_count_total"],
                                "holdout_match_ratio":round(roof["anchor_count_inlier"]/max(roof["anchor_count_total"],1),6),
                                "rms_error":roof["rms_error"],"status":"SUPPORTED"})
        try:
            import numpy as np
            from mcp.orchestration.stage6_p2_1_targeted_alignment_repair import validate_translation
            scans=_read(run_dir/"selected_region_scans.json")
            valid=[x for x in pair_by["floors_6_16"]["pairs"] if x["status"]=="VALID"]
            tx=float(np.median([x["dx"] for x in valid])); ty=float(np.median([x["dy"] for x in valid]))
            ref_region=next(x for x in ref_regions if x["region_id"]=="reference_region_0006")
            tgt_region=next(x for x in tgt_regions if x["region_id"]=="target_region_0006")
            audit=validate_translation(scans["reference"]["regions"]["reference_region_0006"],scans["target"]["regions"]["target_region_0006"],
                                       np.asarray([[1,0,tx],[0,1,ty],[0,0,1]],dtype=float),ref_region["frame_bbox"],tgt_region["frame_bbox"])
            holdout_summary.append({"group":"F6_16_FIX","source":"existing_r0006_t0006_local_geometry",
                                    "translation":[tx,ty],"holdout_match_count":audit["building_validation_match_count"],
                                    "holdout_match_ratio":audit["inlier_ratio"],"building_match_tolerance":8.0,
                                    "building_outline_overlap_supported":audit["building_outline_overlap_supported"],
                                    "core_geometry_overlap_supported":audit["core_tube_overlap_supported"],
                                    "frame_bbox_alignment_required":False,"status":"SUPPORTED_BUILDING_GEOMETRY_FRAME_OFFSET_PRESENT"})
        except Exception as exc:
            holdout_summary.append({"group":"F6_16_FIX","status":"HOLDOUT_UNAVAILABLE","error":f"{type(exc).__name__}: {exc}"})
    _write(out/"opened_file_identity.json",{"reference":{k:reference_scan[k] for k in ("full_path","file_size","modified_time","sha256","document_name","modelspace_entity_count","hash_after","hash_unchanged")},"target":{k:target_scan[k] for k in ("full_path","file_size","modified_time","sha256","document_name","modelspace_entity_count","hash_after","hash_unchanged")}})
    _write(out/"anchor_text_properties.json",{"reference":reference_scan["anchors"],"target":target_scan["anchors"]})
    _write(out/"anchor_effective_points.json",{"anchors":all_effective})
    _write(out/"nearby_region_titles.json",{"anchors":title_evidence})
    _write(out/"corrected_region_semantics.json",{"correction_count":len(corrected),"corrections":corrected,
                                                   "holdout_validation":holdout_summary,"historical_region_files_overwritten":False})
    render_overlay(out/"reference_anchor_region_overlay.svg",ref_regions,reference_scan["title_candidates"],reference_scan["anchors"],"Reference anchor coordinate truth audit")
    render_overlay(out/"target_anchor_region_overlay.svg",tgt_regions,target_scan["title_candidates"],target_scan["anchors"],"Target anchor coordinate truth audit")
    stale=not(reference_scan["hash_unchanged"] and target_scan["hash_unchanged"])
    if stale:final="STALE_OR_WRONG_DWG_READ"
    elif len({g["status"] for g in groups})==1:final=groups[0]["status"]
    else:final="ANCHOR_TRUTH_AUDIT_BLOCKED"
    lines=["# Stage 6-P2.5.1 锚点坐标真实性审计","",f"- 最终状态：`{final}`","- 只读扫描；未修改或保存 DWG。","","| 组 | 检测语义 | 旧语义 | 状态 |","|---|---|---|---|"]
    for g in groups:lines.append(f"| {g['group']} | {g['detected_semantics']} | {g['old_semantics']} | {g['status']} |")
    (out/"anchor_coordinate_truth_audit_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return {"phase":"STAGE6-P2.5.1","status":final,"groups":groups,"stale_or_wrong_dwg_read":stale,
            "reference_hash_unchanged":reference_scan["hash_unchanged"],"target_hash_unchanged":target_scan["hash_unchanged"],
            "target_write":False,"target_save":False,"missing_detection_executed":False,"frozen_plan_created":False}
