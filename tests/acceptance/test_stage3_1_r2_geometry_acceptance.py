from __future__ import annotations

from pathlib import Path

from mcp.acceptance import stage3_1_r2_geometry_acceptance as r2


def _anchor(
    index: int,
    anchor_type: str,
    point: tuple[float, float],
    *,
    block: str | None = None,
    dx: float = 100.0,
    dy: float = 50.0,
    extra: dict | None = None,
) -> dict:
    block = block or f"B{index}"
    payload = {
        "anchor_id": f"A{index:02d}",
        "anchor_type": anchor_type,
        "reference_handles": [f"{block}:R{index}"],
        "target_handles": [f"T{block}:T{index}"],
        "reference_point": [point[0], point[1]],
        "target_point": [point[0] + dx, point[1] + dy],
    }
    payload.update(extra or {})
    return payload


def _independent_anchors(count: int = 12, *, one_block: bool = False) -> list[dict]:
    anchor_types = ("rectangle_center", "long_line_midpoint", "unique_block_insertion")
    points = (
        (10, 10), (25, 20), (65, 10), (90, 25),
        (10, 65), (25, 90), (65, 65), (90, 90),
        (15, 45), (45, 15), (85, 45), (45, 85),
    )
    return [
        _anchor(i, anchor_types[i % len(anchor_types)], points[i], block="ONE" if one_block else f"B{i}")
        for i in range(count)
    ]


def _decision_inputs(anchors: list[dict]) -> dict:
    audit = r2.audit_anchor_independence(anchors, [0, 0, 100, 100])
    independent = audit.pop("independent_anchors")
    holdouts = r2.deterministic_holdouts(independent, [100, 50], 150.0, [0, 0, 100, 100])
    return {
        "target_scan_status": "TARGET_SCAN_CONFIRMED_BLOCK_CONTAINED",
        "region_correspondence_confirmed": True,
        "local_bbox_overlap": 1.0,
        "anchor_audit": audit,
        "holdouts": holdouts,
        "overlap": {"passed": True},
        "transform": {
            "transform_type": "translation",
            "transform_parameters": {"rotation_radians": 0.0, "scale": 1.0},
        },
        "confidence": 0.9,
        "hashes_intact": True,
        "safety_passed": True,
        "text_anchor_absence_expected": True,
        "repair_task_generated": False,
        "text_anchor_count": 0,
    }


def test_geometry_dominant_alignment_can_pass_without_text() -> None:
    status, allowed, blockers = r2.decide_geometry_acceptance(**_decision_inputs(_independent_anchors()))
    assert status == "PASS_TRANSLATION_GEOMETRY_DOMINANT"
    assert allowed is True
    assert blockers == []


def test_text_only_alignment_cannot_pass() -> None:
    inputs = _decision_inputs(_independent_anchors())
    inputs["anchor_audit"]["independent_anchor_count"] = 0
    inputs["anchor_audit"]["anchor_type_counts"] = {}
    inputs["text_anchor_count"] = 5
    status, allowed, _ = r2.decide_geometry_acceptance(**inputs)
    assert status == "PARTIAL_GEOMETRY_EVIDENCE_CORRELATED"
    assert allowed is False


def test_fewer_than_twelve_independent_non_text_anchors_cannot_pass() -> None:
    status, allowed, blockers = r2.decide_geometry_acceptance(**_decision_inputs(_independent_anchors(11)))
    assert allowed is False
    assert any("12 independent" in item for item in blockers)


def test_single_anchor_type_cannot_pass() -> None:
    anchors = _independent_anchors()
    for anchor in anchors:
        anchor["anchor_type"] = "rectangle_center"
    status, allowed, blockers = r2.decide_geometry_acceptance(**_decision_inputs(anchors))
    assert allowed is False
    assert any("three independent" in item for item in blockers)


def test_all_anchors_from_one_block_cannot_pass() -> None:
    status, allowed, blockers = r2.decide_geometry_acceptance(**_decision_inputs(_independent_anchors(one_block=True)))
    assert status == "PARTIAL_GEOMETRY_EVIDENCE_CORRELATED"
    assert allowed is False
    assert any("one top-level BlockReference" in item for item in blockers)


def test_spatial_coverage_failure_blocks_pass() -> None:
    anchors = [
        _anchor(i, ("rectangle_center", "long_line_midpoint", "unique_block_insertion")[i % 3], (10 + i, 10 + i / 10))
        for i in range(12)
    ]
    status, allowed, blockers = r2.decide_geometry_acceptance(**_decision_inputs(anchors))
    assert allowed is False
    assert any("spatial coverage" in item for item in blockers)


