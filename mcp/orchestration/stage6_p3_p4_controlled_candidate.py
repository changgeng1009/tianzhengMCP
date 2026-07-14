"""Stage 6-P3/P4 缺失检测与候选副本受控写入。

原始 DWG 仅用于只读扫描；所有 CopyObjects、Move、Save 均被路径守卫限制在
本阶段新建的候选副本。证据不足的对象不会进入冻结计划。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import html
import json
import math
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping, Sequence


VERIFIED_STATUSES = {
    "ALIGNMENT_VERIFIED",
    "ALIGNMENT_VERIFIED_AFTER_SEMANTIC_REINDEX",
    "VERIFIED_BY_MANUAL_ANCHORS_AFTER_SEMANTIC_REINDEX",
}
DIRECT_TDB_TYPES = {
    "TDbPipe", "TDbDoubleLinePipe", "TDbPipeFitting", "TDbPipeValve",
    "TDbPump", "TDbEquipment", "TDbWaterTank", "TDbVPipeDim",
    "TDbSymbMultiLeader",
}
DIRECT_ORDINARY_TYPES = {
    "AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline",
    "AcDbCircle", "AcDbArc", "AcDbBlockReference",
}
ANNOTATION_TYPES = {
    "TDbDimension2", "TDbVPipeDim", "TDbSymbMultiLeader",
    "AcDbText", "AcDbMText", "AcDbDimension", "AcDbAlignedDimension",
}
FRAME_TDB_TYPES = {"TDbDrawingName", "TDbVPort"}
PROFESSIONAL_LAYER_MARKERS = (
    "给水", "排水", "消防", "喷淋", "消火栓", "水泵", "水箱", "阀",
    "pipe", "valve", "equip", "vpipe", "wsd", "dim_",
)
FRAME_LAYER_MARKERS = ("图框", "标题", "title", "frame", "border")
BUILDING_LAYER_MARKERS = (
    "墙", "柱", "门", "窗", "楼梯", "电梯", "轴", "建筑", "wall",
    "column", "door", "window", "stair", "axis",
)
ANCHOR_MARKERS = ("MCP_ANCHOR", "MCP_ANCHOR_POINT")


@dataclass(frozen=True)
class RunPaths:
    root: Path
    input_identity: Path
    missing_detection: Path
    frozen_plan: Path
    previews: Path
    execution: Path
    verification: Path
    backups: Path
    logs: Path

    @classmethod
    def build(cls, root: Path) -> "RunPaths":
        return cls(root, *(root / name for name in (
            "input_identity", "missing_detection", "frozen_plan", "previews",
            "execution", "verification", "backups", "logs",
        )))

    def create(self) -> None:
        for path in self.__dict__.values():
            Path(path).mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "full_path": str(path.resolve()),
        "file_size": stat.st_size,
        "modified_time": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "sha256": sha256_file(path),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(dict(record), ensure_ascii=False) + "\n")


def payload_sha256(payload: Mapping[str, Any]) -> str:
    clean = dict(payload)
    clean.pop("plan_sha256", None)
    raw = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def validate_transform_manifest(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    transforms = list(payload.get("transforms", []))
    if len(transforms) != 7 or payload.get("count") != 7:
        errors.append("transform_count_must_equal_7")
    ref_ids = [item.get("reference_region_id") for item in transforms]
    target_ids = [item.get("target_region_id") for item in transforms]
    if len(set(ref_ids)) != len(ref_ids):
        errors.append("duplicate_reference_region_binding")
    if len(set(target_ids)) != len(target_ids):
        errors.append("duplicate_target_region_binding")
    for item in transforms:
        if item.get("final_status") not in VERIFIED_STATUSES:
            errors.append(f"unverified_transform:{item.get('semantic_key')}")
        if item.get("transform_type") != "translation_only":
            errors.append(f"non_translation_transform:{item.get('semantic_key')}")
        if float(item.get("scale", 0)) != 1.0 or float(item.get("rotation", math.inf)) != 0.0:
            errors.append(f"scale_or_rotation_invalid:{item.get('semantic_key')}")
    text = json.dumps(payload, ensure_ascii=False)
    if "锚点校准" in text or any(marker in text for marker in ANCHOR_MARKERS):
        errors.append("calibration_or_anchor_reference_forbidden")
    return errors


def validate_input_hashes(actual_reference: str, expected_reference: str, actual_target: str, expected_target: str) -> list[str]:
    errors = []
    if actual_reference.casefold() != expected_reference.casefold():
        errors.append("reference_hash_mismatch")
    if actual_target.casefold() != expected_target.casefold():
        errors.append("target_hash_mismatch")
    return errors


def autocad_instance_conflict(state: Mapping[str, Any]) -> bool:
    caption = str(state.get("caption", ""))
    documents = list(state.get("documents", []))
    return "给排水" not in caption or bool(documents) or int(state.get("document_count", len(documents))) != 0


def _bbox_flat(entity: Mapping[str, Any]) -> list[float] | None:
    raw = entity.get("bbox")
    if not raw:
        return None
    if len(raw) == 2 and all(isinstance(item, (list, tuple)) for item in raw):
        return [float(raw[0][0]), float(raw[0][1]), float(raw[1][0]), float(raw[1][1])]
    if len(raw) >= 4:
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    return None


def bbox_center(bbox: Sequence[float] | None) -> tuple[float, float] | None:
    if bbox is None:
        return None
    return ((float(bbox[0]) + float(bbox[2])) / 2, (float(bbox[1]) + float(bbox[3])) / 2)


def translate_bbox(bbox: Sequence[float], tx: float, ty: float) -> list[float]:
    return [bbox[0] + tx, bbox[1] + ty, bbox[2] + tx, bbox[3] + ty]


def bbox_intersects(left: Sequence[float] | None, right: Sequence[float] | None) -> bool:
    if left is None or right is None:
        return False
    return not (left[2] <= right[0] or left[0] >= right[2] or left[3] <= right[1] or left[1] >= right[3])


def bbox_inside(inner: Sequence[float], outer: Sequence[float], tolerance: float = 2.0) -> bool:
    return (
        inner[0] >= outer[0] - tolerance and inner[1] >= outer[1] - tolerance
        and inner[2] <= outer[2] + tolerance and inner[3] <= outer[3] + tolerance
    )


def _normalized(value: Any) -> str:
    return "" if value is None else str(value).strip().casefold()


def is_anchor_entity(entity: Mapping[str, Any]) -> bool:
    values = [entity.get("layer"), entity.get("attributes", {}).get("name"),
              entity.get("attributes", {}).get("effective_name"), entity.get("attributes", {}).get("text")]
    joined = "|".join(_normalized(value) for value in values)
    return any(marker.casefold() in joined for marker in ANCHOR_MARKERS)


def classify_entity(entity: Mapping[str, Any], *, protected: bool = False) -> dict[str, Any]:
    name = str(entity.get("object_name") or "UNKNOWN")
    layer = _normalized(entity.get("layer"))
    attributes = entity.get("attributes") or {}
    text = _normalized(attributes.get("text") or attributes.get("mtext_contents"))
    block = _normalized(attributes.get("effective_name") or attributes.get("name"))
    if is_anchor_entity(entity):
        return {"entity_class": "EXCLUDED_UNRELATED_TEXT", "professional": False, "direct_clone_supported": False, "reason": "MCP_ANCHOR_EXCLUDED"}
    if protected:
        return {"entity_class": "PROTECTED_REGION_ENTITY", "professional": False, "direct_clone_supported": False, "reason": "PROTECTED_COMPLETE_REGION"}
    if name in FRAME_TDB_TYPES or any(marker in layer for marker in FRAME_LAYER_MARKERS):
        return {"entity_class": "FRAME_OR_TITLE", "professional": False, "direct_clone_supported": False, "reason": "FRAME_OR_TITLE_TYPE_OR_LAYER"}
    if any(marker in layer for marker in BUILDING_LAYER_MARKERS):
        return {"entity_class": "BUILDING_BASE", "professional": False, "direct_clone_supported": False, "reason": "BUILDING_LAYER"}
    if name.startswith("TDb"):
        if name in ANNOTATION_TYPES:
            cls = "PROFESSIONAL_ANNOTATION"
        elif name in {"TDbPipe", "TDbDoubleLinePipe"}:
            cls = "PROFESSIONAL_GEOMETRY"
        else:
            cls = "PROFESSIONAL_SYMBOL"
        return {
            "entity_class": cls,
            "professional": name not in FRAME_TDB_TYPES,
            "direct_clone_supported": name in DIRECT_TDB_TYPES,
            "reason": "TDB_OBJECT_TYPE",
        }
    professional_layer = any(marker in layer for marker in PROFESSIONAL_LAYER_MARKERS)
    if name in {"AcDbText", "AcDbMText"}:
        if professional_layer:
            return {"entity_class": "PROFESSIONAL_ANNOTATION", "professional": True, "direct_clone_supported": False, "reason": "PROFESSIONAL_LAYER_TEXT_REQUIRES_ASSOCIATION"}
        return {"entity_class": "GENERAL_TEXT", "professional": False, "direct_clone_supported": False, "reason": "UNRELATED_TEXT"}
    if name == "AcDbBlockReference":
        professional_block = any(marker in block for marker in PROFESSIONAL_LAYER_MARKERS)
        if professional_layer and professional_block:
            return {"entity_class": "PROFESSIONAL_SYMBOL", "professional": True, "direct_clone_supported": True, "reason": "PROFESSIONAL_BLOCK_AND_LAYER"}
        return {"entity_class": "BUILDING_BASE", "professional": False, "direct_clone_supported": False, "reason": "BLOCK_NOT_PROVEN_PROFESSIONAL"}
    if name in DIRECT_ORDINARY_TYPES and professional_layer:
        return {"entity_class": "PROFESSIONAL_GEOMETRY", "professional": True, "direct_clone_supported": True, "reason": "PROFESSIONAL_LAYER_GEOMETRY"}
    if name.startswith("AcDb"):
        return {"entity_class": "BUILDING_BASE", "professional": False, "direct_clone_supported": False, "reason": "ORDINARY_NON_PROFESSIONAL_GEOMETRY"}
    return {"entity_class": "UNKNOWN_CUSTOM_ENTITY", "professional": False, "direct_clone_supported": False, "reason": "UNKNOWN_CUSTOM_ENTITY"}


def bind_region(entity: Mapping[str, Any], regions: Sequence[Mapping[str, Any]]) -> str | None:
    center = bbox_center(_bbox_flat(entity))
    if center is None:
        return None
    candidates = [
        item for item in regions
        if item["frame_bbox"][0] <= center[0] <= item["frame_bbox"][2]
        and item["frame_bbox"][1] <= center[1] <= item["frame_bbox"][3]
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item["frame_bbox"][2] - item["frame_bbox"][0]) * (item["frame_bbox"][3] - item["frame_bbox"][1]))["region_id"]


def _system_type(entity: Mapping[str, Any]) -> str:
    attrs = entity.get("attributes") or {}
    return _normalized(attrs.get("sys_type") or attrs.get("system_type") or entity.get("layer"))


def _geometry_shape(entity: Mapping[str, Any]) -> tuple[float, float]:
    bbox = _bbox_flat(entity)
    if bbox is None:
        return (0.0, 0.0)
    return (round(bbox[2] - bbox[0], 3), round(bbox[3] - bbox[1], 3))


def geometry_stable(entity: Mapping[str, Any]) -> bool:
    bbox = _bbox_flat(entity)
    if bbox is None:
        return False
    name = str(entity.get("object_name"))
    geometry = entity.get("geometry") or {}
    if name in {"TDbPipe", "TDbDoubleLinePipe", "AcDbLine"}:
        return bool(geometry.get("start_point") and geometry.get("end_point")) or max(_geometry_shape(entity)) > 0
    return bbox_center(bbox) is not None


def equivalent_entity(source: Mapping[str, Any], target: Mapping[str, Any], tx: float, ty: float, tolerance: float = 3.0) -> bool:
    if source.get("object_name") != target.get("object_name"):
        return False
    source_bbox, target_bbox = _bbox_flat(source), _bbox_flat(target)
    if source_bbox is None or target_bbox is None:
        return False
    mapped = translate_bbox(source_bbox, tx, ty)
    source_center, target_center = bbox_center(mapped), bbox_center(target_bbox)
    assert source_center is not None and target_center is not None
    if math.dist(source_center, target_center) > tolerance:
        return False
    sw, sh = mapped[2] - mapped[0], mapped[3] - mapped[1]
    tw, th = target_bbox[2] - target_bbox[0], target_bbox[3] - target_bbox[1]
    if abs(sw - tw) > tolerance or abs(sh - th) > tolerance:
        return False
    source_attrs, target_attrs = source.get("attributes") or {}, target.get("attributes") or {}
    for key in ("dn_diameter", "sys_type", "effective_name", "name", "text"):
        left, right = source_attrs.get(key), target_attrs.get(key)
        if left is not None and right is not None and _normalized(left) != _normalized(right):
            return False
    return True


def _grid_key(point: tuple[float, float], size: float = 100.0) -> tuple[int, int]:
    return (math.floor(point[0] / size), math.floor(point[1] / size))


def _nearby_grid_keys(point: tuple[float, float], size: float = 100.0) -> Iterable[tuple[int, int]]:
    gx, gy = _grid_key(point, size)
    for x in range(gx - 1, gx + 2):
        for y in range(gy - 1, gy + 2):
            yield (x, y)


def detect_missing(
    reference_entities: Sequence[Mapping[str, Any]],
    target_entities: Sequence[Mapping[str, Any]],
    transforms: Sequence[Mapping[str, Any]],
    reference_regions: Sequence[Mapping[str, Any]],
    target_regions: Sequence[Mapping[str, Any]],
    protected_bboxes: Sequence[Sequence[float]],
) -> dict[str, Any]:
    transform_by_ref = {item["reference_region_id"]: item for item in transforms}
    target_region_by_ref = {item["reference_region_id"]: item for item in transforms}
    target_frame_by_id = {item["region_id"]: item["frame_bbox"] for item in target_regions}
    target_index: dict[tuple[str, str, str, tuple[int, int]], list[Mapping[str, Any]]] = defaultdict(list)
    for target in target_entities:
        region_id = bind_region(target, target_regions)
        classification = classify_entity(target, protected=any(bbox_intersects(_bbox_flat(target), bbox) for bbox in protected_bboxes))
        center = bbox_center(_bbox_flat(target))
        if region_id and center and classification["professional"]:
            key = (region_id, str(target.get("object_name")), _system_type(target), _grid_key(center))
            target_index[key].append(target)

    buckets: dict[str, list[dict[str, Any]]] = {
        "missing": [], "already_present": [], "review_only": [], "excluded": [],
    }
    region_stats: dict[str, Counter[str]] = defaultdict(Counter)
    class_stats: Counter[str] = Counter()
    for source in reference_entities:
        source = dict(source)
        ref_region = bind_region(source, reference_regions)
        transform = transform_by_ref.get(ref_region or "")
        classification = classify_entity(source)
        source.update(classification)
        source["reference_region_id"] = ref_region
        if not classification["professional"]:
            source["status"] = (
                classification["entity_class"] if classification["entity_class"].startswith("EXCLUDED_")
                else "EXCLUDED_BUILDING_OR_FRAME" if classification["entity_class"] in {"BUILDING_BASE", "FRAME_OR_TITLE"}
                else "UNSUPPORTED_ENTITY"
            )
            buckets["excluded"].append(source)
            if ref_region:
                region_stats[ref_region]["excluded_count"] += 1
            continue
        class_stats[str(source.get("object_name"))] += 1
        if ref_region is None or transform is None:
            source["status"] = "OUTSIDE_ALLOWED_REGION"
            source["reason"] = "REFERENCE_ENTITY_NOT_BOUND_TO_VERIFIED_REGION"
            buckets["review_only"].append(source)
            continue
        target_region_id = transform["target_region_id"]
        source["semantic_region"] = transform.get("semantic_name")
        source_bbox = _bbox_flat(source)
        if source_bbox is None:
            source["status"] = "AMBIGUOUS_REVIEW_ONLY"
            source["reason"] = "BBOX_UNREADABLE"
            buckets["review_only"].append(source)
            region_stats[ref_region]["review_only_count"] += 1
            continue
        tx, ty = float(transform["translation_x"]), float(transform["translation_y"])
        expected_bbox = translate_bbox(source_bbox, tx, ty)
        source["target_region_id"] = target_region_id
        source["expected_target_bbox"] = expected_bbox
        source["transform"] = {"type": "translation_only", "x": tx, "y": ty}
        if any(bbox_intersects(expected_bbox, bbox) for bbox in protected_bboxes):
            source["status"] = "EXCLUDED_PROTECTED_REGION"
            buckets["excluded"].append(source)
            region_stats[ref_region]["protected_intersection_count"] += 1
            continue
        target_frame = target_frame_by_id[target_region_id]
        center = bbox_center(expected_bbox)
        assert center is not None
        if not bbox_inside(expected_bbox, target_frame, tolerance=5.0):
            source["status"] = "OUTSIDE_ALLOWED_REGION" if not bbox_intersects(expected_bbox, target_frame) else "AMBIGUOUS_REVIEW_ONLY"
            source["reason"] = "CROSS_REGION_BOUNDARY_OR_OUTSIDE_TARGET"
            buckets["review_only"].append(source)
            region_stats[ref_region]["review_only_count"] += 1
            continue
        candidates: list[Mapping[str, Any]] = []
        for grid in _nearby_grid_keys(center):
            candidates.extend(target_index.get((target_region_id, str(source.get("object_name")), _system_type(source), grid), []))
            if not candidates and _system_type(source):
                candidates.extend(target_index.get((target_region_id, str(source.get("object_name")), "", grid), []))
        matches = [item for item in candidates if equivalent_entity(source, item, tx, ty)]
        if matches:
            source["status"] = "ALREADY_PRESENT"
            source["equivalent_target_handles"] = [item.get("handle") for item in matches]
            buckets["already_present"].append(source)
            region_stats[ref_region]["already_present_count"] += 1
            continue
        if not classification["direct_clone_supported"] or not geometry_stable(source):
            source["status"] = "UNSUPPORTED_ENTITY" if not classification["direct_clone_supported"] else "AMBIGUOUS_REVIEW_ONLY"
            source["reason"] = "DIRECT_CLONE_UNSUPPORTED_OR_GEOMETRY_UNSTABLE"
            buckets["review_only"].append(source)
            region_stats[ref_region]["unsupported_count" if not classification["direct_clone_supported"] else "review_only_count"] += 1
            continue
        source["status"] = "CONFIRMED_MISSING_DIRECT_CLONE"
        source["confidence"] = 0.95
        source["reason_confirmed_missing"] = "VERIFIED_REGION_TRANSLATION_AND_NO_EQUIVALENT_TARGET_ENTITY"
        buckets["missing"].append(source)
        region_stats[ref_region]["confirmed_missing_count"] += 1

    for region in reference_regions:
        rid = region["region_id"]
        region_stats[rid]["reference_professional_count"] = sum(
            1 for item in reference_entities if bind_region(item, reference_regions) == rid and classify_entity(item)["professional"]
        )
        target_id = target_region_by_ref.get(rid, {}).get("target_region_id")
        region_stats[rid]["target_professional_count"] = sum(
            1 for item in target_entities if target_id and bind_region(item, target_regions) == target_id and classify_entity(item)["professional"]
        )
    return {
        **buckets,
        "region_statistics": {key: dict(value) for key, value in sorted(region_stats.items())},
        "reference_professional_by_object_type": dict(sorted(class_stats.items())),
    }


def scan_dwg_readonly(acad: Any, path: Path, role: str, *, progress_every: int = 500) -> dict[str, Any]:
    """按绝对路径只读扫描 ModelSpace，关闭时明确不保存。"""
    from mcp.acceptance.stage3_1_runtime import (
        _close_document_without_save,
        _open_document_with_retry,
        _resolve_open_document,
        _scan_entity,
    )
    from mcp.acceptance.stage5_2_native_clone_poc import _retry

    resolved = path.resolve()
    before = sha256_file(resolved)
    document = None
    entities: list[dict[str, Any]] = []
    try:
        returned = _open_document_with_retry(acad, resolved)
        document = _resolve_open_document(acad, resolved, returned)
        if Path(str(document.FullName)).resolve() != resolved:
            raise RuntimeError(f"{role}_document_path_mismatch")
        modelspace = _retry(lambda: document.ModelSpace, f"{role} ModelSpace", attempts=40, delay=0.25)
        objects = list(modelspace)
        total = len(objects)
        for index, native in enumerate(objects, 1):
            entities.append(_scan_entity(native, role, "Model"))
            if progress_every and index % progress_every == 0:
                print(f"[{role}] scanned={index}/{total}", flush=True)
        document_info = {
            "name": str(document.Name),
            "full_path": str(document.FullName),
            "modelspace_count": total,
            "saved_before_close": bool(document.Saved),
        }
    finally:
        if document is not None:
            _close_document_without_save(document)
    after = sha256_file(resolved)
    return {
        "document_role": role,
        "document": document_info,
        "entity_count": len(entities),
        "object_type_counts": dict(sorted(Counter(item["object_name"] for item in entities).items())),
        "entities": entities,
        "sha256_before": before,
        "sha256_after": after,
        "hash_unchanged": before == after,
        "write": False,
        "save": False,
    }


def build_dependency_graph(missing: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_region: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in missing:
        by_region[str(item["reference_region_id"])].append(item)
    nodes, edges = [], []
    for region_id, items in sorted(by_region.items()):
        pipes = [item for item in items if item.get("object_name") in {"TDbPipe", "TDbDoubleLinePipe"}]
        for item in items:
            handle = str(item.get("handle"))
            dependencies: list[str] = []
            if item.get("object_name") in {"TDbPipeValve", "TDbPipeFitting", "TDbVPipeDim", "TDbSymbMultiLeader"}:
                center = bbox_center(_bbox_flat(item))
                candidates = []
                for pipe in pipes:
                    pcenter = bbox_center(_bbox_flat(pipe))
                    if center and pcenter:
                        candidates.append((math.dist(center, pcenter), str(pipe.get("handle"))))
                if candidates and candidates[0][0] <= 2000:
                    dependencies = [min(candidates)[1]]
            for dependency in dependencies:
                edges.append({"from_source_handle": dependency, "to_source_handle": handle, "type": "GEOMETRY_NEAREST_DEPENDENCY"})
            nodes.append({"source_handle": handle, "object_name": item.get("object_name"), "reference_region_id": region_id, "dependency_source_handles": dependencies})
    return {"nodes": nodes, "edges": edges, "dependency_count": len(edges), "method": "CONSERVATIVE_GEOMETRY_NEAREST_WITHIN_REGION"}


def build_frozen_plan(missing: Sequence[Mapping[str, Any]], dependency_graph: Mapping[str, Any], identities: Mapping[str, Any]) -> dict[str, Any]:
    dependency_by_handle = {item["source_handle"]: item["dependency_source_handles"] for item in dependency_graph["nodes"]}
    order_rank = {
        "TDbPipe": 10, "TDbDoubleLinePipe": 10, "AcDbLine": 15,
        "AcDbPolyline": 15, "AcDb2dPolyline": 15, "AcDb3dPolyline": 15,
        "TDbPipeFitting": 30, "TDbPipeValve": 40, "TDbPump": 50,
        "TDbEquipment": 50, "TDbWaterTank": 50, "AcDbBlockReference": 50,
        "TDbVPipeDim": 70, "TDbSymbMultiLeader": 70,
    }
    ordered = sorted(missing, key=lambda item: (str(item["reference_region_id"]), order_rank.get(str(item.get("object_name")), 60), str(item.get("handle"))))
    tasks = []
    task_by_handle = {str(item.get("handle")): f"stage6_p3_{str(item['reference_region_id']).replace('reference_region_', 'r')}_{item.get('handle')}" for item in ordered}
    for index, item in enumerate(ordered, 1):
        handle = str(item.get("handle"))
        tasks.append({
            "task_id": task_by_handle[handle],
            "semantic_region": item.get("semantic_region"),
            "reference_region_id": item["reference_region_id"],
            "target_region_id": item["target_region_id"],
            "source_handle": handle,
            "source_object_name": item.get("object_name"),
            "source_layer": item.get("layer"),
            "entity_class": item.get("entity_class"),
            "system_type": _system_type(item),
            "source_bbox": _bbox_flat(item),
            "transform": item["transform"],
            "expected_target_bbox": item["expected_target_bbox"],
            "dependency_ids": [task_by_handle[value] for value in dependency_by_handle.get(handle, []) if value in task_by_handle],
            "execution_order": index,
            "clone_method": "CopyObjects_then_Move_translation_only",
            "verification_method": "IDPairs_handle_bbox_type_properties_persistence",
            "confidence": item.get("confidence", 0.0),
            "reason_confirmed_missing": item.get("reason_confirmed_missing"),
        })
    plan = {
        "phase": "STAGE6-P3-P4-FROZEN-WRITE-PLAN",
        "status": "FROZEN_PREWRITE",
        "frozen_inputs": identities,
        "task_count": len(tasks),
        "tasks": tasks,
        "no_plan_expansion_allowed": True,
        "target_original_write": False,
        "target_original_save": False,
    }
    plan["plan_sha256"] = payload_sha256(plan)
    return plan


def create_candidate_copy(target: Path, candidate: Path, backup: Path) -> dict[str, Any]:
    if candidate.exists() or backup.exists():
        raise FileExistsError("candidate_or_prewrite_backup_already_exists")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, candidate)
    shutil.copy2(candidate, backup)
    target_hash = sha256_file(target)
    candidate_hash = sha256_file(candidate)
    backup_hash = sha256_file(backup)
    if target_hash != candidate_hash or candidate_hash != backup_hash:
        raise RuntimeError("candidate_or_backup_hash_mismatch")
    return {"target_sha256": target_hash, "candidate_initial_sha256": candidate_hash, "prewrite_backup_sha256": backup_hash}


def render_region_preview(path: Path, target_bbox: Sequence[float], planned: Sequence[Mapping[str, Any]], review: Sequence[Mapping[str, Any]], protected: Sequence[Sequence[float]]) -> None:
    width, height = 1200, 800
    xmin, ymin, xmax, ymax = map(float, target_bbox)
    sx, sy = (width - 80) / max(xmax - xmin, 1.0), (height - 80) / max(ymax - ymin, 1.0)
    scale = min(sx, sy)
    def rect(bbox: Sequence[float], color: str, opacity: float) -> str:
        x = 40 + (bbox[0] - xmin) * scale
        y = 40 + (ymax - bbox[3]) * scale
        w, h = max((bbox[2] - bbox[0]) * scale, 1), max((bbox[3] - bbox[1]) * scale, 1)
        return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{color}" fill-opacity="{opacity}" stroke="{color}" stroke-width="1"/>'
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">', '<rect width="100%" height="100%" fill="white"/>', rect(target_bbox, "#444", 0.02)]
    for bbox in protected:
        if bbox_intersects(bbox, target_bbox): lines.append(rect(bbox, "#d62728", 0.20))
    for item in review:
        bbox = item.get("expected_target_bbox")
        if bbox and bbox_intersects(bbox, target_bbox): lines.append(rect(bbox, "#f0ad00", 0.12))
    for item in planned:
        bbox = item.get("expected_target_bbox")
        if bbox and bbox_intersects(bbox, target_bbox): lines.append(rect(bbox, "#148a3d", 0.18))
    lines.append(f'<text x="40" y="25" font-family="sans-serif" font-size="16">planned={len(planned)} review={len(review)}</text>')
    lines.append('</svg>')
    path.write_text("\n".join(lines), encoding="utf-8")


def snapshot_records(entities: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_handle = {str(item.get("handle")).upper(): item for item in entities if item.get("handle")}
    return {
        "modelspace_count": len(entities),
        "handles": sorted(by_handle),
        "signatures": {
            handle: {
                "object_name": item.get("object_name"), "layer": item.get("layer"),
                "bbox": _bbox_flat(item), "geometry": item.get("geometry"), "attributes": item.get("attributes"),
            }
            for handle, item in by_handle.items()
        },
    }


def compare_snapshots(before: Mapping[str, Any], after: Mapping[str, Any], planned_created_handles: Iterable[str]) -> dict[str, list[str]]:
    before_handles = set(before.get("handles", []))
    after_handles = set(after.get("handles", []))
    planned = {str(value).upper() for value in planned_created_handles}
    return {
        "existing_deleted": sorted(before_handles - after_handles),
        "unexpected_new": sorted((after_handles - before_handles) - planned),
        "existing_modified": sorted(
            handle for handle in before_handles & after_handles
            if before.get("signatures", {}).get(handle) != after.get("signatures", {}).get(handle)
        ),
    }


def execute_candidate_plan(acad: Any, reference_path: Path, candidate_path: Path, backup_path: Path, plan: Mapping[str, Any], protected_bboxes: Sequence[Sequence[float]]) -> dict[str, Any]:
    """执行冻结计划；任何异常均关闭不保存并从 prewrite backup 恢复。"""
    from mcp.acceptance.stage3_1_runtime import _close_document_without_save, _open_document_with_retry, _resolve_open_document, _scan_entity
    from mcp.acceptance.stage5_1_valve_component_diagnostics import _copyobjects_with_explicit_idpairs, _parse_copyobjects_return
    from mcp.acceptance.stage5_2_native_clone_poc import _retry, _variant

    if payload_sha256(plan) != plan.get("plan_sha256"):
        raise RuntimeError("frozen_plan_hash_mismatch")
    source_doc = candidate_doc = None
    batches, created_map = [], []
    try:
        returned = _open_document_with_retry(acad, reference_path)
        source_doc = _resolve_open_document(acad, reference_path, returned)
        returned = _open_document_with_retry(acad, candidate_path)
        candidate_doc = _resolve_open_document(acad, candidate_path, returned)
        if Path(str(candidate_doc.FullName)).resolve() != candidate_path.resolve():
            raise RuntimeError("active_candidate_path_mismatch")
        for index, task in enumerate(plan["tasks"], 1):
            source = _retry(lambda h=task["source_handle"]: source_doc.HandleToObject(h), f"source handle {task['source_handle']}")
            returned = _retry(lambda obj=source: _copyobjects_with_explicit_idpairs(source_doc, [obj], candidate_doc.ModelSpace), f"{task['task_id']} CopyObjects", attempts=30, delay=0.5)
            parsed = _parse_copyobjects_return(returned, source_doc, candidate_doc)
            pairs = [item for item in parsed.get("idpairs", []) if str(item.get("source_handle") or "").upper() == task["source_handle"].upper() and item.get("target_handle")]
            if len(pairs) != 1:
                raise RuntimeError(f"{task['task_id']}: primary IDPair count={len(pairs)}")
            target_handle = str(pairs[0]["target_handle"]).upper()
            created = _retry(lambda h=target_handle: candidate_doc.HandleToObject(h), f"created handle {target_handle}")
            vector = [float(task["transform"]["x"]), float(task["transform"]["y"]), 0.0]
            _retry(lambda obj=created: obj.Move(_variant([0.0, 0.0, 0.0]), _variant(vector)), f"{task['task_id']} translation", attempts=30, delay=0.5)
            record = _scan_entity(created, "candidate", "Model")
            actual_bbox = _bbox_flat(record)
            if any(bbox_intersects(actual_bbox, bbox) for bbox in protected_bboxes):
                raise RuntimeError(f"{task['task_id']}: protected_region_intersection")
            if not actual_bbox or not all(abs(a - b) <= 5.0 for a, b in zip(actual_bbox, task["expected_target_bbox"])):
                raise RuntimeError(f"{task['task_id']}: transformed_bbox_mismatch")
            created_map.append({"task_id": task["task_id"], "source_handle": task["source_handle"], "created_handle": target_handle, "object_name": record["object_name"], "bbox": actual_bbox})
            batches.append({"batch_id": f"batch_{index:05d}", "task_ids": [task["task_id"]], "source_handles": [task["source_handle"]], "created_handles": [target_handle], "expected_count": 1, "actual_created_count": 1, "transform_applied": True, "batch_status": "PASS", "error": None})
        candidate_doc.Save()
        saved = True
        candidate_doc.Close(False)
        candidate_doc = None
        source_doc.Close(False)
        source_doc = None
        returned = _open_document_with_retry(acad, candidate_path)
        reopened = _resolve_open_document(acad, candidate_path, returned)
        persisted = []
        for item in created_map:
            native = _retry(lambda h=item["created_handle"]: reopened.HandleToObject(h), f"persisted {item['created_handle']}")
            record = _scan_entity(native, "candidate_persisted", "Model")
            persisted.append({**item, "persisted": True, "object_type_preserved": record["object_name"] == item["object_name"], "geometry_valid": _bbox_flat(record) is not None, "protected_intersection": any(bbox_intersects(_bbox_flat(record), bbox) for bbox in protected_bboxes), "status": "PASS"})
        reopened.Close(False)
        return {"saved": saved, "closed": True, "reopened": True, "batches": batches, "created_map": created_map, "persistence": persisted}
    except Exception:
        if candidate_doc is not None:
            try: _close_document_without_save(candidate_doc)
            except Exception: pass
        if source_doc is not None:
            try: _close_document_without_save(source_doc)
            except Exception: pass
        shutil.copy2(backup_path, candidate_path)
        raise
