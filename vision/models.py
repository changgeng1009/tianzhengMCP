from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import hypot
from typing import Any


class CoordinateSystem(str, Enum):
    """明确区分图像坐标、归一化坐标和后续 CAD 世界坐标。"""

    IMAGE_PIXEL = "image_pixel"
    NORMALIZED = "normalized"
    CAD_WORLD = "cad_world"


class ConfidenceStatus(str, Enum):
    CONFIRMED = "Confirmed"
    NEED_USER_CONFIRMATION = "Need User Confirmation"
    UNCERTAIN = "Uncertain"


class DiffOperation(str, Enum):
    ADD = "add"
    MODIFY = "modify"
    MOVE = "move"
    DELETE_SUGGESTION = "delete_suggestion"


def _coerce_coordinate_system(value: CoordinateSystem | str) -> CoordinateSystem:
    try:
        return value if isinstance(value, CoordinateSystem) else CoordinateSystem(value)
    except ValueError as exc:
        raise ValueError(f"unsupported coordinate_system: {value}") from exc


def _coerce_status(value: ConfidenceStatus | str) -> ConfidenceStatus:
    try:
        return value if isinstance(value, ConfidenceStatus) else ConfidenceStatus(value)
    except ValueError as exc:
        raise ValueError(f"unsupported status: {value}") from exc


def _coerce_operation(value: DiffOperation | str) -> DiffOperation:
    try:
        return value if isinstance(value, DiffOperation) else DiffOperation(value)
    except ValueError as exc:
        raise ValueError(f"unsupported diff operation: {value}") from exc


def _validate_normalized_value(value: float, field_name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"normalized coordinate {field_name} must be between 0 and 1")


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float
    coordinate_system: CoordinateSystem | str

    def __post_init__(self) -> None:
        coordinate_system = _coerce_coordinate_system(self.coordinate_system)
        object.__setattr__(self, "coordinate_system", coordinate_system)
        if coordinate_system == CoordinateSystem.NORMALIZED:
            _validate_normalized_value(self.x, "x")
            _validate_normalized_value(self.y, "y")

    @classmethod
    def from_dict(cls, data: dict[str, Any], default_system: CoordinateSystem | str) -> "Point2D":
        return cls(
            x=float(data["x"]),
            y=float(data["y"]),
            coordinate_system=data.get("coordinate_system", default_system),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
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
        coordinate_system = _coerce_coordinate_system(self.coordinate_system)
        object.__setattr__(self, "coordinate_system", coordinate_system)
        if self.x_min > self.x_max or self.y_min > self.y_max:
            raise ValueError("bounding_box min values must not exceed max values")
        if coordinate_system == CoordinateSystem.NORMALIZED:
            _validate_normalized_value(self.x_min, "x_min")
            _validate_normalized_value(self.y_min, "y_min")
            _validate_normalized_value(self.x_max, "x_max")
            _validate_normalized_value(self.y_max, "y_max")

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], default_system: CoordinateSystem | str
    ) -> "BoundingBox":
        return cls(
            x_min=float(data["x_min"]),
            y_min=float(data["y_min"]),
            x_max=float(data["x_max"]),
            y_max=float(data["y_max"]),
            coordinate_system=data.get("coordinate_system", default_system),
        )

    def center(self) -> Point2D:
        return Point2D(
            x=(self.x_min + self.x_max) / 2,
            y=(self.y_min + self.y_max) / 2,
            coordinate_system=self.coordinate_system,
        )

    def distance_to(self, other: "BoundingBox") -> float:
        if self.coordinate_system != other.coordinate_system:
            raise ValueError("cannot compare bounding boxes in different coordinate systems")
        center = self.center()
        other_center = other.center()
        return hypot(center.x - other_center.x, center.y - other_center.y)

    def to_dict(self) -> dict[str, Any]:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
            "coordinate_system": self.coordinate_system.value,
        }


