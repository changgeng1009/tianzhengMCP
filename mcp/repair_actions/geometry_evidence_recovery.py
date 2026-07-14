from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.repair_actions.geometry_localizer import (
    ALLOWED_GEOMETRY_SOURCES,
    CAD_GEOMETRY_FIELDS,
    FORBIDDEN_GEOMETRY_SOURCES,
    MIN_EXECUTABLE_CONFIDENCE,
    SAFETY_FLAGS,
)


LINEAGE_KEYS = (
    "source_task_id",
    "source_item_type",
    "source_artifact_path",
    "reference_object_id",
    "target_object_id",
    "visual_item_id",
    "crop_id",
    "overlay_id",
    "alignment_id",
)

DANGEROUS_ACTION_TOKENS = {
    "sendcommand",
    "hsxg",
    "hzgx",
    "gxlj",
    "tsaveas",
    "tgbatplots",
    "dcsz",
}


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def recover_geometry_evidence(
    *,
    blocked_task_file: str | Path,
    upstream_artifacts: list[str | Path],
    alignment_artifacts: list[str | Path] | None = None,
) -> dict[str, Any]:
    blocked_doc = load_json(blocked_task_file)
    blocked_tasks = list(blocked_doc.get("tasks") or [])
    upstream_docs = [_load_artifact(path) for path in upstream_artifacts if Path(path).exists()]
    alignment_docs = [_load_artifact(path) for path in (alignment_artifacts or []) if Path(path).exists()]

    executable_tasks: list[dict[str, Any]] = []
    manual_anchor_requests: list[dict[str, Any]] = []
    lineage_records: list[dict[str, Any]] = []
    candidate_records: list[dict[str, Any]] = []

    for blocked_task in blocked_tasks:
        lineage = trace_task_lineage(blocked_task, upstream_docs, alignment_docs)
        lineage_records.append(lineage)

        candidate = find_cad_geometry_candidate(blocked_task, upstream_docs)
        if candidate:
            validated = validate_recovered_geometry(blocked_task, candidate)
            candidate_records.append(validated)
            if validated["execution_allowed"]:
                executable_tasks.append(_build_executable_task(blocked_task, validated, lineage))
                continue

        manual_anchor_requests.append(build_manual_anchor_request(blocked_task, lineage, candidate))

    return {
        "input_blocked_geometry_task_count": len(blocked_tasks),
        "lineage": lineage_records,
        "lineage_found": any(_lineage_has_value(record) for record in lineage_records),
        "cad_geometry_found": bool(executable_tasks),
        "executable_direct_com_tasks": executable_tasks,
        "manual_anchor_requests": manual_anchor_requests,
        "candidate_records": candidate_records,
        "safety": dict(SAFETY_FLAGS),
    }


