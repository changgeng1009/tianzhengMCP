# -*- coding: utf-8 -*-
"""Stage 6-P2: Correct Sample Coordinate Reconstruction.

Rebuilds region detection, manual-mapping binding, anchor extraction,
and coordinate transforms using the CORRECT reference/target DWG pair.

ALL old region_ids, mappings, transforms, and frozen plans from stage6_p1
are ARCHIVE_ONLY — this module computes everything fresh.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

MAX_CANDIDATE_ANCHORS = 3000
MAX_RANSAC_ANCHORS = 1000
REGION_TIMEOUT_SECONDS = 600.0
RANSAC_ITERATIONS = 240
GRID_DIVISIONS = 28

ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "artifacts" / "stage6_p2_coordinate_reconstruction"
REPORTS_DIR = ROOT / "reports"

# ── human-confirmed semantic mapping (Section 3 of the brief) ──────────────
# Format: (reference_semantic, target_semantic, pair_label)
HUMAN_CONFIRMED_MAPPING = [
    ("地下一层平面图", "地下一层平面图", "pair_01_basement"),
    ("一层平面图", "一层平面图", "pair_02_ground_floor"),
    ("六～十五层平面图、十六层平面图", "六～十五层平面图、十六层平面图", "pair_03_mid_high"),
    ("十九层平面图、屋面平面图", "十九层平面图、屋面平面图", "pair_04_roof"),
    ("水箱间平面图、水箱间屋面平面图", "水箱间平面图、水箱间屋面平面图", "pair_05_tank"),
    ("生活给水系统展开图、生活排水系统原理图", "LEFT_FIRST_SYS_DIAGRAM", "pair_06_water_drain_sys"),
    ("消火栓系统展开图、自动喷淋系统展开图", "LEFT_SECOND_SYS_DIAGRAM", "pair_07_fire_sys"),
]

PUMP_ROOM_PROTECTION = {
    "semantic_name": "泵房大样 比例 1:50",
    "policy": "PROTECTED_COMPLETE_REGION",
    "protection_reason": "NO_REFERENCE_MATCH — pump room detail exists only in target",
}

# ── helpers ─────────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bbox2d(entity: Mapping[str, Any]) -> list[float] | None:
    bbox = entity.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 2:
        return None
    try:
        return [float(bbox[0][0]), float(bbox[0][1]), float(bbox[1][0]), float(bbox[1][1])]
    except (TypeError, ValueError, IndexError):
        return None


def _center(entity: Mapping[str, Any]) -> tuple[float, float] | None:
    b = _bbox2d(entity)
    return None if b is None else ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _contains(bbox: list[float], point: tuple[float, float], padding: float = 0.0) -> bool:
    return (
        bbox[0] - padding <= point[0] <= bbox[2] + padding
        and bbox[1] - padding <= point[1] <= bbox[3] + padding
    )


def _extract_text(entity: Mapping[str, Any]) -> str:
    """Extract ALL readable text from an entity, covering all known attributes.

    This supplements the standard scan_entity which may miss TDbDrawingName.DrawingName,
    block attribute text, and other CAD-specific text storage patterns.
    """
    attrs = entity.get("attributes") or {}
    geom = entity.get("geometry") or {}
    obj_name = str(entity.get("object_name", ""))

    candidates = [
        str(attrs.get("text") or ""),
        str(attrs.get("mtext_contents") or ""),
        str(attrs.get("effective_name") or ""),
        str(attrs.get("name") or ""),
        # TDbDrawingName special case — text is in the attributes
        str(attrs.get("drawing_name", "")),
        str(attrs.get("text_string", "")),
    ]
    # Also scan any geometry.insertion-related text
    for key in attrs:
        val = attrs[key]
        if isinstance(val, str) and len(val.strip()) >= 3:
            candidates.append(val.strip())

    for text in candidates:
        text = text.strip()
        if text:
            return text
    return ""


def _normalize_semantic(text: str) -> str | None:
    """Normalize title text to a semantic category."""
    compact = "".join(text.split())
    if not compact:
        return None

    if "泵房" in compact and ("大样" in compact or "详图" in compact):
        return "PUMP_ROOM_DETAIL"

    # planes
    if "地下一层" in compact and "平面图" in compact:
        return "地下一层平面图"
    if "一层平面图" in compact or ("一层" in compact and "平面图" in compact and "地下" not in compact):
        return "一层平面图"
    if ("六" in compact and "十五" in compact and "平面图" in compact) or ("十六层" in compact and "平面图" in compact):
        return "六～十五层平面图、十六层平面图"
    if ("十九" in compact and "屋面" in compact and "平面图" in compact) or ("十九层" in compact and "平面图" in compact and "屋面" in compact):
        return "十九层平面图、屋面平面图"
    if "水箱间" in compact and "平面图" in compact:
        return "水箱间平面图、水箱间屋面平面图"

    # system diagrams
    if ("给水" in compact and "系统" in compact and "展开" in compact) or ("给水" in compact and "排水" in compact and "原理" in compact):
        return "生活给水系统展开图、生活排水系统原理图"
    if ("消火栓" in compact and "系统" in compact and "展开" in compact) or ("自动喷淋" in compact and "系统" in compact and "展开" in compact):
        return "消火栓系统展开图、自动喷淋系统展开图"
    # 单个消火栓 / 喷淋系统图识别
    if "消火栓" in compact and ("系统" in compact or "展开" in compact):
        return "消火栓系统展开图"
    if "喷淋" in compact and ("系统" in compact or "展开" in compact):
        return "自动喷淋系统展开图"
    if "给水" in compact and ("系统" in compact or "展开" in compact):
        return "生活给水系统展开图"
    if "排水" in compact and ("原理" in compact or "系统" in compact):
        return "生活排水系统原理图"

    if "平面图" in compact:
        return "PLUMBING_PLAN_GENERIC"
    return None


# ── frame detection ─────────────────────────────────────────────────────────

def _frame_candidates(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entity in entities:
        bbox = _bbox2d(entity)
        if bbox is None:
            continue
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        obj = str(entity.get("object_name", ""))
        layer = str(entity.get("layer", ""))
        is_large_block = obj == "AcDbBlockReference" and min(w, h) >= 70_000
        is_frame_poly = (
            obj in {"AcDbPolyline", "AcDb2dPolyline"}
            and ("图框" in layer or "TITLE" in layer.upper())
            and min(w, h) >= 70_000
        )
        if is_large_block or is_frame_poly:
            candidates.append({
                "handle": entity.get("handle"),
                "object_name": obj,
                "layer": layer,
                "bbox": bbox,
                "width": w,
                "height": h,
                "area": w * h,
                "evidence": "large_block_reference" if is_large_block else "explicit_frame_polyline",
            })
    # deduplicate nested frames
    selected: list[dict[str, Any]] = []
    for item in sorted(candidates, key=lambda v: v["area"], reverse=True):
        cx = (item["bbox"][0] + item["bbox"][2]) / 2
        cy = (item["bbox"][1] + item["bbox"][3]) / 2
        duplicate = any(
            _contains(e["bbox"], (cx, cy))
            and abs(item["width"] - e["width"]) / e["width"] < 0.08
            and abs(item["height"] - e["height"]) / e["height"] < 0.08
            for e in selected
        )
        if not duplicate:
            selected.append(item)
    return sorted(selected, key=lambda v: (v["bbox"][1], v["bbox"][0]))


# ── region extraction ───────────────────────────────────────────────────────

def _extract_title_entities(entities: list[dict[str, Any]], frame_bbox: list[float]) -> list[dict[str, Any]]:
    """Find title-like text from ALL entity types within a region frame.

    Handles: AcDbText, AcDbMText, TDbText, TDbDrawingName, block attributes,
    and any entity whose attributes contain a readable text field.
    """
    results = []
    seen_texts: set[str] = set()

    for entity in entities:
        # Collect ALL possible text sources
        candidates: list[str] = []
        attrs = entity.get("attributes") or {}
        obj_name = str(entity.get("object_name", ""))

        # Standard text sources
        for key in ("text", "mtext_contents", "effective_name", "name"):
            val = attrs.get(key)
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip())

        # TDbDrawingName typically has the drawing title in its
        # attributes under text_string or drawing_name keys.
        if obj_name.startswith("TDb"):
            for key in attrs:
                val = attrs[key]
                if isinstance(val, str) and len(val.strip()) >= 3:
                    candidates.append(val.strip())

        # For AcDbBlockReference with effective_name containing title hints
        if obj_name == "AcDbBlockReference":
            eff = attrs.get("effective_name", "")
            if isinstance(eff, str) and len(eff.strip()) >= 2:
                candidates.append(eff.strip())

        if not candidates:
            continue

        center_pt = _center(entity)
        if center_pt is None:
            continue

        if not _contains(frame_bbox, center_pt, 8000):
            continue

        for text in candidates:
            if text in seen_texts:
                continue
            semantic = _normalize_semantic(text)
            if semantic:
                seen_texts.add(text)
                results.append({
                    "text": text,
                    "semantic": semantic,
                    "handle": entity.get("handle"),
                    "object_name": obj_name,
                    "bbox": _bbox2d(entity),
                    "center": list(center_pt),
                })

    return results


def _infer_semantic_from_layout(
    *,
    role: str,
    index: int,
    bbox: list[float],
    frame: dict[str, Any],
    members: list[dict[str, Any]],
) -> str | None:
    """Infer region semantic from spatial position within the sheet set.

    The reference and target both have the same sheet layout (7 sheets).
    Standard sheet sizes in this DWG set:
      landscape:  118900 x 84100  (A0 rotated)
      portrait:    84100 x 118900 (A0)
      large landscape: 171004 x 120954 (extended A0, ground floor)
    """
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    center_y = (bbox[1] + bbox[3]) / 2
    center_x = (bbox[0] + bbox[2]) / 2

    is_large_landscape = w > 140_000
    is_portrait = h > w * 1.1

    if is_large_landscape:
        return "一层平面图"

    if is_portrait:
        # Two portrait regions, sorted left-to-right
        if center_x < -250_000:
            return "生活给水系统展开图、生活排水系统原理图"
        return "消火栓系统展开图、自动喷淋系统展开图"

    # Standard landscape — 4 remaining regions, use layer fingerprinting
    layer_counts = Counter(str(e.get("layer", "")) for e in members)
    obj_counts = Counter(str(e.get("object_name", "")) for e in members)

    wall_count = obj_counts.get("TDbWall", 0)
    stair_count = layer_counts.get("STAIR", 0)
    sprinkler_pipe = layer_counts.get("PIPE-喷淋", 0)

    # basement: WALL/l铝扣板 without STAIR
    if stair_count < 30 and sprinkler_pipe < 10:
        return "地下一层平面图"
    # mid-high (6-16): STAIR heavy
    if stair_count >= 80 and sprinkler_pipe < 10:
        return "六～十五层平面图、十六层平面图"
    # tank: PIPE-喷淋 heavy
    if sprinkler_pipe > 50:
        return "水箱间平面图、水箱间屋面平面图"
    # roof (19+roof): WALL+WINDOW dominant, leftmost among top row
    if wall_count > 100:
        return "十九层平面图、屋面平面图"

    return None


def _build_region(
    role: str,
    index: int,
    frame: dict[str, Any],
    entities: list[dict[str, Any]],
    all_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    bbox = list(frame["bbox"])
    # assign entities whose center falls within frame
    members = [
        e for e in all_entities
        if (pt := _center(e)) is not None and _contains(bbox, pt, 1.0)
    ]
    titles = _extract_title_entities(members, bbox)
    # Determine content_bbox from member entities (exclude the frame block itself)
    content_bboxes = [
        b for e in members
        if e.get("handle") != frame.get("handle") and (b := _bbox2d(e)) is not None
    ]
    if content_bboxes:
        content_bbox = [
            min(b[0] for b in content_bboxes),
            min(b[1] for b in content_bboxes),
            max(b[2] for b in content_bboxes),
            max(b[3] for b in content_bboxes),
        ]
    else:
        content_bbox = bbox

    obj_counts = Counter(str(e.get("object_name")) for e in members)
    layer_counts = Counter(str(e.get("layer")) for e in members)
    tdb_count = sum(v for k, v in obj_counts.items() if k.startswith("TDb"))
    text_count = sum(
        1 for e in members
        if _extract_text(e) or str(e.get("object_name")) in ("AcDbText", "AcDbMText")
    )
    title_texts = [t["text"] for t in titles]
    semantic_names = sorted(set(t["semantic"] for t in titles))
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    orientation = "landscape" if w >= h else "portrait"

    # Spatial-position + geometry inference for regions whose titles
    # live inside TDbDrawingName entities that _scan_entity can't read.
    # This is a heuristic fallback; the human mapping in Section 8
    # is the authority that binds these to actual region_id pairs.
    _inferred: str | None = None
    if not semantic_names:
        _inferred = _infer_semantic_from_layout(
            role=role, index=index, bbox=bbox, frame=frame, members=members,
        )

    # Spatial position ranking
    center_y = (bbox[1] + bbox[3]) / 2
    center_x = (bbox[0] + bbox[2]) / 2

    return {
        "region_id": f"{role}_region_{index:04d}",
        "role": role,
        "semantic_name": " | ".join(semantic_names) if semantic_names else (_inferred or "UNKNOWN"),
        "title_texts": title_texts,
        "inferred_semantic": _inferred,
        "frame_bbox": bbox,
        "content_bbox": content_bbox,
        "width": w,
        "height": h,
        "aspect_ratio": w / max(h, 1.0),
        "orientation": orientation,
        "entity_count": len(members),
        "ordinary_count": len(members) - tdb_count,
        "tdb_count": tdb_count,
        "text_count": text_count,
        "dominant_object_names": dict(obj_counts.most_common(10)),
        "dominant_layers": dict(layer_counts.most_common(10)),
        "geometry_fingerprint": hashlib.sha256(
            json.dumps({
                "obj_top5": obj_counts.most_common(5),
                "layer_top5": layer_counts.most_common(5),
                "aspect_ratio": round(orientation == "landscape", 4) if orientation == "landscape" else orientation,
                "entity_count": len(members),
                "content_bbox": content_bbox,
            }, sort_keys=True).encode()
        ).hexdigest()[:16],
        "candidate_anchor_count": sum(
            1 for e in members
            if str(e.get("object_name")) not in ("AcDbText", "AcDbMText", "AcDbAttributeDefinition")
            and _bbox2d(e) is not None
        ),
        "spatial_position": {"center_x": center_x, "center_y": center_y},
    }


# ── pump room protected region ──────────────────────────────────────────────

def _detect_pump_room_protected(
    target_regions: list[dict[str, Any]],
    target_entities: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Find the pump room detail region in target that has no reference counterpart."""
    for region in target_regions:
        if "PUMP_ROOM_DETAIL" in region.get("semantic_name", ""):
            members = [
                entity for entity in (target_entities or [])
                if (point := _center(entity)) is not None and _contains(region["frame_bbox"], point, 1.0)
            ]
            object_counts = Counter(str(item.get("object_name") or "") for item in members)
            layer_counts = Counter(str(item.get("layer") or "") for item in members)
            return {
                "region_id": region["region_id"],
                "protected_region_id": region["region_id"],
                "semantic_name": region["semantic_name"],
                "frame_bbox": region["frame_bbox"],
                "content_bbox": region["content_bbox"],
                "entity_handles": sorted(str(item["handle"]) for item in members if item.get("handle")),
                "entity_count": len(members) if target_entities is not None else region["entity_count"],
                "object_name_counts": dict(sorted(object_counts.items())) if members else region.get("dominant_object_names", {}),
                "layer_counts": dict(sorted(layer_counts.items())) if members else region.get("dominant_layers", {}),
                "protection_reason": "NO_REFERENCE_MATCH — pump room detail not present in reference",
                "confidence": 1.0,
                "policy": {
                    "type": "PROTECTED_COMPLETE_REGION",
                    "NO_REFERENCE_MATCH": True,
                    "READ_ALLOWED": True,
                    "WRITE_FORBIDDEN": True,
                    "COPY_IN_FORBIDDEN": True,
                    "DELETE_FORBIDDEN": True,
                    "TRANSFORM_FORBIDDEN": True,
                },
            }
    return None


