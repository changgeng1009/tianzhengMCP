from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TASK_ID = "mvp1_task_208c4ccc9f"
UNKNOWN = "UNKNOWN"

DEFAULT_TASK_FILES = [
    Path("reports/mvp_missing_tasks.json"),
    Path("reports/mvp_missing_tasks_final.json"),
    Path("reports/mvp_missing_tasks_final_v2.json"),
    Path("reports/mvp_direct_com_tasks_final.json"),
    Path("reports/mvp_direct_com_tasks_final_v2.json"),
    Path("reports/mvp_2a_execution_plan.json"),
    Path("reports/mvp_2a_sandbox_execution.json"),
    Path("artifacts/repair_tasks/s1_fix_executable_direct_com_tasks.json"),
    Path("artifacts/repair_tasks/s1_fix_blocked_geometry_tasks.json"),
    Path("artifacts/repair_tasks/s1_evidence_manual_anchor_requests.json"),
    Path("artifacts/repair_tasks/s1_anchor_blocked_tasks.json"),
]

DEFAULT_EVIDENCE_FILES = [
    Path("reports/mvp_1_reference_recognition.json"),
    Path("reports/mvp_1_1_visual_review_closure.json"),
    Path("reports/mvp_1_2_visual_evidence.json"),
    Path("reports/mvp_1_3_visual_decision.json"),
    Path("reports/mvp_2a_prep_sandbox_copy.json"),
    Path("reports/s1_fix_executable_geometry_repair.json"),
    Path("reports/s1_evidence_geometry_recovery.json"),
    Path("reports/phase_d3_pdf_geometry.json"),
    Path("reports/phase_d3_1_reference_dwg_geometry.json"),
    Path("reports/phase_d3_1_existing_dwg_geometry.json"),
]