def trace_task_lineage(
    blocked_task: dict[str, Any],
    upstream_docs: list[dict[str, Any]],
    alignment_docs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    task_id = str(blocked_task.get("task_id") or "")
    lineage = {key: None for key in LINEAGE_KEYS}
    lineage["source_task_id"] = task_id or None

    for artifact in upstream_docs:
        path = artifact["path"]
        for item in _iter_candidate_items(artifact["data"]):
            if str(item.get("task_id") or "") != task_id:
                continue
            lineage["source_item_type"] = str(item.get("task_type") or item.get("mode") or "task")
            lineage["source_artifact_path"] = path
            lineage["reference_object_id"] = item.get("source_object_id") or item.get("reference_object_id")
            lineage["target_object_id"] = item.get("target_object_id")
            break
        if lineage["source_artifact_path"]:
            break

    source_object_id = str(lineage.get("reference_object_id") or "")
    for artifact in upstream_docs:
        for item in _iter_candidate_items(artifact["data"]):
            related_ids = [str(value) for value in (item.get("related_object_ids") or [])]
            if source_object_id and source_object_id in related_ids:
                lineage["visual_item_id"] = item.get("item_id") or lineage["visual_item_id"]
                lineage["crop_id"] = item.get("crop_path") or item.get("pdf_page_crop_path") or lineage["crop_id"]
                lineage["overlay_id"] = item.get("overlay_crop_path") or lineage["overlay_id"]
                break

    for artifact in alignment_docs or []:
        data = artifact["data"]
        if isinstance(data, dict) and data.get("alignment_status"):
            lineage["alignment_id"] = artifact["path"]
            break

    return lineage


def find_cad_geometry_candidate(blocked_task: dict[str, Any], upstream_docs: list[dict[str, Any]]) -> dict[str, Any] | None:
    task_id = str(blocked_task.get("task_id") or "")
    source_object_id = str(blocked_task.get("source_object_id") or blocked_task.get("reference_object_id") or "")

    for artifact in upstream_docs:
        for item in _iter_candidate_items(artifact["data"]):
            if task_id and str(item.get("task_id") or "") == task_id:
                candidate = _candidate_from_item(item, artifact["path"])
                if candidate:
                    return candidate
            related_ids = [str(value) for value in (item.get("related_object_ids") or [])]
            item_object_id = str(item.get("object_id") or item.get("source_object_id") or "")
            if source_object_id and (source_object_id == item_object_id or source_object_id in related_ids):
                candidate = _candidate_from_item(item, artifact["path"])
                if candidate:
                    return candidate
    return None


def validate_recovered_geometry(blocked_task: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    task_type = str(candidate.get("task_type") or blocked_task.get("task_type") or "")
    if task_type and task_type != "direct_com_create":
        return _invalid_candidate(candidate, "review/manual/non-direct task cannot become executable")

    action_text = json.dumps(candidate, ensure_ascii=False).lower()
    if any(token in action_text for token in DANGEROUS_ACTION_TOKENS):
        return _invalid_candidate(candidate, "SendCommand or Tianzheng command is forbidden")

    source = str(candidate.get("geometry_source") or "")
    if source in FORBIDDEN_GEOMETRY_SOURCES:
        return _invalid_candidate(candidate, f"forbidden geometry source: {source}")
    if source not in ALLOWED_GEOMETRY_SOURCES:
        return _invalid_candidate(candidate, f"geometry source is not approved: {source}")

    confidence = float(candidate.get("geometry_confidence") or 0.0)
    if confidence < MIN_EXECUTABLE_CONFIDENCE:
        return _invalid_candidate(candidate, "geometry confidence below 0.80")

    cad_geometry = normalize_cad_geometry(candidate.get("cad_geometry") or candidate.get("geometry") or {})
    if not has_executable_cad_geometry(cad_geometry):
        return _invalid_candidate(candidate, "missing executable CAD coordinates")
    if has_default_or_placeholder_geometry(cad_geometry):
        return _invalid_candidate(candidate, "default or placeholder CAD coordinates are forbidden")

    return {
        "execution_allowed": True,
        "cad_geometry": cad_geometry,
        "geometry_source": source,
        "geometry_confidence": confidence,
        "evidence_ids": list(candidate.get("evidence_ids") or []),
        "transform_used": bool(candidate.get("transform_used", False)),
        "localization_method": str(candidate.get("localization_method") or "evidence_recovery"),
        "rejection_reason": "",
    }


def build_manual_anchor_request(
    blocked_task: dict[str, Any],
    lineage: dict[str, Any],
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    original_fields = dict(blocked_task.get("original_fields") or blocked_task.get("geometry") or {})
    missing_fields = list(blocked_task.get("missing_geometry_fields") or CAD_GEOMETRY_FIELDS)
    related_artifacts = [value for value in (lineage.get("source_artifact_path"), lineage.get("crop_id"), lineage.get("overlay_id"), lineage.get("alignment_id")) if value]
    why_blocked = str(blocked_task.get("rejection_reason") or blocked_task.get("block_reason") or "no reliable CAD-space geometry found")
    if candidate:
        why_blocked = f"{why_blocked}; recovered candidate rejected: {candidate.get('geometry_source') or 'unknown source'}"

    return {
        "task_id": blocked_task.get("task_id"),
        "object_type": blocked_task.get("object_type") or "unknown",
        "why_blocked": why_blocked,
        "missing_geometry_fields": missing_fields,
        "required_user_input": [
            "Provide CAD-space insert_point or text bounding bbox for the missing title/block text.",
            "Provide at least two reference-to-target anchor points if the location must be transformed.",
            "Provide a localized overlay or crop that ties the PDF text to a CAD coordinate region.",
        ],
        "recommended_capture_method": "在 sandbox 或 reference 中点选该标题/图签文字对象，记录 CAD 坐标 insert_point 或 bbox；不要在 source DWG 上操作。",
        "nearby_context": [
            {
                "source_object_id": lineage.get("reference_object_id"),
                "semantic_text_preview": _text_preview(original_fields),
            }
        ],
        "related_artifacts": related_artifacts,
        "lineage": lineage,
    }


def normalize_cad_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    normalized = {field: geometry.get(field) for field in CAD_GEOMETRY_FIELDS}
    normalized["type"] = geometry.get("type") or _infer_type(normalized)
    return normalized


def has_executable_cad_geometry(cad_geometry: dict[str, Any]) -> bool:
    return any(
        [
            cad_geometry.get("insert_point"),
            cad_geometry.get("position"),
            cad_geometry.get("center"),
            cad_geometry.get("bbox"),
            cad_geometry.get("vertices"),
            cad_geometry.get("start_point") and cad_geometry.get("end_point"),
        ]
    )


def has_default_or_placeholder_geometry(cad_geometry: dict[str, Any]) -> bool:
    values = []
    for field in CAD_GEOMETRY_FIELDS:
        value = cad_geometry.get(field)
        if value is not None:
            values.append(value)
    if not values:
        return True
    flattened = [_flatten_numbers(value) for value in values]
    flattened_numbers = [number for group in flattened for number in group]
    if flattened_numbers and all(abs(number) < 1e-9 for number in flattened_numbers):
        return True
    raw = json.dumps(values, ensure_ascii=False).lower()
    return any(token in raw for token in ("placeholder", "todo", "unknown", "default"))


def _load_artifact(path: str | Path) -> dict[str, Any]:
    return {"path": str(path), "data": load_json(path)}


def _iter_candidate_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    items: list[dict[str, Any]] = []
    for key in ("tasks", "items", "decisions", "objects", "review_tasks", "missing_tasks", "blocked_tasks", "execution_tasks"):
        value = data.get(key)
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return items


def _candidate_from_item(item: dict[str, Any], artifact_path: str) -> dict[str, Any] | None:
    geometry = item.get("cad_geometry") or item.get("geometry") or {}
    if not isinstance(geometry, dict) or not has_executable_cad_geometry(normalize_cad_geometry(geometry)):
        return None
    source = item.get("geometry_source") or item.get("cad_geometry_source")
    if not source:
        source = "semantic_model_geometry" if item.get("object_id") or item.get("source_object_id") else ""
    return {
        "task_type": item.get("task_type"),
        "cad_geometry": geometry,
        "geometry_source": source,
        "geometry_confidence": item.get("geometry_confidence", item.get("confidence", 0.0)),
        "evidence_ids": [artifact_path],
        "transform_used": bool(item.get("transform_used", False)),
        "localization_method": item.get("localization_method") or "artifact_geometry_search",
    }


def _build_executable_task(blocked_task: dict[str, Any], validated: dict[str, Any], lineage: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": blocked_task.get("task_id"),
        "object_type": blocked_task.get("object_type") or "unknown",
        "action": blocked_task.get("action") or "direct_com_create",
        "cad_geometry": validated["cad_geometry"],
        "geometry_confidence": validated["geometry_confidence"],
        "geometry_source": validated["geometry_source"],
        "evidence_ids": validated["evidence_ids"],
        "transform_used": validated["transform_used"],
        "localization_method": validated["localization_method"],
        "execution_allowed": True,
        "lineage": lineage,
    }


def _invalid_candidate(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "execution_allowed": False,
        "cad_geometry": normalize_cad_geometry(candidate.get("cad_geometry") or candidate.get("geometry") or {}),
        "geometry_source": str(candidate.get("geometry_source") or ""),
        "geometry_confidence": float(candidate.get("geometry_confidence") or 0.0),
        "evidence_ids": list(candidate.get("evidence_ids") or []),
        "transform_used": bool(candidate.get("transform_used", False)),
        "localization_method": str(candidate.get("localization_method") or ""),
        "rejection_reason": reason,
    }


def _lineage_has_value(lineage: dict[str, Any]) -> bool:
    return any(lineage.get(key) for key in ("source_artifact_path", "reference_object_id", "visual_item_id", "alignment_id"))


def _infer_type(cad_geometry: dict[str, Any]) -> str:
    if cad_geometry.get("insert_point") or cad_geometry.get("position"):
        return "point"
    if cad_geometry.get("center"):
        return "center"
    if cad_geometry.get("bbox"):
        return "bbox"
    if cad_geometry.get("start_point") and cad_geometry.get("end_point"):
        return "line"
    if cad_geometry.get("vertices"):
        return "polyline"
    return "unknown"


def _flatten_numbers(value: Any) -> list[float]:
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, (list, tuple)):
        numbers: list[float] = []
        for item in value:
            numbers.extend(_flatten_numbers(item))
        return numbers
    return []


def _text_preview(fields: dict[str, Any]) -> str:
    text = str(fields.get("text") or fields.get("semantic_text") or "")
    if not text:
        return ""
    return text[:120]
