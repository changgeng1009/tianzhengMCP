from __future__ import annotations

from typing import Any

from cad.connection import default_manager
from cad.entities import EntityService
from execution.models import Operation, OperationType


class CADOperationExecutor:
    """只执行 Phase 4 允许的基础 CAD 增量对象。"""

    def __init__(self, entity_service: EntityService | None = None) -> None:
        self.entity_service = entity_service or EntityService(default_manager)

    def execute(self, operation: Operation) -> dict[str, Any]:
        if operation.action == OperationType.ADD_LINE:
            start = operation.geometry["start"]
            end = operation.geometry["end"]
            return self.entity_service.draw_line(start[0], start[1], end[0], end[1])

        if operation.action == OperationType.ADD_POLYLINE:
            return self.entity_service.draw_polyline(operation.geometry.get("points", []))

        if operation.action == OperationType.ADD_TEXT:
            position = operation.geometry.get("position", [0.0, 0.0, 0.0])
            return self.entity_service.add_text(
                operation.geometry.get("text", ""),
                position[0],
                position[1],
                operation.geometry.get("height", 250.0),
            )

        return {
            "success": False,
            "status": "not_implemented",
            "message": f"{operation.action.value} is planned but not executable in Phase 4 MVP.",
        }
