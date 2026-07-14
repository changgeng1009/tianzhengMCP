from __future__ import annotations

from typing import Any
from uuid import uuid4

from execution.models import ExecutionPlan, Operation, OperationType, RiskLevel


class ExecutionPlanner:
    """把 DiffResult 字典转换成安全执行计划。"""

    def build_plan(self, diff_result: dict[str, Any], plan_id: str | None = None) -> ExecutionPlan:
        operations = [
            self._operation_from_diff(index, item)
            for index, item in enumerate(diff_result.get("items", []), start=1)
        ]
        return ExecutionPlan(id=plan_id or f"plan_{uuid4().hex}", operations=operations)

    def _operation_from_diff(self, index: int, item: dict[str, Any]) -> Operation:
        diff_operation = item["operation"]
        if diff_operation == "add":
            action, geometry = self._add_action_and_geometry(item)
            risk = RiskLevel.LOW
        elif diff_operation == "move":
            action = OperationType.MOVE_ENTITY
            geometry = dict(item.get("changes", {}))
            risk = RiskLevel.MEDIUM
        elif diff_operation == "modify":
            action = OperationType.MODIFY_ENTITY
            geometry = dict(item.get("changes", {}))
            risk = RiskLevel.MEDIUM
        elif diff_operation == "delete_suggestion":
            action = OperationType.DELETE_SUGGESTION
            geometry = self._entity_geometry(item)
            risk = RiskLevel.HIGH
        else:
            raise ValueError(f"unsupported diff operation: {diff_operation}")

        return Operation(
            id=f"op_{index:04d}",
            action=action,
            entity_type=item.get("entity_type") or item.get("entity", {}).get("type", "unknown"),
            geometry=geometry,
            layer=self._layer(item),
            reason=item.get("reason", ""),
            source_diff_id=self._source_diff_id(index, item),
            risk_level=risk,
            requires_confirmation=True,
        )

    def _add_action_and_geometry(self, item: dict[str, Any]) -> tuple[OperationType, dict[str, Any]]:
        entity = item.get("entity") or {}
        properties = entity.get("properties") or {}
        geometry = entity.get("geometry") or {}
        entity_type = item.get("entity_type") or entity.get("type")
        points = geometry.get("points") or []

        if entity_type in {"text", "annotation", "dimension"} or properties.get("text"):
            return OperationType.ADD_TEXT, {
                "coordinate_system": geometry.get("coordinate_system", "cad_world"),
                "text": str(properties.get("text") or properties.get("dimension") or entity.get("id", "")),
                "position": self._point_to_xyz(points[0]) if points else [0.0, 0.0, 0.0],
                "height": float(properties.get("height", 250.0)),
            }

        if len(points) == 2:
            return OperationType.ADD_LINE, {
                "coordinate_system": geometry.get("coordinate_system", "cad_world"),
                "start": self._point_to_xyz(points[0]),
                "end": self._point_to_xyz(points[1]),
            }

        if len(points) > 2:
            return OperationType.ADD_POLYLINE, {
                "coordinate_system": geometry.get("coordinate_system", "cad_world"),
                "points": [self._point_to_xyz(point) for point in points],
            }

        bounding_box = geometry.get("bounding_box")
        if bounding_box:
            return OperationType.ADD_POLYLINE, {
                "coordinate_system": bounding_box.get("coordinate_system", geometry.get("coordinate_system", "cad_world")),
                "points": self._rectangle_points(bounding_box),
            }

        return OperationType.ADD_POLYLINE, {
            "coordinate_system": geometry.get("coordinate_system", "cad_world"),
            "points": [],
        }

    def _entity_geometry(self, item: dict[str, Any]) -> dict[str, Any]:
        entity = item.get("entity") or {}
        return dict(entity.get("geometry") or {})

    def _layer(self, item: dict[str, Any]) -> str:
        entity = item.get("entity") or {}
        properties = entity.get("properties") or {}
        return str(properties.get("layer") or properties.get("layer_hint") or "0")

    def _source_diff_id(self, index: int, item: dict[str, Any]) -> str:
        for key in ("source_diff_id", "reference_entity_id", "current_entity_id"):
            if item.get(key):
                return str(item[key])
        return f"diff_{index:04d}"

    def _point_to_xyz(self, point: dict[str, Any] | list[float]) -> list[float]:
        if isinstance(point, list):
            values = [float(value) for value in point]
            return values + [0.0] * (3 - len(values))
        return [
            float(point.get("x", 0.0)),
            float(point.get("y", 0.0)),
            float(point.get("z", 0.0)),
        ]

    def _rectangle_points(self, bounding_box: dict[str, Any]) -> list[list[float]]:
        x_min = float(bounding_box["x_min"])
        y_min = float(bounding_box["y_min"])
        x_max = float(bounding_box["x_max"])
        y_max = float(bounding_box["y_max"])
        return [
            [x_min, y_min, 0.0],
            [x_max, y_min, 0.0],
            [x_max, y_max, 0.0],
            [x_min, y_max, 0.0],
            [x_min, y_min, 0.0],
        ]