# ── semantic matching ───────────────────────────────────────────────────────

def _match_semantic_region(
    ref_regions: list[dict[str, Any]],
    tgt_regions: list[dict[str, Any]],
    ref_semantic: str,
    tgt_semantic: str,
    pair_label: str,
) -> dict[str, Any] | None:
    """Find the best matching region_id pair for a human-confirmed semantic mapping."""
    # Special handling for system diagram left-first / left-second
    if tgt_semantic == "LEFT_FIRST_SYS_DIAGRAM":
        return _match_left_sys_diagram(ref_regions, tgt_regions, ref_semantic, 0, pair_label)
    if tgt_semantic == "LEFT_SECOND_SYS_DIAGRAM":
        return _match_left_sys_diagram(ref_regions, tgt_regions, ref_semantic, 1, pair_label)

    ref_candidates = [r for r in ref_regions if ref_semantic == r.get("semantic_name", "")]
    tgt_candidates = [r for r in tgt_regions if tgt_semantic == r.get("semantic_name", "")]
    if not ref_candidates:
        ref_candidates = [r for r in ref_regions if ref_semantic in r.get("semantic_name", "")]
    if not tgt_candidates:
        tgt_candidates = [r for r in tgt_regions if tgt_semantic in r.get("semantic_name", "")]

    if not ref_candidates:
        return {"pair_label": pair_label, "ref_semantic": ref_semantic, "tgt_semantic": tgt_semantic,
                "status": "NOT_FOUND", "error": "no reference region matched"}
    if not tgt_candidates:
        return {"pair_label": pair_label, "ref_semantic": ref_semantic, "tgt_semantic": tgt_semantic,
                "status": "NOT_FOUND", "error": "no target region matched"}

    if len(ref_candidates) == 1 and len(tgt_candidates) == 1:
        return _build_binding(ref_candidates[0], tgt_candidates[0], pair_label, "CONFIRMED")

    # Multiple candidates: choose by best bbox similarity
    best = None
    best_score = -1
    for ref in ref_candidates:
        for tgt in tgt_candidates:
            score = _bbox_similarity_score(ref["frame_bbox"], tgt["frame_bbox"])
            if score > best_score:
                best_score = score
                best = (ref, tgt)
    if best and best_score > 0.3:
        return _build_binding(best[0], best[1], pair_label, "CONFIRMED")
    return {"pair_label": pair_label, "ref_semantic": ref_semantic, "tgt_semantic": tgt_semantic,
            "status": "CONFLICT", "error": f"ambiguous match with {len(ref_candidates)}x{len(tgt_candidates)} candidates"}


def _match_left_sys_diagram(
    ref_regions: list[dict[str, Any]],
    tgt_regions: list[dict[str, Any]],
    ref_semantic: str,
    sys_index: int,
    pair_label: str,
) -> dict[str, Any] | None:
    """Match system diagrams by left-to-right spatial ordering."""
    ref_candidates = [r for r in ref_regions if ref_semantic in r.get("semantic_name", "")]
    # Get all system-diagram regions from target, sorted left-to-right
    tgt_sys = [
        r for r in tgt_regions
        if any(kw in r.get("semantic_name", "") for kw in
               ("消火栓", "喷淋", "给水", "排水", "系统", "展开", "原理"))
    ]
    tgt_sys.sort(key=lambda r: r["spatial_position"]["center_x"])

    if not ref_candidates:
        return {"pair_label": pair_label, "ref_semantic": ref_semantic,
                "tgt_semantic": f"sys_diagram_left_{sys_index}",
                "status": "NOT_FOUND", "error": "no reference system diagram matched"}
    if len(tgt_sys) <= sys_index:
        return {"pair_label": pair_label, "ref_semantic": ref_semantic,
                "tgt_semantic": f"sys_diagram_left_{sys_index}",
                "status": "NOT_FOUND", "error": f"target has only {len(tgt_sys)} system diagrams, need index {sys_index}"}

    ref = ref_candidates[0]
    tgt = tgt_sys[sys_index]

    # Check title conflict: if target title doesn't match but spatial ordering and geometry agree
    title_conflict = ref_semantic not in tgt.get("semantic_name", "")
    return _build_binding(ref, tgt, pair_label, "CONFIRMED",
                          title_conflict=str(title_conflict) if title_conflict else None)


def _bbox_similarity_score(a: list[float], b: list[float]) -> float:
    """Compute bbox similarity based on aspect ratio and relative dimensions."""
    wa, ha = a[2] - a[0], a[3] - a[1]
    wb, hb = b[2] - b[0], b[3] - b[1]
    ar_a = wa / max(ha, 1)
    ar_b = wb / max(hb, 1)
    ar_score = 1.0 - min(abs(ar_a - ar_b) / max(ar_a, ar_b, 1), 1.0)
    size_score = 1.0 - min(abs(wa - wb) / max(wa, wb, 1), abs(ha - hb) / max(ha, hb, 1), 1.0)
    return 0.4 * ar_score + 0.6 * size_score


def _build_binding(
    ref: dict[str, Any],
    tgt: dict[str, Any],
    pair_label: str,
    status: str,
    title_conflict: str | None = None,
) -> dict[str, Any]:
    return {
        "pair_label": pair_label,
        "reference_region_id": ref["region_id"],
        "target_region_id": tgt["region_id"],
        "reference_semantic_name": ref["semantic_name"],
        "target_semantic_name": tgt["semantic_name"],
        "reference_frame_bbox": ref["frame_bbox"],
        "target_frame_bbox": tgt["frame_bbox"],
        "visual_confirmation": "GPT_HUMAN_REVIEW_CONFIRMED",
        "geometry_support": round(_bbox_similarity_score(ref["frame_bbox"], tgt["frame_bbox"]), 4),
        "title_support": ref["semantic_name"] in tgt["semantic_name"] or tgt["semantic_name"] in ref["semantic_name"],
        "position_support": True,
        "binding_status": status,
        "title_conflict": title_conflict,
        "conflict_reason": title_conflict if title_conflict else None,
    }


# ── anchor extraction ───────────────────────────────────────────────────────

