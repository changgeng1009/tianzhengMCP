from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CoordinateSystem(str, Enum):
    IMAGE_PIXEL = "image_pixel"
    NORMALIZED = "normalized"
    CAD_WORLD = "cad_world"


def coerce_system(value: CoordinateSystem | str) -> CoordinateSystem:
    return value if isinstance(value, CoordinateSystem) else CoordinateSystem(value)


def _validate_normalized(x: float, y: float) -> None:
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise ValueError("normalized coordinates must be between 0 and 1")


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float
    coordinate_system: CoordinateSystem | str

    def __post_init__(self) -> None:
        system = coerce_system(self.coordinate_system)
        object.__setattr__(self, "coordinate_system", system)
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        if system == CoordinateSystem.NORMALIZED:
            _validate_normalized(self.x, self.y)

    @classmethod
    def from_list(cls, values: list[float], coordinate_system: CoordinateSystem | str) -> "Point2D":
        return cls(values[0], values[1], coordinate_system)

    def to_list(self) -> list[float]:
        return [self.x, self.y]

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "coordinate_system": self.coordinate_system.value,
        }


@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float
    coordinate_system: CoordinateSystem | str

    def __post_init__(self) -> None:
        system = coerce_system(self.coordinate_system)
        object.__setattr__(self, "coordinate_system", system)
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "z", float(self.z))

    @classmethod
    def from_list(cls, values: list[float], coordinate_system: CoordinateSystem | str) -> "Point3D":
        padded = [float(value) for value in values] + [0.0] * (3 - len(values))
        return cls(padded[0], padded[1], padded[2], coordinate_system)

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z]

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "coordinate_system": self.coordinate_system.value,
        }


@dataclass(frozen=True)
class BoundingBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    coordinate_system: CoordinateSystem | str

    def __post_init__(self) -> None:
        system = coerce_system(self.coordinate_system)
        object.__setattr__(self, "coordinate_system", system)
        if self.x_min > self.x_max or self.y_min > self.y_max:
            raise ValueError("bounding box min values must not exceed max values")
        if system == CoordinateSystem.NORMALIZED:
            _validate_normalized(float(self.x_min), float(self.y_min))
            _validate_normalized(float(self.x_max), float(self.y_max))

    def to_points(self) -> list[Point2D]:
        return [
            Point2D(self.x_min, self.y_min, self.coordinate_system),
            Point2D(self.x_max, self.y_min, self.coordinate_system),
            Point2D(self.x_max, self.y_max, self.coordinate_system),
            Point2D(self.x_min, self.y_max, self.coordinate_system),
        ]


@dataclass(frozen=True)
class CalibrationPoint:
    reference_point: Point2D
    cad_world_point: Point3D

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        source_system: CoordinateSystem | str,
    ) -> "CalibrationPoint":
        return cls(
            reference_point=Point2D.from_list(data["reference_point"], source_system),
            cad_world_point=Point3D.from_list(data["cad_world_point"], CoordinateSystem.CAD_WORLD),
        )


@dataclass(frozen=True)
class MappingResult:
    original: Point2D
    mapped: Point3D
    mapping_confidence: float
    calibration_id: str
    transform_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original.to_dict(),
            "mapped": self.mapped.to_dict(),
            "mapping_confidence": self.mapping_confidence,
            "calibration_id": self.calibration_id,
            "transform_type": self.transform_type,
        }
