from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from execution.models import ExecutionPlan, Operation, OperationType, RiskLevel


MAPPING_REQUIRED_MESSAGE = "Coordinate mapping is not calibrated."
HIGH_RISK_CONFIRMATION_MESSAGE = (
    "Mapped execution plan contains high risk coordinates outside configured bounds."
)
DEFAULT_CAD_WORLD_BOUNDS = {
    "min_x": -100000.0,
    "max_x": 100000.0,
    "min_y": -100000.0,
    "max_y": 100000.0,
}


def validate_mapped_execution_plan(
    plan: ExecutionPlan,
    cad_world_bounds: dict[str, float] | None = None,
    allow_high_risk: bool = False,
) -> dict[str, Any]:
    bounds = cad_world_bounds or DEFAULT_CAD_WORLD_BOUNDS
    issues: list[dict[str, Any]] = []
    high_risk_operations: list[str] = []

    for operation in plan.operations:
        if not operation.executable:
            continue

        metadata_issue = _mapping_metadata_issue(operation)
        if metadata_issue:
            issues.append(metadata_issue)
            continue

        geometry = operation.geometry or {}
        if geometry.get("coordinate_system") != "cad_world":
            issues.append(
                {
                    "operation_id": operation.id,
                    "type": "coordinate_system",
                    "message": MAPPING_REQUIRED_MESSAGE,
                }
            )
            continue

        geometry_issue = _required_geometry_issue(operation, geometry)
        if geometry_issue:
            issues.append(geometry_issue)
            continue

        out_of_bounds_points = [
            point for point in _iter_geometry_points(geometry) if not _point_within_bounds(point, bounds)
        ]
        if out_of_bounds_points:
            operation.risk_level = RiskLevel.HIGH
            high_risk_operations.append(operation.id)
            issues.append(
                {
                    "operation_id": operation.id,
                    "type": "cad_world_bounds",
                    "message": HIGH_RISK_CONFIRMATION_MESSAGE,
                    "points": out_of_bounds_points,
                }
            )

    mapping_issues = [issue for issue in issues if issue["message"] == MAPPING_REQUIRED_MESSAGE]
    if mapping_issues:
        return {
            "valid": False,
            "message": MAPPING_REQUIRED_MESSAGE,
            "issues": issues,
            "requires_extra_confirmation": False,
        }

    if high_risk_operations and not allow_high_risk:
        plan.risk_level = RiskLevel.HIGH
        return {
            "valid": False,
            "message": HIGH_RISK_CONFIRMATION_MESSAGE,
            "issues": issues,
            "requires_extra_confirmation": True,
            "high_risk_operations": high_risk_operations,
        }

    if high_risk_operations:
        plan.risk_level = RiskLevel.HIGH

    return {
        "valid": True,
        "message": "OK",
        "issues": issues,
        "requires_extra_confirmation": bool(high_risk_operations),
        "high_risk_operations": high_risk_operations,
    }


def _mapping_metadata_issue(operation: Operation) -> dict[str, Any] | None:
    if operation.mapping_confidence is None:
        return {
            "operation_id": operation.id,
            "type": "mapping_confidence",
            "message": MAPPING_REQUIRED_MESSAGE,
        }
    if not operation.calibration_id:
        return {
            "operation_id": operation.id,
            "type": "calibration_id",
            "message": MAPPING_REQUIRED_MESSAGE,
        }
    if not operation.transform_type:
        return {
            "operation_id": operation.id,
            "type": "transform_type",
            "message": MAPPING_REQUIRED_MESSAGE,
        }
    return None


def _required_geometry_issue(operation: Operation, geometry: dict[str, Any]) -> dict[str, Any] | None:
    if operation.action == OperationType.ADD_LINE:
        if not _is_point(geometry.get("start")) or not _is_point(geometry.get("end")):
            return {
                "operation_id": operation.id,
                "type": "geometry",
                "message": MAPPING_REQUIRED_MESSAGE,
            }
    if operation.action == OperationType.ADD_POLYLINE:
        points = geometry.get("points") or []
        if not points or any(not _is_point(point) for point in points):
            return {
                "operation_id": operation.id,
                "type": "geometry",
                "message": MAPPING_REQUIRED_MESSAGE,
            }
    if operation.action == OperationType.ADD_TEXT:
        if not _is_point(geometry.get("position")):
            return {
                "operation_id": operation.id,
                "type": "geometry",
                "message": MAPPING_REQUIRED_MESSAGE,
            }
    return None


def _iter_geometry_points(geometry: dict[str, Any]) -> Iterable[list[float]]:
    for key in ("start", "end", "position"):
        point = geometry.get(key)
        if _is_point(point):
            yield [float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0]

    for point in geometry.get("points", []) or []:
        if _is_point(point):
            yield [float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0]


def _is_point(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 2


def _point_within_bounds(point: list[float], bounds: dict[str, float]) -> bool:
    x, y = point[0], point[1]
    return (
        bounds["min_x"] <= x <= bounds["max_x"]
        and bounds["min_y"] <= y <= bounds["max_y"]
    )
