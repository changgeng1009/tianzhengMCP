from __future__ import annotations

import inspect
import pytest
from tests.acceptance.run_config_fixture import set_parameter
from pathlib import Path

from mcp.orchestration import stage6_p2_6_region_semantic_reindexing as p26


SYNTHETIC_BINDINGS = {key: (f"synthetic_ref_{i}", f"synthetic_target_{i}") for i, key in enumerate(p26.SEMANTIC_KEYS)}

@pytest.fixture(autouse=True)
def synthetic_run_config(monkeypatch, tmp_path):
    set_parameter(monkeypatch, tmp_path, "stage6_p2_6.actual_bindings", SYNTHETIC_BINDINGS)
    set_parameter(monkeypatch, tmp_path, "stage6_p2_6.old_bindings", SYNTHETIC_BINDINGS)


def _region(region_id: str, old: str = "旧语义") -> dict:
    return {
        "region_id": region_id,
        "frame_bbox": [0.0, 0.0, 100.0, 100.0],
        "content_bbox": [5.0, 5.0, 95.0, 95.0],
        "semantic_name": old,
    }


def _title(text: str, point=(50.0, 50.0)) -> dict:
    return {"text": text, "point": list(point), "object_name": "AcDbText"}


def test_extracts_titles_inside_region_only() -> None:
    titles = p26.titles_in_region(_region("r"), [_title("一层平面图"), _title("屋面平面图", (150, 150))])
    assert [item["text"] for item in titles] == ["一层平面图"]


def test_multiple_titles_are_preserved() -> None:
    rows = p26.build_region_semantics("reference", [_region(SYNTHETIC_BINDINGS["floors_6_to_16"][0])], [_title("六~十五层平面图"), _title("十六层平面图")], {})
    assert rows[0]["all_title_texts"] == ["六~十五层平面图", "十六层平面图"]


def test_basement_synonyms() -> None:
    for text in ("地下一层平面图", "负一层平面图", "地下室平面图"):
        assert p26.select_semantic([text])[0] == "basement"


def test_floors_6_to_16_title() -> None:
    assert p26.select_semantic(["六～十五层平面图", "十六层平面图"])[0] == "floors_6_to_16"


def test_floor_19_and_roof_title() -> None:
    assert p26.select_semantic(["十九层平面图", "屋面平面图"])[0] == "floor_19_and_roof"


def test_water_tank_title_has_priority_over_roof() -> None:
    assert p26.select_semantic(["水箱间平面图", "水箱间屋面平面图"])[0] == "water_tank_and_tank_roof"


def test_system_titles() -> None:
    assert p26.select_semantic(["生活给水系统展开图", "生活排水系统原理图"])[0] == "domestic_water_and_drainage_system"
    assert p26.select_semantic(["消火栓系统展开图", "自动喷淋系统展开图"])[0] == "fire_hydrant_and_sprinkler_system"


def test_old_semantic_conflict_is_recorded() -> None:
    rows = p26.build_region_semantics("reference", [_region(SYNTHETIC_BINDINGS["basement"][0], "十九层平面图、屋面平面图")], [_title("地下一层平面图")], {})
    assert rows[0]["selected_semantic_key"] == "basement"
    assert rows[0]["old_semantic_consistent"] is False


def test_region_id_unique_constraint() -> None:
    bindings = [
        {"reference_region_id": "r1", "target_region_id": "t1"},
        {"reference_region_id": "r1", "target_region_id": "t2"},
    ]
    assert p26.validate_unique_mapping(bindings)[0]["type"] == "DUPLICATE_REGION_BINDING"


def test_historical_transform_reassociation_does_not_inherit_verified(tmp_path: Path) -> None:
    (tmp_path / "alignment_repair").mkdir()
    (tmp_path / "block_xref_audit").mkdir()
    payload = {"transforms": [{"reference_region_id": "r", "target_region_id": "t", "status": "VERIFIED", "model_type": "translation_only"}]}
    p26._write(tmp_path / "coordinate_transforms.json", payload)
    p26._write(tmp_path / "alignment_repair" / "repaired_coordinate_transforms.json", {"transforms": []})
    p26._write(tmp_path / "block_xref_audit" / "retry_alignment_results.json", {"results": []})
    row = p26.reassociate_history(tmp_path, {("r", "t"): "basement"})[0]
    assert row["actual_semantic_name"] == "地下一层平面图"
    assert row["historical_verified_inherited"] is False


def test_manual_anchor_region_binding_uses_actual_pair() -> None:
    refs = [_region(pair[0], p26.SEMANTIC_NAMES[key]) for key, pair in SYNTHETIC_BINDINGS.items()]
    tgts = [_region(pair[1], p26.SEMANTIC_NAMES[key]) for key, pair in SYNTHETIC_BINDINGS.items()]
    ref_sem = [{**item, "all_title_texts": [], "semantic_confidence": 0.95} for item in refs]
    tgt_sem = [{**item, "all_title_texts": [], "semantic_confidence": 0.95} for item in tgts]
    mappings, conflicts = p26.build_semantic_mapping(ref_sem, tgt_sem)
    basement = next(item for item in mappings if item["semantic_key"] == "basement")
    assert (basement["reference_region_id"], basement["target_region_id"]) == SYNTHETIC_BINDINGS["basement"]
    assert conflicts == []


def test_geometry_holdout_uses_supplied_region_entities() -> None:
    ref = [{"object_name": "AcDbLine", "layer": "WALL", "geometry": {"start_point": [10, 10], "end_point": [20, 10]}}]
    tgt = [{"object_name": "AcDbLine", "layer": "WALL", "geometry": {"start_point": [110, 210], "end_point": [120, 210]}}]
    audit = p26.geometry_holdout(ref, tgt, (100, 200), [100, 200, 130, 230], [])
    assert audit["holdout_match_ratio"] == 1.0
    assert audit["holdout_rms"] == 0.0


def test_old_verified_cannot_be_reused_as_final_status() -> None:
    source = inspect.getsource(p26.reassociate_history)
    assert '"historical_verified_inherited": False' in source


def test_protected_pump_room_policy_constants() -> None:
    assert "protected_pump_room" in p26.classify_title_texts(["泵房详图"])


def test_module_has_no_dwg_write_calls() -> None:
    source = Path(p26.__file__).read_text(encoding="utf-8")
    for forbidden in ("SendCommand", "CopyObjects", "SaveAs(", ".Save(", "AddLine", "TransformBy", "Delete("):
        assert forbidden not in source
