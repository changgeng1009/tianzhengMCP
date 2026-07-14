from __future__ import annotations


def test_pipe_detector_v1_uses_fixture_and_sets_metadata() -> None:
    from mcp.vision.pipe_detector_v1 import detect_pipes_v1

    image = {
        "image_path": "fixture.png",
        "metadata": {
            "source_type": "png",
            "fixture_elements": [
                {
                    "element_id": "pipe_a",
                    "element_type": "pipe_candidate",
                    "bbox": [0, 0, 100, 10],
                    "points": [[0, 5], [100, 5]],
                    "confidence": 0.78,
                    "metadata": {"dn": 50, "system_type": "给水"},
                }
            ],
        },
    }

    elements = detect_pipes_v1(image)

    assert len(elements) == 1
    element = elements[0]
    assert element.element_type == "pipe_candidate"
    assert element.confidence == 0.78
    assert element.metadata["detector"] == "pipe_detector_v1"
    assert element.metadata["length"] == 100.0
    assert element.metadata["angle"] == 0.0


def test_pipe_detector_v1_empty_image_returns_no_fake_candidates() -> None:
    from mcp.vision.pipe_detector_v1 import detect_pipes_v1

    assert detect_pipes_v1({"metadata": {}}) == []

