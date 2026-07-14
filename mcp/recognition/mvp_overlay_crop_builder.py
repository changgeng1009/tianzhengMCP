from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image


def crop_overlay(
    overlay_path: str | Path,
    output_path: str | Path,
    bbox: list[int] | tuple[int, int, int, int] | None,
) -> dict[str, Any]:
    source = Path(overlay_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return {"ok": False, "error": f"overlay not found: {source}", "output_path": str(target)}
    if bbox is None:
        return {"ok": False, "error": "bbox missing", "output_path": str(target)}

    image = Image.open(source)
    width, height = image.size
    x1, y1, x2, y2 = [int(v) for v in bbox]
    safe_bbox = [max(0, x1), max(0, y1), min(width, x2), min(height, y2)]
    if safe_bbox[2] <= safe_bbox[0] or safe_bbox[3] <= safe_bbox[1]:
        image.close()
        return {"ok": False, "error": "invalid bbox", "output_path": str(target)}

    image.crop(tuple(safe_bbox)).save(target)
    image.close()
    return {
        "ok": True,
        "output_path": str(target),
        "bbox": safe_bbox,
        "center": [(safe_bbox[0] + safe_bbox[2]) / 2, (safe_bbox[1] + safe_bbox[3]) / 2],
    }

