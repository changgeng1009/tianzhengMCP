from __future__ import annotations

from pathlib import Path

from mcp.recognition.mvp_pdf_region_extractor import crop_pdf_region, render_pdf_page


def test_render_pdf_page_to_png(tmp_path: Path) -> None:
    out = tmp_path / "page.png"
    result = render_pdf_page("artifacts/input/reference.pdf", out, zoom=0.2)

    assert result["ok"] is True
    assert out.exists()
    assert result["bbox"][2] > 0
    assert result["center"][0] > 0


def test_crop_pdf_region_handles_missing_bbox_as_page_crop(tmp_path: Path) -> None:
    out = tmp_path / "page_crop.png"
    result = crop_pdf_region("artifacts/input/reference.pdf", out, page_number=1, bbox=None, zoom=0.2)

    assert result["ok"] is True
    assert out.exists()

