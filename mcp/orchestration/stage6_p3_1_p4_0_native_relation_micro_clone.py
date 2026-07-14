"""Stage 6-P3.1/P4.0 原生关系恢复与微型复制验证。

全量分析复用上一阶段的只读实体快照；真实 COM 仅用于代表性属性探测，
以及在 L3 固定审批口令存在时对一个一次性副本执行微型复制。
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import html
import json
import math
from pathlib import Path
import re
import shutil
from typing import Any, Iterable, Mapping, Sequence

from mcp.orchestration.stage6_p3_p4_controlled_candidate import (
    _bbox_flat,
    bbox_center,
    bbox_intersects,
    bind_region,
    file_identity,
    payload_sha256,
    sha256_file,
    snapshot_records,
    translate_bbox,
    write_json,
    write_jsonl,
)


PHASE = "STAGE6-P3.1-P4.0"
L3_APPROVAL_PHRASE = "我批准 sandbox 执行"
TDB_TYPES = {
    "TDbPipe", "TDbDoubleLinePipe", "TDbPipeFitting", "TDbPipeValve",
    "TDbEquipment", "TDbWaterTank", "TDbVPipeDim", "TDbSymbMultiLeader",
}
PIPE_TYPES = {"TDbPipe", "TDbDoubleLinePipe"}
ANNOTATION_TYPES = {"TDbVPipeDim", "TDbSymbMultiLeader"}
RELIABLE_EVIDENCE = {
    "NATIVE_OBJECT_REFERENCE", "NATIVE_HANDLE_REFERENCE",
    "NATIVE_OBJECT_ID_REFERENCE", "SHARED_EXTENSION_DICTIONARY_REFERENCE",
    "SHARED_XDATA_REFERENCE", "EXACT_ENDPOINT_TOPOLOGY",
    "EXACT_GEOMETRIC_INTERSECTION",
}
WEAK_EVIDENCE = {"SHARED_SYSTEM_AND_DN_SUPPORT", "NEAREST_GEOMETRY_ONLY"}
REFERENCE_KEYWORDS = (
    "connect", "connection", "pipe", "parent", "child", "owner", "host",
    "network", "system", "source", "target", "start", "end", "node",
    "fitting", "valve", "equipment", "reference", "relation", "link",
    "id", "handle",
)
KNOWN_PROPERTIES = (
    "ObjectName", "Handle", "ObjectID", "OwnerID", "Layer",
    "HasExtensionDictionary", "StartPoint", "EndPoint", "Center",
    "InsertionPoint", "Rotation", "DNDiameter", "SystemType", "SysType",
    "Connect", "Connection", "Connections", "ConnectedObjects", "Pipe",
    "Pipes", "Parent", "Child", "Children", "Host", "Network", "Source",
    "Target", "StartNode", "EndNode", "Node", "Fitting", "Valve",
    "Equipment", "Reference", "Relation", "Link", "ID", "EntityID",
)
HEX_HANDLE = re.compile(r"^[0-9A-Fa-f]{1,16}$")
IDENTITY_PROPERTIES = {"Handle", "ObjectID", "OwnerID", "ObjectName", "Layer"}


@dataclass(frozen=True)
class StagePaths:
    root: Path
    backups: Path

    @classmethod
    def create(cls, base: Path, run_id: str) -> "StagePaths":
        root = base / run_id
        backups = root / "backups"
        backups.mkdir(parents=True, exist_ok=False)
        return cls(root, backups)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    for attr in ("Handle", "ObjectID", "ObjectName"):
        try:
            return {"com_reference": True, attr: _json_value(getattr(value, attr))}
        except Exception:
            pass
    return str(value)


def safe_get(obj: Any, name: str) -> tuple[Any, str | None]:
    try:
        return getattr(obj, name), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def safe_property_inventory(obj: Any) -> dict[str, Any]:
    """只读取属性；不会调用任意 COM 方法。"""
    names = set(KNOWN_PROPERTIES)
    try:
        names.update(
            name for name in dir(obj)
            if any(token in name.casefold() for token in REFERENCE_KEYWORDS)
        )
    except Exception:
        pass
    readable: dict[str, Any] = {}
    errors: dict[str, str] = {}
    value_types: dict[str, str] = {}
    for name in sorted(names):
        value, error = safe_get(obj, name)
        if error:
            errors[name] = error
            continue
        if callable(value):
            continue
        readable[name] = _json_value(value)
        value_types[name] = type(value).__name__
    return {"readable": readable, "errors": errors, "value_types": value_types}


def is_relationship_candidate_property(name: str) -> bool:
    if name in IDENTITY_PROPERTIES:
        return False
    lowered = name.casefold()
    if lowered in {"id", "entityid", "referenceid", "parentid", "childid", "hostid", "sourceid", "targetid"}:
        return True
    return any(token in lowered for token in REFERENCE_KEYWORDS if token != "id") and not any(
        noise in lowered for noise in ("width", "weight", "hide", "show", "floor", "type")
    )


def read_xdata(obj: Any) -> dict[str, Any]:
    method, error = safe_get(obj, "GetXData")
    if error or not callable(method):
        return {"available": False, "value": None, "error": error}
    last_error = None
    for app_name in ("", None):
        try:
            return {"available": True, "value": _json_value(method(app_name)), "error": None}
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
    return {"available": False, "value": None, "error": last_error}


def read_extension_dictionary(obj: Any) -> dict[str, Any]:
    method, error = safe_get(obj, "GetExtensionDictionary")
    if error or not callable(method):
        return {"available": False, "entries": [], "error": error}
    try:
        dictionary = method()
        entries = []
        count = int(getattr(dictionary, "Count", 0) or 0)
        for index in range(count):
            item = dictionary.Item(index)
            entries.append({
                "name": _json_value(getattr(item, "Name", None)),
                "handle": _json_value(getattr(item, "Handle", None)),
                "object_id": _json_value(getattr(item, "ObjectID", None)),
            })
        return {"available": True, "entries": entries, "error": None}
    except Exception as exc:
        return {"available": False, "entries": [], "error": f"{type(exc).__name__}: {exc}"}


def classify_reference_value(value: Any, handles: set[str], object_ids: set[int]) -> str | None:
    if isinstance(value, Mapping) and value.get("com_reference"):
        return "NATIVE_OBJECT_REFERENCE"
    if isinstance(value, str) and HEX_HANDLE.fullmatch(value.strip()) and value.upper() in handles:
        return "NATIVE_HANDLE_REFERENCE"
    if isinstance(value, int) and value in object_ids:
        return "NATIVE_OBJECT_ID_REFERENCE"
    return None


def resolve_property_references(sample: Mapping[str, Any], handles: set[str], object_ids: set[int]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for name, value in sample.get("property_inventory", {}).get("readable", {}).items():
        if not is_relationship_candidate_property(name):
            continue
        evidence = classify_reference_value(value, handles, object_ids)
        if evidence:
            resolved.append({"source_handle": sample.get("handle"), "property": name, "value": value, "evidence_level": evidence})
    return resolved


def _point_bbox(entity: Mapping[str, Any]) -> tuple[float, float] | None:
    return bbox_center(_bbox_flat(entity))


def _pipe_segment(entity: Mapping[str, Any]) -> tuple[tuple[float, float], tuple[float, float]] | None:
    geometry = entity.get("geometry") or {}
    start, end = geometry.get("start_point"), geometry.get("end_point")
    if start and end:
        return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))
    # BBox 只能作为显示证据，不能伪装为 TDbPipe 的真实连接端点。
    return None


def _point_on_segment(point: Sequence[float], segment: tuple[tuple[float, float], tuple[float, float]], tolerance: float = 1e-3) -> bool:
    (x, y), ((x1, y1), (x2, y2)) = point, segment
    cross = abs((x - x1) * (y2 - y1) - (y - y1) * (x2 - x1))
    length = max(math.dist((x1, y1), (x2, y2)), 1.0)
    if cross / length > tolerance:
        return False
    return min(x1, x2) - tolerance <= x <= max(x1, x2) + tolerance and min(y1, y2) - tolerance <= y <= max(y1, y2) + tolerance


def _segment_intersects_bbox(segment: tuple[tuple[float, float], tuple[float, float]], bbox: Sequence[float], tolerance: float = 1e-3) -> bool:
    (x1, y1), (x2, y2) = segment
    xmin, ymin, xmax, ymax = bbox
    if _point_on_segment((xmin, ymin), segment, tolerance) or _point_on_segment((xmax, ymax), segment, tolerance):
        return True
    if min(x1, x2) <= xmax + tolerance and max(x1, x2) >= xmin - tolerance and min(y1, y2) <= ymax + tolerance and max(y1, y2) >= ymin - tolerance:
        if math.isclose(x1, x2, abs_tol=tolerance):
            return xmin - tolerance <= x1 <= xmax + tolerance
        if math.isclose(y1, y2, abs_tol=tolerance):
            return ymin - tolerance <= y1 <= ymax + tolerance
    return False


def exact_relation(left: Mapping[str, Any], right: Mapping[str, Any], tolerance: float = 1e-3) -> dict[str, Any] | None:
    left_name, right_name = str(left.get("object_name")), str(right.get("object_name"))
    if left_name in PIPE_TYPES and right_name in PIPE_TYPES:
        a, b = _pipe_segment(left), _pipe_segment(right)
        if a and b and any(math.dist(p, q) <= tolerance for p in a for q in b):
            return {"evidence_level": "EXACT_ENDPOINT_TOPOLOGY", "distance": 0.0}
        return None
    if left_name in PIPE_TYPES or right_name in PIPE_TYPES:
        pipe, other = (left, right) if left_name in PIPE_TYPES else (right, left)
        segment, bbox = _pipe_segment(pipe), _bbox_flat(other)
        if not segment or not bbox:
            return None
        center = _point_bbox(other)
        if center and _point_on_segment(center, segment, tolerance):
            return {"evidence_level": "EXACT_GEOMETRIC_INTERSECTION", "distance": 0.0}
        if _segment_intersects_bbox(segment, bbox, tolerance):
            return {"evidence_level": "EXACT_GEOMETRIC_INTERSECTION", "distance": 0.0}
    return None


def nearest_geometry_evidence(distance: float) -> dict[str, Any]:
    return {"evidence_level": "NEAREST_GEOMETRY_ONLY", "distance": float(distance), "reliable": False}


def _grid_cells(bbox: Sequence[float], size: float = 5000.0) -> Iterable[tuple[int, int]]:
    for x in range(math.floor(bbox[0] / size), math.floor(bbox[2] / size) + 1):
        for y in range(math.floor(bbox[1] / size), math.floor(bbox[3] / size) + 1):
            yield x, y


def build_exact_edges(entities: Sequence[Mapping[str, Any]], native_edges: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    by_handle = {str(item.get("handle")).upper(): item for item in entities if item.get("handle")}
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for native in native_edges:
        left, right = str(native.get("source_handle", "")).upper(), str(native.get("target_handle", "")).upper()
        evidence = str(native.get("evidence_level", "UNRESOLVED"))
        if left in by_handle and right in by_handle and evidence in RELIABLE_EVIDENCE:
            key = tuple(sorted((left, right)))
            if key not in seen:
                edges.append({"source_handle": key[0], "target_handle": key[1], "evidence_level": evidence, "reliable": True})
                seen.add(key)
    grid: dict[tuple[int, int], list[Mapping[str, Any]]] = defaultdict(list)
    for item in entities:
        bbox = _bbox_flat(item)
        if bbox:
            for cell in _grid_cells(bbox):
                grid[cell].append(item)
    for item in entities:
        bbox = _bbox_flat(item)
        handle = str(item.get("handle", "")).upper()
        if not bbox or not handle:
            continue
        candidates: dict[str, Mapping[str, Any]] = {}
        for cell in _grid_cells([bbox[0] - 1, bbox[1] - 1, bbox[2] + 1, bbox[3] + 1]):
            for other in grid.get(cell, []):
                other_handle = str(other.get("handle", "")).upper()
                if other_handle and other_handle != handle:
                    candidates[other_handle] = other
        for other_handle, other in candidates.items():
            key = tuple(sorted((handle, other_handle)))
            if key in seen:
                continue
            relation = exact_relation(item, other)
            if relation:
                edges.append({"source_handle": key[0], "target_handle": key[1], **relation, "reliable": True})
                seen.add(key)
    return edges


def aggregate_bbox(entities: Sequence[Mapping[str, Any]]) -> list[float] | None:
    values = [_bbox_flat(item) for item in entities]
    values = [item for item in values if item]
    if not values:
        return None
    return [min(v[0] for v in values), min(v[1] for v in values), max(v[2] for v in values), max(v[3] for v in values)]


def _system(entity: Mapping[str, Any]) -> str:
    attrs = entity.get("attributes") or {}
    return str(attrs.get("sys_type") or attrs.get("system_type") or entity.get("layer") or "UNKNOWN")


def build_components(entities: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]], role: str) -> list[dict[str, Any]]:
    by_handle = {str(item.get("handle")).upper(): item for item in entities if item.get("handle")}
    adjacency: dict[str, set[str]] = defaultdict(set)
    edge_by_pair = {}
    for edge in edges:
        if edge.get("evidence_level") not in RELIABLE_EVIDENCE:
            continue
        left, right = str(edge["source_handle"]).upper(), str(edge["target_handle"]).upper()
        adjacency[left].add(right); adjacency[right].add(left)
        edge_by_pair[tuple(sorted((left, right)))] = edge
    components = []
    seen: set[str] = set()
    for handle in sorted(by_handle):
        if handle in seen:
            continue
        queue = deque([handle]); seen.add(handle); handles = []
        while queue:
            current = queue.popleft(); handles.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor); queue.append(neighbor)
        items = [by_handle[value] for value in handles]
        component_edges = [edge_by_pair[pair] for pair in edge_by_pair if pair[0] in handles and pair[1] in handles]
        counts = Counter(str(item.get("object_name")) for item in items)
        regions = {str(item.get("region_id")) for item in items}
        unresolved = sum(1 for item in items if item.get("relation_unresolved"))
        complete = len(regions) == 1 and unresolved == 0 and (len(items) == 1 or len(component_edges) >= len(items) - 1)
        component_id = f"{role}_component_{len(components)+1:05d}"
        bbox = aggregate_bbox(items)
        signature_payload = {
            "types": sorted(counts.items()),
            "systems": sorted(Counter(_system(item) for item in items).items()),
            "degrees": sorted(len(adjacency[h]) for h in handles),
        }
        components.append({
            "component_id": component_id, "role": role,
            "semantic_region": next(iter(regions), None), "system_type": Counter(_system(item) for item in items).most_common(1)[0][0],
            "entity_handles": handles, "entity_types": dict(sorted(counts.items())),
            "pipe_count": sum(counts[name] for name in PIPE_TYPES),
            "fitting_count": counts["TDbPipeFitting"], "valve_count": counts["TDbPipeValve"],
            "equipment_count": counts["TDbEquipment"], "annotation_count": sum(counts[name] for name in ANNOTATION_TYPES),
            "node_count": len(items), "edge_count": len(component_edges),
            "native_relation_count": sum(edge["evidence_level"].startswith("NATIVE_") for edge in component_edges),
            "exact_topology_relation_count": sum(edge["evidence_level"].startswith("EXACT_") for edge in component_edges),
            "weak_relation_count": 0, "unresolved_relation_count": unresolved,
            "bbox": bbox, "geometry_signature": sha256(json.dumps({"bbox_size": None if not bbox else [round(bbox[2]-bbox[0], 3), round(bbox[3]-bbox[1], 3)], "types": sorted(counts.items())}, sort_keys=True).encode()).hexdigest()[:16],
            "topology_signature": sha256(json.dumps(signature_payload, sort_keys=True).encode()).hexdigest()[:16],
            "property_signature": sha256(json.dumps(signature_payload["systems"], ensure_ascii=False).encode()).hexdigest()[:16],
            "relationship_evidence": component_edges,
            "execution_eligibility": "ELIGIBLE_FOR_COMPONENT_COMPARISON" if complete and sum(counts[name] for name in PIPE_TYPES) else "RELATION_UNRESOLVED",
        })
    return components


def _bbox_center_distance(left: Sequence[float] | None, right: Sequence[float] | None) -> float:
    if not left or not right:
        return math.inf
    return math.dist(bbox_center(left), bbox_center(right))  # type: ignore[arg-type]


def _bbox_touches(left: Sequence[float] | None, right: Sequence[float] | None, tolerance: float = 1e-3) -> bool:
    if not left or not right:
        return False
    return not (
        left[2] < right[0] - tolerance or left[0] > right[2] + tolerance
        or left[3] < right[1] - tolerance or left[1] > right[3] + tolerance
    )


def match_components(reference: Sequence[Mapping[str, Any]], target: Sequence[Mapping[str, Any]], transforms: Mapping[str, Mapping[str, Any]], protected: Sequence[Sequence[float]]) -> list[dict[str, Any]]:
    target_by_region: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in target:
        target_by_region[str(item.get("semantic_region"))].append(item)
    results = []
    for component in reference:
        region = str(component.get("semantic_region"))
        transform = transforms.get(region)
        mapped = None
        if transform and component.get("bbox"):
            mapped = translate_bbox(component["bbox"], float(transform["translation_x"]), float(transform["translation_y"]))
        if mapped and any(bbox_intersects(mapped, bbox) for bbox in protected):
            status, match = "COMPONENT_PROTECTED", None
        elif not transform or component.get("execution_eligibility") != "ELIGIBLE_FOR_COMPONENT_COMPARISON":
            status, match = "COMPONENT_RELATION_UNRESOLVED", None
        else:
            candidates = target_by_region.get(str(transform["target_region_id"]), [])
            exact = [item for item in candidates if item.get("entity_types") == component.get("entity_types") and _bbox_center_distance(mapped, item.get("bbox")) <= 5.0]
            overlaps = [item for item in candidates if mapped and _bbox_touches(mapped, item.get("bbox"))]
            if exact:
                status, match = "COMPONENT_ALREADY_PRESENT", exact[0]
            elif overlaps:
                status, match = "COMPONENT_PARTIALLY_PRESENT", min(overlaps, key=lambda item: _bbox_center_distance(mapped, item.get("bbox")))
            else:
                status, match = "COMPONENT_CONFIRMED_MISSING", None
        results.append({
            "reference_component_id": component["component_id"], "target_component_id": None if match is None else match["component_id"],
            "semantic_region": region, "status": status, "mapped_bbox": mapped,
            "evidence": "component_type_topology_property_and_transformed_bbox",
        })
    return results


def reclassify_old_candidates(old: Sequence[Mapping[str, Any]], components: Sequence[Mapping[str, Any]], matches: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    component_by_handle = {handle: item for item in components for handle in item.get("entity_handles", [])}
    status_by_component = {item["reference_component_id"]: item["status"] for item in matches}
    mapping = {
        "COMPONENT_ALREADY_PRESENT": "RECLASSIFIED_ALREADY_PRESENT",
        "COMPONENT_CONFIRMED_MISSING": "RECLASSIFIED_COMPONENT_MISSING",
        "COMPONENT_PARTIALLY_PRESENT": "RECLASSIFIED_PARTIAL_COMPONENT",
        "COMPONENT_PROTECTED": "RECLASSIFIED_PROTECTED",
        "COMPONENT_UNSUPPORTED": "RECLASSIFIED_UNSUPPORTED",
    }
    result = []
    for item in old:
        handle = str(item.get("handle", "")).upper()
        component = component_by_handle.get(handle)
        component_status = status_by_component.get(component["component_id"]) if component else None
        status = mapping.get(component_status, "RECLASSIFIED_RELATION_UNRESOLVED")
        result.append({
            "source_handle": handle, "object_name": item.get("object_name"),
            "old_status": "CANDIDATE_MISSING_RELATION_UNVERIFIED",
            "component_id": None if component is None else component["component_id"],
            "component_status": component_status, "new_status": status,
            "execution_allowed": False,
        })
    return result


def select_micro_component(components: Sequence[Mapping[str, Any]], matches: Sequence[Mapping[str, Any]], entities: Mapping[str, Mapping[str, Any]], fire_region: str) -> dict[str, Any]:
    missing = {item["reference_component_id"] for item in matches if item["status"] == "COMPONENT_CONFIRMED_MISSING"}
    candidates = []
    for component in components:
        handles = component.get("entity_handles", [])
        types = Counter(name for handle in handles if (name := entities.get(handle, {}).get("object_name")))
        if component["component_id"] not in missing or component.get("semantic_region") == fire_region:
            continue
        if not 1 <= len(handles) <= 12 or component.get("pipe_count", 0) < 1:
            continue
        if types["TDbEquipment"] or types["TDbWaterTank"] or component.get("annotation_count", 0) > 2:
            continue
        if component.get("execution_eligibility") != "ELIGIBLE_FOR_COMPONENT_COMPARISON":
            continue
        candidates.append(component)
    candidates.sort(key=lambda item: (abs(len(item["entity_handles"]) - 2), item["component_id"]))
    selected = candidates[0] if candidates else None
    return {
        "selected": selected is not None,
        "component_id": None if selected is None else selected["component_id"],
        "entity_handles": [] if selected is None else selected["entity_handles"],
        "object_types": {} if selected is None else selected["entity_types"],
        "reason": "small_complete_non_fire_component_with_reliable_relations" if selected else "no_component_satisfied_all_micro_clone_gates",
        "candidate_count": len(candidates),
    }


def build_micro_plan(selection: Mapping[str, Any], component: Mapping[str, Any] | None, entities: Mapping[str, Mapping[str, Any]], transform: Mapping[str, Any] | None) -> dict[str, Any]:
    tasks = []
    if selection.get("selected") and component and transform:
        for index, handle in enumerate(component["entity_handles"], 1):
            entity = entities[handle]
            bbox = _bbox_flat(entity)
            tasks.append({
                "task_id": f"micro_clone_{index:03d}", "source_handle": handle,
                "source_object_name": entity.get("object_name"), "component_id": component["component_id"],
                "relationship_evidence": component.get("relationship_evidence", []),
                "dependency_handles": sorted({edge["source_handle"] if edge["target_handle"] == handle else edge["target_handle"] for edge in component.get("relationship_evidence", []) if handle in (edge["source_handle"], edge["target_handle"])}),
                "translation": {"x": transform["translation_x"], "y": transform["translation_y"]},
                "expected_target_bbox": None if not bbox else translate_bbox(bbox, transform["translation_x"], transform["translation_y"]),
                "execution_order": index,
                "verification_fields": ["ObjectName", "Layer", "DNDiameter", "SysType", "XData", "ExtensionDictionary", "relationships"],
            })
    plan = {"phase": PHASE, "task_count": len(tasks), "tasks": tasks, "no_plan_expansion_allowed": True, "invalidated_4068_plan_reused": False}
    plan["plan_sha256"] = payload_sha256(plan)
    return plan


def approval_allows_micro_clone(user_approval_text: str) -> bool:
    return L3_APPROVAL_PHRASE in user_approval_text


def old_plan_is_forbidden(path: Path) -> bool:
    if not path.is_file():
        return True
    payload = read_json(path)
    return payload.get("execution_allowed") is not True or payload.get("status") in {"INVALIDATED", "FROZEN_PLAN_INVALIDATED"}


def render_fire_overlay(path: Path, reference_entities: Sequence[Mapping[str, Any]], target_entities: Sequence[Mapping[str, Any]], transform: Mapping[str, Any]) -> None:
    boxes = []
    for item in reference_entities:
        bbox = _bbox_flat(item)
        if bbox:
            boxes.append((translate_bbox(bbox, transform["translation_x"], transform["translation_y"]), "#d62728"))
    for item in target_entities:
        bbox = _bbox_flat(item)
        if bbox:
            boxes.append((bbox, "#1f77b4"))
    extent = aggregate_bbox([{"bbox": [[b[0], b[1], 0], [b[2], b[3], 0]]} for b, _ in boxes]) or [0, 0, 1, 1]
    width, height = 1200, 800
    sx, sy = (width-40)/max(extent[2]-extent[0], 1), (height-40)/max(extent[3]-extent[1], 1)
    scale = min(sx, sy)
    rows = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="white"/>']
    for bbox, color in boxes:
        x, y = 20+(bbox[0]-extent[0])*scale, 20+(extent[3]-bbox[3])*scale
        rows.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{max((bbox[2]-bbox[0])*scale,1):.2f}" height="{max((bbox[3]-bbox[1])*scale,1):.2f}" fill="none" stroke="{color}" stroke-opacity="0.35"/>')
    rows.append('</svg>')
    path.write_text("\n".join(rows), encoding="utf-8")


def native_sample_document(acad: Any, path: Path, role: str, sample_limit: int = 3) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from mcp.acceptance.stage3_1_runtime import _close_document_without_save, _open_document_with_retry, _resolve_open_document

    document = None
    samples: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []
    try:
        returned = _open_document_with_retry(acad, path)
        document = _resolve_open_document(acad, path, returned)
        handles: set[str] = set()
        object_ids: set[int] = set()
        native_items = []
        for index in range(int(document.ModelSpace.Count)):
            native = document.ModelSpace.Item(index)
            handle = str(getattr(native, "Handle", "")).upper()
            if handle:
                handles.add(handle)
            try:
                object_ids.add(int(native.ObjectID))
            except Exception:
                pass
            native_items.append(native)
        counts: Counter[str] = Counter()
        for native in native_items:
            object_name = str(getattr(native, "ObjectName", ""))
            if object_name not in TDB_TYPES or counts[object_name] >= sample_limit:
                continue
            counts[object_name] += 1
            inventory = safe_property_inventory(native)
            sample = {
                "document_role": role, "object_name": object_name,
                "handle": str(getattr(native, "Handle", "")).upper(),
                "property_inventory": inventory, "xdata": read_xdata(native),
                "extension_dictionary": read_extension_dictionary(native),
            }
            samples.append(sample)
            resolutions.extend(resolve_property_references(sample, handles, object_ids))
    finally:
        if document is not None:
            _close_document_without_save(document)
    return samples, resolutions


def build_fire_audit(reference_entities: Sequence[Mapping[str, Any]], target_entities: Sequence[Mapping[str, Any]], reference_components: Sequence[Mapping[str, Any]], target_components: Sequence[Mapping[str, Any]], matches: Sequence[Mapping[str, Any]], fire_ref: str, fire_target: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ref = [item for item in reference_entities if item.get("region_id") == fire_ref]
    target = [item for item in target_entities if item.get("region_id") == fire_target]
    ref_components = [item for item in reference_components if item.get("semantic_region") == fire_ref]
    target_components = [item for item in target_components if item.get("semantic_region") == fire_target]
    fire_matches = [item for item in matches if item.get("semantic_region") == fire_ref]
    present = Counter(str(item.get("object_name")) for item in target)
    statuses = Counter(item["status"] for item in fire_matches)
    confirmed = statuses["COMPONENT_CONFIRMED_MISSING"] > 0 and statuses["COMPONENT_RELATION_UNRESOLVED"] == 0
    return (
        {"region_id": fire_target, "object_count": len(target), "object_type_counts": dict(sorted(present.items())), "component_count": len(target_components)},
        {"reference_region_id": fire_ref, "target_region_id": fire_target, "reference_component_count": len(ref_components), "target_component_count": len(target_components), "component_status_counts": dict(statuses)},
        {"large_scale_missing_confirmed": confirmed, "status": "FIRE_REGION_MISSING_CONFIRMED_BY_COMPONENTS" if confirmed else "FIRE_REGION_MISSING_DETECTION_UNRESOLVED", "reason": "component-level exact-relation evidence" if confirmed else "unresolved or partial components remain"},
    )


def run_stage(
    *, root: Path, prior_run: Path, p2_run: Path, reference: Path, target: Path,
    expected_reference_hash: str, expected_target_hash: str,
    user_approval_text: str = "",
    cached_sample_run: Path | None = None,
) -> dict[str, Any]:
    run_id = datetime.now().strftime("stage6_p3_1_p4_0_%Y%m%d_%H%M%S")
    paths = StagePaths.create(root / "artifacts" / "stage6_p3_1_p4_0_native_relation_micro_clone", run_id)
    reference_before, target_before = sha256_file(reference), sha256_file(target)
    if reference_before != expected_reference_hash or target_before != expected_target_hash:
        raise RuntimeError("INPUT_HASH_MISMATCH")
    old_plan = prior_run / "frozen_plan" / "frozen_write_plan.json"
    invalidation = prior_run / "frozen_plan" / "frozen_write_plan_invalidation.json"
    if not invalidation.is_file() or not old_plan_is_forbidden(invalidation):
        raise RuntimeError("INVALIDATED_PLAN_ISOLATION_FAILED")
    ref_scan = read_json(prior_run / "logs" / "reference_full_readonly_scan.json")
    target_scan = read_json(prior_run / "logs" / "target_full_readonly_scan.json")
    ref_regions = read_json(p2_run / "reference_regions.json")["regions"]
    target_regions_all = read_json(p2_run / "target_regions.json")["regions"]
    target_regions = [item for item in target_regions_all if not str(item.get("region_id", "")).startswith("target_protected")]
    protected_payload = read_json(p2_run / "protected_regions.json")
    protected_bboxes = [item["frame_bbox"] for item in protected_payload["regions"]]
    transform_payload = read_json(p2_run / "alignment_repair" / "final_verified_coordinate_transforms.json")
    transforms = {item["reference_region_id"]: item for item in transform_payload["transforms"]}

    def professional(scan: Mapping[str, Any], regions: Sequence[Mapping[str, Any]], role: str) -> list[dict[str, Any]]:
        result = []
        for raw in scan["entities"]:
            if raw.get("object_name") not in TDB_TYPES:
                continue
            item = dict(raw)
            item["region_id"] = bind_region(item, regions)
            if item["region_id"] is None:
                continue
            if role == "target" and any(bbox_intersects(_bbox_flat(item), bbox) for bbox in protected_bboxes):
                item["protected"] = True
                continue
            geometry = item.get("geometry") or {}
            item["relation_unresolved"] = not bool(geometry.get("start_point") and geometry.get("end_point"))
            result.append(item)
        return result

    reference_entities = professional(ref_scan, ref_regions, "reference")
    target_entities = professional(target_scan, target_regions, "target")

    samples: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []
    autocad_state = {"connected": False, "documents_before": [], "write_attempted": False}
    if cached_sample_run is not None:
        samples = read_jsonl(cached_sample_run / "native_relationship_samples.jsonl")
        autocad_state = {"connected": False, "documents_before": [], "write_attempted": False, "cached_readonly_samples_from": str(cached_sample_run)}
        # 重新按收紧后的字段规则解析，旧的自引用解析结果不继承。
        for sample in samples:
            readable = sample.get("property_inventory", {}).get("readable", {})
            handles = {str(value).upper() for name, value in readable.items() if name == "Handle" and value}
            object_ids = {int(value) for name, value in readable.items() if name == "ObjectID" and isinstance(value, int)}
            resolutions.extend(resolve_property_references(sample, handles, object_ids))
    else:
        acad = None
        try:
            from mcp.acceptance.stage3_1_runtime import attach_existing_autocad, detach_autocad, enumerate_live_documents
            acad = attach_existing_autocad()
            live = enumerate_live_documents(acad, (reference, target))
            autocad_state = {"connected": True, "documents_before": live["documents"], "write_attempted": False}
            if live["documents"]:
                raise RuntimeError("AUTOCAD_INSTANCE_CONFLICT")
            for role, path in (("reference", reference), ("target", target)):
                role_samples, role_resolutions = native_sample_document(acad, path, role)
                samples.extend(role_samples); resolutions.extend(role_resolutions)
        finally:
            if acad is not None:
                try:
                    detach_autocad()
                except Exception:
                    pass

    inventory_by_type: dict[str, dict[str, Any]] = {}
    for object_name in sorted(TDB_TYPES):
        typed = [sample for sample in samples if sample["object_name"] == object_name]
        readable = sorted({name for sample in typed for name in sample["property_inventory"]["readable"]})
        relation_fields = sorted(name for name in readable if is_relationship_candidate_property(name))
        inventory_by_type[object_name] = {"sample_count": len(typed), "readable_properties": readable, "relationship_candidate_properties": relation_fields}
    write_json(paths.root / "native_relationship_property_inventory.json", {"phase": PHASE, "types": inventory_by_type})
    write_jsonl(paths.root / "native_relationship_samples.jsonl", samples)
    write_jsonl(paths.root / "object_reference_resolution.jsonl", resolutions)

    ref_edges = build_exact_edges(reference_entities, resolutions)
    target_edges = build_exact_edges(target_entities, resolutions)
    ref_components = build_components(reference_entities, ref_edges, "reference")
    target_components = build_components(target_entities, target_edges, "target")
    matches = match_components(ref_components, target_components, transforms, protected_bboxes)
    write_jsonl(paths.root / "reference_components.jsonl", ref_components)
    write_jsonl(paths.root / "target_components.jsonl", target_components)
    write_jsonl(paths.root / "component_matches.jsonl", matches)
    component_statuses = Counter(item["status"] for item in matches)
    relation_counts = Counter(edge["evidence_level"] for edge in ref_edges + target_edges)
    write_json(paths.root / "component_missing_summary.json", {
        "reference_component_count": len(ref_components), "target_component_count": len(target_components),
        "component_status_counts": dict(component_statuses), "relationship_evidence_counts": dict(relation_counts),
    })

    old_candidates = read_jsonl(prior_run / "missing_detection" / "missing_entities.jsonl")
    reclassified = reclassify_old_candidates(old_candidates, ref_components, matches)
    write_jsonl(paths.root / "old_candidate_reclassification.jsonl", reclassified)
    reclass_counts = Counter(item["new_status"] for item in reclassified)
    write_json(paths.root / "old_candidate_reclassification_summary.json", {"input_count": len(old_candidates), "counts": dict(reclass_counts), "all_old_execution_eligibility_revoked": all(not item["execution_allowed"] for item in reclassified)})

    fire = next(item for item in transform_payload["transforms"] if item["semantic_key"] == "fire_hydrant_and_sprinkler_system")
    fire_present, fire_comparison, fire_false = build_fire_audit(reference_entities, target_entities, ref_components, target_components, matches, fire["reference_region_id"], fire["target_region_id"])
    prior_already_present = read_jsonl(prior_run / "missing_detection" / "already_present_entities.jsonl")
    fire_prior_present = [item for item in prior_already_present if item.get("reference_region_id") == fire["reference_region_id"]]
    fire_present["prior_118_already_present_count"] = len(fire_prior_present)
    fire_present["prior_118_actual_composition"] = dict(sorted(Counter(str(item.get("object_name")) for item in fire_prior_present).items()))
    fire_present["prior_118_interpretation"] = "ordinary_line_and_text_matches_not_native_fire_network_components"
    write_json(paths.root / "fire_region_present_object_audit.json", fire_present)
    write_json(paths.root / "fire_region_component_comparison.json", fire_comparison)
    write_json(paths.root / "fire_region_false_negative_analysis.json", fire_false)
    render_fire_overlay(paths.root / "fire_region_overlay.svg", [item for item in reference_entities if item["region_id"] == fire["reference_region_id"]], [item for item in target_entities if item["region_id"] == fire["target_region_id"]], fire)

    ref_by_handle = {str(item["handle"]).upper(): item for item in reference_entities}
    selection = select_micro_component(ref_components, matches, ref_by_handle, fire["reference_region_id"])
    write_json(paths.root / "micro_clone_component_selection.json", selection)
    selected_component = next((item for item in ref_components if item["component_id"] == selection.get("component_id")), None)
    selected_transform = transforms.get(selected_component["semantic_region"]) if selected_component else None
    plan = build_micro_plan(selection, selected_component, ref_by_handle, selected_transform)
    write_json(paths.root / "micro_clone_plan.json", plan)
    (paths.root / "micro_clone_plan.sha256").write_text(plan["plan_sha256"] + "\n", encoding="ascii")
    (paths.root / "micro_clone_plan.md").write_text(f"# 微型复制冻结计划\n\n- task_count: {plan['task_count']}\n- sha256: `{plan['plan_sha256']}`\n- old_4068_plan_reused: false\n", encoding="utf-8")

    approval = approval_allows_micro_clone(user_approval_text)
    execution = {
        "attempted": False, "saved": False, "closed": False, "reopened": False,
        "blocked_by": None if approval else "L3_APPROVAL_PHRASE_MISSING",
        "approval_phrase_required": L3_APPROVAL_PHRASE,
        "candidate_path": None, "prewrite_backup_path": None,
        "copyobjects_called": False, "target_original_write": False, "target_original_save": False,
    }
    # 本轮没有固定审批口令时，严禁进入 CopyObjects 分支。
    write_json(paths.root / "micro_clone_execution.json", execution)
    write_jsonl(paths.root / "micro_clone_created_entity_map.jsonl", [])
    write_json(paths.root / "micro_clone_persistence_verification.json", {"executed": False, "persisted": False, "reason": execution["blocked_by"]})
    write_json(paths.root / "micro_clone_relationship_verification.json", {"executed": False, "status": "RELATIONSHIP_NOT_OBSERVABLE", "reason": execution["blocked_by"]})

    reference_after, target_after = sha256_file(reference), sha256_file(target)
    integrity = {
        "reference": {"before": reference_before, "after": reference_after, "unchanged": reference_before == reference_after},
        "target": {"before": target_before, "after": target_after, "unchanged": target_before == target_after},
        "reference_write": False, "reference_save": False, "target_original_write": False, "target_original_save": False,
        "protected_region_modified": 0,
    }
    write_json(paths.root / "original_file_integrity.json", integrity)
    if fire_false["status"] == "FIRE_REGION_MISSING_DETECTION_UNRESOLVED":
        status = "FIRE_REGION_MISSING_DETECTION_UNRESOLVED"
    elif not selection["selected"]:
        status = "NATIVE_RELATION_RECOVERY_COMPLETE_NO_SAFE_COMPONENT"
    elif not approval:
        status = "NATIVE_RELATION_RECOVERY_COMPLETE_NO_SAFE_COMPONENT"
    else:
        status = "MICRO_CLONE_VALIDATION_FAILED"
    report = {
        "phase": PHASE, "run_id": run_id, "status": status,
        "reference": file_identity(reference), "target": file_identity(target),
        "autocad_state": autocad_state, "old_invalid_plan_reused": False,
        "relationship_evidence_counts": dict(relation_counts),
        "reference_component_count": len(ref_components), "target_component_count": len(target_components),
        "old_candidate_reclassification": dict(reclass_counts),
        "component_status_counts": dict(component_statuses),
        "fire_region_status": fire_false["status"], "micro_selection": selection,
        "micro_execution": execution, "component_clone_method_validated": False,
        "original_file_integrity": integrity,
        "safety": {"sendcommand_used": False, "lisp_used": False, "netload_used": False, "tianzheng_command_used": False, "full_4068_execution": False, "protected_region_modified": 0},
    }
    write_json(paths.root / "stage6_p3_1_p4_0_final_report.json", report)
    (paths.root / "stage6_p3_1_p4_0_final_report.md").write_text(
        "# Stage 6-P3.1/P4.0 最终报告\n\n"
        f"- 状态：{status}\n- Reference 组件：{len(ref_components)}\n- Target 组件：{len(target_components)}\n"
        f"- 完整缺失组件：{component_statuses['COMPONENT_CONFIRMED_MISSING']}\n"
        f"- 部分存在组件：{component_statuses['COMPONENT_PARTIALLY_PRESENT']}\n"
        f"- 未解析组件：{component_statuses['COMPONENT_RELATION_UNRESOLVED']}\n"
        f"- 消防状态：{fire_false['status']}\n- 微型组件：{selection.get('component_id')}\n"
        f"- 微型复制执行：false（{execution['blocked_by']}）\n- 原图哈希不变：{integrity['reference']['unchanged'] and integrity['target']['unchanged']}\n",
        encoding="utf-8",
    )
    return report
