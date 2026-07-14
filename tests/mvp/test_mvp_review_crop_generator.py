from __future__ import annotations

from pathlib import Path

from mcp.recognition.mvp_review_crop_generator import build_contact_sheet, create_evidence_card


def test_create_evidence_card(tmp_path: Path) -> None:
    out = tmp_path / "card.png"
    result = create_evidence_card(out, item_id="mvp1_visual_test", evidence_status="insufficient", reason="bbox missing")

    assert result["ok"] is True
    assert out.exists()
    assert out.stat().st_size > 0


def test_build_contact_sheet(tmp_path: Path) -> None:
    card1 = tmp_path / "one.png"
    card2 = tmp_path / "two.png"
    create_evidence_card(card1, item_id="one", evidence_status="ready", reason="ok")
    create_evidence_card(card2, item_id="two", evidence_status="insufficient", reason="missing")
    sheet = tmp_path / "sheet.png"

    result = build_contact_sheet([card1, card2], sheet)

    assert result["ok"] is True
    assert result["item_count"] == 2
    assert sheet.exists()

