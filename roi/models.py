from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ROIRegion:
    id: str
    name: str
    coordinate_system: str
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        if self.coordinate_system != "cad_world":
            raise ValueError("ROI coordinate_system must be cad_world")
        if float(self.min_x) >= float(self.max_x) or float(self.min_y) >= float(self.max_y):
            raise ValueError("ROI bbox is invalid: min values must be smaller than max values")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ROIRegion":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            coordinate_system=str(data.get("coordinate_system", "cad_world")),
            min_x=float(data["min_x"]),
            min_y=float(data["min_y"]),
            max_x=float(data["max_x"]),
            max_y=float(data["max_y"]),
        )

    def contains_point(self, x: float, y: float) -> bool:
        return self.min_x <= float(x) <= self.max_x and self.min_y <= float(y) <= self.max_y

    def intersects_bbox(self, bbox: dict[str, Any]) -> bool:
        return not (
            float(bbox["x_max"]) < self.min_x
            or float(bbox["x_min"]) > self.max_x
            or float(bbox["y_max"]) < self.min_y
            or float(bbox["y_min"]) > self.max_y
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "coordinate_system": self.coordinate_system,
            "min_x": float(self.min_x),
            "min_y": float(self.min_y),
            "max_x": float(self.max_x),
            "max_y": float(self.max_y),
        }
