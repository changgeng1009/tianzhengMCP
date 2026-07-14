from __future__ import annotations

from typing import Iterable


def clamp_confidence(value: float | int | str | None) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return round(max(0.0, min(1.0, numeric)), 4)


def combine_confidences(values: Iterable[float], method: str = "mean") -> float:
    clamped = [clamp_confidence(value) for value in values]
    if not clamped:
        return 0.0
    if method == "min":
        return min(clamped)
    if method == "max":
        return max(clamped)
    return round(sum(clamped) / len(clamped), 4)


def classify_confidence(confidence: float) -> str:
    value = clamp_confidence(confidence)
    if value >= 0.85:
        return "high"
    if value >= 0.60:
        return "medium"
    return "low"

