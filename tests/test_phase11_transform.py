from __future__ import annotations


def _anchor(anchor_id: str, source: str, x: float, y: float, confidence: float = 0.9):
    from mcp.spatial.models import AnchorPoint, Point2D

    return AnchorPoint(anchor_id, source, Point2D(x, y), anchor_id, "pipe_endpoint", confidence, {})


def test_transform_apply_identity_translation_and_affine() -> None:
    from mcp.spatial.models import BBox2D, Point2D, Transform2D
    from mcp.spatial.transform import TransformEstimator

    estimator = TransformEstimator()

    identity = Transform2D("identity", [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 1.0, 0.0, {})
    translation = Transform2D("translation", [[1, 0, 10], [0, 1, 20], [0, 0, 1]], 0.8, 0.0, {})
    affine = Transform2D("affine", [[2, 0, 10], [0, 3, 20], [0, 0, 1]], 0.8, 0.0, {})

    assert estimator.apply_point(identity, Point2D(1, 2)).to_dict() == {"x": 1.0, "y": 2.0}
    assert estimator.apply_point(translation, Point2D(1, 2)).to_dict() == {"x": 11.0, "y": 22.0}
    assert estimator.apply_point(affine, Point2D(1, 2)).to_dict() == {"x": 12.0, "y": 26.0}
    assert estimator.apply_bbox(translation, BBox2D(0, 0, 1, 1)).to_dict() == {
        "min_x": 10.0,
        "min_y": 20.0,
        "max_x": 11.0,
        "max_y": 21.0,
    }


def test_transform_estimator_returns_unknown_when_anchor_pairs_missing() -> None:
    from mcp.spatial.transform import TransformEstimator

    transform = TransformEstimator().estimate_from_anchor_pairs([])

    assert transform.transform_type == "unknown"
    assert transform.confidence == 0.0
    assert transform.metadata["warning"] == "not enough anchor pairs"


def test_transform_estimator_estimates_translation_from_one_pair() -> None:
    from mcp.spatial.models import AnchorPair
    from mcp.spatial.transform import TransformEstimator

    pair = AnchorPair(_anchor("r", "reference", 1, 2), _anchor("t", "target", 11, 22), 0.8, ["manual"])

    transform = TransformEstimator().estimate_from_anchor_pairs([pair])

    assert transform.transform_type == "translation"
    assert transform.matrix[0][2] == 10.0
    assert transform.matrix[1][2] == 20.0

