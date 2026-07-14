from __future__ import annotations


def test_confidence_helpers_clamp_combine_and_classify() -> None:
    from mcp.vision.confidence import (
        clamp_confidence,
        classify_confidence,
        combine_confidences,
    )

    assert clamp_confidence(-1.0) == 0.0
    assert clamp_confidence(1.5) == 1.0
    assert combine_confidences([0.6, 0.8]) == 0.7
    assert combine_confidences([], method="mean") == 0.0
    assert classify_confidence(0.85) == "high"
    assert classify_confidence(0.6) == "medium"
    assert classify_confidence(0.59) == "low"

