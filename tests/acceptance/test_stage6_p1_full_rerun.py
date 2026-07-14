from __future__ import annotations

import inspect

from mcp.orchestration import stage6_p1_full_rerun as rerun


def test_checkpoint_sets_are_disjoint_and_complete() -> None:
    state = rerun._build_state(
        all_task_ids={"a", "b", "c"},
        completed_task_ids={"a"},
        skipped_task_ids={"b"},
        manual_tasks=[{"task_id": "b"}],
        source_to_target={"A": "10"},
        created_handles={"10"},
        call_count=1,
        current_task_index=2,
        current_component_index=0,
    )
    assert state["completed_task_ids"] == ["a"]
    assert state["skipped_task_ids"] == ["b"]
    assert state["pending_task_ids"] == ["c"]
    assert not (set(state["completed_task_ids"]) & set(state["pending_task_ids"]))


def test_exact_candidate_match_requires_type_owner_bbox_and_geometry() -> None:
    source = {
        "object_name": "AcDbLine",
        "owner": {"object_name": "AcDbBlockTableRecord"},
        "bbox": [[1.0, 2.0, 0.0], [3.0, 4.0, 0.0]],
        "geometry": {"start_point": [1.0, 2.0, 0.0], "end_point": [3.0, 4.0, 0.0]},
    }
    assert rerun._candidate_matches(source, dict(source))
    assert not rerun._candidate_matches(source, {**source, "object_name": "AcDbCircle"})
    assert not rerun._candidate_matches(source, {**source, "bbox": [[1.0, 2.0, 0.0], [3.1, 4.0, 0.0]]})
    assert not rerun._candidate_matches(source, {**source, "geometry": {"radius": 1.0}})


def test_known_idpair_objects_are_frozen() -> None:
    assert rerun.KNOWN_IDPAIR_SOURCES == {"B04C6", "B04C7", "B04C8"}


def test_success_executor_never_saves_or_saveas() -> None:
    source = inspect.getsource(rerun)
    assert ".Save(" not in source
    assert ".SaveAs(" not in source
    assert "document.Close(False)" in inspect.getsource(rerun._close_without_save)


def test_work_file_name_is_new_r2_copy() -> None:
    assert rerun.WORK_FILE_NAME.endswith("-应急提交版-R2.dwg")
