from __future__ import annotations


def _reference_graph() -> dict:
    return {
        "metadata": {"coordinate_space": "normalized_image"},
        "buildings": [{"id": "b1", "bbox": [0.0, 0.0, 1.0, 1.0], "confidence": 0.8}],
        "pipes": [{"id": "p1", "start": [0.1, 0.2, 0], "end": [0.8, 0.2, 0], "confidence": 0.75}],
        "sprinklers": [{"id": "s1", "position": [0.5, 0.5, 0], "confidence": 0.7}],
    }


def _target_graph() -> dict:
    return {
        "metadata": {"coordinate_space": "cad_modelspace"},
        "nodes": [{"id": "n1", "position": [100, 200, 0], "confidence": 0.8}],
        "pipes": [{"id": "p1", "start": [100, 200, 0], "end": [800, 200, 0], "confidence": 0.8}],
        "sprinklers": [{"id": "s1", "position": [500, 500, 0], "confidence": 0.8}],
    }


def test_anchor_extractor_reads_reference_and_target_coordinates() -> None:
    from mcp.spatial.anchor_extractor import extract_reference_anchors, extract_target_anchors

    reference = extract_reference_anchors(_reference_graph())
    target = extract_target_anchors(_target_graph())

    assert any(anchor.element_type == "building_centroid" for anchor in reference)
    assert any(anchor.element_type == "pipe_endpoint" for anchor in reference)
    assert any(anchor.element_type == "sprinkler_center" for anchor in reference)
    assert any(anchor.element_type == "graph_node" for anchor in target)
    assert any(anchor.element_type == "pipe_endpoint" for anchor in target)


def test_anchor_matcher_matches_same_type_without_high_fake_confidence() -> None:
    from mcp.spatial.anchor_extractor import extract_reference_anchors, extract_target_anchors
    from mcp.spatial.anchor_matcher import match_anchors

    pairs = match_anchors(extract_reference_anchors(_reference_graph()), extract_target_anchors(_target_graph()))

    assert pairs
    assert all(pair.confidence < 0.95 for pair in pairs)
    assert all("element_type_match" in pair.reason for pair in pairs)

