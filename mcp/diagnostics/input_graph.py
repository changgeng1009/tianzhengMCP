from __future__ import annotations

import math
from typing import Any

from mcp.vision.cv_provider import CVVisionProvider, is_opencv_available
from mcp.vision.models import VisionElement
from mcp.vision.pdf_renderer import render_pdf_to_images
from mcp.vision.semantic_builder import build_semantic_graph

GRAPH_KEYS = ("buildings", "pipes", "valves", "sprinklers", "texts", "symbols")
PDF_EDGE_FALLBACK_THRESHOLD = 1000


def diagnose_dwg_source(source: dict[str, Any], cad_reader: Any | None = None) -> dict[str, Any]:
    path = str(source.get("path") or "")
    diagnostics = _empty_dwg_diagnostics(path)
    if isinstance(source.get("semantic_graph"), dict):
        graph = _normalize_graph(source["semantic_graph"])
        diagnostics.update(
            {
                "loader_strategy": "provided_semantic_graph",
                "semantic_graph_provided": True,
                "graph_nodes": _graph_node_count(graph),
                "graph_edges": len(graph.get("pipes", [])),
                "empty_reason": "" if _graph_node_count(graph) else "provided_semantic_graph_empty",
            }
        )
        graph.setdefault("metadata", {})["diagnostics"] = diagnostics
        graph, scope_summary = apply_scope_to_graph(graph, source.get("scope"), "target")
        diagnostics["scope_summary"] = scope_summary
        return {"graph": graph, "diagnostics": diagnostics, "warnings": list(scope_summary.get("warnings", [])), "errors": []}

    if cad_reader is None and not source.get("enable_cad_reader"):
        diagnostics["loader_strategy"] = "semantic_graph_only"
        diagnostics["empty_reason"] = "dwg_loader_strategy=semantic_graph_only"
        diagnostics["warnings"].append("dwg_loader_strategy=semantic_graph_only")
        graph = _empty_graph(
            {
                "source": "dwg",
                "confidence": 0.0,
                "empty_reason": diagnostics["empty_reason"],
                "diagnostics": diagnostics,
                "warnings": list(diagnostics["warnings"]),
            }
        )
        graph, scope_summary = apply_scope_to_graph(graph, source.get("scope"), "target")
        diagnostics["scope_summary"] = scope_summary
        return {"graph": graph, "diagnostics": diagnostics, "warnings": list(diagnostics["warnings"]) + list(scope_summary.get("warnings", [])), "errors": []}

    diagnostics["cad_reader_attempted"] = True
    reader = cad_reader or SafeDwgComReader()
    diagnostics["cad_reader_available"] = bool(getattr(reader, "available", True))
    try:
        inspected = reader.inspect(path)
    except Exception as exc:
        diagnostics["loader_strategy"] = "cad_reader_failed"
        diagnostics["empty_reason"] = "cad_reader_failed"
        diagnostics["errors"].append(str(exc))
        graph = _empty_graph(
            {
                "source": "dwg",
                "confidence": 0.0,
                "empty_reason": diagnostics["empty_reason"],
                "diagnostics": diagnostics,
                "warnings": list(diagnostics["warnings"]),
            }
        )
        graph, scope_summary = apply_scope_to_graph(graph, source.get("scope"), "target")
        diagnostics["scope_summary"] = scope_summary
        return {"graph": graph, "diagnostics": diagnostics, "warnings": list(diagnostics["warnings"]) + list(scope_summary.get("warnings", [])), "errors": list(diagnostics["errors"])}

    _merge_dwg_inspection(diagnostics, inspected)
    graph = _primitive_graph_from_diagnostics(diagnostics, inspected)
    if _graph_node_count(graph):
        diagnostics["loader_strategy"] = "cad_reader_primitive_fallback"
        diagnostics["graph_nodes"] = _graph_node_count(graph)
        diagnostics["graph_edges"] = len(graph.get("pipes", []))
        diagnostics["empty_reason"] = ""
    else:
        diagnostics["loader_strategy"] = _empty_dwg_strategy(diagnostics)
        diagnostics["empty_reason"] = diagnostics["loader_strategy"]
    graph.setdefault("metadata", {}).update(
        {
            "diagnostics": diagnostics,
            "empty_reason": diagnostics["empty_reason"],
            "warnings": list(diagnostics["warnings"]),
        }
    )
    graph, scope_summary = apply_scope_to_graph(graph, source.get("scope"), "target")
    diagnostics["scope_summary"] = scope_summary
    diagnostics["graph_nodes"] = _graph_node_count(graph)
    diagnostics["graph_edges"] = len(graph.get("pipes", []))
    return {
        "graph": graph,
        "diagnostics": diagnostics,
        "warnings": list(diagnostics["warnings"]) + list(scope_summary.get("warnings", [])),
        "errors": list(diagnostics["errors"]),
    }


