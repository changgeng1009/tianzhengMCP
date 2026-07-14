from __future__ import annotations

import json


def _pipe(action_id: str, start: list[float], end: list[float], **extra):
    return {
        "action_id": action_id,
        "action_type": "add_pipe",
        "target_space": "cad_modelspace",
        "geometry": {"type": "polyline", "points": [start, end]},
        "system": extra.get("system", "unknown"),
        "dn": extra.get("dn"),
        "layer": extra.get("layer"),
        "source_element_id": action_id.replace("act_", ""),
        "source_type": "aligned_reference_graph",
        "confidence": extra.get("confidence", 0.0),
        "auto_execute": extra.get("auto_execute", False),
        "reason": extra.get("reason", "manual review required"),
        "validation_status": extra.get("validation_status", "review_required"),
        "warnings": [],
        "metadata": dict(extra.get("metadata", {})),
    }


def test_duplicate_short_boundary_and_parallel_actions_are_filtered() -> None:
    from mcp.repair_actions.review_cleanup import cleanup_review_actions

    plan = {
        "review_actions": [
            _pipe("a1", [10, 10], [110, 10]),
            _pipe("a1_dup", [10, 10], [110, 10]),
            _pipe("short", [20, 20], [25, 20]),
            _pipe("boundary", [0, 0], [1000, 0]),
            _pipe("parallel", [10, 12], [110, 12]),
        ]
    }

    result = cleanup_review_actions(
        plan,
        {
            "min_length": 20,
            "reference_bbox": [0, 0, 1000, 1000],
            "boundary_tolerance": 5,
            "parallel_dedupe_tolerance": 5,
        },
    )

    filtered_ids = {item["action_id"] for item in result["filtered_actions"]}
    assert {"a1_dup", "short", "boundary", "parallel"}.issubset(filtered_ids)
    assert result["summary"]["input_review_actions"] == 5
    assert result["summary"]["filtered_actions"] == 4
    assert result["summary"]["auto_executable_after_cleanup"] == 0
    assert result["merged_actions"][0]["auto_execute"] is False
    assert result["merged_actions"][0]["validation_status"] == "review_required"


def test_collinear_neighbor_actions_are_merged_with_source_ids() -> None:
    from mcp.repair_actions.review_cleanup import cleanup_review_actions

    result = cleanup_review_actions(
        {
            "review_actions": [
                _pipe("h1", [0, 10], [100, 10]),
                _pipe("h2", [102, 11], [200, 11]),
                _pipe("v1", [300, 0], [300, 100]),
            ]
        },
        {"merge_gap_tolerance": 5, "collinear_tolerance": 3},
    )

    merged = result["merged_actions"]
    horizontal = next(item for item in merged if item["main_direction"] == "horizontal")
    assert horizontal["source_action_ids"] == ["h1", "h2"]
    assert horizontal["geometry"]["points"] == [[0.0, 10.5], [200.0, 10.5]]
    assert all(item["auto_execute"] is False for item in merged)


def test_actions_are_grouped_by_connectivity_and_direction() -> None:
    from mcp.repair_actions.review_cleanup import cleanup_review_actions

    result = cleanup_review_actions(
        {
            "review_actions": [
                _pipe("g1a", [0, 0], [100, 0]),
                _pipe("g1b", [100, 0], [100, 80]),
                _pipe("g2a", [1000, 1000], [1100, 1000]),
            ]
        },
        {"connectivity_tolerance": 10},
    )

    groups = result["groups"]
    assert len(groups) == 2
    first = max(groups, key=lambda item: item["action_count"])
    assert first["action_count"] == 2
    assert first["main_direction"] == "mixed"
    assert first["review_priority"] in {"high", "medium", "low"}
    assert first["auto_execute"] is False


def test_text_evidence_adds_candidate_dn_but_keeps_review_required() -> None:
    from mcp.repair_actions.review_cleanup import cleanup_review_actions

    result = cleanup_review_actions(
        {"review_actions": [_pipe("p1", [0, 0], [100, 0])]},
        {"text_elements": [{"text": "DN200", "position": [50, 8]}], "text_search_radius": 20},
    )

    action = result["merged_actions"][0]
    group = result["groups"][0]
    assert action["candidate_dn"] == "DN200"
    assert group["candidate_dn"] == "DN200"
    assert action["auto_execute"] is False
    assert action["validation_status"] == "review_required"
    assert result["summary"]["actions_with_dn"] == 1


def test_preview_json_and_markdown_are_generated(tmp_path) -> None:
    from mcp.repair_actions.review_cleanup import cleanup_review_actions, write_review_previews

    result = cleanup_review_actions({"review_actions": [_pipe("p1", [0, 0], [100, 0])]}, {})
    written = write_review_previews(result, str(tmp_path), image_size=[200, 100])

    assert (tmp_path / "pump_room_review_actions.json").exists()
    assert (tmp_path / "pump_room_review_actions.md").exists()
    assert (tmp_path / "pump_room_review_overlay.png").exists()
    assert len(written) == 3
    payload = json.loads((tmp_path / "pump_room_review_actions.json").read_text(encoding="utf-8"))
    assert payload["summary"]["auto_executable_after_cleanup"] == 0
    assert "review_required" in (tmp_path / "pump_room_review_actions.md").read_text(encoding="utf-8")
