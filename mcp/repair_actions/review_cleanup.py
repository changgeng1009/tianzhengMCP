from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any


DEFAULT_OPTIONS = {
    "min_length": 30.0,
    "max_boundary_length_ratio": 0.85,
    "boundary_tolerance": 50.0,
    "duplicate_tolerance": 2.0,
    "parallel_dedupe_tolerance": 8.0,
    "parallel_overlap_ratio": 0.85,
    "merge_gap_tolerance": 120.0,
    "collinear_tolerance": 12.0,
    "connectivity_tolerance": 150.0,
    "text_search_radius": 300.0,
}


def cleanup_review_actions(repair_plan_v2: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    opts = {**DEFAULT_OPTIONS, **dict(options or {})}
    input_actions = [
        _normalize_action(action)
        for action in repair_plan_v2.get("review_actions", [])
        if action.get("action_type") == "add_pipe"
    ]
    filtered: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for action in input_actions:
        reason = _filter_reason(action, kept, opts)
        if reason:
            filtered.append(
                {
                    "action_id": action["action_id"],
                    "filter_reason": reason,
                    "geometry": action["geometry"],
                }
            )
        else:
            kept.append(action)

    merged = _merge_collinear_actions(kept, opts)
    _attach_text_evidence(merged, opts)
    groups = _group_actions(merged, opts)
    actions_with_dn = sum(1 for action in merged if action.get("candidate_dn"))
    preview_files: list[str] = []
    summary = {
        "input_review_actions": len(repair_plan_v2.get("review_actions", [])),
        "filtered_actions": len(filtered),
        "merged_actions": len(merged),
        "groups": len(groups),
        "actions_with_dn": actions_with_dn,
        "actions_without_dn": max(0, len(merged) - actions_with_dn),
        "auto_executable_after_cleanup": 0,
        "preview_files": preview_files,
    }
    return {
        "summary": summary,
        "filtered_actions": filtered,
        "merged_actions": merged,
        "groups": groups,
        "warnings": [],
        "errors": [],
    }


def write_review_previews(
    cleanup_result: dict[str, Any],
    output_dir: str = "artifacts/review_previews",
    image_size: list[int] | tuple[int, int] | None = None,
) -> list[str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "pump_room_review_actions.json"
    md_path = output / "pump_room_review_actions.md"
    png_path = output / "pump_room_review_overlay.png"
    payload = dict(cleanup_result)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_preview_markdown(payload), encoding="utf-8")
    _write_overlay_png(payload, png_path, image_size=image_size)
    files = [str(json_path), str(md_path), str(png_path)]
    cleanup_result.setdefault("summary", {})["preview_files"] = files
    json_path.write_text(json.dumps(cleanup_result, ensure_ascii=False, indent=2), encoding="utf-8")
    return files


def _normalize_action(action: dict[str, Any]) -> dict[str, Any]:
    points = list((action.get("geometry") or {}).get("points") or [])
    start = _point(points[0] if points else [0, 0])
    end = _point(points[1] if len(points) > 1 else start)
    if (end[0], end[1]) < (start[0], start[1]):
        start, end = end, start
    direction = _direction(start, end)
    normalized = dict(action)
    normalized["geometry"] = {"type": "polyline", "points": [start, end]}
    normalized["length"] = _distance(start, end)
    normalized["main_direction"] = direction
    normalized["confidence"] = float(action.get("confidence", 0.0) or 0.0)
    normalized["auto_execute"] = False
    normalized["validation_status"] = "review_required"
    return normalized


def _filter_reason(action: dict[str, Any], kept: list[dict[str, Any]], opts: dict[str, Any]) -> str:
    if action["length"] < float(opts["min_length"]):
        return "too_short"
    if _near_bbox_boundary(action, opts):
        return "near_reference_or_target_bbox_boundary"
    for existing in kept:
        if _same_line(action, existing, float(opts["duplicate_tolerance"])):
            return "duplicate_line"
        if _parallel_overlap(action, existing, opts):
            return "near_overlapping_parallel_double_line"
        if _overlaps_existing_primitive(action, existing, opts):
            return "overlaps_existing_primitive_line"
    return ""


def _near_bbox_boundary(action: dict[str, Any], opts: dict[str, Any]) -> bool:
    bbox = opts.get("target_bbox") or opts.get("reference_bbox")
    if not _valid_bbox(bbox):
        return False
    min_x, min_y, max_x, max_y = [float(value) for value in bbox]
    tol = float(opts["boundary_tolerance"])
    length_threshold = max(max_x - min_x, max_y - min_y) * float(opts["max_boundary_length_ratio"])
    if action["length"] < length_threshold:
        return False
    p1, p2 = action["geometry"]["points"]
    if action["main_direction"] == "horizontal":
        y = (p1[1] + p2[1]) / 2
        return abs(y - min_y) <= tol or abs(y - max_y) <= tol
    if action["main_direction"] == "vertical":
        x = (p1[0] + p2[0]) / 2
        return abs(x - min_x) <= tol or abs(x - max_x) <= tol
    return False


def _merge_collinear_actions(actions: list[dict[str, Any]], opts: dict[str, Any]) -> list[dict[str, Any]]:
    remaining = list(actions)
    merged: list[dict[str, Any]] = []
    while remaining:
        seed = remaining.pop(0)
        component = [seed]
        changed = True
        while changed:
            changed = False
            for candidate in list(remaining):
                if _can_merge_any(component, candidate, opts):
                    component.append(candidate)
                    remaining.remove(candidate)
                    changed = True
        merged.append(_merged_action(component))
    return merged


def _can_merge_any(component: list[dict[str, Any]], candidate: dict[str, Any], opts: dict[str, Any]) -> bool:
    return any(_can_merge(existing, candidate, opts) for existing in component)


def _can_merge(left: dict[str, Any], right: dict[str, Any], opts: dict[str, Any]) -> bool:
    if left["main_direction"] != right["main_direction"] or left["main_direction"] not in {"horizontal", "vertical"}:
        return False
    tol = float(opts["collinear_tolerance"])
    gap = float(opts["merge_gap_tolerance"])
    l1, l2 = left["geometry"]["points"]
    r1, r2 = right["geometry"]["points"]
    if left["main_direction"] == "horizontal":
        if abs(((l1[1] + l2[1]) / 2) - ((r1[1] + r2[1]) / 2)) > tol:
            return False
        return _interval_gap((l1[0], l2[0]), (r1[0], r2[0])) <= gap
    if abs(((l1[0] + l2[0]) / 2) - ((r1[0] + r2[0]) / 2)) > tol:
        return False
    return _interval_gap((l1[1], l2[1]), (r1[1], r2[1])) <= gap


def _merged_action(component: list[dict[str, Any]]) -> dict[str, Any]:
    direction = component[0]["main_direction"]
    points = [point for action in component for point in action["geometry"]["points"]]
    if direction == "horizontal":
        y = sum(point[1] for point in points) / len(points)
        xs = [point[0] for point in points]
        geometry = {"type": "polyline", "points": [[min(xs), y], [max(xs), y]]}
    elif direction == "vertical":
        x = sum(point[0] for point in points) / len(points)
        ys = [point[1] for point in points]
        geometry = {"type": "polyline", "points": [[x, min(ys)], [x, max(ys)]]}
    else:
        geometry = component[0]["geometry"]
    source_ids = [action["action_id"] for action in component]
    merged = {
        "merged_action_id": "merged_" + "_".join(source_ids[:3]),
        "source_action_ids": source_ids,
        "action_type": "add_pipe",
        "geometry": geometry,
        "main_direction": direction,
        "confidence": 0.0,
        "validation_status": "review_required",
        "auto_execute": False,
        "candidate_dn": None,
        "candidate_system": "unknown",
        "text_evidence": [],
        "review_required": True,
        "forbid_auto_writeback": True,
    }
    merged["bbox"] = _bbox_for_actions([merged])
    return merged


def _attach_text_evidence(actions: list[dict[str, Any]], opts: dict[str, Any]) -> None:
    texts = list(opts.get("text_elements") or [])
    radius = float(opts["text_search_radius"])
    for action in actions:
        evidence = []
        for item in texts:
            text = str(item.get("text") or "")
            position = _point(item.get("position") or _bbox_center(item.get("bbox")))
            distance = _distance_to_segment(position, *action["geometry"]["points"])
            if distance <= radius and _text_is_relevant(text):
                evidence.append({"text": text, "position": position, "distance": round(distance, 3)})
        if evidence:
            action["text_evidence"] = evidence
            dn = next((_extract_dn(item["text"]) for item in evidence if _extract_dn(item["text"])), None)
            if dn:
                action["candidate_dn"] = dn
            action["candidate_system"] = _candidate_system_from_text(" ".join(item["text"] for item in evidence))


def _group_actions(actions: list[dict[str, Any]], opts: dict[str, Any]) -> list[dict[str, Any]]:
    remaining = list(actions)
    groups: list[dict[str, Any]] = []
    while remaining:
        seed = remaining.pop(0)
        component = [seed]
        changed = True
        while changed:
            changed = False
            for candidate in list(remaining):
                if any(_connected(existing, candidate, float(opts["connectivity_tolerance"])) for existing in component):
                    component.append(candidate)
                    remaining.remove(candidate)
                    changed = True
        groups.append(_group_from_component(len(groups) + 1, component))
    return groups


def _group_from_component(index: int, actions: list[dict[str, Any]]) -> dict[str, Any]:
    directions = {action["main_direction"] for action in actions}
    main_direction = directions.pop() if len(directions) == 1 else "mixed"
    dn = next((action.get("candidate_dn") for action in actions if action.get("candidate_dn")), None)
    system = next((action.get("candidate_system") for action in actions if action.get("candidate_system") != "unknown"), "unknown")
    return {
        "group_id": f"review_group_{index:03d}",
        "action_count": len(actions),
        "bbox": _bbox_for_actions(actions),
        "main_direction": main_direction,
        "candidate_system": system,
        "candidate_dn": dn,
        "confidence": 0.0,
        "review_priority": "high" if len(actions) >= 5 else ("medium" if len(actions) >= 2 else "low"),
        "actions": actions,
        "has_dn": dn is not None,
        "manual_keep_suggested": True,
        "auto_execute": False,
        "forbid_auto_writeback": True,
    }


def _preview_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    lines = [
        "# 水泵房 review actions 预览",
        "",
        "## Summary",
        f"- input_review_actions: `{summary.get('input_review_actions', 0)}`",
        f"- filtered_actions: `{summary.get('filtered_actions', 0)}`",
        f"- merged_actions: `{summary.get('merged_actions', 0)}`",
        f"- groups: `{summary.get('groups', 0)}`",
        f"- actions_with_dn: `{summary.get('actions_with_dn', 0)}`",
        f"- actions_without_dn: `{summary.get('actions_without_dn', 0)}`",
        f"- auto_executable_after_cleanup: `{summary.get('auto_executable_after_cleanup', 0)}`",
        "",
        "## Groups",
    ]
    for group in result.get("groups", []):
        lines.append(
            "- "
            + json.dumps(
                {
                    "group_id": group["group_id"],
                    "action_count": group["action_count"],
                    "bbox": group["bbox"],
                    "candidate_dn": group["candidate_dn"],
                    "review_required": True,
                    "auto_execute": False,
                    "forbid_auto_writeback": True,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines) + "\n"


def _write_overlay_png(result: dict[str, Any], path: Path, image_size: list[int] | tuple[int, int] | None = None) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        path.write_bytes(b"")
        return
    width, height = (int(image_size[0]), int(image_size[1])) if image_size else (1400, 1000)
    image = Image.new("RGB", (max(width, 1), max(height, 1)), "white")
    draw = ImageDraw.Draw(image)
    all_points = [point for action in result.get("merged_actions", []) for point in action["geometry"]["points"]]
    bbox = _bbox_from_points(all_points) if all_points else [0, 0, width, height]
    for group_index, group in enumerate(result.get("groups", [])):
        color = _color(group_index)
        for action in group.get("actions", []):
            p1, p2 = action["geometry"]["points"]
            draw.line([_map_point(p1, bbox, width, height), _map_point(p2, bbox, width, height)], fill=color, width=3)
    image.save(path)


def _same_line(left: dict[str, Any], right: dict[str, Any], tolerance: float) -> bool:
    l1, l2 = left["geometry"]["points"]
    r1, r2 = right["geometry"]["points"]
    return (_distance(l1, r1) <= tolerance and _distance(l2, r2) <= tolerance) or (
        _distance(l1, r2) <= tolerance and _distance(l2, r1) <= tolerance
    )


def _parallel_overlap(left: dict[str, Any], right: dict[str, Any], opts: dict[str, Any]) -> bool:
    if left["main_direction"] != right["main_direction"] or left["main_direction"] not in {"horizontal", "vertical"}:
        return False
    tol = float(opts["parallel_dedupe_tolerance"])
    ratio = float(opts["parallel_overlap_ratio"])
    l1, l2 = left["geometry"]["points"]
    r1, r2 = right["geometry"]["points"]
    if left["main_direction"] == "horizontal":
        if abs(((l1[1] + l2[1]) / 2) - ((r1[1] + r2[1]) / 2)) > tol:
            return False
        return _overlap_ratio((l1[0], l2[0]), (r1[0], r2[0])) >= ratio
    if abs(((l1[0] + l2[0]) / 2) - ((r1[0] + r2[0]) / 2)) > tol:
        return False
    return _overlap_ratio((l1[1], l2[1]), (r1[1], r2[1])) >= ratio


def _overlaps_existing_primitive(action: dict[str, Any], existing: dict[str, Any], opts: dict[str, Any]) -> bool:
    return False


def _connected(left: dict[str, Any], right: dict[str, Any], tolerance: float) -> bool:
    left_points = left["geometry"]["points"]
    right_points = right["geometry"]["points"]
    if any(_distance(a, b) <= tolerance for a in left_points for b in right_points):
        return True
    return _bbox_distance(left["bbox"], right["bbox"]) <= tolerance


def _direction(start: list[float], end: list[float]) -> str:
    dx = abs(end[0] - start[0])
    dy = abs(end[1] - start[1])
    if dx >= dy * 3:
        return "horizontal"
    if dy >= dx * 3:
        return "vertical"
    return "diagonal"


def _point(value: Any) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return [float(value[0]), float(value[1])]
    return [0.0, 0.0]


def _distance(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _interval_gap(left: tuple[float, float], right: tuple[float, float]) -> float:
    a1, a2 = sorted(left)
    b1, b2 = sorted(right)
    return max(0.0, max(a1, b1) - min(a2, b2))


def _overlap_ratio(left: tuple[float, float], right: tuple[float, float]) -> float:
    a1, a2 = sorted(left)
    b1, b2 = sorted(right)
    overlap = max(0.0, min(a2, b2) - max(a1, b1))
    shorter = max(1e-9, min(a2 - a1, b2 - b1))
    return overlap / shorter


def _valid_bbox(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 4 and float(value[2]) > float(value[0]) and float(value[3]) > float(value[1])


def _bbox_for_actions(actions: list[dict[str, Any]]) -> list[float]:
    points = [point for action in actions for point in action["geometry"]["points"]]
    return _bbox_from_points(points)


def _bbox_from_points(points: list[list[float]]) -> list[float]:
    if not points:
        return [0.0, 0.0, 0.0, 0.0]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _bbox_center(value: Any) -> list[float]:
    if _valid_bbox(value):
        return [(float(value[0]) + float(value[2])) / 2, (float(value[1]) + float(value[3])) / 2]
    return [0.0, 0.0]


def _bbox_distance(left: list[float], right: list[float]) -> float:
    dx = max(left[0] - right[2], right[0] - left[2], 0.0)
    dy = max(left[1] - right[3], right[1] - left[3], 0.0)
    return math.hypot(dx, dy)


def _distance_to_segment(point: list[float], start: list[float], end: list[float]) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return _distance(point, start)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    projection = [x1 + t * dx, y1 + t * dy]
    return _distance(point, projection)


def _text_is_relevant(text: str) -> bool:
    return bool(re.search(r"\b(?:DN|De)\s*\d+", text, re.I)) or any(
        token in text for token in ["水泵", "喷泵", "栓泵", "消火栓", "喷淋"]
    )


def _extract_dn(text: str) -> str | None:
    match = re.search(r"\b(DN|De)\s*(\d+)", text, re.I)
    if not match:
        return None
    return f"{match.group(1).upper()}{match.group(2)}"


def _candidate_system_from_text(text: str) -> str:
    if "喷淋" in text or "喷泵" in text:
        return "spray"
    if "消火栓" in text or "栓泵" in text:
        return "hydrant"
    if "水泵" in text:
        return "water_supply"
    return "unknown"


def _map_point(point: list[float], bbox: list[float], width: int, height: int) -> tuple[int, int]:
    min_x, min_y, max_x, max_y = bbox
    pad = 30
    sx = (width - pad * 2) / max(max_x - min_x, 1.0)
    sy = (height - pad * 2) / max(max_y - min_y, 1.0)
    scale = min(sx, sy)
    return (int(pad + (point[0] - min_x) * scale), int(height - pad - (point[1] - min_y) * scale))


def _color(index: int) -> tuple[int, int, int]:
    colors = [(230, 57, 70), (29, 103, 246), (20, 140, 80), (180, 80, 220), (240, 150, 20)]
    return colors[index % len(colors)]
