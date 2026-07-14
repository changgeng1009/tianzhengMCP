from __future__ import annotations

from pathlib import Path

from mcp.recognition.mvp_visual_evidence_builder import build_visual_evidence


def test_visual_evidence_builder_creates_five_item_report() -> None:
    report = build_visual_evidence()

    assert report["phase"] == "MVP-1.2"
    assert report["deepseek_worker_used"] is True
    assert report["full_chat_sent_to_deepseek"] is False
    assert report["api_key_sent_to_deepseek"] is False
    assert report["input_visual_item_count"] == 5
    assert report["generated_crop_count"] == 5
    assert report["contact_sheet_created"] is True
    assert Path(report["contact_sheet_path"]).exists()
    assert len(report["items"]) == 5


def test_visual_evidence_does_not_fake_missing_bbox() -> None:
    report = build_visual_evidence()
    aggregate_items = [item for item in report["items"] if item["source"] == "reference_dwg"]

    assert aggregate_items
    for item in aggregate_items:
        assert item["evidence_status"] == "insufficient"
        assert item["bbox"] is None
        assert item["center"] is None
        assert Path(item["crop_path"]).exists()

