from __future__ import annotations

from copy import deepcopy
from typing import Any

from mcp.diagnostics.input_graph import (
    diagnose_dwg_source,
    diagnose_pdf_source,
    input_readiness_status,
)
from mcp.vision.cv_provider import CVVisionProvider
from mcp.vision.provider import BasicVisionProvider, VisionProvider

SUPPORTED_SOURCE_TYPES = {"pdf", "png", "dwg"}
GRAPH_KEYS = ("buildings", "pipes", "valves", "sprinklers", "texts", "symbols")


class MultiSourceSemanticLoader:
    def __init__(self, vision_provider: VisionProvider | None = None) -> None:
        self.vision_provider = vision_provider or CVVisionProvider()
        self.fallback_vision_provider = BasicVisionProvider()

    def load_sources(self, sources: list[dict[str, Any]]) -> dict[str, Any]:
        warnings: list[str] = []
        merged = _empty_graph()
        source_types: list[str] = []
        confidences: list[float] = []
        source_diagnostics: list[dict[str, Any]] = []

        for source in sources:
            source_type = str(source.get("type") or "").lower()
            if source_type not in SUPPORTED_SOURCE_TYPES:
                warnings.append(f"unsupported source type skipped: {source_type}")
                continue
            source_types.append(source_type)
            graph, confidence, diagnostics = self._load_one(source, warnings)
            if diagnostics:
                source_diagnostics.append(diagnostics)
            confidences.append(confidence)
            _merge_graph(merged, graph)

        confidence = _combined_confidence(confidences, warnings)
        target_diagnostics = _first_diagnostics(source_diagnostics, "dwg", role="target")
        reference_diagnostics = _first_reference_diagnostics(source_diagnostics)
        return {
            "status": "success",
            "semantic_graph": merged,
            "source_types": source_types,
            "confidence": confidence,
            "warnings": warnings,
            "source_diagnostics": source_diagnostics,
            "target_graph_diagnostics": target_diagnostics,
            "reference_graph_diagnostics": reference_diagnostics,
            "target_graph_empty_reason": target_diagnostics.get("empty_reason", ""),
            "reference_graph_empty_reason": reference_diagnostics.get("empty_reason", ""),
        }

    def _load_one(self, source: dict[str, Any], warnings: list[str]) -> tuple[dict[str, Any], float, dict[str, Any]]:
        if "semantic_graph" in source and isinstance(source["semantic_graph"], dict):
            graph = _normalize_graph(source["semantic_graph"], source)
            diagnostics = {
                "source_type": str(source.get("type") or "").lower(),
                "source_path": source.get("path"),
                "role": source.get("role"),
                "semantic_graph_provided": True,
                "graph_nodes": _graph_node_count(graph),
                "graph_edges": len(graph.get("pipes", [])),
                "empty_reason": "" if _graph_node_count(graph) else "provided_semantic_graph_empty",
                "warnings": [],
                "errors": [],
            }
            graph.setdefault("metadata", {})["diagnostics"] = diagnostics
            return graph, float(graph.get("metadata", {}).get("confidence", 1.0)), diagnostics

        source_type = str(source.get("type") or "").lower()
        if source_type == "dwg":
            result = diagnose_dwg_source(source)
            graph = _normalize_graph(result["graph"], source)
            diagnostics = dict(result["diagnostics"])
            diagnostics["role"] = source.get("role")
            warnings.extend(result.get("warnings", []))
            warnings.extend(result.get("errors", []))
            return graph, float(graph.get("metadata", {}).get("confidence", 0.0)), diagnostics

        if source_type == "pdf":
            result = diagnose_pdf_source(source, vision_provider=self.vision_provider)
            graph = _normalize_graph(result["graph"], source)
            diagnostics = dict(result["diagnostics"])
            diagnostics["role"] = source.get("role")
            warnings.extend(result.get("warnings", []))
            warnings.extend(result.get("errors", []))
            return graph, float(graph.get("metadata", {}).get("confidence", 0.0)), diagnostics

        if source_type in {"pdf", "png"}:
            try:
                parse_result = self._parse_with_provider(source_type, str(source.get("path") or ""))
                graph = _normalize_graph(self.vision_provider.to_semantic_graph(parse_result), source)
                warnings.extend(parse_result.warnings)
                return graph, parse_result.confidence, {}
            except Exception as exc:
                warnings.append(f"vision parse failed for {source.get('path')}: {exc}")
                try:
                    fallback_result = (
                        self.fallback_vision_provider.parse_pdf(str(source.get("path") or ""))
                        if source_type == "pdf"
                        else self.fallback_vision_provider.parse_png(str(source.get("path") or ""))
                    )
                    graph = _normalize_graph(
                        self.fallback_vision_provider.to_semantic_graph(fallback_result),
                        source,
                    )
                    warnings.extend(fallback_result.warnings)
                    return graph, fallback_result.confidence, {}
                except Exception as fallback_exc:
                    warnings.append(f"fallback vision parse failed for {source.get('path')}: {fallback_exc}")
                    return _normalize_graph(_empty_graph(), source), 0.0, {}

        warnings.append(
            f"{source.get('type')} source has no semantic_graph; returned empty graph for {source.get('path')}"
        )
        return _normalize_graph(_empty_graph(), source), 0.0, {}

    def _parse_with_provider(self, source_type: str, path: str):
        if source_type == "pdf":
            return self.vision_provider.parse_pdf(path)
        return self.vision_provider.parse_png(path)