def diagnose_pdf_source(source: dict[str, Any], vision_provider: Any | None = None) -> dict[str, Any]:
    path = str(source.get("path") or "")
    provider = vision_provider or CVVisionProvider()
    diagnostics = _empty_pdf_diagnostics()
    rendered = render_pdf_to_images(path, output_dir=source.get("render_output_dir"))
    diagnostics["pdf_rendered"] = rendered.get("status") == "success" and bool(rendered.get("images"))
    diagnostics["rendered_images"] = [str(item.get("path")) for item in rendered.get("images", [])]
    diagnostics["warnings"].extend(rendered.get("warnings", []))
    if not diagnostics["pdf_rendered"]:
        try:
            provider.parse_pdf(path)
        except Exception as exc:
            diagnostics["warnings"].append(f"vision parse failed for {path}: {exc}")
        diagnostics["empty_reason"] = "pdf_render_failed"
        graph = _empty_graph({"source": "vision", "provider": "CVVisionProvider", "confidence": 0.0})
        graph["metadata"].update({"empty_reason": diagnostics["empty_reason"], "diagnostics": diagnostics})
        graph, scope_summary = apply_scope_to_graph(graph, source.get("scope"), "reference")
        diagnostics["scope_summary"] = scope_summary
        return {"graph": graph, "diagnostics": diagnostics, "warnings": list(diagnostics["warnings"]) + list(scope_summary.get("warnings", [])), "errors": []}

    first_image = diagnostics["rendered_images"][0]
    image_diag = analyze_image_diagnostics(first_image)
    diagnostics.update({key: value for key, value in image_diag.items() if key not in {"warnings", "errors"}})
    diagnostics["warnings"].extend(image_diag.get("warnings", []))
    diagnostics["errors"].extend(image_diag.get("errors", []))

    try:
        parse_result = provider.parse_pdf(path)
        graph = _normalize_graph(provider.to_semantic_graph(parse_result))
        diagnostics["warnings"].extend(parse_result.warnings)
    except Exception as exc:
        diagnostics["warnings"].append(f"vision parse failed: {exc}")
        graph = _empty_graph({"source": "vision", "provider": "CVVisionProvider", "confidence": 0.0})

    counts = _semantic_graph_counts(graph)
    diagnostics["semantic_graph_counts"] = counts
    if not any(counts.values()):
        diagnostics["empty_reason"] = "pdf_rendered_but_no_visual_elements"
        if diagnostics.get("line_candidates"):
            graph = _pdf_line_candidate_fallback(graph, diagnostics, source)
            diagnostics["empty_reason"] = ""
        elif int(diagnostics.get("edge_pixel_count") or 0) > PDF_EDGE_FALLBACK_THRESHOLD:
            graph = _pdf_drawing_content_fallback(graph, diagnostics)
            diagnostics["empty_reason"] = ""
        else:
            diagnostics["warnings"].append("pdf rendered but semantic graph is empty")
    elif not graph.get("pipes") and diagnostics.get("line_candidates"):
        graph = _merge_pdf_line_candidates(graph, diagnostics, source)
    graph.setdefault("metadata", {}).update(
        {
            "diagnostics": diagnostics,
            "empty_reason": diagnostics["empty_reason"],
            "warnings": list(dict.fromkeys(graph.get("metadata", {}).get("warnings", []) + diagnostics["warnings"])),
        }
    )
    graph, scope_summary = apply_scope_to_graph(graph, source.get("scope"), "reference")
    diagnostics["scope_summary"] = scope_summary
    diagnostics["semantic_graph_counts"] = _semantic_graph_counts(graph)
    return {
        "graph": graph,
        "diagnostics": diagnostics,
        "warnings": list(dict.fromkeys(diagnostics["warnings"] + list(scope_summary.get("warnings", [])))),
        "errors": list(diagnostics["errors"]),
    }


