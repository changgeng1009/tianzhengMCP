from __future__ import annotations

import json
from pathlib import Path

from mcp.repair_actions.geometry_evidence_recovery import (
    build_manual_anchor_request,
    recover_geometry_evidence,
    trace_task_lineage,
    validate_recovered_geometry,
)
from mcp.repair_actions.geometry_localizer import SAFETY_FLAGS


def _write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _blocked_doc(task_type: str = "direct_com_create") -> dict:
    return {
        "phase": "S1-FIX",
        "tasks": [
            {
                "task_id": "mvp1_task_208c4ccc9f",
                "task_type": task_type,
                "object_type": "text",
                "source_object_id": "reference_pdf:page_1:text",
                "original_fields": {"page": 1, "width": 2384.0, "height": 3370.0},
                "missing_geometry_fields": ["insert_point", "bbox"],
                "rejection_reason": "only PDF page/width/height is present",
            }
        ],
    }


def test_can_read_s1_fix_blocked_task(tmp_path: Path) -> None:
    blocked_path = _write_json(tmp_path / "blocked.json", _blocked_doc())

    result = recover_geometry_evidence(blocked_task_file=blocked_path, upstream_artifacts=[])

    assert result["input_blocked_geometry_task_count"] == 1
    assert result["manual_anchor_requests"][0]["task_id"] == "mvp1_task_208c4ccc9f"


def test_can_trace_upstream_lineage(tmp_path: Path) -> None:
    upstream = {
        "tasks": [
            {
                "task_id": "mvp1_task_208c4ccc9f",
                "task_type": "direct_com_create",
                "source_object_id": "reference_pdf:page_1:text",
            }
        ]
    }
    visual = {"items": [{"item_id": "v1", "related_object_ids": ["reference_pdf:page_1:text"], "crop_path": "crop.png"}]}
    alignment = {"alignment_status": "ready", "confidence": 1.0}

    lineage = trace_task_lineage(
        _blocked_doc()["tasks"][0],
        [{"path": "upstream.json", "data": upstream}, {"path": "visual.json", "data": visual}],
        [{"path": "alignment.json", "data": alignment}],
    )

    assert lineage["source_artifact_path"] == "upstream.json"
    assert lineage["reference_object_id"] == "reference_pdf:page_1:text"
    assert lineage["visual_item_id"] == "v1"
    assert lineage["alignment_id"] == "alignment.json"


def test_valid_cad_geometry_is_recognized() -> None:
    validated = validate_recovered_geometry(
        {"task_type": "direct_com_create"},
        {
            "task_type": "direct_com_create",
            "cad_geometry": {"insert_point": [120.5, 300.25, 0.0]},
            "geometry_source": "verified_overlay_geometry",
            "geometry_confidence": 0.9,
        },
    )

    assert validated["execution_allowed"] is True
    assert validated["cad_geometry"]["insert_point"] == [120.5, 300.25, 0.0]


def test_rejects_pdf_page_size_only() -> None:
    validated = validate_recovered_geometry(
        {"task_type": "direct_com_create"},
        {
            "cad_geometry": {"page": 1, "width": 2384.0, "height": 3370.0},
            "geometry_source": "pdf_page_size_only",
            "geometry_confidence": 1.0,
        },
    )

    assert validated["execution_allowed"] is False
    assert "forbidden geometry source" in validated["rejection_reason"]


def test_rejects_guessed_default_hardcoded_placeholder_geometry() -> None:
    for source in ["guessed_geometry", "default_origin", "hardcoded_coordinate", "placeholder_geometry"]:
        validated = validate_recovered_geometry(
            {"task_type": "direct_com_create"},
            {
                "cad_geometry": {"insert_point": [10, 20, 0]},
                "geometry_source": source,
                "geometry_confidence": 0.95,
            },
        )
        assert validated["execution_allowed"] is False

    default_point = validate_recovered_geometry(
        {"task_type": "direct_com_create"},
        {
            "cad_geometry": {"insert_point": [0, 0, 0]},
            "geometry_source": "verified_overlay_geometry",
            "geometry_confidence": 0.95,
        },
    )
    assert default_point["execution_allowed"] is False
    assert "default or placeholder" in default_point["rejection_reason"]


def test_no_cad_geometry_generates_manual_anchor_request(tmp_path: Path) -> None:
    blocked_path = _write_json(tmp_path / "blocked.json", _blocked_doc())
    upstream_path = _write_json(
        tmp_path / "missing.json",
        {"tasks": [{"task_id": "mvp1_task_208c4ccc9f", "source_object_id": "reference_pdf:page_1:text", "geometry": {"page": 1}}]},
    )

    result = recover_geometry_evidence(blocked_task_file=blocked_path, upstream_artifacts=[upstream_path])

    assert result["executable_direct_com_tasks"] == []
    assert len(result["manual_anchor_requests"]) == 1
    assert "insert_point" in result["manual_anchor_requests"][0]["missing_geometry_fields"]


def test_valid_geometry_with_confidence_generates_executable(tmp_path: Path) -> None:
    blocked_path = _write_json(tmp_path / "blocked.json", _blocked_doc())
    upstream_path = _write_json(
        tmp_path / "semantic.json",
        {
            "tasks": [
                {
                    "task_id": "mvp1_task_208c4ccc9f",
                    "task_type": "direct_com_create",
                    "geometry": {"insert_point": [10.0, 20.0, 0.0]},
                    "geometry_source": "semantic_model_geometry",
                    "geometry_confidence": 0.88,
                }
            ]
        },
    )

    result = recover_geometry_evidence(blocked_task_file=blocked_path, upstream_artifacts=[upstream_path])

    assert len(result["executable_direct_com_tasks"]) == 1
    assert result["manual_anchor_requests"] == []


def test_review_only_does_not_enter_executable() -> None:
    validated = validate_recovered_geometry(
        {"task_type": "review_only"},
        {
            "task_type": "review_only",
            "cad_geometry": {"insert_point": [10, 20, 0]},
            "geometry_source": "semantic_model_geometry",
            "geometry_confidence": 0.95,
        },
    )

    assert validated["execution_allowed"] is False


def test_sendcommand_tianzheng_task_does_not_enter_executable() -> None:
    validated = validate_recovered_geometry(
        {"task_type": "direct_com_create"},
        {
            "task_type": "direct_com_create",
            "cad_geometry": {"insert_point": [10, 20, 0]},
            "geometry_source": "semantic_model_geometry",
            "geometry_confidence": 0.95,
            "forbidden_action": "SendCommand hsxg",
        },
    )

    assert validated["execution_allowed"] is False
    assert "forbidden" in validated["rejection_reason"].lower()


def test_safety_flags_remain_false() -> None:
    request = build_manual_anchor_request(
        _blocked_doc()["tasks"][0],
        {"source_artifact_path": "missing.json", "reference_object_id": "reference_pdf:page_1:text"},
        None,
    )

    assert request["task_id"] == "mvp1_task_208c4ccc9f"
    assert all(value is False for value in SAFETY_FLAGS.values())
