from __future__ import annotations


def test_cv_provider_parse_png_missing_file_returns_failed_result() -> None:
    from mcp.vision.cv_provider import CVVisionProvider

    result = CVVisionProvider().parse_png("missing.png")

    assert result.confidence == 0.0
    assert result.semantic_graph.metadata["status"] == "failed"
    assert any("image file not found" in warning for warning in result.warnings)


def test_cv_provider_open_cv_missing_with_fixture_still_returns_warning(monkeypatch) -> None:
    from mcp.vision import cv_provider
    from mcp.vision.cv_provider import CVVisionProvider

    monkeypatch.setattr(cv_provider, "is_opencv_available", lambda: False)

    result = CVVisionProvider().parse_png(
        "fixture.png",
        metadata={
            "fixture_elements": [
                {
                    "element_id": "pipe_fixture",
                    "element_type": "pipe_candidate",
                    "bbox": [0, 0, 100, 10],
                    "points": [[0, 5], [100, 5]],
                    "confidence": 0.73,
                    "metadata": {"dn": 50, "system_type": "给水"},
                }
            ],
            "allow_missing_fixture": True,
        },
    )

    data = result.to_dict()

    assert data["semantic_graph"]["pipes"][0]["source_element_id"] == "pipe_fixture"
    assert data["semantic_graph"]["metadata"]["provider"] == "CVVisionProvider"
    assert data["semantic_graph"]["metadata"]["coordinate_space"] == "normalized_image"
    assert any("OpenCV not available" in warning for warning in data["warnings"])