def analyze_image_diagnostics(image_path: str) -> dict[str, Any]:
    diagnostics = {
        "image_size": [0, 0],
        "preprocess_steps": ["grayscale", "canny", "hough_lines_p", "contour_scan"],
        "edge_pixel_count": 0,
        "line_candidate_count": 0,
        "contour_candidate_count": 0,
        "symbol_candidate_count": 0,
        "text_candidate_count": 0,
        "detector_thresholds": {"canny_low": 50, "canny_high": 150, "hough_threshold": 80, "min_line_length": 80},
        "warnings": [],
        "errors": [],
    }
    if not is_opencv_available():
        diagnostics["warnings"].append("OpenCV not available; image diagnostics limited")
        return diagnostics
    try:
        cv2 = __import__("cv2")
        image = _read_grayscale_image(cv2, image_path)
        if image is None:
            diagnostics["warnings"].append(f"image could not be read: {image_path}")
            return diagnostics
        height, width = image.shape[:2]
        diagnostics["image_size"] = [int(width), int(height)]
        if width < 200 or height < 200:
            diagnostics["warnings"].append("image too small for reliable drawing detection")
        if width > 8000 or height > 8000:
            diagnostics["warnings"].append("image very large; detector thresholds may need scaling")
        if float(image.std()) < 5.0:
            diagnostics["warnings"].append("image low contrast")
        edges = cv2.Canny(image, 50, 150)
        diagnostics["edge_pixel_count"] = int((edges > 0).sum())
        lines = cv2.HoughLinesP(edges, 1, 3.14159265 / 180, threshold=80, minLineLength=80, maxLineGap=10)
        diagnostics["line_candidate_count"] = 0 if lines is None else int(len(lines))
        diagnostics["line_candidates"] = _line_candidates_from_hough(lines)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        diagnostics["contour_candidate_count"] = int(len(contours))
        if diagnostics["line_candidate_count"] == 0 and diagnostics["edge_pixel_count"] > PDF_EDGE_FALLBACK_THRESHOLD:
            diagnostics["warnings"].append("line detector returned 0 candidates despite visible edge pixels")
    except Exception as exc:
        diagnostics["errors"].append(str(exc))
    return diagnostics


def input_readiness_status(
    target_graph: dict[str, Any],
    reference_graph: dict[str, Any],
    scope_enabled: bool = False,
    manual_anchor_pairs: list[dict[str, Any]] | None = None,
    alignment_success: bool = False,
    review_only_actions: int = 0,
) -> str:
    target_empty = _graph_node_count(target_graph) == 0
    reference_empty = _graph_node_count(reference_graph) == 0
    if scope_enabled and target_empty:
        return "scoped_target_empty"
    if scope_enabled and reference_empty:
        return "scoped_reference_empty"
    if target_empty and reference_empty:
        return "both_empty"
    if target_empty:
        return "target_empty"
    if reference_empty:
        return "reference_empty"
    if review_only_actions > 0 or alignment_success:
        return "ready_for_review_only_repair"
    if manual_anchor_pairs:
        return "ready_for_manual_anchor_alignment"
    if scope_enabled and (_is_low_confidence(target_graph) or _is_low_confidence(reference_graph)):
        return "scoped_both_non_empty_low_confidence"
    if _is_low_confidence(target_graph) or _is_low_confidence(reference_graph):
        return "both_non_empty_low_confidence"
    return "ready_for_alignment"


