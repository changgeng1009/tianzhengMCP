from __future__ import annotations

from typing import Any


class SemanticDiffV2:
    def compare(
        self,
        reference_graph: dict[str, Any],
        target_graph: dict[str, Any],
        alignment_confidence: float,
    ) -> dict[str, list[dict[str, Any]]]:
        target_signatures = {_pipe_signature(pipe) for pipe in target_graph.get("pipes", [])}
        result = {
            "true_missing": [],
            "design_variation": [],
            "uncertain": [],
        }

        for pipe in reference_graph.get("pipes", []):
            if _pipe_signature(pipe) in target_signatures:
                continue
            confidence = round(float(pipe.get("confidence", 0.7)) * float(alignment_confidence), 4)
            item = {
                "reference_id": pipe.get("id"),
                "entity_type": "pipe",
                "entity": pipe,
                "confidence": confidence,
                "reason": "reference_pipe_not_found_in_target_with_alignment_context",
            }
            if confidence > 0.85:
                result["true_missing"].append(item)
            elif confidence > 0.6:
                result["design_variation"].append(item)
            else:
                result["uncertain"].append(item)

        return result


def _pipe_signature(pipe: dict[str, Any]) -> tuple[Any, ...]:
    return (
        pipe.get("dn"),
        pipe.get("system_type"),
        tuple(pipe.get("start", [])),
        tuple(pipe.get("end", [])),
    )

