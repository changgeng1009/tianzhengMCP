from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VisionTemplate:
    template_id: str
    template_type: str
    name: str
    image_path: str | None = None
    bbox: list[float] = field(default_factory=list)
    keypoints: list[list[float]] = field(default_factory=list)
    expected_symbol_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence_baseline: float = 0.5
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "template_type": self.template_type,
            "name": self.name,
            "image_path": self.image_path,
            "bbox": list(self.bbox),
            "keypoints": [list(point) for point in self.keypoints],
            "expected_symbol_type": self.expected_symbol_type,
            "metadata": dict(self.metadata),
            "confidence_baseline": float(self.confidence_baseline),
            "enabled": bool(self.enabled),
        }


@dataclass
class TemplateMatch:
    match_id: str
    template_id: str
    template_type: str
    bbox: list[float]
    center: list[float]
    confidence: float
    method: str
    source_image: str
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "template_id": self.template_id,
            "template_type": self.template_type,
            "bbox": list(self.bbox),
            "center": list(self.center),
            "confidence": float(self.confidence),
            "method": self.method,
            "source_image": self.source_image,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class ClassifiedSymbol:
    symbol_id: str
    symbol_type: str
    bbox: list[float]
    center: list[float]
    confidence: float
    matched_template_id: str
    method: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "symbol_type": self.symbol_type,
            "bbox": list(self.bbox),
            "center": list(self.center),
            "confidence": float(self.confidence),
            "matched_template_id": self.matched_template_id,
            "method": self.method,
            "metadata": dict(self.metadata),
            "warnings": list(self.warnings),
        }


@dataclass
class ParsedDiameter:
    raw_text: str
    normalized: str
    value: int
    unit: str
    confidence: float
    source_text_id: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "normalized": self.normalized,
            "value": int(self.value),
            "unit": self.unit,
            "confidence": float(self.confidence),
            "source_text_id": self.source_text_id,
            "warnings": list(self.warnings),
        }


@dataclass
class ClassifiedSystem:
    raw_text: str
    system_type: str
    confidence: float
    source_text_id: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "system_type": self.system_type,
            "confidence": float(self.confidence),
            "source_text_id": self.source_text_id,
            "warnings": list(self.warnings),
        }


@dataclass
class TemplateEvaluationResult:
    sample_id: str
    detected_count: int
    expected_count: int
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    confidence_average: float
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "detected_count": int(self.detected_count),
            "expected_count": int(self.expected_count),
            "true_positive": int(self.true_positive),
            "false_positive": int(self.false_positive),
            "false_negative": int(self.false_negative),
            "precision": float(self.precision),
            "recall": float(self.recall),
            "confidence_average": float(self.confidence_average),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

