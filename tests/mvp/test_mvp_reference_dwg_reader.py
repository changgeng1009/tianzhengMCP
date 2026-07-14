from __future__ import annotations

from mcp.recognition.mvp_reference_dwg_reader import read_reference_dwg
from mcp.recognition.mvp_semantic_object_model import validate_semantic_objects


def test_reference_dwg_reader_schema() -> None:
    result = read_reference_dwg()

    assert result["phase"] == "MVP-1"
    assert result["mode"] == "dry_run_gpt_fallback"
    assert result["reference_dwg_loaded"] is True
    assert result["source_dwg_opened"] is False
    assert result["source_dwg_saved"] is False
    assert result["reference_object_count"] >= result["recognized_reference_objects_count"] > 0
    ok, errors = validate_semantic_objects(result["objects"])
    assert ok, errors


def test_semantic_object_model_schema() -> None:
    obj = read_reference_dwg()["objects"][0]
    required = {
        "object_id",
        "source",
        "object_type",
        "geometry",
        "semantic",
        "layer",
        "confidence",
        "requires_visual_review",
    }
    assert required <= set(obj)

