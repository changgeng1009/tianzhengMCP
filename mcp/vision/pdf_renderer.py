from __future__ import annotations

from pathlib import Path
from typing import Any


def render_pdf_to_images(
    pdf_path: str,
    output_dir: str | Path | None = None,
    dpi: int = 300,
) -> dict[str, Any]:
    path = Path(pdf_path)
    if not path.exists():
        return {
            "status": "failed",
            "images": [],
            "warnings": [f"PDF file not found: {path}"],
            "error": str(path),
        }

    try:
        fitz = _import_fitz("fitz")
    except ImportError as exc:
        return {
            "status": "failed",
            "images": [],
            "warnings": [f"PDF renderer dependency unavailable: {exc}"],
            "error": str(exc),
        }

    output_path = Path(output_dir) if output_dir is not None else path.with_suffix("")
    output_path.mkdir(parents=True, exist_ok=True)
    images: list[dict[str, Any]] = []
    try:
        document = fitz.open(str(path))
        zoom = float(dpi) / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for page_index in range(len(document)):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix)
            image_path = output_path / f"{path.stem}_page_{page_index + 1}.png"
            pixmap.save(str(image_path))
            images.append(
                {
                    "page_index": page_index,
                    "path": str(image_path),
                    "dpi": dpi,
                }
            )
        return {
            "status": "success",
            "images": images,
            "warnings": [],
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "images": images,
            "warnings": [f"PDF render failed: {exc}"],
            "error": str(exc),
        }


def _import_fitz(name: str):
    return __import__(name)

