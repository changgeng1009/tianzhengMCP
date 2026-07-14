from __future__ import annotations

from typing import Any

from semantic_diff.matcher import (
    SemanticEntityMatcher,
    SemanticMatch,
    entity_handle,
    normalized_diameter,
    pipe_entities,
)


def empty_diff_result() -> dict[str, list[dict[str, Any]]]:
    return {
        "add_pipe": [],
        "remove_pipe": [],
        "modify_pipe": [],
        "move_pipe": [],
        "diameter_mismatch": [],
        "system_mismatch": [],
    }


class SemanticDiffEngine:
    def __init__(self, match_tolerance: float = 100.0, move_tolerance: float = 10.0) -> None:
        self.match_tolerance = float(match_tolerance)
        self.move_tolerance = float(move_tolerance)
        self.matcher = SemanticEntityMatcher(match_tolerance=match_tolerance)

    def compare(
        self,
        current_model: dict[str, Any],
        reference_model: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        result = empty_diff_result()
        current_pipes = pipe_entities(current_model)
        reference_pipes = pipe_entities(reference_model)
        used_current_handles: set[str] = set()

        for reference in reference_pipes:
            match = self.matcher.find_best_match(reference, current_pipes, used_current_handles)
            if match is None:
                result["add_pipe"].append(self._add_pipe(reference))
                continue

            used_current_handles.add(entity_handle(match.current))
            self._append_matched_pipe_diffs(result, match)

        for current in current_pipes:
            if entity_handle(current) not in used_current_handles:
                result["remove_pipe"].append(self._remove_pipe(current))

        return result

    def _append_matched_pipe_diffs(
        self,
        result: dict[str, list[dict[str, Any]]],
        match: SemanticMatch,
    ) -> None:
        current = match.current
        reference = match.reference

        current_diameter = normalized_diameter(current)
        reference_diameter = normalized_diameter(reference)
        if current_diameter != reference_diameter:
            mismatch = {
                "pipe_handle": entity_handle(current),
                "reference_pipe_handle": entity_handle(reference),
                "current": current_diameter,
                "reference": reference_diameter,
                "severity": "high",
            }
            result["diameter_mismatch"].append(mismatch)
            result["modify_pipe"].append(
                self._modify_pipe(match, "diameter_mismatch", {"diameter": mismatch})
            )

        current_system = current.get("system_type")
        reference_system = reference.get("system_type")
        if current_system != reference_system:
            mismatch = {
                "pipe_handle": entity_handle(current),
                "reference_pipe_handle": entity_handle(reference),
                "current": current_system,
                "reference": reference_system,
                "severity": "high",
            }
            result["system_mismatch"].append(mismatch)
            result["modify_pipe"].append(
                self._modify_pipe(match, "system_mismatch", {"system_type": mismatch})
            )

        if match.distance > self.move_tolerance:
            result["move_pipe"].append(
                {
                    "pipe_handle": entity_handle(current),
                    "reference_pipe_handle": entity_handle(reference),
                    "distance": match.distance,
                    "current_geometry": current.get("inferred_geometry") or current.get("geometry"),
                    "reference_geometry": reference.get("inferred_geometry") or reference.get("geometry"),
                    "severity": "medium",
                }
            )

    def _add_pipe(self, reference: dict[str, Any]) -> dict[str, Any]:
        return {
            "pipe_handle": entity_handle(reference),
            "reference_diameter": normalized_diameter(reference),
            "reference_system_type": reference.get("system_type"),
            "reference_layer": reference.get("layer"),
            "reference_geometry": reference.get("inferred_geometry") or reference.get("geometry"),
            "severity": "medium",
            "reason": "reference_has_pipe_current_missing",
            "automatic_execution_allowed": False,
        }

    def _remove_pipe(self, current: dict[str, Any]) -> dict[str, Any]:
        return {
            "pipe_handle": entity_handle(current),
            "current_diameter": normalized_diameter(current),
            "current_system_type": current.get("system_type"),
            "current_layer": current.get("layer"),
            "current_geometry": current.get("inferred_geometry") or current.get("geometry"),
            "severity": "medium",
            "reason": "current_has_pipe_reference_missing",
            "automatic_execution_allowed": False,
        }

    def _modify_pipe(
        self,
        match: SemanticMatch,
        change_type: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "pipe_handle": entity_handle(match.current),
            "reference_pipe_handle": entity_handle(match.reference),
            "change_type": change_type,
            "changes": changes,
            "severity": "high",
            "automatic_execution_allowed": False,
        }
