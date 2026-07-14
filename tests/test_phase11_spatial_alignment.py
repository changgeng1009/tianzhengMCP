from __future__ import annotations


def test_spatial_alignment_manual_anchors_maps_reference_graph() -> None:
    from mcp.spatial.spatial_alignment import align_reference_graph_to_target

    reference = {
        "metadata": {"coordinate_space": "normalized_image"},
        "pipes": [{"id": "p1", "start": [0, 0, 0], "end": [1, 0, 0], "confidence": 0.9}],
        "buildings": [],
        "valves": [],
        "sprinklers": [],
        "texts": [],
        "symbols": [],
    }
    target = {
        "metadata": {"coordinate_space": "cad_modelspace"},
        "pipes": [],
        "buildings": [],
        "valves": [],
        "sprinklers": [],
    }
    manual = [
        {
            "reference": {"x": 0, "y": 0},
            "target": {"x": 100, "y": 200},
            "confidence": 0.9,
            "reason": ["manual_anchor"],
        }
    ]

    result = align_reference_graph_to_target(reference, target, manual_anchor_pairs=manual)
    data = result.to_dict()

    assert data["transform"]["transform_type"] == "translation"
    assert data["aligned_reference_graph"]["metadata"]["coordinate_space"] == "cad_modelspace"
    assert data["confidence"] > 0.5
    assert data["errors"] == []


def test_alignment_validator_flags_low_confidence_transform() -> None:
    from mcp.spatial.alignment_validator import validate_alignment
    from mcp.spatial.models import Transform2D

    result = validate_alignment(
        {"metadata": {"coordinate_space": "cad_modelspace"}, "pipes": []},
        {},
        Transform2D("translation", [[1, 0, 1], [0, 1, 1], [0, 0, 1]], 0.2, 0.0, {}),
    )

    assert result["valid"] is False
    assert "transform confidence below threshold" in result["warnings"]

