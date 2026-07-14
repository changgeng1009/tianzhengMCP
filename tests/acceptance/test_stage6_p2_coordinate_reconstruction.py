from __future__ import annotations

import inspect

import numpy as np

from mcp.orchestration import stage6_p2_coordinate_reconstruction as p2


def _anchor(index: int, point: list[float], *, kind: str = "line_endpoint", layer: str = "WALL") -> dict:
    return {
        "anchor_id": f"a{index}",
        "anchor_type": kind,
        "point": point,
        "handle": f"{index:X}",
        "object_name": "AcDbLine",
        "layer": layer,
        "direction_deg": 0.0,
        "feature_length": 1000.0,
    }


def test_anchor_sampling_enforces_limits_and_deduplicates() -> None:
    anchors = [_anchor(i, [float(i % 100), float(i // 100)]) for i in range(5000)]
    anchors.extend([dict(anchors[0]) for _ in range(20)])
    deduped, sampled, stats = p2._deduplicate_and_sample_anchors(
        anchors, [0.0, 0.0, 100.0, 100.0]
    )
    assert len(deduped) <= 3000
    assert len(sampled) <= 1000
    assert stats["raw_count"] == 5020


def test_bucketed_kdtree_matching_avoids_cartesian_pairing() -> None:
    ref = [_anchor(i, [float(i), float(i % 7)]) for i in range(100)]
    tgt = [_anchor(i, [float(i + 10), float(i % 7 + 20)]) for i in range(100)]
    matched = p2._match_anchors_kdtree(ref, tgt, [0, 0, 100, 10], [10, 20, 110, 30])
    assert len(matched) >= 90
    assert all(item["match_reason"].startswith("bucketed_kdtree") for item in matched)


def test_ransac_translation_recovers_outlier_resistant_transform() -> None:
    matched = []
    for i in range(30):
        matched.append({"reference_point": [i * 10.0, (i % 5) * 20.0], "target_point": [i * 10.0 + 500.0, (i % 5) * 20.0 - 200.0]})
    for i in range(5):
        matched.append({"reference_point": [i * 3.0, i * 7.0], "target_point": [9000.0 + i, -8000.0 - i]})
    candidates = p2._fit_transforms(matched, [0, 0, 300, 100], [500, -200, 800, -100])
    selected = p2._select_transform(candidates)
    assert selected is not None
    assert selected["model_type"] == "translation_only"
    assert selected["anchor_count_inlier"] >= 30
    matrix = np.asarray(selected["matrix"])
    assert abs(matrix[0, 2] - 500.0) < 1e-6
    assert abs(matrix[1, 2] + 200.0) < 1e-6


def test_protected_region_contains_required_policy_and_handles() -> None:
    region = {
        "region_id": "target_region_0008",
        "semantic_name": "PUMP_ROOM_DETAIL",
        "frame_bbox": [0, 0, 100, 100],
        "content_bbox": [5, 5, 95, 95],
        "entity_count": 1,
        "dominant_object_names": {},
        "dominant_layers": {},
    }
    entity = {"handle": "AA", "object_name": "TDbPump", "layer": "PUMP", "bbox": [[10, 10, 0], [20, 20, 0]]}
    protected = p2._detect_pump_room_protected([region], [entity])
    assert protected is not None
    assert protected["entity_handles"] == ["AA"]
    assert protected["policy"]["WRITE_FORBIDDEN"] is True
    assert protected["policy"]["TRANSFORM_FORBIDDEN"] is True


def test_stage6_p2_has_no_dwg_write_or_old_plan_loading_surface() -> None:
    source = inspect.getsource(p2.run_stage6_p2)
    for token in (".Save(", ".SaveAs(", ".CopyObjects(", ".SendCommand(", ".TransformBy("):
        assert token not in source
    assert "stage6_p1_20260712_010124" not in source


def test_exact_floor_semantic_prevents_basement_ground_collision() -> None:
    ref = [
        {"region_id": "r0", "semantic_name": "地下一层平面图", "frame_bbox": [0, 0, 10, 10]},
        {"region_id": "r1", "semantic_name": "一层平面图", "frame_bbox": [20, 0, 30, 10]},
    ]
    tgt = [
        {"region_id": "t0", "semantic_name": "一层平面图", "frame_bbox": [100, 0, 110, 10]},
        {"region_id": "t1", "semantic_name": "地下一层平面图", "frame_bbox": [120, 0, 130, 10]},
    ]
    basement = p2._match_semantic_region(ref, tgt, "地下一层平面图", "地下一层平面图", "p1")
    ground = p2._match_semantic_region(ref, tgt, "一层平面图", "一层平面图", "p2")
    assert basement["reference_region_id"] == "r0" and basement["target_region_id"] == "t1"
    assert ground["reference_region_id"] == "r1" and ground["target_region_id"] == "t0"
