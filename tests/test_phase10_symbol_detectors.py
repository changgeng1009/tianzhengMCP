from __future__ import annotations


def test_sprinkler_and_valve_detectors_do_not_fake_without_template() -> None:
    from mcp.vision.sprinkler_detector_v1 import detect_sprinklers_v1
    from mcp.vision.valve_detector_v1 import detect_valves_v1

    image = {"metadata": {}}

    assert detect_sprinklers_v1(image) == []
    assert detect_valves_v1(image) == []


def test_symbol_detectors_use_fixture_metadata() -> None:
    from mcp.vision.sprinkler_detector_v1 import detect_sprinklers_v1
    from mcp.vision.valve_detector_v1 import detect_valves_v1

    image = {
        "image_path": "fixture.png",
        "metadata": {
            "source_type": "png",
            "fixture_elements": [
                {
                    "element_id": "spr_1",
                    "element_type": "sprinkler_candidate",
                    "bbox": [10, 10, 20, 20],
                    "points": [],
                    "confidence": 0.62,
                },
                {
                    "element_id": "valve_1",
                    "element_type": "valve_candidate",
                    "bbox": [30, 10, 45, 25],
                    "points": [],
                    "confidence": 0.66,
                },
            ],
        },
    }

    sprinklers = detect_sprinklers_v1(image)
    valves = detect_valves_v1(image)

    assert sprinklers[0].metadata["detector"] == "sprinkler_detector_v1"
    assert sprinklers[0].metadata["method"] == "fixture"
    assert valves[0].metadata["detector"] == "valve_detector_v1"
    assert valves[0].metadata["method"] == "fixture"

