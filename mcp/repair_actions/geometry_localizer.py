from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_GEOMETRY_SOURCES = {
    "reference_dwg_entity_geometry",
    "transformed_reference_geometry",
    "target_anchor_geometry",
    "alignment_transform",
    "semantic_model_geometry",
    "verified_overlay_geometry",
}

FORBIDDEN_GEOMETRY_SOURCES = {
    "guessed_geometry",
    "default_origin",
    "pdf_page_size_only",
    "hardcoded_coordinate",
    "random_coordinate",
    "placeholder_geometry",
}

CAD_GEOMETRY_FIELDS = ("insert_point", "position", "center", "bbox", "start_point", "end_point", "vertices")
MIN_EXECUTABLE_CONFIDENCE = 0.80

SAFETY_FLAGS = {
    "source_dwg_opened": False,
    "source_dwg_saved": False,
    "source_modified": False,
    "save_called_on_source": False,
    "sendcommand_used": False,
    "tianzheng_command_executed": False,
    "dangerous_command_executed": False,
    "production_d1_allowed": False,
    "drawing_executed": False,
    "sandbox_saved": False,
}


@dataclass(frozen=True)
class LocalizationInputs:
    blocked_tasks: list[dict[str, Any]]
    reference_objects: list[dict[str, Any]]
    target_objects: list[dict[str, Any]]
    alignment_transform: dict[str, Any]
    overlay_metadata: dict[str, Any]
    visual_evidence: dict[str, Any]
    semantic_model: dict[str, Any]


def infer_object_type(task: dict[str, Any]) -> str:
    source_object_id = str(task.get("source_object_id") or "")
    semantic = task.get("semantic") or {}
    text = str(semantic.get("text") or "")
    if "text" in source_object_id.lower() or text:
        return "text"
    return str(task.get("object_type") or "unknown")


def infer_action(task: dict[str, Any], object_type: str) -> str:
    task_type = str(task.get("task_type") or "")
    if task_type != "direct_com_create":
        return "blocked"
    if object_type == "text":
        return "AddText"
    if object_type == "line":
        return "AddLine"
    if object_type == "polyline":
        return "AddPolyline"
    if object_type == "circle":
        return "AddCircle"
    return "direct_com_create"


def localize_geometry_for_tasks(inputs: LocalizationInputs) -> dict[str, Any]:
    executable: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    for task in inputs.blocked_tasks:
        localized = localize_single_task(task, inputs)
        evidence.append(localized["localization_evidence"])
        if localized["execution_allowed"]:
            executable.append(localized)
        else:
            blocked.append(localized)

    return {
        "executable_direct_com_tasks": executable,
        "blocked_geometry_tasks": blocked,
        "localization_evidence": evidence,
        "safety": dict(SAFETY_FLAGS),
    }


def localize_single_task(task: dict[str, Any], inputs: LocalizationInputs) -> dict[str, Any]:
    object_type = infer_object_type(task)
    action = infer_action(task, object_type)
    original_geometry = dict(task.get("geometry") or {})
    attempted_sources = _attempted_sources(inputs)

    if task.get("task_type") != "direct_com_create":
        return _task_result(
            task,
            object_type=object_type,
            action="blocked",
            cad_geometry=_empty_cad_geometry(),
            confidence=0.0,
            geometry_source="non_direct_com_task",
            evidence_ids=[],
            transform_used=False,
            localization_method="blocked_non_direct_com_task",
            execution_allowed=False,
            block_reason="only confirmed direct_com_create tasks can become executable",
            original_fields=original_geometry,
            attempted_sources=attempted_sources,
            missing_geometry_fields=[field for field in CAD_GEOMETRY_FIELDS if field not in original_geometry],
        )

    candidate = _candidate_from_task(task)
    rejection_reason = ""
    if _is_pdf_page_size_only(original_geometry):
        candidate = None
        rejection_reason = "only PDF page/width/height is present; no CAD coordinate geometry"
    elif candidate is None:
        rejection_reason = "missing CAD geometry fields: insert_point/position/center/bbox/start_point/end_point/vertices"

    if candidate is not None:
        validation = validate_candidate_geometry(candidate)
        if validation["execution_allowed"]:
            return _task_result(
                task,
                object_type=object_type,
                action=action,
                cad_geometry=validation["cad_geometry"],
                confidence=validation["geometry_confidence"],
                geometry_source=validation["geometry_source"],
                evidence_ids=validation["evidence_ids"],
                transform_used=validation["transform_used"],
                localization_method=validation["localization_method"],
                execution_allowed=True,
                block_reason="",
                original_fields=original_geometry,
                attempted_sources=attempted_sources,
                missing_geometry_fields=[],
            )
        rejection_reason = validation["rejection_reason"]

    missing_fields = [field for field in CAD_GEOMETRY_FIELDS if field not in original_geometry or original_geometry.get(field) is None]
    return _task_result(
        task,
        object_type=object_type,
        action=action,
        cad_geometry=_empty_cad_geometry(),
        confidence=0.0,
        geometry_source="pdf_page_size_only" if _is_pdf_page_size_only(original_geometry) else "missing_geometry",
        evidence_ids=[],
        transform_used=False,
        localization_method="blocked_no_reliable_cad_geometry",
        execution_allowed=False,
        block_reason=rejection_reason,
        original_fields=original_geometry,
        attempted_sources=attempted_sources,
        missing_geometry_fields=missing_fields,
    )


