from __future__ import annotations


def _aligned_pipe(confidence: float = 0.9) -> dict:
    return {
        "metadata": {"coordinate_space": "cad_modelspace"},
        "pipes": [
            {
                "id": "p1",
                "source_element_id": "vision_p1",
                "mapped_geometry": {"start": [0.0, 0.0, 0.0], "end": [100.0, 0.0, 0.0]},
                "mapped_confidence": confidence,
                "dn": "DN50",
                "system_type": "给水",
                "layer": "PIPE-给水",
            }
        ],
        "sprinklers": [],
        "valves": [],
    }


def test_missing_detector_finds_true_missing_pipe() -> None:
    from mcp.repair_actions.missing_detector import detect_coordinate_missing

    result = detect_coordinate_missing(_aligned_pipe(), {"pipes": []})

    assert result["true_missing"][0]["element_id"] == "p1"
    assert result["true_missing"][0]["element_type"] == "pipe"
    assert result["confidence"] > 0.8


def test_missing_detector_classifies_existing_and_low_confidence() -> None:
    from mcp.repair_actions.missing_detector import detect_coordinate_missing

    existing = {
        "pipes": [{"id": "target_p", "start": [0.5, 0, 0], "end": [100.5, 0, 0]}],
    }

    already = detect_coordinate_missing(_aligned_pipe(), existing, {"tolerance": 2.0})
    uncertain = detect_coordinate_missing(_aligned_pipe(0.5), {"pipes": []})

    assert already["already_exists"][0]["target_element_id"] == "target_p"
    assert uncertain["uncertain"][0]["element_id"] == "p1"

