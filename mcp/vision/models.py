from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VisionElement:
    element_id: str
    element_type: str
    bbox: list[float]
    points: list[list[float]]
    text: str | None
    confidence: float
    source: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.element_id:
            raise ValueError("element_id is required")
        if not self.element_type:
            raise ValueError("element_type is required")
        _validate_confidence(self.confidence)
        object.__setattr__(self, "bbox", [float(value) for value in self.bbox])
        object.__setattr__(
            self,
            "points",
            [[float(coord) for coord in point] for point in self.points],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: dict[str, Any] | None = None) -> "VisionElement":
        return cls(
            element_id=str(data.get("element_id") or data.get("id") or ""),
            element_type=str(data.get("element_type") or data.get("type") or ""),
            bbox=list(data.get("bbox", [])),
            points=[list(point) for point in data.get("points", [])],
            text=data.get("text"),
            confidence=float(data.get("confidence", 0.0)),
            source=dict(data.get("source") or source or {}),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "element_type": self.element_type,
            "bbox": list(self.bbox),
            "points": [list(point) for point in self.points],
            "text": self.text,
            "confidence": self.confidence,
            "source": dict(self.source),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SemanticGraph:
    buildings: list[dict[str, Any]]
    pipes: list[dict[str, Any]]
    valves: list[dict[str, Any]]
    sprinklers: list[dict[str, Any]]
    texts: list[dict[str, Any]] = field(default_factory=list)
    symbols: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "buildings": [dict(item) for item in self.buildings],
            "pipes": [dict(item) for item in self.pipes],
            "valves": [dict(item) for item in self.valves],
            "sprinklers": [dict(item) for item in self.sprinklers],
            "texts": [dict(item) for item in self.texts],
            "symbols": [dict(item) for item in self.symbols],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class VisionParseResult:
    source_path: str
    source_type: str
    page_index: int
    elements: list[VisionElement]
    warnings: list[str]
    confidence: float
    semantic_graph: SemanticGraph

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)
        elements = [
            element if isinstance(element, VisionElement) else VisionElement.from_dict(element)
            for element in self.elements
        ]
        object.__setattr__(self, "elements", elements)
        if not isinstance(self.semantic_graph, SemanticGraph):
            object.__setattr__(self, "semantic_graph", SemanticGraph(**self.semantic_graph))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_type": self.source_type,
            "page_index": self.page_index,
            "elements": [element.to_dict() for element in self.elements],
            "warnings": list(self.warnings),
            "confidence": self.confidence,
            "semantic_graph": self.semantic_graph.to_dict(),
        }


def _validate_confidence(value: float) -> None:
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