@dataclass(frozen=True)
class EntityGeometry:
    coordinate_system: CoordinateSystem | str
    points: list[Point2D] = field(default_factory=list)
    bounding_box: BoundingBox | None = None

    def __post_init__(self) -> None:
        coordinate_system = _coerce_coordinate_system(self.coordinate_system)
        object.__setattr__(self, "coordinate_system", coordinate_system)
        points = [
            point if isinstance(point, Point2D) else Point2D.from_dict(point, coordinate_system)
            for point in self.points
        ]
        for point in points:
            if point.coordinate_system != coordinate_system:
                raise ValueError("geometry points must use the geometry coordinate_system")
        object.__setattr__(self, "points", points)
        if self.bounding_box is not None and not isinstance(self.bounding_box, BoundingBox):
            object.__setattr__(
                self,
                "bounding_box",
                BoundingBox.from_dict(self.bounding_box, coordinate_system),
            )
        if self.bounding_box is not None and self.bounding_box.coordinate_system != coordinate_system:
            raise ValueError("geometry bounding_box must use the geometry coordinate_system")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityGeometry":
        coordinate_system = _coerce_coordinate_system(data["coordinate_system"])
        bounding_box_data = data.get("bounding_box")
        return cls(
            coordinate_system=coordinate_system,
            points=[
                Point2D.from_dict(point, coordinate_system)
                for point in data.get("points", [])
            ],
            bounding_box=(
                BoundingBox.from_dict(bounding_box_data, coordinate_system)
                if bounding_box_data
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "coordinate_system": self.coordinate_system.value,
            "points": [point.to_dict() for point in self.points],
            "bounding_box": self.bounding_box.to_dict() if self.bounding_box else None,
        }


@dataclass(frozen=True)
class VisionEntity:
    entity_id: str
    type: str
    geometry: EntityGeometry
    confidence: float
    status: ConfidenceStatus | str
    evidence: str
    uncertainties: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id is required")
        if not self.type:
            raise ValueError("entity type is required")
        if not isinstance(self.geometry, EntityGeometry):
            object.__setattr__(self, "geometry", EntityGeometry.from_dict(self.geometry))
        status = _coerce_status(self.status)
        object.__setattr__(self, "status", status)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.evidence.strip():
            raise ValueError("evidence is required")
        if (status != ConfidenceStatus.CONFIRMED or self.confidence < 0.7) and not self.uncertainties:
            raise ValueError("uncertainties are required for low-confidence entities")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisionEntity":
        return cls(
            entity_id=data.get("entity_id") or data["id"],
            type=data["type"],
            geometry=EntityGeometry.from_dict(data["geometry"]),
            confidence=float(data["confidence"]),
            status=data["status"],
            evidence=data["evidence"],
            uncertainties=list(data.get("uncertainties", [])),
            properties=dict(data.get("properties", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.entity_id,
            "type": self.type,
            "geometry": self.geometry.to_dict(),
            "confidence": self.confidence,
            "status": self.status.value,
            "evidence": self.evidence,
            "uncertainties": list(self.uncertainties),
            "properties": dict(self.properties),
        }


@dataclass(frozen=True)
class ReferenceModel:
    source: dict[str, Any]
    entities: list[VisionEntity]
    image_quality: dict[str, Any] = field(default_factory=dict)
    global_uncertainties: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReferenceModel":
        return cls(
            source=dict(data.get("source", {"kind": "image"})),
            image_quality=dict(data.get("image_quality", {})),
            global_uncertainties=list(data.get("global_uncertainties", [])),
            entities=[VisionEntity.from_dict(entity) for entity in data.get("entities", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": dict(self.source),
            "image_quality": dict(self.image_quality),
            "global_uncertainties": list(self.global_uncertainties),
            "entities": [entity.to_dict() for entity in self.entities],
        }


@dataclass(frozen=True)
class CurrentCADModel:
    source: dict[str, Any]
    entities: list[VisionEntity]
    global_uncertainties: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CurrentCADModel":
        return cls(
            source=dict(data.get("source", {"kind": "mock"})),
            global_uncertainties=list(data.get("global_uncertainties", [])),
            entities=[VisionEntity.from_dict(entity) for entity in data.get("entities", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": dict(self.source),
            "global_uncertainties": list(self.global_uncertainties),
            "entities": [entity.to_dict() for entity in self.entities],
        }


@dataclass(frozen=True)
class DiffItem:
    operation: DiffOperation | str
    entity_type: str
    confidence: float
    reason: str
    reference_entity_id: str | None = None
    current_entity_id: str | None = None
    changes: dict[str, Any] = field(default_factory=dict)
    entity: dict[str, Any] | None = None
    automatic_execution_allowed: bool = True

    def __post_init__(self) -> None:
        operation = _coerce_operation(self.operation)
        object.__setattr__(self, "operation", operation)
        if operation == DiffOperation.DELETE_SUGGESTION:
            object.__setattr__(self, "automatic_execution_allowed", False)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("diff confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "entity_type": self.entity_type,
            "reference_entity_id": self.reference_entity_id,
            "current_entity_id": self.current_entity_id,
            "confidence": self.confidence,
            "reason": self.reason,
            "changes": dict(self.changes),
            "entity": self.entity,
            "automatic_execution_allowed": self.automatic_execution_allowed,
        }


@dataclass(frozen=True)
class DiffResult:
    items: list[DiffItem]

    def summary(self) -> dict[str, int]:
        counts = {operation.value: 0 for operation in DiffOperation}
        for item in self.items:
            counts[item.operation.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "items": [item.to_dict() for item in self.items],
        }
