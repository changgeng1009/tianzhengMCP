from __future__ import annotations

from typing import Any

from mcp.spatial.models import Transform2D


def validate_alignment(
    aligned_reference_graph: dict[str, Any],
    target_graph: dict[str, Any],
    transform: Transform2D,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    metrics = {
        "mapped_pipe_count": len(aligned_reference_graph.get("pipes", [])),
        "target_pipe_count": len(target_graph.get("pipes", [])),
        "transform_type": transform.transform_type,
        "residual_error": transform.residual_error,
    }

    if transform.transform_type == "unknown":
        errors.append("transform unavailable")
    if transform.confidence < 0.6:
        warnings.append("transform confidence below threshold")
    if transform.residual_error is not None and transform.residual_error > 1000:
        warnings.append("transform residual error is high")

    low_mapped = [
        item.get("id")
        for key in ("pipes", "valves", "sprinklers", "buildings")
        for item in aligned_reference_graph.get(key, [])
        if float(item.get("mapped_confidence", 1.0)) < 0.6
    ]
    if low_mapped:
        warnings.append("mapped confidence below threshold")
        metrics["low_confidence_items"] = low_mapped

    return {
        "valid": not errors and transform.confidence >= 0.6,
        "confidence": transform.confidence,
        "warnings": warnings,
        "errors": errors,
        "metrics": metrics,
    }