def run_input_graph_diagnostics(
    target_dwg: str,
    reference_pdf: str,
    scope: dict[str, Any] | None = None,
    manual_anchor_pairs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    target = diagnose_dwg_source(
        {"type": "dwg", "role": "target", "path": target_dwg, "enable_cad_reader": True, "scope": scope}
    )
    reference = diagnose_pdf_source({"type": "pdf", "path": reference_pdf, "scope": scope})
    readiness = input_readiness_status(
        target["graph"],
        reference["graph"],
        scope_enabled=bool((scope or {}).get("enabled")),
        manual_anchor_pairs=manual_anchor_pairs,
    )
    scope_summary = {
        "enabled": bool((scope or {}).get("enabled")),
        "target": target["diagnostics"].get("scope_summary", {}),
        "reference": reference["diagnostics"].get("scope_summary", {}),
    }
    return {
        "target": target,
        "reference": reference,
        "input_readiness_status": readiness,
        "readiness_status": readiness,
        "scope_summary": scope_summary,
        "manual_anchor_summary": {
            "used_manual_anchors": bool(manual_anchor_pairs),
            "manual_anchor_count": len(manual_anchor_pairs or []),
        },
        "warnings": list(dict.fromkeys(target.get("warnings", []) + reference.get("warnings", []))),
        "errors": list(target.get("errors", []) + reference.get("errors", [])),
    }


def apply_scope_to_graph(
    graph: dict[str, Any],
    scope: dict[str, Any] | None,
    side: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scope = dict(scope or {})
    before = _graph_node_count(graph)
    summary = {
        "enabled": bool(scope.get("enabled")),
        "side": side,
        "mode": scope.get("mode", "bbox"),
        "label": scope.get("label", ""),
        "before_count": before,
        "after_count": before,
        "filtered_out_count": 0,
        "warnings": [],
    }
    if not scope.get("enabled"):
        return graph, summary
    bbox = scope.get("reference_bbox") if side == "reference" else scope.get("target_bbox")
    parsed = _parse_bbox(bbox)
    if parsed is None:
        summary["warnings"].append(f"invalid bbox for {side} scope")
        return graph, summary
    scoped = _empty_graph(dict(graph.get("metadata", {})))
    for key in GRAPH_KEYS:
        scoped[key] = [item for item in graph.get(key, []) if _entity_inside_bbox(item, parsed)]
    metadata = dict(scoped.get("metadata", {}))
    metadata["scope"] = {"enabled": True, "bbox": parsed, "side": side, "label": scope.get("label", "")}
    scoped["metadata"] = metadata
    after = _graph_node_count(scoped)
    summary["after_count"] = after
    summary["filtered_out_count"] = before - after
    return scoped, summary


class SafeDwgComReader:
    available = True

    def inspect(self, path: str) -> dict[str, Any]:
        try:
            import win32com.client  # type: ignore
        except Exception as exc:
            self.available = False
            return {"warnings": [f"CAD COM reader unavailable: {exc}"], "errors": [], "document_resolved": False}
        acad = win32com.client.GetActiveObject("AutoCAD.Application")
        document = _resolve_document(acad, path)
        if document is None:
            return {"warnings": ["target document not resolved in AutoCAD"], "errors": [], "document_resolved": False}
        return _inspect_document(document)


def _empty_dwg_diagnostics(path: str) -> dict[str, Any]:
    return {
        "source_type": "dwg",
        "target_dwg_path": path,
        "loader_strategy": "",
        "semantic_graph_provided": False,
        "cad_reader_attempted": False,
        "cad_reader_available": False,
        "document_resolved": False,
        "modelspace_entity_count": 0,
        "paperspace_entity_count": 0,
        "entity_type_histogram": {},
        "t30_object_count": 0,
        "primitive_object_count": 0,
        "block_reference_count": 0,
        "block_reference_names": [],
        "layers": [],
        "graph_nodes": 0,
        "graph_edges": 0,
        "empty_reason": "",
        "warnings": [],
        "errors": [],
    }


def _empty_pdf_diagnostics() -> dict[str, Any]:
    return {
        "source_type": "pdf",
        "pdf_rendered": False,
        "rendered_images": [],
        "image_size": [0, 0],
        "preprocess_steps": [],
        "edge_pixel_count": 0,
        "line_candidate_count": 0,
        "contour_candidate_count": 0,
        "symbol_candidate_count": 0,
        "text_candidate_count": 0,
        "semantic_graph_counts": {key: 0 for key in GRAPH_KEYS},
        "empty_reason": "",
        "warnings": [],
        "errors": [],
    }


def _empty_graph(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {**{key: [] for key in GRAPH_KEYS}, "metadata": dict(metadata or {})}


def _normalize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    normalized = _empty_graph(dict(graph.get("metadata", {})))
    for key in GRAPH_KEYS:
        items = graph.get(key, [])
        normalized[key] = list(items) if isinstance(items, list) else []
    normalized.setdefault("metadata", {})
    return normalized


def _merge_dwg_inspection(diagnostics: dict[str, Any], inspected: dict[str, Any]) -> None:
    for key in (
        "document_resolved",
        "modelspace_entity_count",
        "paperspace_entity_count",
        "entity_type_histogram",
        "t30_object_count",
        "primitive_object_count",
        "block_reference_count",
        "block_reference_names",
        "layers",
    ):
        if key in inspected:
            diagnostics[key] = inspected[key]
    diagnostics["warnings"].extend(inspected.get("warnings", []))
    diagnostics["errors"].extend(inspected.get("errors", []))


def _primitive_graph_from_diagnostics(diagnostics: dict[str, Any], inspected: dict[str, Any]) -> dict[str, Any]:
    primitives = inspected.get("primitives", [])
    pipes = []
    for index, primitive in enumerate(primitives):
        primitive_type = str(primitive.get("type") or "")
        if primitive_type not in {"Line", "Polyline", "AcDbLine", "AcDbPolyline"}:
            continue
        start, end = _primitive_endpoints(primitive)
        if not start or not end:
            continue
        pipes.append(
            {
                "id": f"dwg_primitive_candidate_{index}",
                "type": "pipe_like_candidate",
                "start": start,
                "end": end,
                "geometry": {
                    "type": "line" if primitive_type in {"Line", "AcDbLine"} else "polyline",
                    "points": _primitive_points(primitive, start, end),
                },
                "dn": None,
                "system_type": "unknown",
                "confidence": 0.35,
                "source": "dwg_primitive_fallback",
                "metadata": {
                    "source": "dwg_primitive_fallback",
                    "not_t30_semantic": True,
                    "primitive_type": primitive_type,
                    "entity_type": primitive_type,
                    "layer": primitive.get("layer"),
                    "handle": primitive.get("handle", ""),
                    "auto_execute_allowed": False,
                    "requires_manual_review": True,
                },
            }
        )
    return {
        "buildings": [],
        "pipes": pipes,
        "valves": [],
        "sprinklers": [],
        "texts": [],
        "symbols": [],
        "metadata": {
            "source": "dwg_primitive_fallback" if pipes else "dwg",
            "not_t30_semantic": bool(pipes),
            "confidence": 0.35 if pipes else 0.0,
            "coordinate_space": "cad_modelspace",
            "warnings": ["DWG primitive fallback is low confidence and manual-review only"] if pipes else [],
        },
    }


def _primitive_endpoints(primitive: dict[str, Any]) -> tuple[list[float] | None, list[float] | None]:
    if primitive.get("start") and primitive.get("end"):
        return _point3d(primitive["start"]), _point3d(primitive["end"])
    points = primitive.get("points") or []
    if len(points) >= 2:
        return _point3d(points[0]), _point3d(points[-1])
    return None, None


def _primitive_points(primitive: dict[str, Any], start: list[float], end: list[float]) -> list[list[float]]:
    if primitive.get("points"):
        return [_point3d(point) for point in primitive.get("points", [])]
    return [list(start), list(end)]


def _line_candidates_from_hough(lines: Any) -> list[dict[str, Any]]:
    if lines is None:
        return []
    candidates: list[dict[str, Any]] = []
    for row in lines[:1000]:
        x1, y1, x2, y2 = [float(value) for value in row[0]]
        length = math.hypot(x2 - x1, y2 - y1)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        candidates.append({"points": [[x1, y1], [x2, y2]], "length": length, "angle": angle})
    return candidates


def _pdf_line_candidate_fallback(
    graph: dict[str, Any],
    diagnostics: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    line_candidates = _filtered_line_candidates(
        diagnostics.get("line_candidates", []),
        diagnostics.get("image_size", [0, 0]),
        int(source.get("max_line_candidates", 300)),
    )
    elements = [
        VisionElement(
            element_id=f"pdf_line_candidate_{index}",
            element_type="pipe_candidate",
            bbox=_bbox_from_points(candidate["points"]),
            points=[list(point) for point in candidate["points"]],
            text=None,
            confidence=float(candidate.get("confidence", 0.45)),
            source={"provider": "pdf_line_candidate_fallback"},
            metadata={
                "source": "pdf_line_candidate_fallback",
                "not_confirmed_pipe": True,
                "auto_execute_allowed": False,
                "requires_manual_review": True,
                "detector": "line_candidate_fallback",
                "length": candidate.get("length"),
                "angle": candidate.get("angle"),
            },
        )
        for index, candidate in enumerate(line_candidates)
    ]
    fallback_graph = build_semantic_graph(elements, provider="PDFLineCandidateFallback")
    fallback_graph["metadata"].update(
        {
            "source": "pdf_line_candidate_fallback",
            "confidence": _average([element.confidence for element in elements]),
            "fallback": True,
            "warnings": list(
                dict.fromkeys(
                    graph.get("metadata", {}).get("warnings", [])
                    + diagnostics.get("warnings", [])
                    + ["PDF line candidates promoted to low-confidence pipe_candidate; manual-review only"]
                )
            ),
            "image_size": diagnostics.get("image_size", [0, 0]),
        }
    )
    summary = {
        "detected_line_candidates": int(diagnostics.get("line_candidate_count", len(diagnostics.get("line_candidates", [])))),
        "generated_pipe_candidates": len(elements),
        "max_line_candidates": int(source.get("max_line_candidates", 300)),
        "confidence": fallback_graph["metadata"]["confidence"],
    }
    diagnostics["pdf_line_candidate_summary"] = summary
    diagnostics["semantic_graph_counts"] = _semantic_graph_counts(fallback_graph)
    return fallback_graph


def _merge_pdf_line_candidates(graph: dict[str, Any], diagnostics: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    fallback = _pdf_line_candidate_fallback(_empty_graph(), diagnostics, source)
    merged = _normalize_graph(graph)
    merged["pipes"].extend(fallback.get("pipes", []))
    metadata = dict(merged.get("metadata", {}))
    metadata["confidence"] = min(float(metadata.get("confidence", 0.0) or 0.0), 0.55)
    metadata["pdf_line_candidate_summary"] = diagnostics.get("pdf_line_candidate_summary", {})
    metadata["warnings"] = list(dict.fromkeys(metadata.get("warnings", []) + fallback.get("metadata", {}).get("warnings", [])))
    merged["metadata"] = metadata
    diagnostics["semantic_graph_counts"] = _semantic_graph_counts(merged)
    return merged


def _filtered_line_candidates(
    candidates: list[dict[str, Any]],
    image_size: list[int],
    max_count: int,
) -> list[dict[str, Any]]:
    width = float(image_size[0]) if image_size else 0.0
    height = float(image_size[1]) if len(image_size) > 1 else 0.0
    diagonal = math.hypot(width, height) if width and height else 0.0
    kept: list[dict[str, Any]] = []
    for candidate in candidates:
        points = candidate.get("points") or []
        if len(points) < 2:
            continue
        length = float(candidate.get("length") or _line_length(points))
        if length < 20.0:
            continue
        confidence = 0.45
        if diagonal and length > diagonal * 0.8:
            confidence = 0.35
        angle = abs(float(candidate.get("angle", 0.0))) % 180.0
        off_axis = min(abs(angle), abs(angle - 90.0), abs(angle - 180.0))
        if off_axis > 15.0:
            confidence = min(confidence, 0.38)
        kept.append({**candidate, "length": length, "confidence": confidence})
    kept.sort(key=lambda item: float(item.get("length", 0.0)), reverse=True)
    return kept[: max(0, max_count)]


def _line_length(points: list[list[float]]) -> float:
    return math.hypot(float(points[-1][0]) - float(points[0][0]), float(points[-1][1]) - float(points[0][1]))


def _bbox_from_points(points: list[list[float]]) -> list[float]:
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _pdf_drawing_content_fallback(graph: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
    width, height = diagnostics.get("image_size") or [0, 0]
    fallback = VisionElement(
        element_id="pdf_drawing_content_candidate_0",
        element_type="drawing_content_candidate",
        bbox=[0, 0, float(width), float(height)],
        points=[],
        text=None,
        confidence=0.45,
        source={"provider": "pdf_line_fallback"},
        metadata={
            "source": "pdf_line_fallback",
            "auto_execute_allowed": False,
            "requires_manual_review": True,
            "edge_pixel_count": diagnostics.get("edge_pixel_count", 0),
            "line_candidate_count": diagnostics.get("line_candidate_count", 0),
        },
    )
    fallback_graph = build_semantic_graph([fallback], provider="PDFLineFallback")
    fallback_graph["metadata"].update(
        {
            "source": "pdf_line_fallback",
            "confidence": 0.45,
            "fallback": True,
            "warnings": list(
                dict.fromkeys(
                    graph.get("metadata", {}).get("warnings", [])
                    + diagnostics.get("warnings", [])
                    + ["PDF line fallback produced drawing_content_candidate; manual-review only"]
                )
            ),
        }
    )
    diagnostics["semantic_graph_counts"] = _semantic_graph_counts(fallback_graph)
    return fallback_graph


def _parse_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    bbox = [float(item) for item in value]
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


def _entity_inside_bbox(entity: dict[str, Any], bbox: list[float]) -> bool:
    points = _entity_points(entity)
    if not points:
        return False
    return any(bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3] for point in points)


def _entity_points(entity: dict[str, Any]) -> list[list[float]]:
    if entity.get("start") and entity.get("end"):
        return [list(entity["start"]), list(entity["end"])]
    geometry = entity.get("geometry", {})
    if geometry.get("points"):
        return [list(point) for point in geometry["points"]]
    if entity.get("position"):
        return [list(entity["position"])]
    if entity.get("points"):
        return [list(point) for point in entity["points"]]
    if entity.get("bbox"):
        bbox = entity["bbox"]
        return [[bbox[0], bbox[1]], [bbox[2], bbox[3]]]
    return []


def _semantic_graph_counts(graph: dict[str, Any]) -> dict[str, int]:
    return {key: len(graph.get(key, [])) for key in GRAPH_KEYS}


def _graph_node_count(graph: dict[str, Any]) -> int:
    return sum(len(graph.get(key, [])) for key in GRAPH_KEYS)


def _is_low_confidence(graph: dict[str, Any]) -> bool:
    return float(graph.get("metadata", {}).get("confidence", 1.0)) < 0.6


def _empty_dwg_strategy(diagnostics: dict[str, Any]) -> str:
    if not diagnostics.get("document_resolved"):
        return "cad_reader_document_not_resolved"
    if diagnostics.get("block_reference_count", 0) and diagnostics.get("primitive_object_count", 0) == 0:
        return "block_reference_only"
    if diagnostics.get("t30_object_count", 0) == 0:
        return "no_t30_or_supported_primitives"
    return "no_supported_graph_entities"


def _point3d(values: Any) -> list[float]:
    point = [float(value) for value in list(values)[:3]]
    return point + [0.0] * (3 - len(point))


def _resolve_document(acad: Any, path: str) -> Any | None:
    target = str(path).replace("/", "\\").lower()
    for document in acad.Documents:
        full_name = str(getattr(document, "FullName", "") or "").replace("/", "\\").lower()
        if full_name == target:
            return document
    active = getattr(acad, "ActiveDocument", None)
    if active and str(getattr(active, "FullName", "") or "").replace("/", "\\").lower() == target:
        return active
    return None


def _read_grayscale_image(cv2: Any, image_path: str):
    try:
        import numpy as np  # type: ignore

        buffer = np.fromfile(str(image_path), dtype=np.uint8)
        if buffer.size:
            return cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
    except Exception:
        pass
    return cv2.imread(str(image_path), 0)


def _inspect_document(document: Any) -> dict[str, Any]:
    histogram: dict[str, int] = {}
    layers: set[str] = set()
    primitives: list[dict[str, Any]] = []
    block_names: list[str] = []
    modelspace_count = 0
    primitive_count = 0
    block_count = 0
    t30_count = 0
    for entity in document.ModelSpace:
        modelspace_count += 1
        name = str(getattr(entity, "ObjectName", "") or getattr(entity, "EntityName", "") or type(entity).__name__)
        short = name.replace("AcDb", "")
        histogram[short] = histogram.get(short, 0) + 1
        layer = str(getattr(entity, "Layer", "") or "")
        if layer:
            layers.add(layer)
        if "TDb" in name:
            t30_count += 1
        if short in {"Line", "Polyline", "2dPolyline", "3dPolyline"}:
            primitive_count += 1
            primitive = _entity_to_primitive(entity, short, layer)
            if primitive:
                primitives.append(primitive)
        if short == "BlockReference":
            block_count += 1
            block_names.append(str(getattr(entity, "Name", "") or getattr(entity, "EffectiveName", "") or ""))
    return {
        "document_resolved": True,
        "modelspace_entity_count": modelspace_count,
        "paperspace_entity_count": _safe_count(getattr(document, "PaperSpace", [])),
        "entity_type_histogram": histogram,
        "t30_object_count": t30_count,
        "primitive_object_count": primitive_count,
        "block_reference_count": block_count,
        "block_reference_names": block_names,
        "layers": sorted(layers),
        "primitives": primitives,
        "warnings": [],
        "errors": [],
    }


def _entity_to_primitive(entity: Any, entity_type: str, layer: str) -> dict[str, Any] | None:
    try:
        if entity_type == "Line":
            return {
                "type": "Line",
                "start": list(entity.StartPoint),
                "end": list(entity.EndPoint),
                "layer": layer,
                "handle": str(getattr(entity, "Handle", "") or ""),
            }
        coordinates = list(entity.Coordinates)
        points = [coordinates[index : index + 2] for index in range(0, len(coordinates), 2)]
        return {"type": "Polyline", "points": points, "layer": layer, "handle": str(getattr(entity, "Handle", "") or "")}
    except Exception:
        return None


def _safe_count(collection: Any) -> int:
    try:
        return int(collection.Count)
    except Exception:
        try:
            return sum(1 for _ in collection)
        except Exception:
            return 0