def _empty_graph() -> dict[str, Any]:
    graph: dict[str, Any] = {key: [] for key in GRAPH_KEYS}
    graph["metadata"] = {"source": "multi_source_loader", "confidence": 0.0, "warnings": []}
    return graph


def _normalize_graph(graph: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    normalized = _empty_graph()
    for key in GRAPH_KEYS:
        items = graph.get(key, [])
        if not isinstance(items, list):
            items = []
        normalized[key] = []
        for item in items:
            entity = deepcopy(item)
            entity.setdefault("source_type", source.get("type"))
            entity.setdefault("source_path", source.get("path"))
            entity.setdefault("role", source.get("role"))
            normalized[key].append(entity)
    metadata = dict(graph.get("metadata", {}))
    metadata.setdefault("source", "unknown")
    metadata.setdefault("confidence", 1.0 if any(normalized[key] for key in GRAPH_KEYS) else 0.0)
    metadata.setdefault("warnings", [])
    normalized["metadata"] = metadata
    return normalized


def _merge_graph(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in GRAPH_KEYS:
        target[key].extend(source.get(key, []))
    target_metadata = target.setdefault("metadata", {})
    source_metadata = source.get("metadata", {})
    target_warnings = target_metadata.setdefault("warnings", [])
    target_warnings.extend(source_metadata.get("warnings", []))
    for key in ("coordinate_space", "source", "provider"):
        if source_metadata.get(key):
            target_metadata[key] = source_metadata[key]
    if source_metadata.get("confidence") is not None:
        target_metadata["confidence"] = source_metadata["confidence"]
    if source_metadata.get("diagnostics"):
        target_metadata["diagnostics"] = source_metadata["diagnostics"]


def _combined_confidence(confidences: list[float], warnings: list[str]) -> float:
    if not confidences:
        return 0.0
    value = sum(confidences) / len(confidences)
    if warnings:
        value = min(value, 0.75)
    return round(value, 4)


def _first_diagnostics(
    diagnostics: list[dict[str, Any]], source_type: str, role: str | None = None
) -> dict[str, Any]:
    for item in diagnostics:
        if item.get("source_type") != source_type:
            continue
        if role is not None and item.get("role") != role:
            continue
        return item
    return {}


def _first_reference_diagnostics(diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    for item in diagnostics:
        if item.get("role") == "target":
            continue
        if item.get("source_type") in {"pdf", "png"}:
            return item
    return {}


def _graph_node_count(graph: dict[str, Any]) -> int:
    return sum(len(graph.get(key, [])) for key in GRAPH_KEYS)
