from __future__ import annotations

from mcp.recognition.mvp_reference_pdf_reader import read_reference_pdf
from mcp.recognition.mvp_semantic_object_model import validate_semantic_objects


def test_reference_pdf_reader_schema() -> None:
    result = read_reference_pdf()

    assert result["phase"] == "MVP-1"
    assert result["mode"] == "dry_run_gpt_fallback"
    assert result["reference_pdf_loaded"] is True
    assert result["source_dwg_opened"] is False
    assert result["pdf_text_count"] >= 1
    assert "pdf_vector_count" in result
    ok, errors = validate_semantic_objects(result["objects"])
    assert ok, errors


def test_ambiguous_pdf_object_classified_for_visual_review() -> None:
    result = read_reference_pdf()
    ambiguous = result["ambiguous_visual_regions"]

    assert ambiguous
    assert any(item.get("requires_visual_review") is True for item in ambiguous)

