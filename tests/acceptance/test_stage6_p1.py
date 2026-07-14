from __future__ import annotations

import json
from pathlib import Path

import yaml

from mcp.orchestration import stage6_p1 as p1


def _sample(reference: Path, target: Path) -> dict:
    return {
        "sample_id": "sample_multi_region_pilot",
        "reference_path": str(reference),
        "target_path": str(target),
        "scope": "multi_region",
        "blind_test": False,
        "dimension2_required": False,
        "protected_regions": ["水泵房大样图"],
        "write_mode": "AUTHORIZED_TARGET_IN_PLACE",
        "target_in_place_write_allowed": True,
        "target_save_allowed": True,
        "reference_write_allowed": False,
        "reference_save_allowed": False,
    }


def test_authorization_is_exact_path_scoped_and_reference_read_only(tmp_path: Path, synthetic_cad_factory) -> None:
    reference, target = tmp_path / "r.dwg", tmp_path / "t.dwg"
    synthetic_cad_factory(reference)
    synthetic_cad_factory(target)
    assert p1.validate_pilot_authorization(_sample(reference, target)) == []
    invalid = _sample(reference, target)
    invalid["reference_write_allowed"] = True
    assert "reference_must_be_read_only" in p1.validate_pilot_authorization(invalid)


def test_preflight_creates_byte_identical_backup(monkeypatch, tmp_path: Path, synthetic_cad_factory) -> None:
    reference, target = tmp_path / "r.dwg", tmp_path / "t.dwg"
    synthetic_cad_factory(reference)
    synthetic_cad_factory(target)
    config = tmp_path / "samples.yaml"
    config.write_text(yaml.safe_dump({"samples": [_sample(reference, target)]}, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(p1, "RUNS_ROOT", tmp_path / "runs")
    synthetic_cad_factory(
        tmp_path / "runs" / "stage6_p1_test" / "backups" / "t.prewrite.dwg",
        create=False,
    )
    manifest = p1.run_prewrite_preflight("stage6_p1_test", config)
    assert manifest["status"] == "PASS_P1_PREWRITE_FROZEN"
    assert manifest["prewrite_backup_hash_matches"] is True
    assert manifest["target_write_started"] is False
    assert manifest["safety"]["reference_opened"] is False
    backup = Path(manifest["prewrite_backup"]["path"])
    assert backup.read_bytes() == target.read_bytes()


def test_lock_file_blocks_before_backup(monkeypatch, tmp_path: Path, synthetic_cad_factory) -> None:
    reference, target = tmp_path / "r.dwg", tmp_path / "t.dwg"
    synthetic_cad_factory(reference)
    synthetic_cad_factory(target)
    reference.with_suffix(".dwl2").write_text("lock", encoding="utf-8")
    config = tmp_path / "samples.yaml"
    config.write_text(yaml.safe_dump({"samples": [_sample(reference, target)]}, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(p1, "RUNS_ROOT", tmp_path / "runs")
    manifest = p1.run_prewrite_preflight("stage6_p1_locked", config)
    assert manifest["status"] == "BLOCKED_P1_PREFLIGHT"
    assert "reference_locked" in manifest["errors"]
    assert manifest["prewrite_backup"] is None


def test_difference_policy_never_treats_color_as_missing() -> None:
    policy = p1.difference_policy()
    assert policy["color_is_missing_evidence"] is False
    assert policy["classifications"]["PROTECTED_COMPLETE_REGION"]["modification_allowed"] is False
    assert policy["classifications"]["ALLOWED_DIFFERENCE"]["object_names"] == ["TDbDimension2"]


def test_runtime_does_not_use_commands_or_fixed_handles() -> None:
    source = Path(p1.__file__).read_text(encoding="utf-8")
    assert ".SendCommand" not in source
    assert ".NETLOAD" not in source
    assert "TDbPipe.Insert" not in source
    assert '"reference_handle":' not in source
    assert '"production_d1_allowed": False' in source


def test_report_keeps_pilot_and_mvp4_incomplete(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(p1, "REPORT_JSON", tmp_path / "report.json")
    monkeypatch.setattr(p1, "REPORT_MD", tmp_path / "report.md")
    p1.write_preflight_report({"status": "PASS_P1_PREWRITE_FROZEN", "run_id": "x"})
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["pilot_completed"] is False
    assert report["mvp3_completed"] is False
    assert report["mvp4_allowed"] is False


def test_readonly_scan_runtime_has_no_save_or_entity_creation() -> None:
    source = Path(p1.__file__).read_text(encoding="utf-8")
    forbidden_calls = (".Save(", ".SaveAs(", ".AddLine(", ".AddText(", ".AddPolyline(", ".AddCircle(")
    assert not any(call in source for call in forbidden_calls)
    assert '"target_write_started": False' in source


def test_title_aliases_and_pump_room_normalize_without_mutating_titles() -> None:
    assert p1._normalize_title("屋顶给排水平面图") == "ROOF_PLUMBING_PLAN"
    assert p1._normalize_title("地下一层平面图") == "BASEMENT_PLUMBING_PLAN"
    assert p1._normalize_title("泵房大样") == "PUMP_ROOM_DETAIL"


def test_frame_candidates_deduplicate_nested_title_frames() -> None:
    scan = {"entities": [
        {"handle": "outer", "object_name": "AcDbPolyline", "layer": "TWT_TITLE", "bbox": [[0, 0, 0], [100000, 120000, 0]]},
        {"handle": "inner", "object_name": "AcDbPolyline", "layer": "TWT_TITLE", "bbox": [[2000, 2000, 0], [98000, 118000, 0]]},
    ]}
    frames = p1._frame_candidates(scan)
    assert len(frames) == 1
    assert frames[0]["evidence_handle"] == "outer"


def test_protected_pump_region_requires_unique_title_and_never_allows_repair() -> None:
    scan = {"entities": [
        {"handle": "title", "object_name": "AcDbText", "bbox": [[100, 100, 0], [200, 120, 0]], "attributes": {"text": "泵房大样"}},
        {"handle": "pipe", "object_name": "TDbPipe", "bbox": [[110, 50, 0], [190, 90, 0]], "attributes": {}},
    ]}
    region = p1._protected_pump_region(scan)
    assert region is not None
    assert region["protected"] is True
    assert region["repair_allowed"] is False


def test_disjoint_explicit_region_titles_are_not_compatible() -> None:
    left = {"normalized_titles": ["WATER_SUPPLY_SYSTEM_DIAGRAM"]}
    right = {"normalized_titles": ["SPRINKLER_SYSTEM_DIAGRAM"]}
    similarity, compatible = p1._title_compatibility(left, right)
    assert similarity == 0.0
    assert compatible is False


def test_explicit_different_floor_titles_are_not_compatible() -> None:
    left = {"normalized_titles": ["PLUMBING_PLAN"], "title_items": [{"text": "六~十六层自动喷淋平面图"}]}
    right = {"normalized_titles": ["PLUMBING_PLAN"], "title_items": [{"text": "一层平面图"}]}
    _, compatible = p1._title_compatibility(left, right)
    assert compatible is False


def test_region_class_separates_system_diagrams_from_plans() -> None:
    assert p1._region_class({"normalized_titles": ["SPRINKLER_SYSTEM_DIAGRAM"]}) == "SYSTEM_DIAGRAM"
    assert p1._region_class({"normalized_titles": [], "object_type_counts": {"TDbWall": 40}}) == "PLAN"


def _entity(handle: str, name: str, x: float, y: float, *, color: int = 1, layer: str = "A") -> dict:
    return {
        "handle": handle,
        "object_name": name,
        "bbox": [[x - 1, y - 1, 0], [x + 1, y + 1, 0]],
        "attributes": {},
        "color": color,
        "layer": layer,
        "linetype": "Continuous",
    }


def test_user_confirmed_compound_region_splits_into_seven_logical_regions() -> None:
    compound = {
        "region_id": "reference_region_0002",
        "bbox": [0, 0, 100000, 100000],
        "frame_evidence_handle": "frame",
    }
    other = [
        {"region_id": f"reference_region_{index:04d}", "bbox": [0, 0, 10, 10]}
        for index in (1, 3, 4, 5, 6)
    ]
    manifest = {"reference_regions": [other[0], compound, *other[1:]]}
    scan = {"entities": [
        *[_entity(f"l{i}", "AcDbLine", 20000 + i, 30000 + i) for i in range(5)],
        *[_entity(f"u{i}", "AcDbLine", 20000 + i, 70000 + i) for i in range(5)],
    ]}
    regions, evidence = p1._logical_reference_regions(manifest, scan)
    assert len(regions) == 7
    assert [item["region_id"] for item in regions[1:3]] == [
        "reference_region_0002_upper", "reference_region_0002_lower"
    ]
    assert evidence["gap"] > 1_000


def test_logical_region_split_is_idempotent() -> None:
    regions = [
        {"region_id": "reference_region_0002_upper", "bbox": [0, 50, 100, 100]},
        {"region_id": "reference_region_0002_lower", "bbox": [0, 0, 100, 50]},
    ]
    manifest = {
        "reference_regions": regions,
        "logical_split_evidence": {"split_coordinate": 50, "gap": 20},
    }
    result, evidence = p1._logical_reference_regions(manifest, {"entities": []})
    assert result == regions
    assert evidence["split_coordinate"] == 50


def test_region_transform_is_uniform_and_records_aspect_residual() -> None:
    transform = p1._bbox_similarity_transform([0, 0, 100, 50], [10, 20, 210, 120])
    assert transform["uniform_scale"] == 2.0
    assert transform["rotation_degrees"] == 0.0
    assert transform["aspect_log_residual"] == 0.0


def test_final_manual_mapping_is_exact_user_confirmed_bijection() -> None:
    pairs = [(reference_id, target_id) for reference_id, target_id, _ in p1.FINAL_MANUAL_REGION_PAIRS]
    assert pairs == [
        ("reference_region_0001", "target_region_0007"),
        ("reference_region_0002_upper", "target_region_0001"),
        ("reference_region_0002_lower", "target_region_0002"),
        ("reference_region_0003", "target_region_0004"),
        ("reference_region_0004", "target_region_0005"),
        ("reference_region_0005", "target_region_0003"),
        ("reference_region_0006", "target_region_0006"),
    ]
    assert len({item[0] for item in pairs}) == 7
    assert len({item[1] for item in pairs}) == 7
    assert ("reference_region_0002_lower", "target_region_0006") not in pairs
    assert ("reference_region_0006", "target_region_0002") not in pairs


def test_frozen_plan_requires_verified_alignment_hashes_and_zero_protected_intersection() -> None:
    assert p1._frozen_plan_gate(
        all_alignment_verified=True, protected_intersection_count=0, hashes_unchanged=True
    ) is True
    assert p1._frozen_plan_gate(
        all_alignment_verified=False, protected_intersection_count=0, hashes_unchanged=True
    ) is False


def test_native_geometry_alignment_accepts_independent_scale_one_translation() -> None:
    reference_entities = []
    target_entities = []
    object_names = ("AcDbLine", "AcDbPolyline", "TDbWall")
    for index in range(12):
        x = 10 + (index % 4) * 25
        y = 10 + (index // 4) * 35
        name = object_names[index % len(object_names)]
        geometry = {"length": 5.0} if name == "AcDbLine" else {}
        reference_entities.append({
            "handle": f"R{index}", "object_name": name, "layer": "A",
            "bbox": [[x, y, 0], [x + 5, y + 5, 0]], "geometry": geometry,
        })
        target_entities.append({
            "handle": f"T{index}", "object_name": name, "layer": "A",
            "bbox": [[x + 100, y + 50, 0], [x + 105, y + 55, 0]], "geometry": geometry,
        })
    region = {"bbox": [0, 0, 120, 120], "frame_width": 120, "frame_height": 120}
    target_region = {"bbox": [90, 40, 220, 170], "frame_width": 130, "frame_height": 130}
    result = p1._native_geometry_alignment(
        {"entities": reference_entities}, {"entities": target_entities}, region, target_region
    )
    assert result["geometry_dominant_verified"] is True
    assert result["transform"]["uniform_scale"] == 1.0
    assert result["transform"]["translation"] == [100.0, 50.0]
    assert result["independent_anchor_count"] == 12
    assert len(result["anchor_type_counts"]) == 3
    assert result["target_to_reference_overlap"] == 1.0


def test_native_geometry_alignment_rejects_correlated_two_type_evidence() -> None:
    reference = []
    target = []
    for index in range(12):
        name = "AcDbLine" if index % 2 else "AcDbPolyline"
        reference.append({
            "handle": f"R{index}", "object_name": name, "layer": "A",
            "bbox": [[index * 10, 0, 0], [index * 10 + 5, 5, 0]], "geometry": {},
        })
        target.append({
            "handle": f"T{index}", "object_name": name, "layer": "A",
            "bbox": [[index * 10 + 100, 50, 0], [index * 10 + 105, 55, 0]], "geometry": {},
        })
    result = p1._native_geometry_alignment(
        {"entities": reference}, {"entities": target},
        {"bbox": [0, 0, 120, 120], "frame_width": 120, "frame_height": 120},
        {"bbox": [90, 40, 220, 170], "frame_width": 130, "frame_height": 130},
    )
    assert result["geometry_dominant_verified"] is False
    assert "fewer than 3 native anchor types" in result["blockers"]


def test_relaxed_alignment_accepts_stable_multi_type_completed_subset() -> None:
    reference = []
    target = []
    names = ("AcDbLine", "AcDbPolyline", "TDbWall")
    for index in range(18):
        name = names[index % 3]
        x = 10 + (index % 6) * 20
        y = 10 + (index // 6) * 35
        size = 2.0 ** (index // 3 + 1)
        geometry = {"start_point": [x, y, 0], "end_point": [x + size, y, 0], "length": size} if name == "AcDbLine" else {}
        reference.append({"handle": f"R{index}", "object_name": name, "layer": "A", "bbox": [[x, y, 0], [x + size, y + size, 0]], "geometry": geometry})
        moved_geometry = {"start_point": [x + 100, y + 50, 0], "end_point": [x + 100 + size, y + 50, 0], "length": size} if name == "AcDbLine" else {}
        target.append({"handle": f"T{index}", "object_name": name, "layer": "A", "bbox": [[x + 100, y + 50, 0], [x + 100 + size, y + 50 + size, 0]], "geometry": moved_geometry})
    result = p1._relaxed_geometry_alignment(
        {"entities": reference}, {"entities": target},
        {"bbox": [0, 0, 220, 180], "frame_width": 220, "frame_height": 180, "normalized_titles": ["PLUMBING_PLAN"]},
        {"bbox": [90, 40, 330, 250], "frame_width": 240, "frame_height": 210, "normalized_titles": ["PLUMBING_PLAN"]},
    )
    assert result["verified"] is True
    assert result["mode"] == "COMPLETED_TARGET_SUBSET"
    assert result["transform"]["translation"] == [100.0, 50.0]


def test_system_riser_sequence_requires_unique_stable_vertical_span() -> None:
    reference = []
    target = []
    levels = [0, 5100, 10200, 15300, 19100, 22900, 26700, 30500, 34300, 38100, 41900, 45700]
    for index, y in enumerate(levels):
        reference.append({
            "handle": f"R{index}", "object_name": "AcDbLine", "layer": "PIPE",
            "bbox": [[100, y, 0], [5100, y, 0]],
            "geometry": {"start_point": [100, y, 0], "end_point": [5100, y, 0], "length": 5000},
        })
        target.append({
            "handle": f"T{index}", "object_name": "AcDbLine", "layer": "PIPE",
            "bbox": [[20100, y + 30000, 0], [25100, y + 30000, 0]],
            "geometry": {"start_point": [20100, y + 30000, 0], "end_point": [25100, y + 30000, 0], "length": 5000},
        })
    result = p1._relaxed_geometry_alignment(
        {"entities": reference}, {"entities": target},
        {"bbox": [0, 0, 10000, 60000], "frame_width": 10000, "frame_height": 60000, "normalized_titles": ["WATER_SUPPLY_SYSTEM_DIAGRAM"]},
        {"bbox": [20000, 30000, 30000, 90000], "frame_width": 10000, "frame_height": 60000, "normalized_titles": ["WATER_SUPPLY_SYSTEM_DIAGRAM"]},
    )
    assert result["verified"] is True
    assert result["mode"] == "SYSTEM_RISER_SEQUENCE"
    assert result["transform"]["translation"] == [20000.0, 30000.0]
    assert p1._frozen_plan_gate(
        all_alignment_verified=True, protected_intersection_count=1, hashes_unchanged=True
    ) is False
    assert p1._frozen_plan_gate(
        all_alignment_verified=True, protected_intersection_count=0, hashes_unchanged=False
    ) is False


def test_style_difference_is_existing_and_never_missing() -> None:
    region = {"region_id": "r", "bbox": [0, 0, 100, 100], "frame_width": 100, "frame_height": 100}
    reference = {"entities": [_entity("r1", "AcDbLine", 20, 20, color=1)]}
    target = {"entities": [_entity("t1", "AcDbLine", 20, 20, color=3)]}
    transform = p1._bbox_similarity_transform(region["bbox"], region["bbox"])
    summary, tasks = p1._pair_difference_summary(
        reference, target, region, region, {"geometry_coverage": 1.0}, transform, [200, 200, 300, 300]
    )
    assert summary["existing_with_style_difference_count"] == 1
    assert summary["required_missing_count"] == 0
    assert tasks == []
    assert summary["source_to_target_matches"][0]["source_handle"] == "r1"
    assert summary["source_to_target_matches"][0]["target_handle"] == "t1"


def test_protected_intersection_is_excluded_from_execution_plan() -> None:
    region = {"region_id": "r", "bbox": [0, 0, 100, 100], "frame_width": 100, "frame_height": 100}
    reference = {"entities": [_entity("r1", "AcDbLine", 20, 20)]}
    transform = p1._bbox_similarity_transform(region["bbox"], region["bbox"])
    summary, tasks = p1._pair_difference_summary(
        reference, {"entities": []}, region, region, {"geometry_coverage": 1.0}, transform, [10, 10, 30, 30]
    )
    assert summary["protected_excluded_count"] == 1
    assert summary["required_missing_count"] == 0
    assert tasks == []


def test_diff_never_emits_unsupported_tdb_execution_task() -> None:
    region = {"region_id": "r", "bbox": [0, 0, 100, 100], "frame_width": 100, "frame_height": 100}
    reference = {"entities": [{
        "handle": "wall", "object_name": "TDbWall", "layer": "WALL", "color": 1,
        "linetype": "ByLayer", "bbox": [[10, 10, 0], [20, 20, 0]], "geometry": {}, "attributes": {},
    }]}
    transform = {"uniform_scale": 1.0, "translation": [100.0, 100.0]}
    summary, tasks = p1._pair_difference_summary(
        reference, {"entities": []}, region, region, {"geometry_coverage": 1.0}, transform,
        [500, 500, 600, 600], geometry_verified_override=True,
    )
    assert tasks == []
    assert summary["unsupported_missing_review_count"] == 1
    assert summary["review_count"] == 1


def test_core_tdb_diff_requires_component_graph_before_execution() -> None:
    region = {"region_id": "r", "bbox": [0, 0, 100, 100], "frame_width": 100, "frame_height": 100}
    reference = {"entities": [{
        "handle": "pipe", "object_name": "TDbPipe", "layer": "PIPE", "color": 1,
        "linetype": "ByLayer", "bbox": [[10, 10, 0], [20, 10, 0]],
        "geometry": {"length": 10}, "attributes": {"dn_diameter": 100, "sys_type": "给水"},
    }]}
    summary, tasks = p1._pair_difference_summary(
        reference, {"entities": []}, region, region, {"geometry_coverage": 1.0},
        {"uniform_scale": 1.0, "translation": [100.0, 100.0]}, [500, 500, 600, 600],
        geometry_verified_override=True,
    )
    assert summary["required_missing_core_tdb_count"] == 1
    assert tasks[0]["execution_allowed"] is False
    assert tasks[0]["component_graph_required"] is True


def test_core_component_plan_orders_valve_after_pipe_and_fitting() -> None:
    region = {"region_id": "r", "bbox": [0, 0, 100, 100]}
    entities = [
        {"handle": "P", "object_name": "TDbPipe", "bbox": [[0, 0, 0], [10, 0, 0]]},
        {"handle": "F", "object_name": "TDbPipeFitting", "bbox": [[10, 0, 0], [10, 0, 0]]},
        {"handle": "V", "object_name": "TDbPipeValve", "bbox": [[5, 0, 0], [5, 0, 0]]},
    ]
    tasks = [
        {"task_id": f"task_{item['handle']}", "reference_region_id": "r", "source_entity_id": item["handle"], "task_group": "core_tdb"}
        for item in entities
    ]
    plan = p1._build_core_component_dependency_plan(
        {"entities": entities}, [region],
        [{"reference_region_id": "r", "source_to_target_matches": []}], tasks,
    )
    assert plan["component_graph_ready"] is True
    order = plan["components"][0]["execution_order"]
    assert order[-1] == "task_V"
    assert set(order[:-1]) == {"task_P", "task_F"}


def test_core_component_plan_preserves_empty_fitting_relationship_set() -> None:
    entity = {"handle": "F", "object_name": "TDbPipeFitting", "bbox": [[10, 10, 0], [10, 10, 0]]}
    task = {"task_id": "task_F", "reference_region_id": "r", "source_entity_id": "F", "task_group": "core_tdb"}
    plan = p1._build_core_component_dependency_plan(
        {"entities": [entity]}, [{"region_id": "r", "bbox": [0, 0, 100, 100]}],
        [{"reference_region_id": "r", "source_to_target_matches": []}], [task],
    )
    assert plan["component_graph_ready"] is True
    expectation = plan["components"][0]["relationship_expectations"][0]
    assert expectation["expected_related_pipe_source_handles"] == []
    assert expectation["empty_relationship_set_allowed"] is True


def test_similarity_transform_solver_recovers_verified_cad_anchors() -> None:
    import pytest

    transform = p1.solve_similarity_from_anchor_points(
        [[10, 20], [30, 20], [10, 40]],
        [[105, 207.5], [105, 237.5], [75, 207.5]],
    )
    assert transform["uniform_scale"] == pytest.approx(1.5)
    assert abs(transform["rotation_degrees"] - 90.0) < 1e-9
    assert transform["translation"] == pytest.approx([135.0, 192.5])
    assert transform["anchor_rmse"] < 1e-9
    assert transform["anchor_pair_count"] == 3


def test_similarity_transform_solver_rejects_missing_or_degenerate_anchors() -> None:
    import pytest

    with pytest.raises(ValueError, match="at least two"):
        p1.solve_similarity_from_anchor_points([[1, 2]], [[3, 4]])
    with pytest.raises(ValueError, match="degenerate"):
        p1.solve_similarity_from_anchor_points([[1, 2], [1, 2]], [[3, 4], [5, 6]])


def test_frozen_execution_plan_hash_detects_tampering() -> None:
    plan = {
        "phase": "STAGE6-P1-FROZEN-EXECUTION-PLAN",
        "tasks": [{"task_id": "task_1", "execution_allowed": True}],
        "target_write_allowed": True,
    }
    plan["plan_sha256"] = p1._payload_sha256(plan)

    valid, actual = p1.validate_frozen_execution_plan(plan)
    assert valid is True
    assert actual == plan["plan_sha256"]

    plan["tasks"][0]["execution_allowed"] = False
    valid, _actual = p1.validate_frozen_execution_plan(plan)
    assert valid is False