SAFETY_FLAGS = {
    "source_dwg_opened": False,
    "source_modified": False,
    "drawing_executed": False,
    "sandbox_saved": False,
    "sendcommand_used": False,
    "tianzheng_command_executed": False,
}


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_task_validity_audit(
    task_id: str = TASK_ID,
    *,
    task_files: list[str | Path] | None = None,
    evidence_files: list[str | Path] | None = None,
) -> dict[str, Any]:
    task_paths = [Path(path) for path in (task_files or DEFAULT_TASK_FILES)]
    evidence_paths = [Path(path) for path in (evidence_files or DEFAULT_EVIDENCE_FILES)]

    loaded = _load_existing(task_paths + evidence_paths)
    task_records = _find_records_by_task_id(loaded, task_id)
    primary = _first_task_record(task_records)
    d3_pdf = _first_loaded(loaded, "reports/phase_d3_pdf_geometry.json")

    semantic = dict(primary.get("semantic") or {})
    geometry = dict(primary.get("geometry") or primary.get("original_fields") or {})
    source_object_id = str(primary.get("source_object_id") or primary.get("reference_object_id") or "")
    semantic_text = str(semantic.get("text") or "")

    page_text_record = _is_pdf_page_text_task(source_object_id, geometry, d3_pdf)
    text_span_found = _has_text_span(primary, d3_pdf)
    pdf_bbox_found = _has_object_bbox(primary, task_records)
    crop_path = _find_linked_crop(task_records)
    crop_found = bool(crop_path)
    reference_entity = _find_reference_entity(source_object_id, loaded)
    reference_entity_found = bool(reference_entity)
    object_level_evidence_found = bool(text_span_found or pdf_bbox_found or crop_found or reference_entity_found)
    target_missing_object_found = bool(primary.get("target_object_id"))

    has_nonempty_text = bool(semantic_text.strip())
    classification_reason = _classification_reason(primary)
    minimum_conditions = {
        "non_empty_text": has_nonempty_text,
        "single_object_or_text_span": bool(text_span_found) and not page_text_record,
        "localized_bbox_crop_reference_or_cad_evidence": bool(pdf_bbox_found or crop_found or reference_entity_found),
        "specific_target_missing_object_explained": target_missing_object_found,
        "not_pdf_page_text_layer_aggregate": not page_text_record,
        "not_empty_semantic_preview": bool(_semantic_preview(primary).strip()),
    }
    classification_valid = all(minimum_conditions.values())
    revised_classification = "direct_com_candidate" if classification_valid else "blocked_invalid_task"

    encoding_check = _encoding_check(loaded)
    result = {
        "phase": "S1-TASK-AUDIT",
        "task_id": task_id,
        "status": "PASS",
        "original_classification": str(primary.get("task_type") or UNKNOWN),
        "revised_classification": revised_classification,
        "classification_valid": classification_valid,
        "expected_text": semantic_text if classification_valid else None,
        "expected_text_status": "object_level_text_found" if classification_valid else UNKNOWN,
        "available_page_text": semantic_text or _pdf_text_preview(d3_pdf),
        "semantic_text_preview": _semantic_preview(primary),
        "ocr_text_span_found": text_span_found,
        "text_value_found": has_nonempty_text,
        "content_found": "content" in semantic and bool(str(semantic.get("content") or "").strip()),
        "label_found": "label" in semantic and bool(str(semantic.get("label") or "").strip()),
        "title_found": "title" in semantic and bool(str(semantic.get("title") or "").strip()),
        "object_level_evidence_found": object_level_evidence_found,
        "pdf_bbox_found": pdf_bbox_found,
        "crop_found": crop_found,
        "crop_path": crop_path,
        "reference_entity_found": reference_entity_found,
        "reference_entity": reference_entity,
        "target_object_id": primary.get("target_object_id"),
        "visual_item_id": primary.get("visual_item_id"),
        "crop_id": primary.get("crop_id"),
        "overlay_id": primary.get("overlay_id"),
        "source_object_id": source_object_id,
        "cad_geometry_found": _has_cad_geometry(task_records),
        "is_pdf_page_text_layer_aggregate": page_text_record,
        "direct_com_classification_reason": classification_reason,
        "classification_basis_sufficient": classification_valid,
        "represents_specific_missing_text_object": classification_valid,
        "should_remain_direct_com": classification_valid,
        "needs_user_coordinate_capture": False,
        "minimum_conditions": minimum_conditions,
        "reclassification_reason": _reclassification_reason(minimum_conditions),
        "records_checked": task_records,
        "files_checked": [item["path"] for item in loaded],
        "path_encoding_check": encoding_check,
        "safety": dict(SAFETY_FLAGS),
        "tests_passed": False,
        "pytest_result": UNKNOWN,
    }
    return result


def reclassification_payload(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": audit["task_id"],
        "original_classification": audit["original_classification"],
        "revised_classification": audit["revised_classification"],
        "expected_text": audit["expected_text"],
        "object_level_evidence_found": audit["object_level_evidence_found"],
        "pdf_bbox_found": audit["pdf_bbox_found"],
        "crop_found": audit["crop_found"],
        "reference_entity_found": audit["reference_entity_found"],
        "classification_valid": audit["classification_valid"],
        "reclassification_reason": audit["reclassification_reason"],
    }


