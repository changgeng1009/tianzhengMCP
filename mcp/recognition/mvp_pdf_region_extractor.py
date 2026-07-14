from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image


def render_pdf_page(pdf_path: str | Path, output_path: str | Path, *, page_number: int = 1, zoom: float = 1.0) -> dict[str, Any]:
    """渲染 PDF 页面为 PNG；不读取 DWG，不连接 AutoCAD。"""
    source = Path(pdf_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return {"ok": False, "error": f"pdf not found: {source}", "output_path": str(target)}

    try:
        import fitz

        with fitz.open(source) as doc:
            page_index = max(page_number - 1, 0)
            if page_index >= len(doc):
                return {"ok": False, "error": "page out of range", "output_path": str(target)}
            page = doc[page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pix.save(target)
        image = Image.open(target)
        width, height = image.size
        image.close()
        return {"ok": True, "output_path": str(target), "bbox": [0, 0, width, height], "center": [width / 2, height / 2]}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "output_path": str(target)}


def crop_pdf_region(
    pdf_path: str | Path,
    output_path: str | Path,
    *,
    page_number: int = 1,
    bbox: list[int] | tuple[int, int, int, int] | None = None,
    zoom: float = 1.0,
) -> dict[str, Any]:
    rendered = render_pdf_page(pdf_path, output_path, page_number=page_number, zoom=zoom)
    if not rendered.get("ok") or bbox is None:
        return rendered

    image = Image.open(output_path)
    width, height = image.size
    x1, y1, x2, y2 = [int(v) for v in bbox]
    safe_bbox = [max(0, x1), max(0, y1), min(width, x2), min(height, y2)]
    if safe_bbox[2] <= safe_bbox[0] or safe_bbox[3] <= safe_bbox[1]:
        image.close()
        return {"ok": False, "error": "invalid bbox", "output_path": str(output_path)}
    image.crop(tuple(safe_bbox)).save(output_path)
    image.close()
    return {
        "ok": True,
        "output_path": str(output_path),
        "bbox": safe_bbox,
        "center": [(safe_bbox[0] + safe_bbox[2]) / 2, (safe_bbox[1] + safe_bbox[3]) / 2],
    }

