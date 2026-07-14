from __future__ import annotations

from typing import Any

from cad_compare.matcher import EntityMatcher
from cad_compare.similarity import entity_text, max_point_distance, points
from execution.models import OperationStatus
from execution.planner import ExecutionPlanner
from reference.filters import ReferenceEntityFilter


class CADToCADDiffEngine:
    def __init__(
        self,
        tolerance: float = 1.0,
        reference_filter: ReferenceEntityFilter | None = None,
    ) -> None:
        self.matcher = EntityMatcher(tolerance=tolerance)
        self.tolerance = float(tolerance)
        self.reference_filter = reference_filter or ReferenceEntityFilter()

    def compare(self, reference_model: dict[str, Any], current_model: dict[str, Any]) -> dict[str, Any]:
        reference_entities = self.reference_filter.filter_entities(
            list(reference_model.get("entities", []))
        )
        current_entities = list(current_model.get("entities", []))
        used_current: set[str] = set()
        items: list[dict[str, Any]] = []

        for reference in reference_entities:
            match = self._find_match(reference, current_entities, used_current)
            if match is None:
                items.append(self._add_item(reference))
                continue

            used_current.add(str(match.get("id")))
            if self._has_property_changes(reference, match):
                items.append(self._modify_item(reference, match))
                continue
            if self._is_moved(reference, match):
                items.append(self._move_item(reference, match))

        for current in current_entities:
            if str(current.get("id")) not in used_current:
                items.append(self._delete_suggestion_item(current))

        return {"summary": self._summary(items), "items": items}

    def build_execution_plan_preview(self, diff_result: dict[str, Any]) -> dict[str, Any]:
        plan = ExecutionPlanner().build_plan(diff_result)
        plan.previewed = True
        for operation in plan.operations:
            operation.status = OperationStatus.PREVIEWED
        return plan.to_dict()

    def _find_match(
        self,
        reference: dict[str, Any],
        current_entities: list[dict[str, Any]],
        used_current: set[str],
    ) -> dict[str, Any] | None:
        for current in current_entities:
            if str(current.get("id")) in used_current:
                continue
            if self.matcher.is_match(reference, current):
                return current
        for current in current_entities:
            if str(current.get("id")) in used_current:
                continue
            if self.matcher.is_stable_match(reference, current):
                return current
        return None

    def _has_property_changes(self, reference: dict[str, Any], current: dict[str, Any]) -> bool:
        if reference.get("type") in {"text", "mtext", "dimension"}:
            return entity_text(reference) != entity_text(current)
        return False

    def _is_moved(self, reference: dict[str, Any], current: dict[str, Any]) -> bool:
        reference_points = points(reference)
        current_points = points(current)
        if not reference_points or not current_points:
            return False
        return max_point_distance(reference_points, current_points) > self.tolerance

    def _add_item(self, reference: dict[str, Any]) -> dict[str, Any]:
        entity = dict(reference)
        entity["source"] = "reference_dwg"
        return {
            "operation": "add",
            "entity_type": entity.get("type"),
            "reference_entity_id": entity.get("id"),
            "current_entity_id": None,
            "confidence": entity.get("confidence", 1.0),
            "reason": "Reference DWG contains this entity, but Current CAD has no match.",
            "entity": entity,
            "automatic_execution_allowed": True,
        }

    def _modify_item(self, reference: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation": "modify",
            "entity_type": reference.get("type"),
            "reference_entity_id": reference.get("id"),
            "current_entity_id": current.get("id"),
            "confidence": min(reference.get("confidence", 1.0), current.get("confidence", 1.0)),
            "reason": "Matched CAD entity exists, but properties differ.",
            "changes": {
                "properties": {
                    "from": {"text": entity_text(current)},
                    "to": {"text": entity_text(reference)},
                }
            },
            "automatic_execution_allowed": False,
        }

    def _move_item(self, reference: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation": "move",
            "entity_type": reference.get("type"),
            "reference_entity_id": reference.get("id"),
            "current_entity_id": current.get("id"),
            "confidence": min(reference.get("confidence", 1.0), current.get("confidence", 1.0)),
            "reason": "Matched CAD entity exists, but geometry moved beyond tolerance.",
            "changes": {
                "coordinate_system": "cad_world",
                "from": current.get("geometry", {}),
                "to": reference.get("geometry", {}),
            },
            "automatic_execution_allowed": False,
        }

    def _delete_suggestion_item(self, current: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation": "delete_suggestion",
            "entity_type": current.get("type"),
            "reference_entity_id": None,
            "current_entity_id": current.get("id"),
            "confidence": current.get("confidence", 1.0),
            "reason": "Current CAD contains this entity, but Reference DWG has no match. Suggestion only.",
            "entity": current,
            "automatic_execution_allowed": False,
        }

    def _summary(self, items: list[dict[str, Any]]) -> dict[str, int]:
        summary = {"add": 0, "modify": 0, "move": 0, "delete_suggestion": 0}
        for item in items:
            summary[item["operation"]] += 1
        return summary
