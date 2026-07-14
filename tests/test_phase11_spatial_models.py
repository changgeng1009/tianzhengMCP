from __future__ import annotations


def test_spatial_models_serialize_to_json_dict() -> None:
    from mcp.spatial.models import (
        AnchorPair,
        AnchorPoint,
        BBox2D,
        Point2D,
        SpatialAlignmentResult,
        Transform2D,
    )

    ref = AnchorPoint("r1", "reference", Point2D(0.1, 0.2), "p1", "pipe_endpoint", 0.8, {})
    tgt = AnchorPoint("t1", "target", Point2D(100.0, 200.0), "p2", "pipe_endpoint", 0.9, {})
    pair = AnchorPair(ref, tgt, 0.72, ["element_type_match"])
    transform = Transform2D("translation", [[1, 0, 100], [0, 1, 200], [0, 0, 1]], 0.72, 0.0, {})
    result = SpatialAlignmentResult(
        reference_graph_id="ref",
        target_graph_id="target",
        transform=transform,
        aligned_reference_graph={"metadata": {"coordinate_space": "cad_modelspace"}},
        anchor_pairs=[pair],
        confidence=0.72,
        warnings=[],
        errors=[],
        metadata={},
    )

    assert BBox2D(0, 0, 1, 1).to_dict()["max_x"] == 1
    assert result.to_dict()["anchor_pairs"][0]["reference_anchor"]["anchor_id"] == "r1"
    assert result.to_dict()["transform"]["transform_type"] == "translation"

