from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float

    def to_dict(self) -> dict[str, float]:
        return {"x": float(self.x), "y": float(self.y)}


@dataclass(frozen=True)
class BBox2D:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def to_dict(self) -> dict[str, float]:
        return {
            "min_x": float(self.min_x),
            "min_y": float(self.min_y),
            "max_x": float(self.max_x),
            "max_y": float(self.max_y),
        }


@dataclass(frozen=True)
class AnchorPoint:
    anchor_id: str
    source: str
    point: Point2D
    element_id: str
    element_type: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "source": self.source,
            "point": self.point.to_dict(),
            "element_id": self.element_id,
            "element_type": self.element_type,
            "confidence": float(self.confidence),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AnchorPair:
    reference_anchor: AnchorPoint
    target_anchor: AnchorPoint
    confidence: float
    reason: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_anchor": self.reference_anchor.to_dict(),
            "target_anchor": self.target_anchor.to_dict(),
            "confidence": float(self.confidence),
            "reason": list(self.reason),
        }


@dataclass(frozen=True)
class Transform2D:
    transform_type: str
    matrix: list[list[float]]
    confidence: float
    residual_error: float | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transform_type": self.transform_type,
            "matrix": [list(row) for row in self.matrix],
            "confidence": float(self.confidence),
            "residual_error": self.residual_error,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SpatialAlignmentResult:
    reference_graph_id: str
    target_graph_id: str
    transform: Transform2D
    aligned_reference_graph: dict[str, Any]
    anchor_pairs: list[AnchorPair]
    confidence: float
    warnings: list[str]
    errors: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_graph_id": self.reference_graph_id,
            "target_graph_id": self.target_graph_id,
            "transform": self.transform.to_dict(),
            "aligned_reference_graph": self.aligned_reference_graph,
            "anchor_pairs": [pair.to_dict() for pair in self.anchor_pairs],
            "confidence": float(self.confidence),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }

