from __future__ import annotations

import json
import math
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from mcp.acceptance.stage3_1_r1_analysis import (
    build_confidence_breakdown,
    build_non_text_anchor_candidates,
    build_object_inventory,
    classify_text_anchors,
    cluster_translation_deltas,
    confirm_target_scan,
    decide_final_status,
    disambiguate_text_anchors,
    evaluate_transforms,
    select_non_text_anchors,
    select_pump_region,
    validate_geometry_overlap,
)
from mcp.acceptance.stage3_1_runtime import (
    _close_document_without_save,
    _get_variable,
    _json_value,
    _layout_record,
    _norm_path,
    _open_document_with_retry,
    _read_bool,
    _read_string,
    _resolve_open_document,
    _safe_bbox,
    _safe_property,
    _scan_entity,
    attach_existing_autocad,
    create_verified_copy,
    detach_autocad,
    enumerate_live_documents,
    freeze_source,
    sha256_file,
    write_json,
)


PHASE = "STAGE3.1-R1-TARGET-SCAN-ALIGNMENT"
ROOT = Path(__file__).parents[2]
RUNS_ROOT = ROOT / "artifacts" / "stage3_1_r1"
REPORT_JSON = ROOT / "reports" / "stage3_1_r1_target_scan_alignment.json"
REPORT_MD = ROOT / "reports" / "stage3_1_r1_target_scan_alignment.md"
REFERENCE_SOURCE = ROOT / "artifacts" / "validation" / "s1_reference_fixture_20260710_134249.dwg"
TARGET_SOURCE = Path(r"E:\SampleDrawings\target_sample.dwg")


