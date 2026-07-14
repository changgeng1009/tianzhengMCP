from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoordinateMapper:
    image_width: float
    image_height: float
    cad_origin: list[float] | None = None
    cad_scale: float | None = None
    rotation: float = 0.0
    scale_status: str = "unknown"

    def image_to_normalized(self, point: list[float] | tuple[float, ...]) -> list[float]:
        return [
            round(float(point[0]) / self.image_width, 6) if self.image_width else 0.0,
            round(float(point[1]) / self.image_height, 6) if self.image_height else 0.0,
        ]

    def normalized_to_image(self, point: list[float] | tuple[float, ...]) -> list[float]:
        return [
            round(float(point[0]) * self.image_width, 6),
            round(float(point[1]) * self.image_height, 6),
        ]

    def image_bbox_to_normalized(self, bbox: list[float] | tuple[float, ...]) -> list[float]:
        return self.image_to_normalized([bbox[0], bbox[1]]) + self.image_to_normalized([bbox[2], bbox[3]])

    def metadata(self) -> dict:
        return {
            "coordinate_space": "normalized_image",
            "image_size": [int(self.image_width), int(self.image_height)],
            "scale_status": self.scale_status,
        }