def validate_candidate_geometry(candidate: dict[str, Any]) -> dict[str, Any]:
    source = str(candidate.get("geometry_source") or "")
    confidence = float(candidate.get("geometry_confidence") or 0.0)
    cad_geometry = _normalize_cad_geometry(candidate.get("cad_geometry") or candidate.get("geometry") or {})

    if source in FORBIDDEN_GEOMETRY_SOURCES:
        return _invalid(candidate, cad_geometry, f"forbidden geometry source: {source}")
    if source not in ALLOWED_GEOMETRY_SOURCES:
        return _invalid(candidate, cad_geometry, f"geometry source is not approved: {source}")
    if confidence < MIN_EXECUTABLE_CONFIDENCE:
        return _invalid(candidate, cad_geometry, "geometry confidence below 0.80")
    if not _has_executable_cad_geometry(cad_geometry):
        return _invalid(candidate, cad_geometry, "missing executable CAD coordinates")

    return {
        "execution_allowed": True,
        "cad_geometry": cad_geometry,
        "geometry_confidence": confidence,
        "geometry_source": source,
        "evidence_ids": list(candidate.get("evidence_ids") or []),
        "transform_used": bool(candidate.get("transform_used", False)),
        "localization_method": str(candidate.get("localization_method") or "direct_geometry_validation"),
        "rejection_reason": "",
    }


def _candidate_from_task(task: dict[str, Any]) -> dict[str, Any] | None:
    if "cad_geometry" in task or "geometry_source" in task:
        return task
    geometry = task.get("geometry") or {}
    if _has_executable_cad_geometry(geometry):
        return {
            "cad_geometry": geometry,
            "geometry_source": task.get("geometry_source", "missing_geometry_source"),
            "geometry_confidence": task.get("geometry_confidence", task.get("confidence", 0.0)),
            "evidence_ids": task.get("evidence_ids", []),
            "transform_used": task.get("transform_used", False),
            "localization_method": task.get("localization_method", "task_geometry"),
        }
    return None


def _task_result(
    task: dict[str, Any],
    *,
    object_type: str,
    action: str,
    cad_geometry: dict[str, Any],
    confidence: float,
    geometry_source: str,
    evidence_ids: list[str],
    transform_used: bool,
    localization_method: str,
    execution_allowed: bool,
    block_reason: str,
    original_fields: dict[str, Any],
    attempted_sources: list[str],
    missing_geometry_fields: list[str],
) -> dict[str, Any]:
    result = {
        "task_id": task.get("task_id"),
        "object_type": object_type,
        "action": action,
        "cad_geometry": cad_geometry,
        "geometry_confidence": confidence,
        "geometry_source": geometry_source,
        "evidence_ids": evidence_ids,
        "transform_used": transform_used,
        "localization_method": localization_method,
        "execution_allowed": execution_allowed,
        "block_reason": block_reason,
    }
    if not execution_allowed:
        result.update(
            {
                "original_fields": original_fields,
                "missing_geometry_fields": missing_geometry_fields,
                "attempted_sources": attempted_sources,
                "rejection_reason": block_reason,
                "required_manual_input": "CAD-space insert point/center/bbox/start-end/vertices from reference DWG, verified overlay, or transformed semantic geometry",
            }
        )
    result["localization_evidence"] = {
        "task_id": task.get("task_id"),
        "attempted_sources": attempted_sources,
        "geometry_source": geometry_source,
        "geometry_confidence": confidence,
        "execution_allowed": execution_allowed,
        "rejection_reason": block_reason,
    }
    return result


def _normalize_cad_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    normalized = _empty_cad_geometry()
    for key in CAD_GEOMETRY_FIELDS:
        if key in geometry:
            normalized[key] = geometry.get(key)
    normalized["type"] = geometry.get("type") or _infer_geometry_type(normalized)
    return normalized


def _empty_cad_geometry() -> dict[str, Any]:
    return {
        "type": "unknown",
        "insert_point": None,
        "center": None,
        "bbox": None,
        "start_point": None,
        "end_point": None,
        "vertices": None,
    }


def _infer_geometry_type(geometry: dict[str, Any]) -> str:
    if geometry.get("insert_point") or geometry.get("position"):
        return "point"
    if geometry.get("center"):
        return "center"
    if geometry.get("start_point") and geometry.get("end_point"):
        return "line"
    if geometry.get("vertices"):
        return "polyline"
    if geometry.get("bbox"):
        return "bbox"
    return "unknown"


def _has_executable_cad_geometry(geometry: dict[str, Any]) -> bool:
    if geometry.get("insert_point") or geometry.get("position") or geometry.get("center"):
        return True
    if geometry.get("start_point") and geometry.get("end_point"):
        return True
    if geometry.get("vertices"):
        return True
    if geometry.get("bbox"):
        return True
    return False


def _is_pdf_page_size_only(geometry: dict[str, Any]) -> bool:
    keys = {key for key, value in geometry.items() if value is not None}
    return bool(keys) and keys <= {"page", "width", "height"}


def _attempted_sources(inputs: LocalizationInputs) -> list[str]:
    attempted = []
    if inputs.reference_objects:
        attempted.append("reference_objects")
    if inputs.target_objects:
        attempted.append("target_objects")
    if inputs.alignment_transform:
        attempted.append("alignment_transform")
    if inputs.overlay_metadata:
        attempted.append("overlay_metadata")
    if inputs.visual_evidence:
        attempted.append("visual_evidence")
    if inputs.semantic_model:
        attempted.append("semantic_model")
    return attempted


def _invalid(candidate: dict[str, Any], cad_geometry: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "execution_allowed": False,
        "cad_geometry": cad_geometry,
        "geometry_confidence": float(candidate.get("geometry_confidence") or 0.0),
        "geometry_source": str(candidate.get("geometry_source") or ""),
        "evidence_ids": list(candidate.get("evidence_ids") or []),
        "transform_used": bool(candidate.get("transform_used", False)),
        "localization_method": str(candidate.get("localization_method") or ""),
        "rejection_reason": reason,
    }
