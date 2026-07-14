from __future__ import annotations

import math
from dataclasses import dataclass

from coordinate.models import CoordinateSystem, MappingResult, Point2D, Point3D, coerce_system


@dataclass(frozen=True)
class CoordinateTransform:
    source_system: CoordinateSystem
    target_system: CoordinateSystem
    transform_type: str
    matrix: tuple[tuple[float, float, float], tuple[float, float, float]]
    calibration_id: str
    mapping_confidence: float = 0.95
    image_width: float | None = None
    image_height: float | None = None

    @classmethod
    def similarity(
        cls,
        source_system: CoordinateSystem | str,
        scale: float,
        rotation_degrees: float,
        translate: tuple[float, float],
        calibration_id: str,
        mapping_confidence: float = 0.95,
    ) -> "CoordinateTransform":
        radians = math.radians(rotation_degrees)
        cos_value = math.cos(radians)
        sin_value = math.sin(radians)
        return cls(
            source_system=coerce_system(source_system),
            target_system=CoordinateSystem.CAD_WORLD,
            transform_type="similarity",
            matrix=(
                (scale * cos_value, -scale * sin_value, float(translate[0])),
                (scale * sin_value, scale * cos_value, float(translate[1])),
            ),
            calibration_id=calibration_id,
            mapping_confidence=mapping_confidence,
        )

    @classmethod
    def affine(
        cls,
        source_system: CoordinateSystem | str,
        matrix: tuple[tuple[float, float, float], tuple[float, float, float]],
        calibration_id: str,
        mapping_confidence: float = 0.98,
    ) -> "CoordinateTransform":
        return cls(
            source_system=coerce_system(source_system),
            target_system=CoordinateSystem.CAD_WORLD,
            transform_type="affine",
            matrix=matrix,
            calibration_id=calibration_id,
            mapping_confidence=mapping_confidence,
        )

    @classmethod
    def image_to_normalized(
        cls,
        image_width: float,
        image_height: float,
        calibration_id: str,
    ) -> "CoordinateTransform":
        return cls(
            source_system=CoordinateSystem.IMAGE_PIXEL,
            target_system=CoordinateSystem.NORMALIZED,
            transform_type="image_to_normalized",
            matrix=((1.0 / float(image_width), 0.0, 0.0), (0.0, 1.0 / float(image_height), 0.0)),
            calibration_id=calibration_id,
            mapping_confidence=1.0,
            image_width=float(image_width),
            image_height=float(image_height),
        )

    def map_point(self, point: Point2D) -> MappingResult:
        if point.coordinate_system != self.source_system:
            raise ValueError(
                f"point coordinate system {point.coordinate_system.value} does not match transform source {self.source_system.value}"
            )
        x, y, z = self.map_xy(point.x, point.y)
        mapped_system = self.target_system
        mapped = Point3D(x, y, z, mapped_system)
        return MappingResult(
            original=point,
            mapped=mapped,
            mapping_confidence=self.mapping_confidence,
            calibration_id=self.calibration_id,
            transform_type=self.transform_type,
        )

    def map_xy(self, x: float, y: float) -> list[float]:
        a, b, c = self.matrix[0]
        d, e, f = self.matrix[1]
        return [
            round(a * float(x) + b * float(y) + c, 10),
            round(d * float(x) + e * float(y) + f, 10),
            0.0,
        ]

    def inverse_map_point(self, x: float, y: float) -> Point2D:
        a, b, c = self.matrix[0]
        d, e, f = self.matrix[1]
        determinant = a * e - b * d
        if abs(determinant) < 1e-12:
            raise ValueError("transform matrix is not invertible")
        dx = float(x) - c
        dy = float(y) - f
        source_x = (e * dx - b * dy) / determinant
        source_y = (-d * dx + a * dy) / determinant
        return Point2D(round(source_x, 10), round(source_y, 10), self.source_system)