def scan_copy_r1(acad: Any, path: Path, role: str, forbidden_sources: Iterable[Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = path.resolve(strict=True)
    if _norm_path(resolved) in {_norm_path(item) for item in forbidden_sources}:
        raise ValueError("source path cannot be opened")
    copy_hash_before = sha256_file(resolved)
    document = None
    document_errors: list[str] = []
    entities: list[dict[str, Any]] = []
    try:
        returned = _open_document_with_retry(acad, resolved)
        document = _resolve_open_document(acad, resolved, returned)
        modelspace = document.ModelSpace
        paperspace = document.PaperSpace
        live_block_references: list[tuple[Any, dict[str, Any]]] = []
        for layout, collection in (("Model", modelspace), ("Paper", paperspace)):
            for index in range(int(collection.Count)):
                native = collection.Item(index)
                record = _scan_entity(native, role, layout)
                record.update(_extra_entity_properties(native, record))
                entities.append(record)
                if record["object_name"] == "AcDbBlockReference":
                    live_block_references.append((native, record))
        definitions, native_definitions = _scan_block_definitions(document, role)
        block_audit = _build_block_audit(
            role=role,
            entities=entities,
            live_block_references=live_block_references,
            definitions=definitions,
            native_definitions=native_definitions,
        )
        document_info = {
            "full_name": _read_string(document, "FullName"),
            "name": _read_string(document, "Name"),
            "read_only": _read_bool(document, "ReadOnly"),
            "saved": _read_bool(document, "Saved"),
            "modelspace_count": int(modelspace.Count),
            "paperspace_count": int(paperspace.Count),
            "layout_count": int(document.Layouts.Count),
            "layouts": [_layout_record(document.Layouts.Item(i)) for i in range(int(document.Layouts.Count))],
            "insunits": _get_variable(document, "INSUNITS", document_errors),
            "acadver": _get_variable(document, "ACADVER", document_errors),
        }
    finally:
        if document is not None:
            _close_document_without_save(document)
    copy_hash_after = sha256_file(resolved)
    counts = Counter(item["object_name"] for item in entities)
    scan = {
        "schema_version": "stage3.1-r1-scan-v1",
        "document_role": role,
        "document": document_info,
        "entities": entities,
        "entity_count": len(entities),
        "object_name_counts": dict(sorted(counts.items())),
        "modelspace_entity_count": sum(item["owner_layout"] == "Model" for item in entities),
        "paperspace_entity_count": sum(item["owner_layout"] == "Paper" for item in entities),
        "objects_without_bbox": sum(item.get("bbox") is None for item in entities),
        "objects_with_read_errors": sum(bool(item.get("read_errors")) for item in entities),
        "copy_sha256_before": copy_hash_before,
        "copy_sha256_after": copy_hash_after,
        "copy_hash_unchanged": copy_hash_before == copy_hash_after,
        "copy_saved": False,
        "closed_with_save": False,
        "document_read_errors": document_errors,
    }
    return scan, block_audit


def run_stage3_1_r1(
    *,
    reference_source: Path = REFERENCE_SOURCE,
    target_source: Path = TARGET_SOURCE,
    tests: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = datetime.now().strftime("stage3_1_r1_%Y%m%d_%H%M%S")
    run_root = RUNS_ROOT / run_id
    copies = run_root / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    safety = _safety_flags()
    report = _base_report(run_id, reference_source, target_source, safety, tests)
    acad = None
    try:
        reference_baseline = freeze_source(reference_source)
        target_baseline = freeze_source(target_source)
        report["reference_source_exists"] = True
        report["target_source_exists"] = True
        report["reference_source_sha256_before"] = reference_baseline["sha256"]
        report["target_source_sha256_before"] = target_baseline["sha256"]
        input_manifest = {
            "phase": PHASE, "run_id": run_id,
            "stage2_status": "PARTIAL_DEEPSEEK_DEFERRED",
            "reference": reference_baseline, "target": target_baseline,
            "deepseek_checked": False, "deepseek_call_attempted": False,
        }
        write_json(run_root / "input_manifest.json", input_manifest)

        acad = attach_existing_autocad()
        safety["autocad_connected"] = True
        report["autocad_version"] = str(getattr(acad, "Version", None) or getattr(acad, "Name", "unknown"))
        live_state = enumerate_live_documents(acad, (reference_source, target_source))
        report["live_document_diverges_from_disk"] = live_state["live_document_diverges_from_disk"]
        report["existing_source_documents_observed"] = len([
            item for item in live_state["documents"]
            if item.get("full_name") and _norm_path(Path(item["full_name"])) in {_norm_path(reference_source), _norm_path(target_source)}
        ])
        if live_state["live_document_diverges_from_disk"]:
            report["stage3_1_r1_final_status"] = "PARTIAL_SCAN_LIMITED"
            report["input_state_blocked"] = True
            report["target_scan_status"] = "TARGET_SCAN_UNDETERMINED"
            report["target_top_level_count_basically_credible"] = None
            report["stage3_2_allowed"] = False
            report["errors"].append("a source document has unsaved changes")
            raise _ControlledStop()

        reference_copy = copies / "reference_working_copy.dwg"
        target_copy = copies / "target_analysis_sandbox.dwg"
        reference_copy_info = create_verified_copy(reference_source, reference_copy, reference_baseline["sha256"])
        target_copy_info = create_verified_copy(target_source, target_copy, target_baseline["sha256"])
        report["reference_copy_path"] = str(reference_copy)
        report["target_copy_path"] = str(target_copy)
        report["reference_copy_sha256_initial"] = reference_copy_info["copy_sha256"]
        report["target_copy_sha256_initial"] = target_copy_info["copy_sha256"]
        report["copy_hashes_match_sources"] = reference_copy_info["hash_matches"] and target_copy_info["hash_matches"]

        forbidden_sources = (reference_source, target_source)
        reference_scan, reference_block_audit = scan_copy_r1(acad, reference_copy, "reference", forbidden_sources)
        safety["reference_copy_opened"] = True
        target_scan, target_block_audit = scan_copy_r1(acad, target_copy, "target", forbidden_sources)
        safety["target_copy_opened"] = True
        report["copies_opened"] = True
        write_json(run_root / "reference_scan.json", reference_scan)
        write_json(run_root / "target_scan.json", target_scan)

        reference_inventory = build_object_inventory(reference_scan)
        target_inventory = build_object_inventory(target_scan)
        write_json(run_root / "reference_object_type_inventory.json", reference_inventory)
        write_json(run_root / "target_object_type_inventory.json", target_inventory)
        write_json(run_root / "reference_block_audit.json", reference_block_audit)
        write_json(run_root / "target_block_audit.json", target_block_audit)
        write_json(run_root / "target_proxy_xref_audit.json", {
            "proxy_count": target_block_audit["proxy_count"],
            "xref_count": target_block_audit["xref_count"],
            "unknown_object_counts": target_inventory["unknown_object_counts"],
            "paperspace_viewport_count": target_block_audit["paperspace_viewport_count"],
        })
        target_confirmation = confirm_target_scan(target_inventory, target_block_audit)
        write_json(run_root / "target_scan_confirmation.json", target_confirmation)

        reference_region = select_pump_region(reference_scan, reference_block_audit, "reference")
        target_region = select_pump_region(target_scan, target_block_audit, "target")
        write_json(run_root / "reference_region.json", reference_region)
        write_json(run_root / "target_region.json", target_region)
        reference_analysis_scan = _scan_with_virtual(reference_scan, reference_block_audit)
        target_analysis_scan = _scan_with_virtual(target_scan, target_block_audit)
        text_classification = classify_text_anchors(reference_analysis_scan, target_analysis_scan, reference_region, target_region)
        write_json(run_root / "text_anchor_classification.json", text_classification)

        non_text_candidates = build_non_text_anchor_candidates(
            reference_scan, target_scan, reference_region, target_region,
            reference_block_audit, target_block_audit,
        )
        cluster_tolerance = min(1000.0, max(float(reference_region.get("diagonal") or 1.0), float(target_region.get("diagonal") or 1.0)) * 0.005)
        clusters = cluster_translation_deltas(non_text_candidates, cluster_tolerance)
        non_text_anchors = select_non_text_anchors(non_text_candidates, clusters.get("primary_cluster"))
        write_json(run_root / "non_text_anchor_candidates.json", {
            "candidate_count": len(non_text_candidates),
            "accepted_count": len(non_text_anchors),
            "candidates": non_text_candidates,
            "accepted": non_text_anchors,
        })
        write_json(run_root / "translation_delta_clusters.json", clusters)
        primary_delta = clusters.get("primary_cluster", {}).get("center") if clusters.get("primary_cluster") else None
        text_disambiguation = disambiguate_text_anchors(text_classification, primary_delta, cluster_tolerance)
        if clusters.get("primary_cluster") is not None:
            clusters["primary_cluster"]["accepted_text_support_count"] = text_disambiguation["accepted_count"]
            clusters["primary_cluster"]["accepted_non_text_support_count"] = len(non_text_anchors)
            clusters["primary_cluster"]["contains_text_and_non_text"] = bool(text_disambiguation["accepted_count"] and non_text_anchors)
            write_json(run_root / "translation_delta_clusters.json", clusters)
        write_json(run_root / "duplicate_text_disambiguation.json", text_disambiguation)

        transforms = evaluate_transforms(
            text_disambiguation["accepted_anchors"], non_text_anchors,
            reference_region, target_region,
        )
        write_json(run_root / "transform_candidates.json", transforms)
        transform_candidate = transforms.get("selected") or transforms.get("best_geometric_candidate")
        selected_matrix = (transform_candidate or {}).get("transform_parameters", {}).get("matrix")
        geometry_validation = validate_geometry_overlap(
            reference_scan, target_scan, reference_region, target_region, selected_matrix,
            reference_block_audit, target_block_audit,
        )
        write_json(run_root / "geometry_overlap_validation.json", geometry_validation)
        confidence = build_confidence_breakdown(
            reference_region=reference_region,
            target_region=target_region,
            target_scan_confirmation=target_confirmation,
            text_classification=text_classification,
            text_disambiguation=text_disambiguation,
            non_text_anchors=non_text_anchors,
            transform_evaluation=transforms,
            geometry_validation=geometry_validation,
        )
        write_json(run_root / "confidence_breakdown.json", confidence)
        final_status, stage3_2_allowed, blockers = decide_final_status(
            target_confirmation, reference_region, target_region,
            transforms, geometry_validation, confidence,
        )
        selected_transform = {
            "status": final_status,
            "selected": transforms.get("selected"),
            "best_geometric_candidate": transforms.get("best_geometric_candidate"),
            "mixed_text_non_text_gate_passed": transforms.get("selected") is not None,
            "blockers": blockers,
            "stage3_2_allowed": stage3_2_allowed,
        }
        write_json(run_root / "selected_transform.json", selected_transform)

        report.update({
            "target_modelspace_count": target_inventory["modelspace_count"],
            "target_paperspace_count": target_inventory["paperspace_count"],
            "target_object_name_counts": target_inventory["object_name_counts"],
            "target_classification_sum_matches_scan": target_inventory["classification_sum_matches_scan"],
            "target_block_reference_count": target_block_audit["block_reference_count"],
            "target_block_definition_count": target_block_audit["block_definition_count"],
            "target_xref_count": target_block_audit["xref_count"],
            "target_proxy_count": target_block_audit["proxy_count"],
            "target_nested_block_count": target_block_audit["nested_block_count"],
            "target_dynamic_block_count": target_block_audit["dynamic_block_count"],
            "virtual_expansion_required": target_block_audit["virtual_expansion_required"],
            "virtual_expansion_performed": target_block_audit["virtual_expansion_performed"],
            "virtual_entity_count": target_block_audit["virtual_entity_count"],
            "target_scan_status": target_confirmation["status"],
            "target_top_level_count_basically_credible": target_confirmation["top_level_count_basically_credible"],
            "reference_region": reference_region,
            "target_region": target_region,
            "region_correspondence_status": "CONFIRMED" if reference_region["status"] == target_region["status"] == "SELECTED" and geometry_validation["geometry_overlap_score"] >= 0.55 else "NOT_CONFIRMED",
            "text_anchor_classification_count": len(text_classification["records"]),
            "accepted_text_anchor_count": text_disambiguation["accepted_count"],
            "duplicate_text_accepted_count": text_disambiguation["duplicate_accepted_count"],
            "duplicate_text_rejected_count": text_disambiguation["rejected_count"],
            "low_information_text_excluded_count": text_classification["category_counts"].get("low_information_text", 0),
            "non_text_anchor_candidate_count": len(non_text_candidates),
            "non_text_anchor_count": len(non_text_anchors),
            "non_text_anchor_types": dict(Counter(item["anchor_type"] for item in non_text_anchors)),
            "translation_primary_cluster": clusters.get("primary_cluster"),
            "selected_transform": transform_candidate,
            "mixed_text_non_text_gate_passed": transforms.get("selected") is not None,
            "geometry_overlap_score": geometry_validation["geometry_overlap_score"],
            "geometry_overlap_validation": geometry_validation,
            "alignment_score_components": {
                "text_alignment_score": min(1.0, text_disambiguation["accepted_count"] / 3),
                "non_text_alignment_score": (
                    (transform_candidate or {}).get("inlier_count", 0)
                    / max((transform_candidate or {}).get("anchor_count", 0), 1)
                ),
                "geometry_overlap_score": geometry_validation["geometry_overlap_score"],
                "region_correspondence_score": min(reference_region["region_confidence"], target_region["region_confidence"]),
            },
            "confidence_breakdown": confidence,
            "alignment_confidence": confidence["final_confidence"],
            "stage3_1_r1_final_status": final_status,
            "stage3_2_allowed": stage3_2_allowed,
            "alignment_blockers": blockers,
        })
    except _ControlledStop:
        pass
    except Exception as exc:
        report["stage3_1_r1_final_status"] = "PARTIAL_SCAN_LIMITED"
        report["stage3_2_allowed"] = False
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["traceback"] = traceback.format_exc()
    finally:
        if acad is not None:
            detach_autocad()
        if report["reference_source_exists"]:
            report["reference_source_sha256_after"] = sha256_file(reference_source)
        if report["target_source_exists"]:
            report["target_source_sha256_after"] = sha256_file(target_source)
        report["source_hashes_unchanged"] = bool(
            report["reference_source_sha256_before"]
            and report["reference_source_sha256_before"] == report["reference_source_sha256_after"]
            and report["target_source_sha256_before"] == report["target_source_sha256_after"]
        )
        if report.get("reference_copy_path"):
            report["reference_copy_sha256_after"] = sha256_file(Path(report["reference_copy_path"]))
        if report.get("target_copy_path"):
            report["target_copy_sha256_after"] = sha256_file(Path(report["target_copy_path"]))
        if report.get("reference_copy_sha256_initial") and report.get("target_copy_sha256_initial"):
            report["copy_hashes_unchanged"] = bool(
                report.get("reference_copy_sha256_initial") == report.get("reference_copy_sha256_after")
                and report.get("target_copy_sha256_initial") == report.get("target_copy_sha256_after")
            )
        else:
            report["copy_hashes_unchanged"] = None
        report["production_d1_allowed"] = False
        report["repair_task_generated"] = False
        report["stage3_2_executed"] = False
        report["safety_flags"] = dict(safety)
        write_json(run_root / "source_integrity.json", {
            "reference_source_sha256_before": report["reference_source_sha256_before"],
            "reference_source_sha256_after": report["reference_source_sha256_after"],
            "target_source_sha256_before": report["target_source_sha256_before"],
            "target_source_sha256_after": report["target_source_sha256_after"],
            "source_hashes_unchanged": report["source_hashes_unchanged"],
            "reference_copy_sha256_initial": report.get("reference_copy_sha256_initial"),
            "reference_copy_sha256_after": report.get("reference_copy_sha256_after"),
            "target_copy_sha256_initial": report.get("target_copy_sha256_initial"),
            "target_copy_sha256_after": report.get("target_copy_sha256_after"),
            "copy_hashes_unchanged": report["copy_hashes_unchanged"],
        })
        write_json(run_root / "stage3_1_r1_manifest.json", _manifest(report))
        _write_reports(report)
    return report


def _extra_entity_properties(native: Any, record: Mapping[str, Any]) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for source, target in (
        ("XScaleFactor", "x_scale"), ("YScaleFactor", "y_scale"),
        ("ZScaleFactor", "z_scale"), ("IsDynamicBlock", "is_dynamic_block"),
        ("Path", "path"),
    ):
        value = _safe_property(native, source, [], record_missing=False)
        if value is not None:
            attributes[target] = _json_value(value)
    return {"attributes": {**record.get("attributes", {}), **attributes}}


def _scan_with_virtual(scan: Mapping[str, Any], block_audit: Mapping[str, Any]) -> dict[str, Any]:
    """仅为内存分析合并顶层与已审计的虚拟块实体。"""
    return {
        **dict(scan),
        "entities": list(scan.get("entities", [])) + list(block_audit.get("virtual_entities", [])),
    }


def _scan_block_definitions(document: Any, role: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = []
    native: dict[str, Any] = {}
    blocks = document.Blocks
    for index in range(int(blocks.Count)):
        definition_errors: list[str] = []
        try:
            definition = blocks.Item(index)
            name = str(_optional(definition, "Name", f"block_{index}", definition_errors))
            native[name] = definition
            entity_count = int(_optional(definition, "Count", 0, definition_errors) or 0)
            object_counts = Counter()
            nested_names = []
            for item_index in range(entity_count):
                try:
                    entity = definition.Item(item_index)
                    object_name = str(_optional(entity, "ObjectName", "UNKNOWN", definition_errors))
                    object_counts[object_name] += 1
                    if object_name == "AcDbBlockReference":
                        nested_names.append(str(_optional(entity, "Name", "", definition_errors)))
                except Exception as exc:
                    definition_errors.append(f"Item({item_index}): {type(exc).__name__}: {exc}")
            records.append({
                "name": name,
                "is_xref": bool(_optional(definition, "IsXRef", False, definition_errors)),
                "is_layout": bool(_optional(definition, "IsLayout", False, definition_errors)),
                "entity_count": entity_count,
                "object_name_counts": dict(sorted(object_counts.items())),
                "nested_block_reference_count": len(nested_names),
                "nested_block_names": nested_names,
                "origin": _json_value(_optional(definition, "Origin", [0.0, 0.0, 0.0], definition_errors)),
                "path": str(_optional(definition, "Path", "", definition_errors) or ""),
                "document_role": role,
                "read_errors": definition_errors,
            })
        except Exception as exc:
            records.append({
                "name": f"unreadable_block_{index}", "is_xref": False,
                "is_layout": False, "entity_count": 0, "object_name_counts": {},
                "nested_block_reference_count": 0, "nested_block_names": [],
                "origin": [0.0, 0.0, 0.0], "path": "", "document_role": role,
                "read_errors": [f"{type(exc).__name__}: {exc}"],
            })
    return records, native


def _optional(obj: Any, name: str, default: Any, errors: list[str] | None = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception as exc:
        if errors is not None:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
        return default


def _build_block_audit(
    *,
    role: str,
    entities: list[Mapping[str, Any]],
    live_block_references: list[tuple[Any, Mapping[str, Any]]],
    definitions: list[Mapping[str, Any]],
    native_definitions: Mapping[str, Any],
) -> dict[str, Any]:
    definition_by_name = {item["name"]: item for item in definitions}
    references = []
    triggers = []
    for native, record in live_block_references:
        name = str(record.get("attributes", {}).get("name") or getattr(native, "Name", ""))
        effective_name = str(record.get("attributes", {}).get("effective_name") or name)
        definition = definition_by_name.get(name) or definition_by_name.get(effective_name) or {}
        entity_count = int(definition.get("entity_count", 0))
        substantive = bool(record.get("bbox") and entity_count >= 10) or entity_count >= 50 or int(definition.get("nested_block_reference_count", 0)) > 0
        ref_record = {
            "handle": record.get("handle"),
            "name": name,
            "effective_name": effective_name,
            "insertion_point": record.get("geometry", {}).get("insertion_point"),
            "rotation": record.get("geometry", {}).get("rotation"),
            "x_scale": record.get("attributes", {}).get("x_scale"),
            "y_scale": record.get("attributes", {}).get("y_scale"),
            "z_scale": record.get("attributes", {}).get("z_scale"),
            "bbox": record.get("bbox"),
            "is_dynamic_block": bool(record.get("attributes", {}).get("is_dynamic_block", False)),
            "is_xref": bool(definition.get("is_xref", False)),
            "definition_entity_count": entity_count,
            "definition_nested_block_count": int(definition.get("nested_block_reference_count", 0)),
            "substantive_definition": substantive,
        }
        references.append(ref_record)
        if substantive:
            triggers.append((native, ref_record, definition))
    virtual_entities: list[dict[str, Any]] = []
    errors: list[str] = []
    for native, reference, definition in triggers:
        try:
            virtual_entities.extend(_virtual_expand_reference(native, reference, definition, native_definitions, role, max_entities=5000 - len(virtual_entities)))
        except Exception as exc:
            errors.append(f"block {reference.get('handle')}: {type(exc).__name__}: {exc}")
    counts = Counter(str(item.get("object_name")) for item in entities)
    xref_names = {item["name"] for item in definitions if item.get("is_xref")}
    return {
        "document_role": role,
        "block_reference_count": counts.get("AcDbBlockReference", 0),
        "block_definition_count": len(definitions),
        "xref_count": sum(item.get("is_xref", False) for item in references),
        "xref_definition_count": len(xref_names),
        "proxy_count": counts.get("AcDbProxyEntity", 0),
        "nested_block_detected": any(item.get("nested_block_reference_count", 0) for item in definitions),
        "nested_block_count": sum(int(item.get("nested_block_reference_count", 0)) for item in definitions),
        "dynamic_block_count": sum(item.get("is_dynamic_block", False) for item in references),
        "paperspace_viewport_count": sum(item.get("object_name") == "AcDbViewport" and item.get("owner_layout") == "Paper" for item in entities),
        "block_definition_entity_counts": {item["name"]: item["entity_count"] for item in definitions},
        "block_definitions": definitions,
        "block_references": references,
        "virtual_expansion_required": bool(triggers),
        "virtual_expansion_performed": bool(triggers) and not errors and bool(virtual_entities),
        "virtual_entity_count": len(virtual_entities),
        "virtual_entities": virtual_entities,
        "virtual_expansion_errors": errors,
        "expansion_limit": 5000,
    }


def _virtual_expand_reference(
    native_reference: Any,
    reference: Mapping[str, Any],
    definition: Mapping[str, Any],
    native_definitions: Mapping[str, Any],
    role: str,
    max_entities: int,
) -> list[dict[str, Any]]:
    if max_entities <= 0:
        return []
    definition_name = str(definition.get("name") or reference.get("name"))
    native_definition = native_definitions.get(definition_name)
    if native_definition is None:
        return []
    matrix = _block_matrix(native_reference, definition.get("origin"))
    return _expand_definition(
        native_definition, matrix, str(reference.get("handle")), native_definitions,
        role=role, depth=0, max_depth=4, max_entities=max_entities,
    )


def _expand_definition(
    definition: Any,
    parent_matrix: np.ndarray,
    source_block_handle: str,
    native_definitions: Mapping[str, Any],
    *,
    role: str,
    depth: int,
    max_depth: int,
    max_entities: int,
) -> list[dict[str, Any]]:
    if depth > max_depth or max_entities <= 0:
        return []
    output = []
    for index in range(min(int(definition.Count), max_entities)):
        native = definition.Item(index)
        object_name = str(getattr(native, "ObjectName", "UNKNOWN"))
        if object_name == "AcDbBlockReference" and depth < max_depth:
            child_name = str(getattr(native, "Name", ""))
            child_definition = native_definitions.get(child_name)
            if child_definition is not None:
                child_matrix = parent_matrix @ _block_matrix(native, getattr(child_definition, "Origin", [0.0, 0.0, 0.0]))
                output.extend(_expand_definition(
                    child_definition, child_matrix, source_block_handle, native_definitions,
                    role=role, depth=depth + 1, max_depth=max_depth,
                    max_entities=max_entities - len(output),
                ))
                continue
        record = _scan_entity(native, role, "VirtualBlock")
        record = _transform_virtual_record(record, parent_matrix)
        record["source_block_handle"] = source_block_handle
        record["virtual_expansion_depth"] = depth
        record["handle"] = f"{source_block_handle}:{record.get('handle') or index}"
        output.append(record)
        if len(output) >= max_entities:
            break
    return output


def _block_matrix(reference: Any, origin: Any) -> np.ndarray:
    insertion = list(getattr(reference, "InsertionPoint", [0.0, 0.0, 0.0]))
    rotation = float(getattr(reference, "Rotation", 0.0) or 0.0)
    sx = float(getattr(reference, "XScaleFactor", 1.0) or 1.0)
    sy = float(getattr(reference, "YScaleFactor", 1.0) or 1.0)
    origin_values = list(origin or [0.0, 0.0, 0.0])
    cosine, sine = math.cos(rotation), math.sin(rotation)
    matrix = np.array([
        [sx * cosine, -sy * sine, float(insertion[0])],
        [sx * sine, sy * cosine, float(insertion[1])],
        [0.0, 0.0, 1.0],
    ])
    origin_matrix = np.eye(3)
    origin_matrix[0, 2] = -float(origin_values[0])
    origin_matrix[1, 2] = -float(origin_values[1])
    return matrix @ origin_matrix


def _transform_virtual_record(record: dict[str, Any], matrix: np.ndarray) -> dict[str, Any]:
    geometry = dict(record.get("geometry", {}))
    for key in ("start_point", "end_point", "center", "insertion_point", "insert_point"):
        value = geometry.get(key)
        if isinstance(value, list) and len(value) >= 2:
            geometry[key] = _transform_point(value, matrix)
    vertices = geometry.get("vertices")
    if isinstance(vertices, list) and vertices:
        if isinstance(vertices[0], list):
            geometry["vertices"] = [_transform_point(point, matrix) for point in vertices]
        else:
            transformed = []
            for index in range(0, len(vertices) - 1, 2):
                transformed.extend(_transform_point([vertices[index], vertices[index + 1], 0.0], matrix)[:2])
            geometry["vertices"] = transformed
    record["geometry"] = geometry
    bbox = record.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 2:
        corners = [
            _transform_point([bbox[0][0], bbox[0][1], 0.0], matrix),
            _transform_point([bbox[0][0], bbox[1][1], 0.0], matrix),
            _transform_point([bbox[1][0], bbox[0][1], 0.0], matrix),
            _transform_point([bbox[1][0], bbox[1][1], 0.0], matrix),
        ]
        record["bbox"] = [
            [min(item[0] for item in corners), min(item[1] for item in corners), 0.0],
            [max(item[0] for item in corners), max(item[1] for item in corners), 0.0],
        ]
    return record


def _transform_point(point: list[float], matrix: np.ndarray) -> list[float]:
    transformed = matrix @ np.array([float(point[0]), float(point[1]), 1.0])
    return [float(transformed[0]), float(transformed[1]), float(point[2]) if len(point) > 2 else 0.0]


def _base_report(run_id: str, reference: Path, target: Path, safety: Mapping[str, bool], tests: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "phase": PHASE, "run_id": run_id,
        "stage2_status": "PARTIAL_DEEPSEEK_DEFERRED",
        "deepseek_checked": False, "deepseek_call_attempted": False,
        "reference_source_path": str(reference), "target_source_path": str(target),
        "reference_source_exists": False, "target_source_exists": False,
        "reference_source_sha256_before": None, "target_source_sha256_before": None,
        "reference_source_sha256_after": None, "target_source_sha256_after": None,
        "source_hashes_unchanged": False, "copy_hashes_unchanged": None,
        "copy_hashes_match_sources": False, "live_document_diverges_from_disk": None,
        "reference_copy_path": None, "target_copy_path": None,
        "copies_opened": False, "copies_saved": False,
        "stage3_1_r1_final_status": "PARTIAL_SCAN_LIMITED",
        "stage3_2_allowed": False, "stage3_2_executed": False,
        "repair_task_generated": False, "production_d1_allowed": False,
        "safety_flags": safety, "tests": dict(tests or {}), "errors": [],
    }


def _safety_flags() -> dict[str, bool]:
    return {
        "autocad_connected": False, "new_autocad_instance_created": False,
        "source_reference_opened": False, "source_target_opened": False,
        "source_reference_activated": False, "source_target_activated": False,
        "source_reference_saved": False, "source_target_saved": False,
        "source_modified": False, "reference_copy_opened": False,
        "target_copy_opened": False, "reference_copy_saved": False,
        "target_copy_saved": False, "current_live_drawings_modified": False,
        "entities_created": False, "entities_modified": False,
        "entities_deleted": False, "explode_used": False,
        "copyobjects_used": False, "saveas_used": False,
        "sendcommand_used": False, "lisp_executed": False,
        "netload_used": False, "tianzheng_command_executed": False,
        "tdb_modified": False, "automatic_fallback_used": False,
        "repair_task_generated": False, "stage3_2_executed": False,
        "production_d1_allowed": False,
    }


def _manifest(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": PHASE, "run_id": report["run_id"],
        "stage2_status": report["stage2_status"],
        "reference_source_sha256": report["reference_source_sha256_before"],
        "target_source_sha256": report["target_source_sha256_before"],
        "reference_copy_path": report["reference_copy_path"],
        "target_copy_path": report["target_copy_path"],
        "target_scan_status": report.get("target_scan_status"),
        "stage3_1_r1_final_status": report["stage3_1_r1_final_status"],
        "stage3_2_allowed": report["stage3_2_allowed"],
        "repair_task_generated": False,
        "safety_flags": report["safety_flags"],
    }


def _write_reports(report: Mapping[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(dict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_MD.write_text(_render_markdown(report), encoding="utf-8")


def _render_markdown(report: Mapping[str, Any]) -> str:
    selected = report.get("selected_transform") or {}
    lines = [
        "# Stage 3.1-R1 — 目标图扫描真实性确认与局部对齐修复", "",
        "## 结论", "",
        f"- status: {report['stage3_1_r1_final_status']}",
        f"- target_scan_status: {report.get('target_scan_status')}",
        f"- target_top_level_count_basically_credible: {str(report.get('target_top_level_count_basically_credible')).lower()}",
        f"- region_correspondence_status: {report.get('region_correspondence_status')}",
        f"- transform: {selected.get('transform_type')}",
        f"- non_text_anchor_count: {report.get('non_text_anchor_count')}",
        f"- geometry_overlap_score: {report.get('geometry_overlap_score')}",
        f"- alignment_confidence: {report.get('alignment_confidence')}",
        f"- stage3_2_allowed: {str(report.get('stage3_2_allowed')).lower()}", "",
        "## Target 顶层实体", "",
        f"- ModelSpace: {report.get('target_modelspace_count')}",
        f"- PaperSpace: {report.get('target_paperspace_count')}",
        f"- ObjectName: `{json.dumps(report.get('target_object_name_counts'), ensure_ascii=False)}`", "",
        "## Block / XRef / Proxy", "",
        f"- block references: {report.get('target_block_reference_count')}",
        f"- block definitions: {report.get('target_block_definition_count')}",
        f"- xrefs: {report.get('target_xref_count')}",
        f"- proxies: {report.get('target_proxy_count')}",
        f"- nested blocks: {report.get('target_nested_block_count')}",
        f"- virtual expansion required/performed/entities: {report.get('virtual_expansion_required')} / {report.get('virtual_expansion_performed')} / {report.get('virtual_entity_count')}", "",
        "## 安全", "",
    ]
    lines.extend(f"- {name}={str(value).lower()}" for name, value in report["safety_flags"].items())
    if report.get("alignment_blockers"):
        lines.extend(["", "## 阻断证据", "", *[f"- {item}" for item in report["alignment_blockers"]]])
    if report.get("errors"):
        lines.extend(["", "## 错误", "", *[f"- {item}" for item in report["errors"]]])
    lines.append("")
    return "\n".join(lines)


class _ControlledStop(Exception):
    pass


if __name__ == "__main__":
    result = run_stage3_1_r1()
    print(json.dumps({
        "run_id": result["run_id"],
        "stage3_1_r1_final_status": result["stage3_1_r1_final_status"],
        "target_scan_status": result.get("target_scan_status"),
        "stage3_2_allowed": result["stage3_2_allowed"],
        "errors": result["errors"],
    }, ensure_ascii=False))