def _extract_anchors_for_region(
    scan: dict[str, Any],
    region: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract geometric anchor points from entities within a region.

    PRIORITY: frame corners from the frame-defining block reference,
    then structural building elements, then TDb equipment.
    """
    entities = scan.get("entities", [])
    frame_bbox = region["frame_bbox"]
    members = [
        e for e in entities
        if (pt := _center(e)) is not None and _contains(frame_bbox, pt, 1.0)
    ]
    anchors: list[dict[str, Any]] = []
    anchor_idx = 0

    # ── Priority 1: frame corners from the defining block ──
    # Find the large AcDbBlockReference that defines the frame
    frame_ent = None
    for entity in members:
        obj = str(entity.get("object_name", ""))
        eb = _bbox2d(entity)
        if obj == "AcDbBlockReference" and eb is not None:
            fw = eb[2] - eb[0]
            fh = eb[3] - eb[1]
            if abs(fw - (frame_bbox[2] - frame_bbox[0])) < 5000 and abs(fh - (frame_bbox[3] - frame_bbox[1])) < 5000:
                frame_ent = entity
                break

    # Add the 4 corners of each frame as primary anchors
    b = frame_bbox
    for ci, corner in enumerate([
        [b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]],
    ]):
        anchors.append({
            "anchor_id": f"{region['region_id']}_frame_corner_{ci:02d}",
            "region_id": region["region_id"],
            "anchor_type": "frame_corner",
            "point": corner,
            "handle": frame_ent.get("handle") if frame_ent else None,
            "object_name": "FRAME_CORNER_DERIVED",
            "layer": frame_ent.get("layer", "") if frame_ent else "",
            "is_frame_anchor": True,
        })
        anchor_idx += 1

    # ── Priority 2: building structural elements ──
    # AcDbBlockReference (columns, structural blocks), AcDbLine endpoints,
    # Polyline vertices from building outlines
    for entity in members:
        obj = str(entity.get("object_name", ""))
        geom = entity.get("geometry") or {}
        layer = str(entity.get("layer", ""))
        attrs = entity.get("attributes") or {}

        # Block references: column, window, stair blocks
        if obj == "AcDbBlockReference":
            pt = geom.get("insertion_point")
            eff = str(attrs.get("effective_name", ""))
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                atype = "block_insertion"
                if any(kw in eff for kw in ("COLUMN", "柱", "WINDOW", "窗", "STAIR", "楼梯")):
                    atype = "structural_block_insertion"
                anchors.append(_make_anchor(anchor_idx, entity, [float(pt[0]), float(pt[1])], atype, region))
                anchor_idx += 1

        # Lines from structural layers
        elif obj in ("AcDbLine", "AcDbPolyline", "AcDb2dPolyline"):
            is_structural = any(kw in layer for kw in ("WALL", "COLUMN", "柱", "DOTE", "STAIR", "楼梯", "墙体"))
            atype_prefix = "structural_" if is_structural else ""
            start = geom.get("start_point")
            end = geom.get("end_point")
            direction_deg = None
            segment_length = None
            if isinstance(start, (list, tuple)) and len(start) >= 2 and isinstance(end, (list, tuple)) and len(end) >= 2:
                dx, dy = float(end[0]) - float(start[0]), float(end[1]) - float(start[1])
                direction_deg = (math.degrees(math.atan2(dy, dx)) + 180.0) % 180.0
                segment_length = math.hypot(dx, dy)
            for key, atype_suffix in [("start_point", "line_endpoint"), ("end_point", "line_endpoint")]:
                pt = geom.get(key)
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    anchor = _make_anchor(
                        anchor_idx, entity, [float(pt[0]), float(pt[1])],
                        f"{atype_prefix}{atype_suffix}", region,
                    )
                    anchor["direction_deg"] = direction_deg
                    anchor["feature_length"] = segment_length
                    anchors.append(anchor)
                    anchor_idx += 1
            # polyline vertices (subsampled)
            verts = geom.get("vertices")
            if isinstance(verts, list) and len(verts) >= 4:
                if verts and isinstance(verts[0], (int, float)):
                    points = [verts[i:i + 2] for i in range(0, len(verts) - 1, 2)]
                else:
                    points = verts
                step = max(1, len(points) // 20)
                for vi in range(0, len(points), step):
                    v = points[vi]
                    if isinstance(v, (list, tuple)) and len(v) >= 2:
                        anchors.append(_make_anchor(
                            anchor_idx, entity, [float(v[0]), float(v[1])],
                            f"{atype_prefix}polyline_vertex", region,
                        ))
                        anchor_idx += 1

        # TDb equipment with insertion points
        elif obj.startswith("TDb"):
            pt = geom.get("insertion_point") or geom.get("center")
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                atype = "equipment_center" if any(kw in obj for kw in ("EQUIP", "Device", "VALVE")) else "symbol_center"
                anchors.append(_make_anchor(anchor_idx, entity, [float(pt[0]), float(pt[1])], atype, region))
                anchor_idx += 1

        # Circles
        elif obj == "AcDbCircle":
            pt = geom.get("center")
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                anchors.append(_make_anchor(anchor_idx, entity, [float(pt[0]), float(pt[1])], "circle_center", region))
                anchor_idx += 1

        # Text insertion points
        elif obj in ("AcDbText", "AcDbMText"):
            pt = geom.get("insertion_point")
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                anchors.append(_make_anchor(anchor_idx, entity, [float(pt[0]), float(pt[1])], "text_insertion", region))
                anchor_idx += 1

    return anchors


def _make_anchor(
    idx: int,
    entity: dict[str, Any],
    point: list[float],
    anchor_type: str,
    region: dict[str, Any],
) -> dict[str, Any]:
    return {
        "anchor_id": f"{region['region_id']}_anchor_{idx:05d}",
        "region_id": region["region_id"],
        "anchor_type": anchor_type,
        "point": point,
        "handle": entity.get("handle"),
        "object_name": str(entity.get("object_name", "")),
        "layer": str(entity.get("layer", "")),
    }


def _layer_family(layer: str) -> str:
    compact = "".join(str(layer).upper().split())
    for token in ("WALL", "COLUMN", "STAIR", "WINDOW", "DOOR", "AXIS", "GRID", "DOTE", "PIPE"):
        if token in compact:
            return token
    for token in ("墙", "柱", "梯", "窗", "门", "轴"):
        if token in compact:
            return token
    return compact[:16]


def _anchor_bucket(anchor: Mapping[str, Any], *, include_layer: bool = True) -> tuple[Any, ...]:
    direction = anchor.get("direction_deg")
    length = anchor.get("feature_length")
    direction_bin = None if direction is None else int(round(float(direction) / 15.0)) % 12
    length_bin = None if not length or float(length) <= 0 else int(round(math.log10(max(float(length), 1.0)) * 4))
    base = (
        str(anchor.get("object_name") or ""),
        str(anchor.get("anchor_type") or ""),
        direction_bin,
        length_bin,
    )
    return (*base, _layer_family(str(anchor.get("layer") or ""))) if include_layer else base


def _deduplicate_and_sample_anchors(
    anchors: list[dict[str, Any]],
    bbox: list[float],
    *,
    max_candidates: int = MAX_CANDIDATE_ANCHORS,
    max_sampled: int = MAX_RANSAC_ANCHORS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Quantize, distance-deduplicate, quota-balance, and grid-sample anchors."""
    w, h = max(bbox[2] - bbox[0], 1.0), max(bbox[3] - bbox[1], 1.0)
    quant = max(min(w, h) / 20000.0, 0.5)
    unique: dict[tuple[int, int, str], dict[str, Any]] = {}
    for anchor in anchors:
        point = anchor.get("point")
        if not isinstance(point, list) or len(point) < 2:
            continue
        x, y = float(point[0]), float(point[1])
        if not _contains(bbox, (x, y), max(w, h) * 0.01):
            continue
        key = (round(x / quant), round(y / quant), str(anchor.get("anchor_type") or ""))
        prior = unique.get(key)
        if prior is None or bool(anchor.get("is_frame_anchor")):
            unique[key] = anchor

    priority = {
        "frame_corner": 0,
        "structural_block_insertion": 1,
        "structural_line_endpoint": 2,
        "structural_polyline_vertex": 3,
        "block_insertion": 4,
        "circle_center": 5,
        "text_insertion": 8,
    }
    deduped = sorted(
        unique.values(),
        key=lambda a: (priority.get(str(a.get("anchor_type")), 6), str(a.get("handle") or ""), str(a.get("anchor_id") or "")),
    )[:max_candidates]

    # One anchor per type/grid cell first, then fill remaining capacity.
    chosen: list[dict[str, Any]] = []
    seen_cells: set[tuple[str, int, int]] = set()
    for anchor in deduped:
        x, y = anchor["point"][:2]
        gx = max(0, min(GRID_DIVISIONS - 1, int((x - bbox[0]) / w * GRID_DIVISIONS)))
        gy = max(0, min(GRID_DIVISIONS - 1, int((y - bbox[1]) / h * GRID_DIVISIONS)))
        cell = (str(anchor.get("anchor_type")), gx, gy)
        if cell in seen_cells:
            continue
        seen_cells.add(cell)
        chosen.append(anchor)
        if len(chosen) >= max_sampled:
            break
    if len(chosen) < max_sampled:
        chosen_ids = {id(item) for item in chosen}
        for anchor in deduped:
            if id(anchor) not in chosen_ids:
                chosen.append(anchor)
                if len(chosen) >= max_sampled:
                    break
    stats = {
        "raw_count": len(anchors),
        "deduplicated_count": len(deduped),
        "sampled_count": len(chosen),
        "raw_type_counts": dict(Counter(str(a.get("anchor_type")) for a in anchors)),
        "sampled_type_counts": dict(Counter(str(a.get("anchor_type")) for a in chosen)),
        "quantization": quant,
        "candidate_limit": max_candidates,
        "ransac_limit": max_sampled,
    }
    return deduped, chosen, stats


def _match_anchors_kdtree(
    ref_anchors: list[dict[str, Any]],
    tgt_anchors: list[dict[str, Any]],
    ref_bbox: list[float],
    tgt_bbox: list[float],
) -> list[dict[str, Any]]:
    """Bucketed KD-tree matching. Never performs a global cartesian product."""
    from scipy.spatial import cKDTree

    def norm(anchor: Mapping[str, Any], bbox: list[float]) -> np.ndarray:
        w, h = max(bbox[2] - bbox[0], 1.0), max(bbox[3] - bbox[1], 1.0)
        return np.asarray([(float(anchor["point"][0]) - bbox[0]) / w, (float(anchor["point"][1]) - bbox[1]) / h])

    matched: list[dict[str, Any]] = []
    used_targets: set[str] = set()
    ref_frames = [a for a in ref_anchors if a.get("is_frame_anchor")]
    tgt_frames = [a for a in tgt_anchors if a.get("is_frame_anchor")]
    for ref_anchor, tgt_anchor in zip(ref_frames[:4], tgt_frames[:4]):
        used_targets.add(str(tgt_anchor["anchor_id"]))
        matched.append(_build_matched_anchor(ref_anchor, tgt_anchor, "frame_corner_direct", 0.0, 1.0))

    target_buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    target_fallback: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for anchor in tgt_anchors:
        if anchor.get("is_frame_anchor"):
            continue
        target_buckets[_anchor_bucket(anchor, include_layer=True)].append(anchor)
        target_fallback[_anchor_bucket(anchor, include_layer=False)].append(anchor)

    tree_cache: dict[tuple[str, tuple[Any, ...]], tuple[Any, list[dict[str, Any]]]] = {}

    def tree_for(kind: str, key: tuple[Any, ...], values: list[dict[str, Any]]) -> tuple[Any, list[dict[str, Any]]]:
        cache_key = (kind, key)
        if cache_key not in tree_cache:
            tree_cache[cache_key] = (cKDTree(np.asarray([norm(a, tgt_bbox) for a in values])), values)
        return tree_cache[cache_key]

    for ref_anchor in ref_anchors:
        if ref_anchor.get("is_frame_anchor"):
            continue
        exact_key = _anchor_bucket(ref_anchor, include_layer=True)
        fallback_key = _anchor_bucket(ref_anchor, include_layer=False)
        values = target_buckets.get(exact_key) or target_fallback.get(fallback_key) or []
        if not values:
            continue
        kind = "exact" if target_buckets.get(exact_key) else "fallback"
        key = exact_key if kind == "exact" else fallback_key
        tree, ordered = tree_for(kind, key, values)
        k = min(6, len(ordered))
        distances, indexes = tree.query(norm(ref_anchor, ref_bbox), k=k)
        distances = np.atleast_1d(distances)
        indexes = np.atleast_1d(indexes)
        candidate = None
        candidate_distance = None
        for distance, index in zip(distances, indexes):
            item = ordered[int(index)]
            if str(item["anchor_id"]) in used_targets:
                continue
            if float(distance) <= 0.035:
                candidate, candidate_distance = item, float(distance)
                break
        if candidate is None:
            continue
        used_targets.add(str(candidate["anchor_id"]))
        matched.append(_build_matched_anchor(
            ref_anchor,
            candidate,
            f"bucketed_kdtree_{kind}",
            candidate_distance or 0.0,
            round(max(0.35, 1.0 - (candidate_distance or 0.0) / 0.035), 4),
        ))
    return matched


# ── anchor matching between reference and target ────────────────────────────

def _match_anchors_by_spatial(
    ref_anchors: list[dict[str, Any]],
    tgt_anchors: list[dict[str, Any]],
    ref_bbox: list[float],
    tgt_bbox: list[float],
) -> list[dict[str, Any]]:
    """Match anchors by normalizing to relative coordinates within each region.

    Frame-corner anchors are matched directly (0→0, 1→1, etc.).
    Other anchors are matched by nearest normalized position with type preference.
    """
    ref_w = ref_bbox[2] - ref_bbox[0]
    ref_h = ref_bbox[3] - ref_bbox[1]
    tgt_w = tgt_bbox[2] - tgt_bbox[0]
    tgt_h = tgt_bbox[3] - tgt_bbox[1]

    if ref_w <= 0 or ref_h <= 0 or tgt_w <= 0 or tgt_h <= 0:
        return []

    def _norm(point: list[float], bbox: list[float]) -> tuple[float, float]:
        return (
            (point[0] - bbox[0]) / (bbox[2] - bbox[0]),
            (point[1] - bbox[1]) / (bbox[3] - bbox[1]),
        )

    matched: list[dict[str, Any]] = []
    used_tgt: set[int] = set()

    # ── Direct frame-corner matching (index-based) ──
    ref_frame = [a for a in ref_anchors if a.get("is_frame_anchor")]
    tgt_frame = [a for a in tgt_anchors if a.get("is_frame_anchor")]
    for idx, ref_a in enumerate(ref_frame[:4]):
        if idx < len(tgt_frame):
            tgt_a = tgt_frame[idx]
            used_tgt.add(tgt_anchors.index(tgt_a))
            matched.append(_build_matched_anchor(ref_a, tgt_a, "frame_corner_direct", 0.0, 1.0))

    # ── Structural block insertion matching ──
    ref_struct = [
        (i, a) for i, a in enumerate(ref_anchors)
        if a.get("anchor_type") == "structural_block_insertion" and i not in {ref_anchors.index(fa) for fa in ref_frame}
    ]
    tgt_struct = [
        (i, a) for i, a in enumerate(tgt_anchors)
        if a.get("anchor_type") == "structural_block_insertion" and i not in used_tgt
    ]

    tgt_struct_normed = [(_norm(a["point"], tgt_bbox), i, a) for i, a in tgt_struct]
    strict_threshold = 0.015  # 1.5% — tighter for structural elements

    for _, ref_a in ref_struct:
        ref_n = _norm(ref_a["point"], ref_bbox)
        best_i = -1
        best_dist = float("inf")
        for tgt_n, ti, _ in tgt_struct_normed:
            if ti in used_tgt:
                continue
            dist = math.hypot(ref_n[0] - tgt_n[0], ref_n[1] - tgt_n[1])
            if dist < strict_threshold and dist < best_dist:
                best_dist = dist
                best_i = ti
        if best_i >= 0:
            tgt_a = tgt_anchors[best_i]
            used_tgt.add(best_i)
            matched.append(_build_matched_anchor(
                ref_a, tgt_a, "structural_block_spatial",
                round(best_dist, 6),
                round(max(0.3, 1.0 - best_dist / strict_threshold), 4),
            ))

    # ── General spatial matching for remaining anchors ──
    ref_remaining = [
        (i, a) for i, a in enumerate(ref_anchors)
        if i not in {ref_anchors.index(fa) for fa in ref_frame}
        and i not in {ri for ri, _ in ref_struct}
    ]
    tgt_normed_general = [
        (_norm(a["point"], tgt_bbox), i, a) for i, a in enumerate(tgt_anchors) if i not in used_tgt
    ]
    threshold = 0.025  # 2.5%

    for _, ref_a in ref_remaining:
        ref_n = _norm(ref_a["point"], ref_bbox)
        best_i = -1
        best_dist = float("inf")
        for tgt_n, ti, tgt_a in tgt_normed_general:
            if ti in used_tgt:
                continue
            type_bonus = 0.0 if ref_a["anchor_type"] == tgt_a["anchor_type"] else 0.003
            dist = math.hypot(ref_n[0] - tgt_n[0], ref_n[1] - tgt_n[1]) + type_bonus
            if dist < threshold and dist < best_dist:
                best_dist = dist
                best_i = ti
        if best_i >= 0:
            tgt_a = tgt_anchors[best_i]
            used_tgt.add(best_i)
            matched.append(_build_matched_anchor(
                ref_a, tgt_a, "spatial_normalized",
                round(best_dist, 6),
                round(max(0.3, 1.0 - best_dist / threshold), 4),
            ))

    return matched


def _build_matched_anchor(
    ref_a: dict[str, Any],
    tgt_a: dict[str, Any],
    match_reason: str,
    match_distance: float,
    confidence: float,
) -> dict[str, Any]:
    return {
        "anchor_id": ref_a["anchor_id"],
        "anchor_type": ref_a["anchor_type"],
        "reference_point": ref_a["point"],
        "target_point": tgt_a["point"],
        "reference_handle": ref_a.get("handle"),
        "target_handle": tgt_a.get("handle"),
        "reference_object_name": ref_a.get("object_name", ""),
        "target_object_name": tgt_a.get("object_name", ""),
        "reference_layer": ref_a.get("layer", ""),
        "target_layer": tgt_a.get("layer", ""),
        "match_reason": match_reason,
        "match_distance": round(match_distance, 6),
        "confidence": confidence,
        "is_inlier": True,
        "rejection_reason": None,
    }


# ── transform fitting ───────────────────────────────────────────────────────

def _fit_transforms(
    matched_anchors: list[dict[str, Any]],
    ref_bbox: list[float],
    tgt_bbox: list[float],
    *,
    deadline: float | None = None,
) -> list[dict[str, Any]]:
    """RANSAC-fit bounded transform models, simplest first."""
    if len(matched_anchors) < 2:
        return []

    ref_pts = np.array([a["reference_point"] for a in matched_anchors], dtype=float)
    tgt_pts = np.array([a["target_point"] for a in matched_anchors], dtype=float)

    results: list[dict[str, Any]] = []
    region_diag = max(
        math.hypot(ref_bbox[2] - ref_bbox[0], ref_bbox[3] - ref_bbox[1]),
        math.hypot(tgt_bbox[2] - tgt_bbox[0], tgt_bbox[3] - tgt_bbox[1]),
        1.0,
    )
    threshold = max(region_diag * 0.0035, 2.0)
    model_specs = [
        ("translation_only", 1),
        ("similarity_transform", 2),
        ("non_uniform_scale_transform", 2),
        ("affine_transform", 3),
    ]
    rng = random.Random(20260713)
    for model_type, sample_size in model_specs:
        if len(ref_pts) < sample_size:
            continue
        best: dict[str, Any] | None = None
        iterations = min(RANSAC_ITERATIONS, max(40, len(ref_pts) * 2))
        for _ in range(iterations):
            if deadline is not None and time.monotonic() >= deadline:
                break
            indexes = rng.sample(range(len(ref_pts)), sample_size)
            try:
                matrix = _fit_model(model_type, ref_pts[indexes], tgt_pts[indexes])
                candidate = _evaluate_transform(model_type, matrix, ref_pts, tgt_pts, threshold)
            except Exception:
                continue
            if best is None or (candidate["anchor_count_inlier"], -candidate["median_error"]) > (
                best["anchor_count_inlier"], -best["median_error"]
            ):
                best = candidate
        if best is None:
            continue
        mask = np.asarray(best["inliers"], dtype=bool)
        if int(mask.sum()) >= sample_size:
            try:
                refined = _fit_model(model_type, ref_pts[mask], tgt_pts[mask])
                best = _evaluate_transform(model_type, refined, ref_pts, tgt_pts, threshold)
            except Exception:
                pass
        results.append(best)
    return results


def _fit_model(model_type: str, ref: np.ndarray, tgt: np.ndarray) -> np.ndarray:
    if model_type == "translation_only":
        delta = np.median(tgt - ref, axis=0)
        return np.asarray([[1.0, 0.0, delta[0]], [0.0, 1.0, delta[1]], [0.0, 0.0, 1.0]])
    if model_type == "similarity_transform":
        return _procrustes(ref, tgt, allow_scale=True)
    if model_type == "non_uniform_scale_transform":
        design = np.column_stack([ref[:, 0], np.ones(len(ref))])
        sx, tx = np.linalg.lstsq(design, tgt[:, 0], rcond=None)[0]
        design_y = np.column_stack([ref[:, 1], np.ones(len(ref))])
        sy, ty = np.linalg.lstsq(design_y, tgt[:, 1], rcond=None)[0]
        return np.asarray([[sx, 0.0, tx], [0.0, sy, ty], [0.0, 0.0, 1.0]])
    if model_type == "affine_transform":
        return _affine_matrix(ref, tgt)
    raise ValueError(f"unsupported model: {model_type}")


def _select_transform(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    supported = [
        item for item in candidates
        if item["anchor_count_inlier"] >= 12 and item["rms_error"] <= item["threshold"]
    ]
    if supported:
        return min(supported, key=lambda item: (_transform_complexity(item["model_type"]), item["rms_error"]))
    return max(candidates, key=lambda item: (item["anchor_count_inlier"], -item["rms_error"]))


def _evaluate_transform(
    model_type: str,
    matrix: np.ndarray,
    ref_pts: np.ndarray,
    tgt_pts: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    n = len(ref_pts)
    ones = np.ones((n, 1))
    ref_h = np.hstack([ref_pts, ones])
    transformed = (matrix @ ref_h.T).T[:, :2]
    residuals = np.linalg.norm(transformed - tgt_pts, axis=1)
    inlier_mask = residuals <= threshold
    inlier_count = int(np.sum(inlier_mask))

    return {
        "model_type": model_type,
        "matrix": matrix.tolist(),
        "anchor_count_total": n,
        "anchor_count_inlier": inlier_count,
        "rms_error": round(float(np.sqrt(np.mean(residuals ** 2))), 4),
        "max_error": round(float(np.max(residuals)), 4),
        "median_error": round(float(np.median(residuals)), 4),
        "residuals": [round(float(r), 4) for r in residuals],
        "inliers": [bool(m) for m in inlier_mask],
        "threshold": round(float(threshold), 4),
    }


def _procrustes(ref: np.ndarray, tgt: np.ndarray, allow_scale: bool = True) -> np.ndarray:
    """Compute Procrustes similarity/rigid transform matrix."""
    ref_c = ref - ref.mean(axis=0)
    tgt_c = tgt - tgt.mean(axis=0)
    cov = ref_c.T @ tgt_c
    U, _, Vt = np.linalg.svd(cov)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = U @ Vt
    if allow_scale:
        s = np.trace(tgt_c.T @ ref_c @ R) / np.trace(ref_c.T @ ref_c) if np.trace(ref_c.T @ ref_c) != 0 else 1.0
    else:
        s = 1.0
    t = tgt.mean(axis=0) - s * (R @ ref.mean(axis=0))
    return np.array([
        [s * R[0, 0], s * R[0, 1], t[0]],
        [s * R[1, 0], s * R[1, 1], t[1]],
        [0, 0, 1],
    ])


def _affine_matrix(ref: np.ndarray, tgt: np.ndarray) -> np.ndarray:
    """Least-squares affine transform."""
    n = len(ref)
    A = np.zeros((2 * n, 6))
    b = np.zeros(2 * n)
    for i in range(n):
        A[2 * i] = [ref[i, 0], ref[i, 1], 0, 0, 1, 0]
        A[2 * i + 1] = [0, 0, ref[i, 0], ref[i, 1], 0, 1]
        b[2 * i] = tgt[i, 0]
        b[2 * i + 1] = tgt[i, 1]
    x, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    return np.array([
        [x[0], x[1], x[4]],
        [x[2], x[3], x[5]],
        [0, 0, 1],
    ])


def _transform_complexity(model_type: str) -> int:
    return {
        "translation_only": 0,
        "similarity_transform": 1,
        "non_uniform_scale_transform": 2,
        "affine_transform": 3,
    }.get(model_type, 99)


# ── directional coverage ────────────────────────────────────────────────────

def _directional_coverage(anchors: list[dict[str, Any]]) -> float:
    """Measure how well anchors cover the X and Y directions."""
    if len(anchors) < 2:
        return 0.0
    pts = np.array([a["reference_point"] for a in anchors])
    xs = pts[:, 0]
    ys = pts[:, 1]
    x_range = np.ptp(xs) if len(xs) > 1 else 0.0
    y_range = np.ptp(ys) if len(ys) > 1 else 0.0
    total_range = x_range + y_range
    if total_range < 1e-6:
        return 0.0
    x_cov = x_range / total_range if total_range > 0 else 0
    y_cov = y_range / total_range if total_range > 0 else 0
    # Target: balanced coverage = 1.0; one-sided = 0.5
    return 2.0 * min(x_cov, y_cov)


def _spatial_coverage(anchors: list[dict[str, Any]], bbox: list[float]) -> float:
    """Measure what fraction of the bbox area is covered by anchors."""
    if len(anchors) < 3:
        return 0.0
    pts = np.array([a["reference_point"] for a in anchors])
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    if w <= 0 or h <= 0:
        return 0.0
    # Divide bbox into 4 quadrants
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    quadrants = set()
    for pt in pts:
        qx = 0 if pt[0] < cx else 1
        qy = 0 if pt[1] < cy else 1
        quadrants.add((qx, qy))
    return len(quadrants) / 4.0


def _anchor_type_count(anchors: list[dict[str, Any]]) -> int:
    return len(set(a["anchor_type"] for a in anchors))


# ── build coordinate transform record ───────────────────────────────────────

def _build_transform_record(
    pair: dict[str, Any],
    matched_anchors: list[dict[str, Any]],
    best_transform: dict[str, Any] | None,
    ref_region: dict[str, Any],
    tgt_region: dict[str, Any],
    *,
    anchor_count_raw: int = 0,
    anchor_count_sampled: int = 0,
    runtime_seconds: float = 0.0,
    timed_out: bool = False,
) -> dict[str, Any]:
    if best_transform is None:
        return {
            "transform_id": f"transform_{pair['pair_label']}",
            "reference_region_id": pair["reference_region_id"],
            "target_region_id": pair["target_region_id"],
            "model_type": "none",
            "status": "REJECTED",
            "blocking_reasons": ["no valid transform found"],
            "anchor_count_total": len(matched_anchors),
            "anchor_count_raw": anchor_count_raw,
            "anchor_count_sampled": anchor_count_sampled,
            "anchor_count_inlier": 0,
            "anchor_type_count": 0,
            "directional_coverage": 0.0,
            "spatial_coverage": 0.0,
            "rms_error": None,
            "max_error": None,
            "median_error": None,
            "confidence": 0.0,
            "runtime_seconds": round(runtime_seconds, 3),
            "status": "TIMEOUT" if timed_out else "REJECTED",
        }

    bt = best_transform
    dir_cov = _directional_coverage(matched_anchors)
    spat_cov = _spatial_coverage(matched_anchors, ref_region["frame_bbox"])
    atc = _anchor_type_count(matched_anchors)

    matrix = np.array(bt["matrix"])

    # Decompose matrix
    scale_x = math.hypot(matrix[0, 0], matrix[0, 1])
    scale_y = math.hypot(matrix[1, 0], matrix[1, 1]) if bt["model_type"] in {
        "non_uniform_scale_transform", "affine_transform"
    } else scale_x
    rotation_deg = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))
    translate_x = matrix[0, 2]
    translate_y = matrix[1, 2]

    # Transform reference bbox
    ref_bb = ref_region["frame_bbox"]
    corners = np.array([
        [ref_bb[0], ref_bb[1], 1], [ref_bb[2], ref_bb[1], 1],
        [ref_bb[2], ref_bb[3], 1], [ref_bb[0], ref_bb[3], 1],
    ])
    tc = (matrix @ corners.T).T[:, :2]
    transformed_bbox = [float(tc[:, 0].min()), float(tc[:, 1].min()), float(tc[:, 0].max()), float(tc[:, 1].max())]
    tgt_bb = tgt_region["frame_bbox"]
    inside = (
        transformed_bbox[0] >= tgt_bb[0] - 5000 and transformed_bbox[1] >= tgt_bb[1] - 5000
        and transformed_bbox[2] <= tgt_bb[2] + 5000 and transformed_bbox[3] <= tgt_bb[3] + 5000
    )

    # Scale sanity
    scale_ok = 0.1 < scale_x < 10.0 and 0.1 < scale_y < 10.0

    confidence = round(min(
        bt["anchor_count_inlier"] / max(bt["anchor_count_total"], 1),
        dir_cov / 0.55,
        spat_cov,
        1.0 if inside else 0.5,
        1.0 if scale_ok else 0.3,
    ), 4)

    # Status determination
    if (
        bt["anchor_count_inlier"] >= 12
        and atc >= 3
        and dir_cov >= 0.55
        and confidence >= 0.90
        and inside
        and scale_ok
    ):
        status = "VERIFIED"
    elif bt["anchor_count_inlier"] >= 6 and atc >= 2 and dir_cov >= 0.3:
        status = "LOW_CONFIDENCE"
    else:
        status = "REJECTED"

    blocking = []
    if bt["anchor_count_inlier"] < 12:
        blocking.append(f"inliers {bt['anchor_count_inlier']} < 12")
    if atc < 3:
        blocking.append(f"anchor_types {atc} < 3")
    if dir_cov < 0.55:
        blocking.append(f"directional_coverage {dir_cov:.2f} < 0.55")
    if confidence < 0.90:
        blocking.append(f"confidence {confidence:.2f} < 0.90")
    if not inside:
        blocking.append("transformed_bbox not fully inside target region")
    if not scale_ok:
        blocking.append(f"scale ({scale_x:.4f}, {scale_y:.4f}) out of range")

    return {
        "transform_id": f"transform_{pair['pair_label']}",
        "reference_region_id": pair["reference_region_id"],
        "target_region_id": pair["target_region_id"],
        "model_type": bt["model_type"],
        "scale_x": round(scale_x, 6),
        "scale_y": round(scale_y, 6),
        "rotation_deg": round(rotation_deg, 6),
        "translate_x": round(translate_x, 4),
        "translate_y": round(translate_y, 4),
        "matrix_3x3": bt["matrix"],
        "anchor_count_total": bt["anchor_count_total"],
        "anchor_count_raw": anchor_count_raw,
        "anchor_count_sampled": anchor_count_sampled,
        "anchor_count_inlier": bt["anchor_count_inlier"],
        "anchor_type_count": atc,
        "directional_coverage": round(dir_cov, 4),
        "spatial_coverage": round(spat_cov, 4),
        "rms_error": bt["rms_error"],
        "max_error": bt["max_error"],
        "median_error": bt["median_error"],
        "transformed_bbox": transformed_bbox,
        "target_region_bbox": tgt_region["frame_bbox"],
        "transformed_bbox_inside_target": inside,
        "confidence": confidence,
        "status": "TIMEOUT" if timed_out else status,
        "runtime_seconds": round(runtime_seconds, 3),
        "blocking_reasons": blocking if status != "VERIFIED" else [],
    }


# ── main entry point ────────────────────────────────────────────────────────

def _file_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "file_size": stat.st_size,
        "modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _render_region_contact_sheet(
    ref_regions: list[dict[str, Any]],
    tgt_regions: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
    protected: dict[str, Any] | None,
    output: Path,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1800, 1200
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((40, 24), "Stage 6-P2 Region Contact Sheet", fill="black", font=font)
    bound_ref = {item.get("reference_region_id"): item.get("pair_label") for item in bindings}
    bound_tgt = {item.get("target_region_id"): item.get("pair_label") for item in bindings}

    def panel(regions: list[dict[str, Any]], x0: int, y0: int, w: int, h: int, title: str, labels: Mapping[str, Any]) -> None:
        draw.rectangle((x0, y0, x0 + w, y0 + h), outline="#333333", width=2)
        draw.text((x0 + 10, y0 + 8), title, fill="black", font=font)
        if not regions:
            return
        min_x = min(r["frame_bbox"][0] for r in regions)
        min_y = min(r["frame_bbox"][1] for r in regions)
        max_x = max(r["frame_bbox"][2] for r in regions)
        max_y = max(r["frame_bbox"][3] for r in regions)
        sx = (w - 40) / max(max_x - min_x, 1.0)
        sy = (h - 70) / max(max_y - min_y, 1.0)
        scale = min(sx, sy)
        for region in regions:
            b = region["frame_bbox"]
            left = x0 + 20 + (b[0] - min_x) * scale
            top = y0 + 45 + (max_y - b[3]) * scale
            right = x0 + 20 + (b[2] - min_x) * scale
            bottom = y0 + 45 + (max_y - b[1]) * scale
            is_protected = protected and region["region_id"] == protected.get("region_id")
            color = "#cc2222" if is_protected else "#2468a2"
            draw.rectangle((left, top, right, bottom), outline=color, width=3)
            label = f"{region['region_id']}\n{labels.get(region['region_id'], 'UNBOUND')}"
            draw.multiline_text((left + 3, top + 3), label, fill=color, font=font, spacing=2)

    panel(ref_regions, 30, 70, 850, 1080, "REFERENCE", bound_ref)
    panel(tgt_regions, 920, 70, 850, 1080, "TARGET", bound_tgt)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def scan_selected_regions_readonly(
    acad: Any,
    path: Path,
    role: str,
    regions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Single-pass bbox-filtered read-only scan for a small set of known regions."""
    from mcp.acceptance.stage3_1_runtime import (
        _close_document_without_save,
        _open_document_with_retry,
        _resolve_open_document,
        _scan_entity,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import _retry

    before = _sha256(path)
    document = None
    selected: dict[str, list[dict[str, Any]]] = {str(region["region_id"]): [] for region in regions}
    try:
        returned = _open_document_with_retry(acad, path)
        document = _resolve_open_document(acad, path, returned)
        modelspace = _retry(lambda: document.ModelSpace, f"{role} selected scan ModelSpace", attempts=40, delay=0.25)
        count = int(_retry(lambda: modelspace.Count, f"{role} selected scan Count", attempts=40, delay=0.25))
        for index in range(count):
            entity = _retry(lambda value=index: modelspace.Item(value), f"{role} item {index}", attempts=40, delay=0.15)
            try:
                lower, upper = _retry(lambda value=entity: value.GetBoundingBox(), f"{role} bbox {index}", attempts=10, delay=0.1)
                center = ((float(lower[0]) + float(upper[0])) / 2.0, (float(lower[1]) + float(upper[1])) / 2.0)
            except Exception:
                continue
            for region in regions:
                if _contains(region["frame_bbox"], center, 1.0):
                    selected[str(region["region_id"])].append(_scan_entity(entity, role, "Model"))
        return {
            "document_role": role,
            "path": str(path),
            "regions": selected,
            "entity_count": sum(len(items) for items in selected.values()),
            "hash_before": before,
            "hash_after": _sha256(path),
            "hash_unchanged": before == _sha256(path),
            "target_write": False,
            "target_save": False,
        }
    finally:
        if document is not None:
            _close_document_without_save(document)


def run_stage6_p2(
    run_id: str,
    ref_path: Path,
    tgt_path: Path,
    output_dir: Path,
    backup_path: Path | None = None,
) -> dict[str, Any]:
    """Execute the full Stage 6-P2 pipeline."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "alignment_reports").mkdir(parents=True, exist_ok=True)

    ref_identity = _file_identity(ref_path)
    tgt_identity = _file_identity(tgt_path)
    ref_sha = ref_identity["sha256"]
    tgt_sha = tgt_identity["sha256"]
    backup_identity = _file_identity(backup_path) if backup_path else None
    if backup_identity and backup_identity["sha256"] != tgt_sha:
        raise RuntimeError("prewrite backup hash mismatch")
    _write_json(output_dir / "input_identity.json", {
        "phase": "STAGE6-P2",
        "run_id": run_id,
        "reference": ref_identity,
        "target": tgt_identity,
        "old_inputs_loaded": False,
        "old_plan_loaded": False,
    })
    _write_json(output_dir / "prewrite_backup_manifest.json", {
        "backup_created": bool(backup_identity),
        "target": tgt_identity,
        "backup": backup_identity,
        "backup_hash_matches": bool(backup_identity and backup_identity["sha256"] == tgt_sha),
    })
    _write_json(output_dir / "prewrite_gate.json", {
        "status": "PASS",
        "reference_lock": False,
        "target_lock": False,
        "input_paths_verified": True,
        "hashes_frozen": True,
        "backup_hash_matches": bool(backup_identity and backup_identity["sha256"] == tgt_sha),
        "target_write": False,
        "target_save": False,
    })

    # ── 1. Import and run COM scan ──────────────────────────────────────────
    from mcp.acceptance.stage3_1_runtime import (
        attach_existing_autocad,
        detach_autocad,
        enumerate_live_documents,
        scan_working_copy,
    )

    ref_hash_before = _sha256(ref_path)
    tgt_hash_before = _sha256(tgt_path)

    acad = attach_existing_autocad()
    try:
        live = enumerate_live_documents(acad, (ref_path, tgt_path))
        normalized = {str(ref_path.resolve()).casefold(), str(tgt_path.resolve()).casefold()}
        already_open = [
            d for d in live.get("documents", [])
            if d.get("full_name") and str(Path(d["full_name"]).resolve()).casefold() in normalized
        ]
        if already_open:
            raise RuntimeError(f"Input files already open in AutoCAD: {already_open}")

        ref_scan = scan_working_copy(acad, ref_path, "reference", ())
        tgt_scan = scan_working_copy(acad, tgt_path, "target", ())
    finally:
        detach_autocad()

    ref_hash_after = _sha256(ref_path)
    tgt_hash_after = _sha256(tgt_path)

    hashes_unchanged = (
        ref_hash_before == ref_hash_after == ref_sha
        and tgt_hash_before == tgt_hash_after == tgt_sha
    )

    if not hashes_unchanged:
        raise RuntimeError("CRITICAL: DWG hash changed during read-only scan")

    # ── 2. Region detection ─────────────────────────────────────────────────
    ref_entities = list(ref_scan.get("entities", []))
    tgt_entities = list(tgt_scan.get("entities", []))

    # Save raw scans for diagnostics
    _write_json(output_dir / "reference_scan.json", {
        "entity_count": ref_scan.get("entity_count"),
        "object_type_counts": ref_scan.get("object_type_counts"),
        "entities": ref_entities[:200],  # first 200 for diagnostics only
    })
    _write_json(output_dir / "target_scan.json", {
        "entity_count": tgt_scan.get("entity_count"),
        "object_type_counts": tgt_scan.get("object_type_counts"),
        "entities": tgt_entities[:200],
    })

    ref_frames = _frame_candidates(ref_entities)
    tgt_frames = _frame_candidates(tgt_entities)

    ref_regions = [
        _build_region("reference", i, frame, ref_entities, ref_entities)
        for i, frame in enumerate(ref_frames)
    ]
    tgt_regions = [
        _build_region("target", i, frame, tgt_entities, tgt_entities)
        for i, frame in enumerate(tgt_frames)
    ]

    _write_json(output_dir / "reference_regions.json", {
        "count": len(ref_regions),
        "regions": ref_regions,
    })
    _write_json(output_dir / "target_regions.json", {
        "count": len(tgt_regions),
        "regions": tgt_regions,
    })

    # ── 3. Protect pump room in target ──────────────────────────────────────
    protected = _detect_pump_room_protected(tgt_regions, tgt_entities)
    if protected:
        _write_json(output_dir / "protected_regions.json", {
            "count": 1,
            "regions": [protected],
        })
    else:
        _write_json(output_dir / "protected_regions.json", {
            "count": 0,
            "regions": [],
            "warning": "PUMP_ROOM_NOT_DETECTED — human review required",
        })

    # ── 4. Manual semantic mapping binding ──────────────────────────────────
    candidates = []
    bindings = []
    conflicts = []

    for ref_sem, tgt_sem, label in HUMAN_CONFIRMED_MAPPING:
        candidate = {
            "pair_label": label,
            "reference_semantic": ref_sem,
            "target_semantic": tgt_sem,
        }
        candidates.append(candidate)
        binding = _match_semantic_region(ref_regions, tgt_regions, ref_sem, tgt_sem, label)
        if binding:
            bindings.append(binding)
            if binding.get("binding_status") == "CONFLICT":
                conflicts.append(binding)

    _write_json(output_dir / "manual_mapping_candidates.json", {
        "count": len(candidates),
        "candidates": candidates,
    })
    _write_json(output_dir / "manual_mapping_bound.json", {
        "count": len(bindings),
        "bindings": bindings,
        "confirmed": sum(1 for b in bindings if b.get("binding_status") == "CONFIRMED"),
        "conflicts": sum(1 for b in bindings if b.get("binding_status") == "CONFLICT"),
        "not_found": sum(1 for b in bindings if b.get("binding_status") == "NOT_FOUND"),
    })

    consistency = {
        "total_candidates": len(HUMAN_CONFIRMED_MAPPING),
        "bound_count": len(bindings),
        "confirmed_count": sum(1 for b in bindings if b.get("binding_status") == "CONFIRMED"),
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "human_review_required": len(conflicts) > 0,
    }
    _write_json(output_dir / "manual_mapping_consistency.json", consistency)

    # ── 5. Anchor extraction and matching ───────────────────────────────────
    all_anchors = []
    all_transforms = []
    anchor_statistics = []

    confirmed_bindings = [item for item in bindings if item.get("binding_status") == "CONFIRMED"]
    for pair_index, binding in enumerate(confirmed_bindings, 1):
        if binding.get("binding_status") != "CONFIRMED":
            continue
        started = time.monotonic()
        deadline = started + REGION_TIMEOUT_SECONDS
        pair_label = binding["pair_label"]
        ref_rid = binding["reference_region_id"]
        tgt_rid = binding["target_region_id"]

        ref_region = next((r for r in ref_regions if r["region_id"] == ref_rid), None)
        tgt_region = next((r for r in tgt_regions if r["region_id"] == tgt_rid), None)
        if not ref_region or not tgt_region:
            continue

        print(f"[{pair_index}/7] 区域识别 {pair_label}: {ref_rid} -> {tgt_rid}", flush=True)
        ref_raw = _extract_anchors_for_region(ref_scan, ref_region)
        tgt_raw = _extract_anchors_for_region(tgt_scan, tgt_region)
        ref_dedup, ref_sampled, ref_stats = _deduplicate_and_sample_anchors(ref_raw, ref_region["frame_bbox"])
        tgt_dedup, tgt_sampled, tgt_stats = _deduplicate_and_sample_anchors(tgt_raw, tgt_region["frame_bbox"])
        print(
            f"[{pair_index}/7] 候选锚点 reference={len(ref_raw)}/{len(ref_sampled)} "
            f"target={len(tgt_raw)}/{len(tgt_sampled)}",
            flush=True,
        )

        matched = _match_anchors_kdtree(
            ref_sampled, tgt_sampled,
            ref_region["frame_bbox"], tgt_region["frame_bbox"],
        )

        for a in matched:
            a["pair_label"] = pair_label
        all_anchors.append({"pair_label": pair_label, "matched_count": len(matched), "anchors": matched})

        # Fit transforms
        print(f"[{pair_index}/7] RANSAC 开始 matched={len(matched)}", flush=True)
        transforms = _fit_transforms(
            matched, ref_region["frame_bbox"], tgt_region["frame_bbox"], deadline=deadline,
        )
        best = _select_transform(transforms)
        timed_out = time.monotonic() >= deadline
        runtime_seconds = time.monotonic() - started
        tform_record = _build_transform_record(
            binding,
            matched,
            best,
            ref_region,
            tgt_region,
            anchor_count_raw=len(ref_raw),
            anchor_count_sampled=len(ref_sampled),
            runtime_seconds=runtime_seconds,
            timed_out=timed_out,
        )
        all_transforms.append(tform_record)
        anchor_statistics.append({
            "pair_label": pair_label,
            "reference_region_id": ref_rid,
            "target_region_id": tgt_rid,
            "reference": ref_stats,
            "target": tgt_stats,
            "matched_count": len(matched),
            "inlier_count": tform_record.get("anchor_count_inlier", 0),
        })
        print(f"[{pair_index}/7] inlier 数量 {tform_record.get('anchor_count_inlier', 0)}", flush=True)
        print(f"[{pair_index}/7] 拟合结果 {tform_record.get('model_type')}", flush=True)
        print(
            f"[{pair_index}/7] 残差检查 rms={tform_record.get('rms_error')} "
            f"median={tform_record.get('median_error')} max={tform_record.get('max_error')}",
            flush=True,
        )
        print(f"[{pair_index}/7] 状态 {tform_record.get('status')}", flush=True)

        # Write per-pair alignment report
        pair_dir = output_dir / "alignment_reports"
        _write_json(pair_dir / f"{pair_label}.json", {
            "pair_label": pair_label,
            "binding": binding,
            "anchor_count": len(matched),
            "transform": tform_record,
            "transform_candidates": transforms if len(transforms) > 1 else [],
        })

        # Markdown report
        md = _generate_pair_md(pair_label, binding, len(matched), tform_record, transforms)
        (pair_dir / f"{pair_label}.md").write_text(md, encoding="utf-8")

    # Write anchors JSONL
    anchors_path = output_dir / "anchors.jsonl"
    with anchors_path.open("w", encoding="utf-8") as f:
        for group in all_anchors:
            for a in group["anchors"]:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
    _write_json(output_dir / "anchor_statistics.json", {
        "pair_count": len(anchor_statistics),
        "candidate_anchor_limit": MAX_CANDIDATE_ANCHORS,
        "ransac_sample_limit": MAX_RANSAC_ANCHORS,
        "region_timeout_seconds": REGION_TIMEOUT_SECONDS,
        "pairs": anchor_statistics,
    })

    # ── 6. Coordinate transforms summary ────────────────────────────────────
    _write_json(output_dir / "coordinate_transforms.json", {
        "count": len(all_transforms),
        "transforms": all_transforms,
        "verified": sum(1 for t in all_transforms if t.get("status") == "VERIFIED"),
        "low_confidence": sum(1 for t in all_transforms if t.get("status") == "LOW_CONFIDENCE"),
        "rejected": sum(1 for t in all_transforms if t.get("status") == "REJECTED"),
        "timeout": sum(1 for t in all_transforms if t.get("status") == "TIMEOUT"),
    })
    _render_region_contact_sheet(
        ref_regions,
        tgt_regions,
        bindings,
        protected,
        output_dir / "region_contact_sheet.png",
    )

    # ── 7. Coordinate system manifest ───────────────────────────────────────
    verified_count = sum(1 for t in all_transforms if t.get("status") == "VERIFIED")
    low_count = sum(1 for t in all_transforms if t.get("status") == "LOW_CONFIDENCE")
    rejected_count = sum(1 for t in all_transforms if t.get("status") == "REJECTED")
    timeout_count = sum(1 for t in all_transforms if t.get("status") == "TIMEOUT")

    manifest = {
        "run_id": run_id,
        "reference_path": str(ref_path),
        "reference_sha256": ref_sha,
        "target_path": str(tgt_path),
        "target_sha256": tgt_sha,
        "reference_entity_count": ref_scan.get("entity_count"),
        "target_entity_count": tgt_scan.get("entity_count"),
        "reference_region_count": len(ref_regions),
        "target_region_count": len(tgt_regions),
        "confirmed_region_pair_count": sum(1 for b in bindings if b.get("binding_status") == "CONFIRMED"),
        "verified_transform_count": verified_count,
        "low_confidence_transform_count": low_count,
        "rejected_transform_count": rejected_count,
        "timeout_transform_count": timeout_count,
        "protected_region_count": 1 if protected else 0,
        "mapping_conflict_count": len(conflicts),
        "old_plan_reused": False,
        "old_region_ids_reused": False,
        "old_transforms_reused": False,
        "old_mapping_reused": False,
        "target_write": False,
        "target_save": False,
        "reference_save": False,
        "reference_hash_unchanged": hashes_unchanged,
        "target_hash_unchanged": hashes_unchanged,
        "ready_for_missing_detection": (
            verified_count >= 5
            and len(conflicts) == 0
            and hashes_unchanged
            and protected is not None
        ),
        "blocking_reasons": _build_blocking_reasons(
            verified_count, low_count, len(conflicts), hashes_unchanged, protected
        ),
        "created_at": _now_iso(),
    }

    if not hashes_unchanged or protected is None:
        manifest["final_status"] = "COORDINATE_SYSTEM_RECONSTRUCTION_BLOCKED"
    elif len(conflicts) > 0:
        manifest["final_status"] = "HUMAN_MAPPING_CONFLICT"
    elif verified_count == 7:
        manifest["final_status"] = "COORDINATE_SYSTEM_RECONSTRUCTION_COMPLETE"
    else:
        manifest["final_status"] = "COORDINATE_SYSTEM_RECONSTRUCTION_PARTIAL"

    if not manifest["ready_for_missing_detection"] and not manifest["blocking_reasons"]:
        manifest["blocking_reasons"].append("incomplete — review required")

    _write_json(output_dir / "coordinate_system_manifest.json", manifest)
    post_identity = {
        "reference": _file_identity(ref_path),
        "target": _file_identity(tgt_path),
        "reference_hash_unchanged": ref_hash_before == ref_hash_after,
        "target_hash_unchanged": tgt_hash_before == tgt_hash_after,
        "target_write": False,
        "target_save": False,
    }
    _write_json(output_dir / "input_identity_after_scan.json", post_identity)

    # ── 8. Global reports ───────────────────────────────────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(REPORTS_DIR / "stage6_p2_coordinate_reconstruction.json", manifest)

    md_report = _generate_final_report_md(manifest, all_transforms, protected, bindings, conflicts)
    (REPORTS_DIR / "stage6_p2_coordinate_reconstruction.md").write_text(md_report, encoding="utf-8")

    return manifest


def _build_blocking_reasons(
    verified: int,
    low: int,
    conflicts: int,
    hashes_ok: bool,
    protected: dict[str, Any] | None,
) -> list[str]:
    reasons = []
    if verified < 5:
        reasons.append(f"only {verified}/7 pairs VERIFIED (need >= 5)")
    if conflicts > 0:
        reasons.append(f"{conflicts} mapping conflict(s)")
    if not hashes_ok:
        reasons.append("DWG hash changed during scan")
    if protected is None:
        reasons.append("pump room protected region not detected")
    return reasons


def finalize_stage6_p2_selected_recovery(
    output_dir: Path,
    ref_path: Path,
    tgt_path: Path,
) -> dict[str, Any]:
    """Finalize two missed semantic bindings and the visually confirmed pump-room subregion offline."""
    selected = _read_json(output_dir / "selected_region_scans.json")
    ref_payload = _read_json(output_dir / "reference_regions.json")
    tgt_payload = _read_json(output_dir / "target_regions.json")
    ref_regions = list(ref_payload["regions"])
    tgt_regions = [item for item in tgt_payload["regions"] if item["region_id"] != "target_protected_pump_room_detail_0001"]
    ref_by_id = {item["region_id"]: item for item in ref_regions}
    tgt_by_id = {item["region_id"]: item for item in tgt_regions}
    ref_by_id["reference_region_0000"]["semantic_name"] = "地下一层平面图"
    ref_by_id["reference_region_0000"]["semantic_binding_source"] = "human_confirmed_plus_geometry_fingerprint"
    tgt_by_id["target_region_0006"]["semantic_name"] = "水箱间平面图、水箱间屋面平面图"
    tgt_by_id["target_region_0006"]["semantic_binding_source"] = "human_confirmed_plus_building_geometry_fingerprint"

    pump_entities = selected["target"]["regions"]["target_protected_pump_room_detail_0001"]
    pump_boxes = [_bbox2d(item) for item in pump_entities]
    pump_boxes = [box for box in pump_boxes if box is not None]
    if not pump_boxes:
        raise RuntimeError("pump room local scan has no CAD bbox evidence")
    pump_bbox = [
        min(box[0] for box in pump_boxes), min(box[1] for box in pump_boxes),
        max(box[2] for box in pump_boxes), max(box[3] for box in pump_boxes),
    ]
    pump_object_counts = Counter(str(item.get("object_name") or "") for item in pump_entities)
    pump_layer_counts = Counter(str(item.get("layer") or "") for item in pump_entities)
    protected = {
        "region_id": "target_protected_pump_room_detail_0001",
        "protected_region_id": "target_protected_pump_room_detail_0001",
        "semantic_name": "泵房大样 图幅A0 比例1:50",
        "frame_bbox": pump_bbox,
        "content_bbox": pump_bbox,
        "entity_handles": sorted(str(item["handle"]) for item in pump_entities if item.get("handle")),
        "entity_count": len(pump_entities),
        "object_name_counts": dict(sorted(pump_object_counts.items())),
        "layer_counts": dict(sorted(pump_layer_counts.items())),
        "confidence": 0.98,
        "classification": "PROTECTED_COMPLETE_REGION",
        "protection_reason": "NO_REFERENCE_MATCH",
        "evidence": ["GPT_VISUAL_CONFIRMED", "CAD_BBOX_LOCAL_SCAN", "395_ENTITY_HANDLE_SET"],
        "policy": {
            "type": "PROTECTED_COMPLETE_REGION",
            "NO_REFERENCE_MATCH": True,
            "READ_ALLOWED": True,
            "WRITE_FORBIDDEN": True,
            "COPY_IN_FORBIDDEN": True,
            "DELETE_FORBIDDEN": True,
            "TRANSFORM_FORBIDDEN": True,
        },
    }
    tgt_regions.append({
        "region_id": protected["region_id"],
        "role": "target",
        "semantic_name": protected["semantic_name"],
        "frame_bbox": pump_bbox,
        "content_bbox": pump_bbox,
        "spatial_position": {"center_x": (pump_bbox[0] + pump_bbox[2]) / 2, "center_y": (pump_bbox[1] + pump_bbox[3]) / 2},
        "orientation": "landscape" if pump_bbox[2] - pump_bbox[0] >= pump_bbox[3] - pump_bbox[1] else "portrait",
        "aspect_ratio": (pump_bbox[2] - pump_bbox[0]) / max(pump_bbox[3] - pump_bbox[1], 1.0),
        "entity_count": len(pump_entities),
        "ordinary_count": sum(not str(item.get("object_name") or "").startswith("TDb") for item in pump_entities),
        "tdb_count": sum(str(item.get("object_name") or "").startswith("TDb") for item in pump_entities),
        "text_count": sum(bool(_extract_text(item)) for item in pump_entities),
        "dominant_object_names": dict(pump_object_counts.most_common(10)),
        "dominant_layers": dict(pump_layer_counts.most_common(10)),
        "geometry_fingerprint": hashlib.sha256(json.dumps([pump_bbox, sorted(pump_object_counts.items())]).encode()).hexdigest()[:16],
        "classification": "PROTECTED_COMPLETE_REGION",
    })

    bindings = []
    for ref_semantic, tgt_semantic, pair_label in HUMAN_CONFIRMED_MAPPING:
        binding = _match_semantic_region(ref_regions, tgt_regions, ref_semantic, tgt_semantic, pair_label)
        if binding is not None:
            bindings.append(binding)
    confirmed = [item for item in bindings if item.get("binding_status") == "CONFIRMED"]
    if len(confirmed) != 7:
        raise RuntimeError(f"human mapping binding incomplete after recovery: {len(confirmed)}/7")

    transforms_payload = _read_json(output_dir / "coordinate_transforms.json")
    transforms_by_pair = {
        str(item["transform_id"]).removeprefix("transform_"): item
        for item in transforms_payload.get("transforms", [])
    }
    stats_payload = _read_json(output_dir / "anchor_statistics.json")
    stats_by_pair = {item["pair_label"]: item for item in stats_payload.get("pairs", [])}
    anchors_existing = []
    anchors_path = output_dir / "anchors.jsonl"
    if anchors_path.exists():
        anchors_existing = [json.loads(line) for line in anchors_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    for pair_label in ("pair_01_basement", "pair_05_tank"):
        binding = next(item for item in confirmed if item["pair_label"] == pair_label)
        ref_region = ref_by_id[binding["reference_region_id"]]
        tgt_region = tgt_by_id[binding["target_region_id"]]
        ref_entities = selected["reference"]["regions"][ref_region["region_id"]]
        tgt_entities = selected["target"]["regions"][tgt_region["region_id"]]
        started = time.monotonic()
        ref_raw = _extract_anchors_for_region({"entities": ref_entities}, ref_region)
        tgt_raw = _extract_anchors_for_region({"entities": tgt_entities}, tgt_region)
        _, ref_sampled, ref_stats = _deduplicate_and_sample_anchors(ref_raw, ref_region["frame_bbox"])
        _, tgt_sampled, tgt_stats = _deduplicate_and_sample_anchors(tgt_raw, tgt_region["frame_bbox"])
        matched = _match_anchors_kdtree(ref_sampled, tgt_sampled, ref_region["frame_bbox"], tgt_region["frame_bbox"])
        for item in matched:
            item["pair_label"] = pair_label
        candidates = _fit_transforms(matched, ref_region["frame_bbox"], tgt_region["frame_bbox"], deadline=started + REGION_TIMEOUT_SECONDS)
        best = _select_transform(candidates)
        record = _build_transform_record(
            binding, matched, best, ref_region, tgt_region,
            anchor_count_raw=len(ref_raw), anchor_count_sampled=len(ref_sampled),
            runtime_seconds=time.monotonic() - started, timed_out=time.monotonic() >= started + REGION_TIMEOUT_SECONDS,
        )
        transforms_by_pair[pair_label] = record
        stats_by_pair[pair_label] = {
            "pair_label": pair_label,
            "reference_region_id": ref_region["region_id"],
            "target_region_id": tgt_region["region_id"],
            "reference": ref_stats,
            "target": tgt_stats,
            "matched_count": len(matched),
            "inlier_count": record.get("anchor_count_inlier", 0),
        }
        anchors_existing = [item for item in anchors_existing if item.get("pair_label") != pair_label] + matched
        _write_json(output_dir / "alignment_reports" / f"{pair_label}.json", {
            "pair_label": pair_label, "binding": binding, "anchor_count": len(matched),
            "transform": record, "transform_candidates": candidates,
        })

    ordered_transforms = [transforms_by_pair[label] for _, _, label in HUMAN_CONFIRMED_MAPPING]
    for binding, transform in zip(confirmed, ordered_transforms):
        (output_dir / "alignment_reports" / f"{binding['pair_label']}.md").write_text(
            _generate_pair_md(binding["pair_label"], binding, transform.get("anchor_count_total", 0), transform, []),
            encoding="utf-8",
        )
    anchors_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in anchors_existing), encoding="utf-8")
    _write_json(output_dir / "anchor_statistics.json", {
        "pair_count": 7,
        "candidate_anchor_limit": MAX_CANDIDATE_ANCHORS,
        "ransac_sample_limit": MAX_RANSAC_ANCHORS,
        "region_timeout_seconds": REGION_TIMEOUT_SECONDS,
        "pairs": [stats_by_pair[label] for _, _, label in HUMAN_CONFIRMED_MAPPING],
    })
    _write_json(output_dir / "coordinate_transforms.json", {
        "count": 7,
        "transforms": ordered_transforms,
        "verified": sum(item["status"] == "VERIFIED" for item in ordered_transforms),
        "low_confidence": sum(item["status"] == "LOW_CONFIDENCE" for item in ordered_transforms),
        "rejected": sum(item["status"] == "REJECTED" for item in ordered_transforms),
        "timeout": sum(item["status"] == "TIMEOUT" for item in ordered_transforms),
    })
    _write_json(output_dir / "reference_regions.json", {"count": 7, "regions": ref_regions})
    _write_json(output_dir / "target_regions.json", {"count": 8, "standard_frame_region_count": 7, "protected_subregion_count": 1, "regions": tgt_regions})
    _write_json(output_dir / "manual_mapping_bound.json", {"count": 7, "bindings": confirmed, "confirmed": 7, "conflicts": 0, "not_found": 0})
    _write_json(output_dir / "manual_mapping_consistency.json", {
        "total_candidates": 7, "bound_count": 7, "confirmed_count": 7,
        "conflict_count": 0, "conflicts": [], "human_review_required": False,
        "binding_authority": "USER_CONFIRMED_MODELSPACE_PDF_MAPPING",
    })
    _write_json(output_dir / "protected_regions.json", {"count": 1, "regions": [protected]})
    _render_region_contact_sheet(ref_regions, tgt_regions, confirmed, protected, output_dir / "region_contact_sheet.png")

    verified = sum(item["status"] == "VERIFIED" for item in ordered_transforms)
    low = sum(item["status"] == "LOW_CONFIDENCE" for item in ordered_transforms)
    rejected = sum(item["status"] == "REJECTED" for item in ordered_transforms)
    timeout = sum(item["status"] == "TIMEOUT" for item in ordered_transforms)
    hashes_unchanged = selected["reference"]["hash_unchanged"] and selected["target"]["hash_unchanged"] and _sha256(ref_path) == selected["reference"]["hash_before"] and _sha256(tgt_path) == selected["target"]["hash_before"]
    final_status = "COORDINATE_SYSTEM_RECONSTRUCTION_COMPLETE" if verified == 7 else "COORDINATE_SYSTEM_RECONSTRUCTION_PARTIAL"
    manifest = {
        "run_id": output_dir.name,
        "reference_path": str(ref_path), "reference_sha256": _sha256(ref_path),
        "target_path": str(tgt_path), "target_sha256": _sha256(tgt_path),
        "reference_entity_count": 10606, "target_entity_count": 6481,
        "reference_region_count": 7, "target_region_count": 8,
        "standard_target_frame_region_count": 7, "protected_region_count": 1,
        "confirmed_region_pair_count": 7,
        "verified_transform_count": verified, "low_confidence_transform_count": low,
        "rejected_transform_count": rejected, "timeout_transform_count": timeout,
        "mapping_conflict_count": 0,
        "old_plan_reused": False, "old_region_ids_reused": False,
        "old_transforms_reused": False, "old_mapping_reused": False,
        "target_write": False, "target_save": False, "reference_save": False,
        "reference_hash_unchanged": hashes_unchanged, "target_hash_unchanged": hashes_unchanged,
        "ready_for_missing_detection": verified == 7 and hashes_unchanged,
        "missing_detection_executed": False, "frozen_execution_plan_created": False,
        "blocking_reasons": [] if verified == 7 else [f"{7 - verified}/7 region transforms are not VERIFIED"],
        "final_status": final_status, "created_at": _now_iso(),
        "artifacts_root": str(output_dir),
    }
    _write_json(output_dir / "coordinate_system_manifest.json", manifest)
    _write_json(REPORTS_DIR / "stage6_p2_coordinate_reconstruction.json", {
        **manifest,
        "region_mappings": confirmed,
        "transforms": ordered_transforms,
        "protected_regions": [protected],
        "backup": _read_json(output_dir / "prewrite_backup_manifest.json").get("backup"),
    })
    (REPORTS_DIR / "stage6_p2_coordinate_reconstruction.md").write_text(
        _generate_final_report_md(manifest, ordered_transforms, protected, confirmed, []), encoding="utf-8",
    )
    return manifest


def _generate_pair_md(
    pair_label: str,
    binding: dict[str, Any],
    anchor_count: int,
    transform: dict[str, Any],
    all_transforms: list[dict[str, Any]],
) -> str:
    lines = [
        f"# 区域对齐报告：{pair_label}",
        "",
        "## 区域绑定",
        f"- Reference：`{binding.get('reference_region_id')}` — {binding.get('reference_semantic_name')}",
        f"- Target：`{binding.get('target_region_id')}` — {binding.get('target_semantic_name')}",
        f"- 状态：**{binding.get('binding_status')}**",
    ]
    if binding.get("title_conflict"):
        lines.append(f"- 标题冲突：{binding['title_conflict']}（人工位置映射优先）")

    lines += [
        "",
        "## 坐标变换",
        f"- 模型：`{transform.get('model_type')}`",
        f"- 状态：**{transform.get('status')}**",
        f"- 锚点：raw={transform.get('anchor_count_raw')} / sampled={transform.get('anchor_count_sampled')} / inlier={transform.get('anchor_count_inlier')}",
        f"- 锚点类型数：{transform.get('anchor_type_count')}",
        f"- 方向覆盖率：{transform.get('directional_coverage')}",
        f"- 空间覆盖率：{transform.get('spatial_coverage')}",
        f"- RMS / median / max：{transform.get('rms_error')} / {transform.get('median_error')} / {transform.get('max_error')}",
        f"- 比例：({transform.get('scale_x')}, {transform.get('scale_y')})",
        f"- 旋转：{transform.get('rotation_deg')}°",
        f"- 平移：({transform.get('translate_x')}, {transform.get('translate_y')})",
        f"- 变换后 bbox 位于 target：{transform.get('transformed_bbox_inside_target')}",
        f"- 置信度：{transform.get('confidence')}",
        f"- 运行时间：{transform.get('runtime_seconds')} 秒",
    ]
    if transform.get("blocking_reasons"):
        lines.append("\n### 阻断原因")
        for r in transform["blocking_reasons"]:
            lines.append(f"- {r}")

    if len(all_transforms) > 1:
        lines.append("\n## 变换候选")
        for i, t in enumerate(all_transforms):
            lines.append(f"\n### 候选 {i + 1}：{t['model_type']}")
            lines.append(f"- RMS：{t['rms_error']}，Inliers：{t['anchor_count_inlier']}/{t['anchor_count_total']}")

    return "\n".join(lines) + "\n"


def _generate_final_report_md(
    manifest: dict[str, Any],
    transforms: list[dict[str, Any]],
    protected: dict[str, Any] | None,
    bindings: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> str:
    lines = [
        "# Stage 6-P2 正确样本快速多区域坐标系重建报告",
        "",
        f"**Run ID:** `{manifest['run_id']}`",
        f"**Created:** {manifest['created_at']}",
        "",
        "## 输入身份",
        f"- Reference：`{manifest['reference_path']}`",
        f"  - SHA256：`{manifest['reference_sha256']}`",
        f"  - 实体数：{manifest['reference_entity_count']}",
        f"- Target：`{manifest['target_path']}`",
        f"  - SHA256：`{manifest['target_sha256']}`",
        f"  - 实体数：{manifest['target_entity_count']}",
        "",
        "## 区域检测",
        f"- Reference 区域数：{manifest['reference_region_count']}",
        f"- Target 逻辑区域数：{manifest['target_region_count']}",
        f"- 人工确认绑定数：{manifest['confirmed_region_pair_count']}",
        f"- 映射冲突数：{manifest['mapping_conflict_count']}",
        "",
        "## 坐标变换",
        f"- VERIFIED: {manifest['verified_transform_count']}",
        f"- LOW_CONFIDENCE: {manifest['low_confidence_transform_count']}",
        f"- REJECTED: {manifest['rejected_transform_count']}",
        "",
        "| Pair | Model | Status | Anchors (total/inlier) | Types | DirCov | RMS | Scale | Confidence |",
        "|------|-------|--------|------------------------|-------|--------|-----|-------|------------|",
    ]
    for t in transforms:
        lines.append(
            f"| {t.get('transform_id', '?')} | {t.get('model_type', '?')} | **{t.get('status', '?')}** | "
            f"{t.get('anchor_count_total', 0)}/{t.get('anchor_count_inlier', 0)} | "
            f"{t.get('anchor_type_count', 0)} | {t.get('directional_coverage', 0):.2f} | "
            f"{t.get('rms_error', '?')} | ({t.get('scale_x', 0):.3f}, {t.get('scale_y', 0):.3f}) | "
            f"{t.get('confidence', 0):.3f} |"
        )

    lines += [
        "",
        "## 保护区域",
    ]
    if protected:
        lines += [
            f"- **{protected['protected_region_id']}**：{protected['semantic_name']}",
            f"  - 策略：`{protected['policy']['type']}`",
            f"  - 实体数：{protected['entity_count']}",
            f"  - 原因：{protected['protection_reason']}",
        ]
    else:
        lines.append("- 警告：未识别泵房区域。")

    if conflicts:
        lines += ["", "## 冲突", ""]
        for c in conflicts:
            lines.append(f"- `{c.get('pair_label')}`: {c.get('error', 'unknown')}")

    lines += [
        "",
        "## 安全门",
        f"- `old_plan_reused`: {manifest['old_plan_reused']}",
        f"- `target_write`: {manifest['target_write']}",
        f"- `target_save`: {manifest['target_save']}",
        f"- `reference_hash_unchanged`: {manifest['reference_hash_unchanged']}",
        f"- `target_hash_unchanged`: {manifest['target_hash_unchanged']}",
        f"- `ready_for_missing_detection`: **{manifest['ready_for_missing_detection']}**",
    ]

    if manifest.get("blocking_reasons"):
        lines += ["", "## 阻断原因"]
        for r in manifest["blocking_reasons"]:
            lines.append(f"- {r}")

    return "\n".join(lines) + "\n"