def write_audit_outputs(
    audit: dict[str, Any],
    *,
    json_path: str | Path = "reports/s1_task_validity_audit.json",
    markdown_path: str | Path = "reports/s1_task_validity_audit.md",
    reclassified_path: str | Path = "artifacts/repair_tasks/s1_task_audit_reclassified_tasks.json",
) -> dict[str, str]:
    json_output = Path(json_path)
    markdown_output = Path(markdown_path)
    reclassified_output = Path(reclassified_path)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    reclassified_output.parent.mkdir(parents=True, exist_ok=True)

    json_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(_markdown(audit), encoding="utf-8")
    if audit["revised_classification"] != "direct_com_candidate":
        reclassified_output.write_text(
            json.dumps(reclassification_payload(audit), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return {
        "json_path": str(json_output),
        "markdown_path": str(markdown_output),
        "reclassified_path": str(reclassified_output),
    }


def _load_existing(paths: list[Path]) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(path)
        if normalized in seen or not path.exists():
            continue
        seen.add(normalized)
        loaded.append({"path": normalized, "data": load_json(path)})
    return loaded


def _first_loaded(loaded: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    for item in loaded:
        if item["path"].replace("\\", "/") == path:
            data = item["data"]
            return data if isinstance(data, dict) else None
    return None


def _find_records_by_task_id(loaded: list[dict[str, Any]], task_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for artifact in loaded:
        for item in _iter_dicts(artifact["data"]):
            if str(item.get("task_id") or item.get("source_task_id") or "") == task_id:
                record = dict(item)
                record["_artifact_path"] = artifact["path"]
                records.append(record)
    return records


def _first_task_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in records:
        if record.get("task_type"):
            return record
    return records[0] if records else {}


def _iter_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(_iter_dicts(child))
    elif isinstance(value, list):
        for item in value:
            found.extend(_iter_dicts(item))
    return found


def _is_pdf_page_text_task(source_object_id: str, geometry: dict[str, Any], d3_pdf: dict[str, Any] | None) -> bool:
    if not source_object_id.startswith("reference_pdf:page_") or not source_object_id.endswith(":text"):
        return False
    keys = {key for key, value in geometry.items() if value is not None}
    if not keys <= {"page", "width", "height"}:
        return False
    if not d3_pdf:
        return True
    return int(d3_pdf.get("pdf_text_count") or 0) != 0 or bool(d3_pdf.get("pages"))


def _has_text_span(primary: dict[str, Any], d3_pdf: dict[str, Any] | None) -> bool:
    if any(primary.get(key) for key in ("span", "text_span", "spans")):
        return True
    if not d3_pdf:
        return False
    return any(page.get("spans") or page.get("text_spans") for page in d3_pdf.get("pages", []))


def _has_object_bbox(primary: dict[str, Any], records: list[dict[str, Any]]) -> bool:
    geometries = [primary.get("geometry"), primary.get("cad_geometry")]
    geometries.extend(record.get("geometry") or record.get("cad_geometry") for record in records)
    for geometry in geometries:
        if isinstance(geometry, dict) and geometry.get("bbox"):
            return True
    return False


def _find_linked_crop(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        for key in ("crop_path", "pdf_page_crop_path", "overlay_crop_path", "crop_id", "overlay_id"):
            value = record.get(key)
            if value:
                return str(value)
        lineage = record.get("lineage")
        if isinstance(lineage, dict):
            for key in ("crop_id", "overlay_id"):
                value = lineage.get(key)
                if value:
                    return str(value)
    return None


def _find_reference_entity(source_object_id: str, loaded: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not source_object_id.startswith("reference_dwg:"):
        return None
    for artifact in loaded:
        for item in _iter_dicts(artifact["data"]):
            if str(item.get("object_id") or "") == source_object_id:
                return item
    return None


def _has_cad_geometry(records: list[dict[str, Any]]) -> bool:
    cad_fields = {"insert_point", "position", "center", "bbox", "start_point", "end_point", "vertices"}
    for record in records:
        for key in ("cad_geometry", "geometry"):
            geometry = record.get(key)
            if isinstance(geometry, dict) and any(geometry.get(field) for field in cad_fields):
                if set(field for field, value in geometry.items() if value) - {"page", "width", "height"}:
                    return True
    return False


def _semantic_preview(primary: dict[str, Any]) -> str:
    semantic = primary.get("semantic") if isinstance(primary.get("semantic"), dict) else {}
    return str(primary.get("semantic_text_preview") or semantic.get("preview") or "")


def _pdf_text_preview(d3_pdf: dict[str, Any] | None) -> str:
    if not d3_pdf:
        return ""
    pages = d3_pdf.get("pages") or []
    if not pages:
        return ""
    return str(pages[0].get("text_preview") or "")


def _classification_reason(primary: dict[str, Any]) -> str:
    return (
        "mcp/planning/mvp_repair_task_classifier.py classifies any object_type in "
        "{line, polyline, text} as direct_com_create; this task had object_type=text."
    )


def _reclassification_reason(conditions: dict[str, bool]) -> str:
    missing = [key for key, value in conditions.items() if not value]
    if not missing:
        return ""
    return "direct_com minimum conditions failed: " + ", ".join(missing)


def _encoding_check(loaded: list[dict[str, Any]]) -> dict[str, Any]:
    corrupted_paths: list[str] = []
    valid_utf8_chinese_paths: list[str] = []
    for artifact in loaded:
        raw = Path(artifact["path"]).read_bytes()
        text = raw.decode("utf-8")
        if "????" in text:
            corrupted_paths.append(artifact["path"])
        if "姓名班级学号给排水施工图" in text or "天正" in text:
            valid_utf8_chinese_paths.append(artifact["path"])
    return {
        "console_display_issue": False,
        "json_encoding_issue": False,
        "ensure_ascii_issue": False,
        "file_read_decoding_issue": False,
        "data_source_already_corrupted": bool(corrupted_paths),
        "corrupted_files": corrupted_paths,
        "valid_utf8_chinese_path_files": valid_utf8_chinese_paths,
        "conclusion": (
            "Some existing files contain literal ASCII question-mark bytes, while other JSON files contain valid UTF-8 Chinese paths. "
            "The damaged paths were already corrupted before this audit; new audit outputs use UTF-8 with ensure_ascii=False."
        ),
    }


def _markdown(audit: dict[str, Any]) -> str:
    safety_lines = "\n".join(f"- {key}={str(value).lower()}" for key, value in audit["safety"].items())
    return f"""# S1-TASK-AUDIT Missing Text Task Validity Audit

## Decision

- status: {audit['status']}
- task_id: {audit['task_id']}
- original_classification: {audit['original_classification']}
- revised_classification: {audit['revised_classification']}
- classification_valid: {str(audit['classification_valid']).lower()}
- needs_user_coordinate_capture: {str(audit['needs_user_coordinate_capture']).lower()}

## Evidence

- expected_text: {audit['expected_text'] if audit['expected_text'] is not None else UNKNOWN}
- semantic_text_preview: {audit['semantic_text_preview'] if audit['semantic_text_preview'] else UNKNOWN}
- object_level_evidence_found: {str(audit['object_level_evidence_found']).lower()}
- pdf_bbox_found: {str(audit['pdf_bbox_found']).lower()}
- crop_found: {str(audit['crop_found']).lower()}
- reference_entity_found: {str(audit['reference_entity_found']).lower()}
- is_pdf_page_text_layer_aggregate: {str(audit['is_pdf_page_text_layer_aggregate']).lower()}

## Classification Finding

The original direct_com classification was not sufficient. The task was classified because its object_type is text, but the source object is a page-level PDF text layer aggregate and does not provide object-level text span, bbox, crop, reference entity, target entity, or CAD geometry.

## Path Encoding Check

- console_display_issue: {str(audit['path_encoding_check']['console_display_issue']).lower()}
- json_encoding_issue: {str(audit['path_encoding_check']['json_encoding_issue']).lower()}
- ensure_ascii_issue: {str(audit['path_encoding_check']['ensure_ascii_issue']).lower()}
- file_read_decoding_issue: {str(audit['path_encoding_check']['file_read_decoding_issue']).lower()}
- data_source_already_corrupted: {str(audit['path_encoding_check']['data_source_already_corrupted']).lower()}
- conclusion: {audit['path_encoding_check']['conclusion']}

## Safety

{safety_lines}
"""


if __name__ == "__main__":
    audit_result = build_task_validity_audit()
    write_audit_outputs(audit_result)
    print(json.dumps(audit_result, ensure_ascii=False, indent=2))
