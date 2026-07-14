from __future__ import annotations

from pathlib import Path

from mcp.orchestration import stage6_p2_7_remaining_region_manual_disambiguation as p27


def _anchor(anchor_id: str, point: tuple[float, float], handle: str = "1") -> dict:
    return {
        "anchor_id": anchor_id,
        "handle": handle,
        "effective_anchor_point": [point[0], point[1], 0.0],
        "alignment_name": "LEFT_BASELINE",
    }


def _region(region_id: str, semantic: str) -> dict:
    return {
        "region_id": region_id,
        "frame_bbox": [0.0, 0.0, 10000.0, 10000.0],
        "selected_semantic_name": semantic,
        "all_title_texts": [semantic],
    }


def test_required_anchor_ids_are_exact() -> None:
    assert len(p27.ANCHOR_IDS) == 6
    assert "F19_ROOF_FIX_01" in p27.ANCHOR_IDS
    assert "TANK_FIX_03" in p27.ANCHOR_IDS


def test_pairs_same_name_anchors() -> None:
    refs = [_anchor("F19_ROOF_FIX_01", (1, 2))]
    tgts = [_anchor("F19_ROOF_FIX_01", (101, 202))]
    result = p27.pair_named_anchors(refs, tgts, ["F19_ROOF_FIX_01"])
    assert result["pairs"][0]["dx"] == 100
    assert result["pairs"][0]["dy"] == 200


def test_missing_anchor_is_rejected() -> None:
    result = p27.pair_named_anchors([], [], ["TANK_FIX_01"])
    assert result["errors"][0]["reason"] == "MISSING_OR_DUPLICATE_ANCHOR"


def test_duplicate_anchor_is_rejected() -> None:
    refs = [_anchor("TANK_FIX_01", (1, 1)), _anchor("TANK_FIX_01", (2, 2), "2")]
    result = p27.pair_named_anchors(refs, [_anchor("TANK_FIX_01", (3, 3))], ["TANK_FIX_01"])
    assert result["errors"]


def test_region_precheck_accepts_correct_regions_and_semantics() -> None:
    pair = {"anchor_id": "A", "reference_point": [10, 10, 0], "target_point": [20, 20, 0]}
    semantic = "十九层平面图、屋面平面图"
    result = p27.region_precheck([pair, {**pair, "anchor_id": "B"}], _region("r", semantic), _region("t", semantic), semantic)
    assert result["passed"] is True


def test_region_precheck_rejects_wrong_placement() -> None:
    pair = {"anchor_id": "A", "reference_point": [20000, 10, 0], "target_point": [20, 20, 0]}
    semantic = "水箱间平面图、水箱间屋面平面图"
    assert p27.region_precheck([pair], _region("r", semantic), _region("t", semantic), semantic)["passed"] is False


def test_region_precheck_rejects_wrong_semantic() -> None:
    pair = {"anchor_id": "A", "reference_point": [10, 10, 0], "target_point": [20, 20, 0]}
    assert p27.region_precheck([pair, pair], _region("r", "一层平面图"), _region("t", "一层平面图"), "十九层平面图、屋面平面图")["passed"] is False


def test_manual_translation_uses_group_median() -> None:
    pairs = [
        {"anchor_id": "1", "reference_point": [100, 100, 0], "dx": 1000.0, "dy": 2000.0},
        {"anchor_id": "2", "reference_point": [9000, 9000, 0], "dx": 1000.1, "dy": 1999.9},
        {"anchor_id": "3", "reference_point": [8000, 1000, 0], "dx": 1000.0, "dy": 2000.0},
    ]
    result = p27.manual_translation_metrics(pairs, [0, 0, 10000, 10000])
    assert result["manual_translation"] == {"x": 1000.0, "y": 2000.0}
    assert result["spatially_distributed"] is True


def test_cluster_scoring_selects_manual_supported_cluster() -> None:
    manual = {
        "pairs": [{"dx": 100, "dy": 200}, {"dx": 100.1, "dy": 200.1}],
        "manual_translation": {"x": 100.05, "y": 200.05},
    }
    clusters = [
        {"dx_median": 100.0, "dy_median": 200.0, "ratio": 0.7},
        {"dx_median": 500.0, "dy_median": 600.0, "ratio": 0.3},
    ]
    result = p27.score_candidate_clusters(manual, clusters)
    assert result["selected_translation"] == {"x": 100.0, "y": 200.0}
    assert result["competing_cluster_remaining"] is False


def test_near_equal_competing_cluster_remains() -> None:
    manual = {"pairs": [{"dx": 100, "dy": 200}], "manual_translation": {"x": 100, "y": 200}}
    clusters = [
        {"dx_median": 100, "dy_median": 200, "ratio": 0.6},
        {"dx_median": 110, "dy_median": 200, "ratio": 0.4},
    ]
    assert p27.score_candidate_clusters(manual, clusters)["competing_cluster_remaining"] is True


def test_anchor_scanner_has_no_dwg_write_surface() -> None:
    source = Path(p27.__file__).read_text(encoding="utf-8")
    for forbidden in ("SendCommand", "CopyObjects", "SaveAs(", ".Save(", "AddLine", "TransformBy", "Delete("):
        assert forbidden not in source


def test_final_manifest_requires_both_groups() -> None:
    source = Path(p27.__file__).read_text(encoding="utf-8")
    assert "if len(passed) == 2:" in source
    assert '"count": 7' in source
