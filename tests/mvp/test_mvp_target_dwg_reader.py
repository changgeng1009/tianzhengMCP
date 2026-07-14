from __future__ import annotations

from mcp.recognition.mvp_semantic_object_model import validate_semantic_objects
from mcp.recognition.mvp_target_dwg_reader import read_target_dwg


def test_target_dwg_reader_schema() -> None:
    result = read_target_dwg()

    assert result["phase"] == "MVP-1"
    assert result["mode"] == "dry_run_gpt_fallback"
    assert result["target_copy_loaded"] is True
    assert result["source_dwg_opened"] is False
    assert result["source_dwg_saved"] is False
    assert result["target_object_count"] >= result["recognized_target_objects_count"] > 0
    ok, errors = validate_semantic_objects(result["objects"])
    assert ok, errors

