from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from coordinate.models import CalibrationPoint, CoordinateSystem, coerce_system
from coordinate.transform import CoordinateTransform


@dataclass(frozen=True)
class CalibrationSet:
    id: str
    source_system: CoordinateSystem
    points: list[CalibrationPoint]
    reasonable_cad_bounds: dict[str, float] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalibrationSet":
        source_system = coerce_system(data.get("source_system", CoordinateSystem.NORMALIZED))
        return cls(
            id=data["id"],
            source_system=source_system,
            points=[
                CalibrationPoint.from_dict(point, source_system)
                for point in data.get("points", [])
            ],
            reasonable_cad_bounds=data.get("reasonable_cad_bounds"),
        )

    def build_transform(self) -> CoordinateTransform:
        if len(self.points) < 2:
            raise ValueError("coordinate calibration requires at least 2 points")
        if len(self.points) >= 3:
            return self._build_affine()
        return self._build_similarity()

    def _build_similarity(self) -> CoordinateTransform:
        first, second = self.points[0], self.points[1]
        sx = second.reference_point.x - first.reference_point.x
        sy = second.reference_point.y - first.reference_point.y
        tx = second.cad_world_point.x - first.cad_world_point.x
        ty = second.cad_world_point.y - first.cad_world_point.y
        source_distance = math.hypot(sx, sy)
        target_distance = math.hypot(tx, ty)
        if source_distance <= 1e-12:
            raise ValueError("calibration source points must not overlap")
        scale = target_distance / source_distance
        rotation = math.degrees(math.atan2(ty, tx) - math.atan2(sy, sx))

        radians = math.radians(rotation)
        cos_value = math.cos(radians)
        sin_value = math.sin(radians)
        mapped_x = scale * (cos_value * first.reference_point.x - sin_value * first.reference_point.y)
        mapped_y = scale * (sin_value * first.reference_point.x + cos_value * first.reference_point.y)
        translate = (
            first.cad_world_point.x - mapped_x,
            first.cad_world_point.y - mapped_y,
        )
        return CoordinateTransform.similarity(
            source_system=self.source_system,
            scale=scale,
            rotation_degrees=rotation,
            translate=translate,
            calibration_id=self.id,
            mapping_confidence=0.95,
        )

    def _build_affine(self) -> CoordinateTransform:
        p1, p2, p3 = self.points[0], self.points[1], self.points[2]
        source_matrix = (
            (p1.reference_point.x, p1.reference_point.y, 1.0),
            (p2.reference_point.x, p2.reference_point.y, 1.0),
            (p3.reference_point.x, p3.reference_point.y, 1.0),
        )
        inv = _invert_3x3(source_matrix)
        target_x = (p1.cad_world_point.x, p2.cad_world_point.x, p3.cad_world_point.x)
        target_y = (p1.cad_world_point.y, p2.cad_world_point.y, p3.cad_world_point.y)
        coeff_x = _multiply_matrix_vector(inv, target_x)
        coeff_y = _multiply_matrix_vector(inv, target_y)
        return CoordinateTransform.affine(
            source_system=self.source_system,
            matrix=(
                (coeff_x[0], coeff_x[1], coeff_x[2]),
                (coeff_y[0], coeff_y[1], coeff_y[2]),
            ),
            calibration_id=self.id,
            mapping_confidence=0.98,
        )


def _invert_3x3(matrix: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(determinant) < 1e-12:
        raise ValueError("calibration points cannot form an invertible affine transform")
    return (
        ((e * i - f * h) / determinant, (c * h - b * i) / determinant, (b * f - c * e) / determinant),
        ((f * g - d * i) / determinant, (a * i - c * g) / determinant, (c * d - a * f) / determinant),
        ((d * h - e * g) / determinant, (b * g - a * h) / determinant, (a * e - b * d) / determinant),
    )


def _multiply_matrix_vector(matrix: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]], vector: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        matrix[0][0] * vector[0] + matrix[0][1] * vector[1] + matrix[0][2] * vector[2],
        matrix[1][0] * vector[0] + matrix[1][1] * vector[1] + matrix[1][2] * vector[2],
        matrix[2][0] * vector[0] + matrix[2][1] * vector[1] + matrix[2][2] * vector[2],
    )
