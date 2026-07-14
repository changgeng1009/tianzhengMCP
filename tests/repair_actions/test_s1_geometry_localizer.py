from __future__ import annotations

from mcp.repair_actions.geometry_localizer import (
    LocalizationInputs,
    SAFETY_FLAGS,
    localize_geometry_for_tasks,
    validate_candidate_geometry,
)


def _inputs(tasks: list[dict]) -> LocalizationInputs:
    return LocalizationInputs(
        blocked_tasks=tasks,
        reference_objects=[],
        target_objects=[],
        alignment_transform={"confidence": 1.0},
        overlay_metadata={},
        visual_evidence={"items": []},
        semantic_model={},
    )


def test_pdf_page_size_only_is_blocked() -> None:
    task = {
        "task_id": "t_pdf",
        "task_type": "direct_com_create",
        "source_object_id": "reference_pdf:page_1:text",
        "geometry": {"page": 1, "width": 2384.0, "height": 3370.0},
        "semantic": {"text": "title"},
    }

    result = localize_geometry_for_tasks(_inputs([task]))

    assert result["executable_direct_com_tasks"] == []
    assert len(result["blocked_geometry_tasks"]) == 1
    blocked = result["blocked_geometry_tasks"][0]
    assert blocked["geometry_source"] == "pdf_page_size_only"
    assert blocked["execution_allowed"] is False


def test_missing_cad_coordinates_are_blocked() -> None:
    task = {"task_id": "t_missing", "task_type": "direct_com_create", "geometry": {}, "semantic": {}}

    result = localize_geometry_for_tasks(_inputs([task]))

    assert result["blocked_geometry_tasks"][0]["execution_allowed"] is False
    assert "missing CAD geometry" in result["blocked_geometry_tasks"][0]["block_reason"]


def test_forbidden_geometry_sources_are_rejected() -> None:
    for source in ["guessed_geometry", "default_origin", "hardcoded_coordinate", "pdf_page_size_only"]:
        result = validate_candidate_geometry(
            {
                "cad_geometry": {"insert_point": [0, 0, 0]},
                "geometry_source": source,
                "geometry_confidence": 0.99,
            }
        )
        assert result["execution_allowed"] is False
        assert "forbidden geometry source" in result["rejection_reason"]


def test_low_confidence_is_blocked() -> None:
    result = validate_candidate_geometry(
        {
            "cad_geometry": {"insert_point": [10, 20, 0]},
            "geometry_source": "verified_overlay_geometry",
            "geometry_confidence": 0.79,
        }
    )

    assert result["execution_allowed"] is False
    assert "below 0.80" in result["rejection_reason"]


def test_valid_source_and_confidence_allows_executable() -> None:
    task = {
        "task_id": "t_ok",
        "task_type": "direct_com_create",
        "source_object_id": "reference_dwg:text_1",
        "cad_geometry": {"insert_point": [100.0, 200.0, 0.0]},
        "geometry_source": "verified_overlay_geometry",
        "geometry_confidence": 0.9,
        "evidence_ids": ["overlay_1"],
        "semantic": {"text": "A"},
    }

    result = localize_geometry_for_tasks(_inputs([task]))

    assert len(result["executable_direct_com_tasks"]) == 1
    executable = result["executable_direct_com_tasks"][0]
    assert executable["execution_allowed"] is True
    assert executable["geometry_confidence"] >= 0.8
    assert executable["cad_geometry"]["insert_point"] == [100.0, 200.0, 0.0]


def test_executable_requires_cad_coordinates() -> None:
    result = validate_candidate_geometry(
        {
            "cad_geometry": {"type": "text"},
            "geometry_source": "semantic_model_geometry",
            "geometry_confidence": 0.95,
        }
    )

    assert result["execution_allowed"] is False
    assert "missing executable CAD coordinates" in result["rejection_reason"]


def test_review_only_does_not_become_executable() -> None:
    task = {
        "task_id": "review",
        "task_type": "review_only",
        "cad_geometry": {"insert_point": [100, 100, 0]},
        "geometry_source": "verified_overlay_geometry",
        "geometry_confidence": 0.95,
    }

    result = localize_geometry_for_tasks(_inputs([task]))

    assert result["executable_direct_com_tasks"] == []
    assert result["blocked_geometry_tasks"][0]["action"] == "blocked"


def test_tianzheng_sendcommand_task_does_not_become_direct_com() -> None:
    task = {
        "task_id": "tdb",
        "task_type": "manual_tianzheng_required",
        "semantic": {"required_command": "hsxg"},
        "cad_geometry": {"insert_point": [100, 100, 0]},
        "geometry_source": "verified_overlay_geometry",
        "geometry_confidence": 0.95,
    }

    result = localize_geometry_for_tasks(_inputs([task]))

    assert result["executable_direct_com_tasks"] == []
    assert result["blocked_geometry_tasks"][0]["action"] == "blocked"


def test_safety_flags_remain_false() -> None:
    result = localize_geometry_for_tasks(_inputs([]))
    assert result["safety"] == SAFETY_FLAGS
    assert all(value is False for value in result["safety"].values())
