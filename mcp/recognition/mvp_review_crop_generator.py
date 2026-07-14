from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


CARD_SIZE = (900, 520)


def create_evidence_card(
    output_path: str | Path,
    *,
    item_id: str,
    evidence_status: str,
    reason: str,
    source_image: str | Path | None = None,
) -> dict[str, Any]:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", CARD_SIZE, "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, CARD_SIZE[0] - 1, CARD_SIZE[1] - 1], outline=(180, 180, 180), width=2)
    draw.text((28, 28), f"{item_id}", fill=(20, 20, 20))
    draw.text((28, 70), f"evidence_status: {evidence_status}", fill=(180, 40, 40) if evidence_status != "ready" else (20, 120, 60))

    y = 120
    for line in _wrap_text(reason, 68):
        draw.text((28, y), line, fill=(40, 40, 40))
        y += 26

    if source_image and Path(source_image).exists():
        thumb = Image.open(source_image).convert("RGB")
        thumb.thumbnail((360, 240))
        canvas.paste(thumb, (CARD_SIZE[0] - thumb.width - 28, CARD_SIZE[1] - thumb.height - 28))
        thumb.close()

    canvas.save(target)
    canvas.close()
    return {"ok": True, "output_path": str(target), "size": list(CARD_SIZE)}


def build_contact_sheet(
    crop_paths: list[str | Path],
    output_path: str | Path,
    *,
    columns: int = 2,
    cell_size: tuple[int, int] = (460, 310),
) -> dict[str, Any]:
    paths = [Path(path) for path in crop_paths]
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = max(1, (len(paths) + columns - 1) // columns)
    sheet = Image.new("RGB", (columns * cell_size[0], rows * cell_size[1]), "white")
    draw = ImageDraw.Draw(sheet)

    for index, path in enumerate(paths):
        x = (index % columns) * cell_size[0]
        y = (index // columns) * cell_size[1]
        draw.rectangle([x, y, x + cell_size[0] - 1, y + cell_size[1] - 1], outline=(210, 210, 210))
        draw.text((x + 12, y + 10), path.stem, fill=(20, 20, 20))
        if path.exists():
            image = Image.open(path).convert("RGB")
            image.thumbnail((cell_size[0] - 24, cell_size[1] - 48))
            sheet.paste(image, (x + 12, y + 42))
            image.close()
        else:
            draw.text((x + 12, y + 52), "missing crop", fill=(180, 40, 40))

    sheet.save(target)
    sheet.close()
    return {"ok": True, "output_path": str(target), "item_count": len(paths)}


def _wrap_text(text: str, width: int) -> list[str]:
    text = str(text)
    lines: list[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= width:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return lines or [""]

