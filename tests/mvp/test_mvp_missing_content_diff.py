from __future__ import annotations

from mcp.diff.mvp_missing_content_diff import compare_missing_content, run_default_diff


def test_missing_diff_schema() -> None:
    result = run_default_diff()
    required = {
        "matched_objects",
        "missing_objects",
        "extra_objects",
        "changed_objects",
        "uncertain_objects",
        "matched_count",
        "missing_count",
        "extra_count",
        "changed_count",
        "uncertain_count",
    }
    assert required <= set(result)
    assert result["source_dwg_opened"] is False
    assert result["sendcommand_used"] is False
    assert result["production_d1_allowed"] is False


def test_diff_produces_missing_when_reference_has_simple_unmatched_geometry() -> None:
    reference = [
        {
            "object_id": "reference_dwg:line_missing",
            "source": "reference_dwg",
            "object_type": "line",
            "geometry": {"start_point": [0, 0], "end_point": [1, 1]},
            "semantic": {"object_name": "AcDbLine"},
            "layer": "A",
            "confidence": 0.9,
            "requires_visual_review": False,
        }
    ]
    result = compare_missing_content(reference, [])
    assert result["missing_count"] == 1
    assert result["missing_objects"][0]["reference_object"]["object_id"] == "reference_dwg:line_missing"


def test_uncertain_object_goes_to_review_only() -> None:
    reference = [
        {
            "object_id": "reference_pdf:ambiguous",
            "source": "reference_pdf",
            "object_type": "unknown",
            "geometry": {},
            "semantic": {},
            "layer": "pdf",
            "confidence": 0.2,
            "requires_visual_review": True,
        }
    ]
    result = compare_missing_content(reference, [])
    assert result["missing_count"] == 0
    assert result["uncertain_count"] == 1
    assert result["review_only"]

