from mcp.orchestration import stage6_p1_override as override


def _record(handle: str, bbox: list[list[float]], *, name: str = "AcDbLine", layer: str = "L") -> dict:
    return {
        "handle": handle,
        "object_name": name,
        "layer": layer,
        "bbox": bbox,
        "geometry": {"length": 10.0},
        "attributes": {},
    }


def test_override_bbox_and_region_helpers_are_cad_space_only() -> None:
    record = _record("A", [[10, 20, 0], [30, 40, 0]])
    assert override._bbox_flat(record) == [10.0, 20.0, 30.0, 40.0]
    regions = [{"region_id": "r1", "bbox": [0, 0, 100, 100]}]
    assert override._region_for_bbox([10, 20, 30, 40], regions) == "r1"
    assert override._region_for_bbox([200, 200, 220, 220], regions) is None


def test_introduced_duplicate_detects_new_exact_engineering_object() -> None:
    before = {"A": _record("A", [[0, 0, 0], [10, 0, 0]])}
    after = {**before, "B": _record("B", [[0, 0, 0], [10, 0, 0]])}
    duplicates = override._introduced_duplicates(before, after, {"B"})
    assert len(duplicates) == 1
    assert duplicates[0]["preexisting_handles"] == ["A"]
    assert duplicates[0]["new_handles"] == ["B"]


def test_changed_fields_distinguishes_geometry_attributes_and_bbox() -> None:
    before = _record("A", [[0, 0, 0], [10, 0, 0]])
    after = {**before, "bbox": [[1, 0, 0], [11, 0, 0]]}
    assert override._changed_fields(before, after) == ["bbox"]
    after = {**before, "geometry": {"length": 12.0}, "attributes": {"dn_diameter": 100}}
    assert override._changed_fields(before, after) == ["geometry", "attributes"]


def test_source_contains_no_forbidden_command_execution_routes() -> None:
    source = open(override.__file__, encoding="utf-8").read()
    assert ".SendCommand(" not in source
    assert "NETLOAD" not in source
    assert "Close(True)" not in source
    assert "production_d1_allowed\": True" not in source


def test_emergency_whole_frame_gate_ignores_sparse_candidates_but_blocks_majority() -> None:
    tasks = [{"target_region_id": "r1"} for _ in range(100)]
    assert override._entire_frame_wrong_regions(tasks, [{"expected_region_id": "r1"} for _ in range(17)]) == []
    assert override._entire_frame_wrong_regions(tasks, [{"expected_region_id": "r1"} for _ in range(50)]) == ["r1"]
