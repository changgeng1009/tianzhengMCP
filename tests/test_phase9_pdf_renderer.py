from __future__ import annotations


def test_pdf_renderer_missing_file_returns_structured_failure(tmp_path) -> None:
    from mcp.vision.pdf_renderer import render_pdf_to_images

    result = render_pdf_to_images(str(tmp_path / "missing.pdf"), output_dir=tmp_path)

    assert result["status"] == "failed"
    assert result["images"] == []
    assert result["warnings"]
    assert "missing.pdf" in result["error"]


def test_pdf_renderer_dependency_missing_is_structured(monkeypatch, tmp_path) -> None:
    from mcp.vision import pdf_renderer

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    def fake_import(name: str):
        raise ImportError("fitz not installed")

    monkeypatch.setattr(pdf_renderer, "_import_fitz", fake_import)

    result = pdf_renderer.render_pdf_to_images(str(pdf_path), output_dir=tmp_path)

    assert result["status"] == "failed"
    assert result["images"] == []
    assert "PDF renderer dependency unavailable" in result["warnings"][0]

