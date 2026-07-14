from __future__ import annotations

import re
from typing import Any


DIRECT_COM_TYPES = {"line", "polyline", "text"}
MANUAL_TDB_TYPES = {"tdb_pipe", "tdb_valve", "tdb_fitting", "equipment"}
DANGEROUS_TOKENS = {"sendcommand", "hsxg", "hzgx", "gxlj", "tsaveas", "tgbatplots", "dcsz"}
MIN_DIRECT_COM_CONFIDENCE = 0.50
PAGE_LEVEL_TEXT_RE = re.compile(r"^reference_pdf:page_\d+:text$")


def validate_text_task_identity(obj: dict[str, Any]) -> dict[str, Any]:
    semantic = dict(obj.get("semantic") or {})
    source_object_id = str(obj.get("object_id") or obj.get("source_object_id") or "")
    page_level = reject_page_level_aggregate(obj)
    text = _expected_text(semantic) if not page_level else ""
    reasons: list[str] = []

    if not text:
        reasons.append("empty_expected_text")
    if page_level:
        reasons.append("page_level_aggregate")
    if not str(obj.get("semantic_text_preview") or semantic.get("preview") or text).strip() or page_level:
        reasons.append("empty_semantic_text_preview")

    return {
        "valid": not reasons,
        "expected_text": text or None,
        "source_object_id": source_object_id,
        "invalid_reasons": reasons,
    }


def validate_object_level_evidence(obj: dict[str, Any]) -> dict[str, Any]:
    geometry = dict(obj.get("geometry") or {})
    semantic = dict(obj.get("semantic") or {})

    pdf_bbox = bool(obj.get("pdf_bbox") or geometry.get("pdf_bbox") or geometry.get("bbox"))
    crop_id = bool(obj.get("crop_id") or obj.get("crop_path") or obj.get("overlay_id") or obj.get("overlay_crop_path"))
    reference_entity = bool(
        obj.get("reference_entity_id")
        or obj.get("reference_object_id")
        or (str(obj.get("object_id") or "").startswith("reference_dwg:"))
    )
    semantic_geometry = any(geometry.get(key) for key in ("insert_point", "position", "center", "start_point", "end_point", "vertices"))
    verified_overlay = bool(obj.get("verified_overlay_region") or semantic.get("verified_overlay_region"))

    missing: list[str] = []
    if not pdf_bbox:
        missing.append("missing_object_bbox")
    if not crop_id:
        missing.append("missing_crop")
    if not reference_entity:
        missing.append("missing_reference_entity")

    found = bool(pdf_bbox or crop_id or reference_entity or semantic_geometry or verified_overlay)
    return {
        "valid": found,
        "object_level_evidence_found": found,
        "pdf_bbox_found": pdf_bbox,
        "crop_found": crop_id,
        "reference_entity_found": reference_entity,
        "semantic_geometry_found": semantic_geometry,
        "verified_overlay_region_found": verified_overlay,
        "invalid_reasons": [] if found else missing,
    }


def reject_page_level_aggregate(obj: dict[str, Any]) -> bool:
    source_object_id = str(obj.get("object_id") or obj.get("source_object_id") or "")
    semantic = dict(obj.get("semantic") or {})
    geometry = dict(obj.get("geometry") or {})
    page_geometry_keys = {key for key, value in geometry.items() if value is not None}
    return bool(
        PAGE_LEVEL_TEXT_RE.match(source_object_id)
        or semantic.get("is_page_level_text_layer")
        or semantic.get("page_level_aggregate")
        or (source_object_id.startswith("reference_pdf:page_") and source_object_id.endswith(":text") and page_geometry_keys <= {"page", "width", "height"})
    )


def classify_invalid_task(obj: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    semantic = dict(obj.get("semantic") or {})
    source_object_id = str(obj.get("object_id") or obj.get("source_object_id") or "")
    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "task_id": _stable_task_id("mvp1_task", source_object_id),
        "task_type": "blocked_invalid_task",
        "classification": "blocked_invalid_task",
        "object_type": str(obj.get("object_type") or "unknown"),
        "expected_text": None,
        "source_object_id": source_object_id,
        "target_status": "invalid_source_task",
        "geometry": dict(obj.get("geometry") or {}),
        "semantic": semantic,
        "object_level_evidence_found": False,
        "invalid_reasons": unique_reasons,
        "execution_allowed": False,
        "requires_user_anchor": False,
        "requires_geometry_localization": False,
        "suggested_executor": "none",
        "confidence": float(obj.get("confidence", 0.0)),
        "reason": "blocked_invalid_task: " + ", ".join(unique_reasons),
    }


def validate_direct_com_candidate(obj: dict[str, Any], *, reason: str = "") -> dict[str, Any]:
    object_type = str(obj.get("object_type") or "unknown")
    semantic = dict(obj.get("semantic") or {})
    object_name = str(semantic.get("object_name") or "")
    serialized = str(obj).lower()
    reasons: list[str] = []

    if obj.get("task_type") in {"review_only", "blocked_invalid_task"}:
        reasons.append("not_classification_candidate")
    if object_type in MANUAL_TDB_TYPES or object_name.startswith("TDb"):
        reasons.append("tianzheng_object_not_direct_com")
    if any(token in serialized for token in DANGEROUS_TOKENS):
        reasons.append("dangerous_command_not_allowed")
    if object_type not in DIRECT_COM_TYPES:
        reasons.append("unsupported_direct_com_object_type")
    if float(obj.get("confidence", 0.0)) < MIN_DIRECT_COM_CONFIDENCE:
        reasons.append("confidence_below_threshold")

    if object_type == "text":
        identity = validate_text_task_identity(obj)
        evidence = validate_object_level_evidence(obj)
        if not identity["valid"]:
            reasons.extend(identity["invalid_reasons"])
        if not evidence["valid"]:
            reasons.extend(evidence["invalid_reasons"])
        if not _has_target_missing_evidence(obj, reason):
            reasons.append("missing_target_missing_evidence")

    valid = not reasons
    return {
        "classification_candidate": valid,
        "valid": valid,
        "invalid_reasons": list(dict.fromkeys(reasons)),
        "expected_text": _expected_text(semantic) if valid else None,
        "object_level_evidence_found": validate_object_level_evidence(obj)["object_level_evidence_found"],
        "execution_allowed": valid,
    }


def is_blocked_invalid_task(task: dict[str, Any]) -> bool:
    return task.get("classification") == "blocked_invalid_task" or task.get("task_type") == "blocked_invalid_task"


def blocked_invalid_enters_anchor_or_loop(task: dict[str, Any]) -> bool:
    if not is_blocked_invalid_task(task):
        return False
    return bool(task.get("requires_user_anchor") or task.get("requires_geometry_localization") or task.get("execution_allowed"))


def _expected_text(semantic: dict[str, Any]) -> str:
    for key in ("text", "content", "value", "label", "title"):
        value = str(semantic.get(key) or "").strip()
        if value and value.upper() != "UNKNOWN":
            return value
    return ""


def _has_target_missing_evidence(obj: dict[str, Any], reason: str) -> bool:
    if obj.get("target_missing_evidence") is True:
        return True
    target_status = str(obj.get("target_status") or "").lower()
    if target_status == "missing":
        return True
    reason_text = str(reason or obj.get("reason") or "").lower()
    return "no matching target object" in reason_text or "missing object" in reason_text


def _stable_task_id(prefix: str, value: object) -> str:
    import hashlib

    digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"