def test_unstable_holdout_blocks_pass() -> None:
    inputs = _decision_inputs(_independent_anchors())
    inputs["holdouts"]["all_valid_holdouts_passed"] = False
    status, allowed, blockers = r2.decide_geometry_acceptance(**inputs)
    assert status == "PARTIAL_HOLDOUT_UNSTABLE"
    assert allowed is False
    assert any("holdout" in item for item in blockers)


def _line_feature(point: tuple[float, float], length: float = 1000.0) -> dict:
    return {
        "feature_type": "long_line_midpoint",
        "point": list(point),
        "handles": [str(point)],
        "signature": {"length": length, "angle": 0.0, "orientation": "horizontal"},
    }


def test_directional_target_to_reference_overlap_is_primary() -> None:
    reference = [_line_feature((i * 1000.0, 0.0)) for i in range(5)]
    target = [_line_feature((100.0, 50.0)), _line_feature((1100.0, 50.0))]
    result = r2.directional_geometry_overlap(
        reference, target, [[1, 0, 100], [0, 1, 50], [0, 0, 1]], 10000.0
    )
    assert result["target_to_reference_overlap"] == 1.0
    assert result["reference_to_target_overlap"] == 0.4
    assert result["passed"] is True


def test_incomplete_target_does_not_fail_directional_overlap() -> None:
    reference = [_line_feature((i * 1000.0, 0.0)) for i in range(10)]
    target = [_line_feature((100.0, 50.0)), _line_feature((1100.0, 50.0))]
    result = r2.directional_geometry_overlap(
        reference, target, [[1, 0, 100], [0, 1, 50], [0, 0, 1]], 10000.0
    )
    assert result["reference_to_target_overlap"] == 0.2
    assert result["target_to_reference_overlap"] == 1.0
    assert result["passed"] is True


def test_title_and_frame_anchors_are_excluded() -> None:
    anchors = _independent_anchors() + [
        _anchor(90, "rectangle_center", (50, 50), extra={"layer": "TWT_TITLE"}),
        _anchor(91, "frame_anchor", (60, 60)),
    ]
    audit = r2.audit_anchor_independence(anchors, [0, 0, 100, 100])
    assert audit["excluded_anchor_count"] >= 2
    assert audit["exclusion_reasons"]["title_or_frame_anchor"] == 2


def test_stage1_seed_line_is_excluded() -> None:
    anchors = _independent_anchors() + [
        _anchor(92, "long_line_midpoint", (50, 50), extra={"source": "stage1_seed_line"}),
    ]
    audit = r2.audit_anchor_independence(anchors, [0, 0, 100, 100])
    assert audit["exclusion_reasons"]["stage1_seed_line"] == 1


def test_duplicate_coordinate_pair_and_derived_corners_are_not_independent() -> None:
    anchors = _independent_anchors()
    duplicate = dict(anchors[0], anchor_id="DUP", reference_handles=["BD:R-DUP"], target_handles=["TBD:T-DUP"])
    corner = _anchor(95, "wall_corner", (30, 30), block="B0")
    corner["reference_handles"] = [anchors[0]["reference_handles"][0], "B0:OTHER"]
    anchors.extend([duplicate, corner])
    audit = r2.audit_anchor_independence(anchors, [0, 0, 100, 100])
    assert audit["duplicated_anchor_count"] == 1
    assert audit["correlated_anchor_count"] == 1
    assert audit["independent_anchor_count"] == 12


def test_r2_module_has_no_cad_runtime_or_mutation_calls() -> None:
    source = Path(r2.__file__).read_text(encoding="utf-8")
    forbidden = (
        "win32com", "GetActiveObject", "Dispatch(", "Documents.Open", "AddLine(",
        "AddText(", "AddPolyline(", "AddCircle(", "SendCommand(", ".Save(",
        "SaveAs(", "CopyObjects(", "Close(True)", "NETLOAD",
    )
    assert not any(token in source for token in forbidden)


def test_safety_flags_never_allow_execution_or_repair() -> None:
    flags = r2._safety_flags()
    assert flags["repair_task_generated"] is False
    assert flags["stage3_2_executed"] is False
    assert flags["production_d1_allowed"] is False
    assert all(value is False for value in flags.values())
