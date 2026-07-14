from __future__ import annotations

from copy import deepcopy
from typing import Any

from coordinate.calibration import CalibrationSet
from coordinate.models import CoordinateSystem, Point2D


class ExecutionPlanCoordinateMapper:
    def __init__(self, calibration: CalibrationSet | None) -> None:
        self.calibration = calibration

    def map_execution_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        if self.calibration is None:
            return {
                "success": False,
                "message": "Coordinate mapping is not calibrated.",
            }
        transform = self.calibration.build_transform()
        mapped_plan = deepcopy(plan)
        mapped_plan["coordinate_mapping"] = {
            "calibration_id": self.calibration.id,
            "transform_type": transform.transform_type,
            "mapping_confidence": transform.mapping_confidence,
        }
        mapped_plan["success"] = True

        high_risk = mapped_plan.get("risk_level") == "high"
        for operation in mapped_plan.get("operations", []):
            geometry = operation.get("geometry", {})
            source_system = geometry.get("coordinate_system")
            if source_system == CoordinateSystem.CAD_WORLD.value or not source_system:
                continue

            original_geometry = deepcopy(geometry)
            mapped_geometry = self._map_geometry(geometry, transform)
            mapped_geometry["original_coordinate_system"] = source_system
            mapped_geometry["original_geometry"] = original_geometry
            mapped_geometry["coordinate_system"] = CoordinateSystem.CAD_WORLD.value
            operation["geometry"] = mapped_geometry
            operation["mapping_confidence"] = transform.mapping_confidence
            operation["calibration_id"] = self.calibration.id
            operation["transform_type"] = transform.transform_type

            warnings = self._bounds_warnings(mapped_geometry)
            if warnings:
                operation["mapping_warnings"] = warnings
                operation["risk_level"] = "high"
                high_risk = True

        if high_risk:
            mapped_plan["risk_level"] = "high"
        return mapped_plan

    def _map_geometry(self, geometry: dict[str, Any], transform: Any) -> dict[str, Any]:
        mapped = deepcopy(geometry)
        if "start" in geometry and "end" in geometry:
            mapped["start"] = self._map_point(geometry["start"], transform)
            mapped["end"] = self._map_point(geometry["end"], transform)
        if "points" in geometry:
            mapped["points"] = [self._map_point(point, transform) for point in geometry.get("points", [])]
        if "position" in geometry:
            mapped["position"] = self._map_point(geometry["position"], transform)
        if "bounding_box" in geometry:
            box = geometry["bounding_box"]
            mapped["points"] = [self._map_point(point, transform) for point in self._box_points(box)]
            mapped.pop("bounding_box", None)
        if "from" in geometry and isinstance(geometry["from"], dict):
            mapped["from_points"] = [
                self._map_point(point, transform)
                for point in self._box_points(geometry["from"])
            ]
        if "to" in geometry and isinstance(geometry["to"], dict):
            mapped["to_points"] = [
                self._map_point(point, transform)
                for point in self._box_points(geometry["to"])
            ]
        return mapped

    def _map_point(self, point: list[float] | dict[str, Any], transform: Any) -> list[float]:
        if isinstance(point, dict):
            x = float(point.get("x", 0.0))
            y = float(point.get("y", 0.0))
        else:
            x = float(point[0])
            y = float(point[1])
        result = transform.map_point(Point2D(x, y, transform.source_system))
        return result.mapped.to_list()

    def _bounds_warnings(self, geometry: dict[str, Any]) -> list[str]:
        bounds = self.calibration.reasonable_cad_bounds if self.calibration else None
        if not bounds:
            return []
        points: list[list[float]] = []
        for key in ("start", "end", "position"):
            if key in geometry:
                points.append(geometry[key])
        points.extend(geometry.get("points", []))
        for point in points:
            x, y = point[0], point[1]
            if (
                x < bounds["x_min"]
                or x > bounds["x_max"]
                or y < bounds["y_min"]
                or y > bounds["y_max"]
            ):
                return ["mapped coordinate is outside reasonable CAD bounds"]
        return []

    def _box_points(self, box: dict[str, Any]) -> list[list[float]]:
        return [
            [box["x_min"], box["y_min"], 0.0],
            [box["x_max"], box["y_min"], 0.0],
            [box["x_max"], box["y_max"], 0.0],
            [box["x_min"], box["y_max"], 0.0],
        ]
