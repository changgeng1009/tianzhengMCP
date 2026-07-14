from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .mvp_semantic_object_model import semantic_object_from_pdf_item


DEFAULT_PDF_REPORT = Path("reports/phase_d3_pdf_geometry.json")
DIAMETER_RE = re.compile(r"(DN|De|D|Φ)\s*\d+", re.IGNORECASE)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_pdf_items(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    text_items: list[dict[str, Any]] = []
    detected_labels: list[dict[str, Any]] = []
    ambiguous_regions: list[dict[str, Any]] = []

    for page in report.get("pages", []):
        page_number = page.get("page_number")
        preview = str(page.get("text_preview") or "")
        if preview:
            text_items.append(
                {
                    "object_id": f"reference_pdf:page_{page_number}:text",
                    "object_type": "text",
                    "semantic": {
                        "text": preview,
                        "page_number": page_number,
                        "is_page_level_text_layer": True,
                        "page_level_aggregate": True,
                    },
                    "geometry": {"page": page_number, "width": page.get("width"), "height": page.get("height")},
                    "confidence": 0.7,
                }
            )
        for match in DIAMETER_RE.finditer(preview):
            detected_labels.append(
                {
                    "object_id": f"reference_pdf:page_{page_number}:label_{len(detected_labels)}",
                    "object_type": "text",
                    "semantic": {"label": match.group(0), "page_number": page_number},
                    "geometry": {"page": page_number},
                    "confidence": 0.75,
                }
            )

    if report and not report.get("vector_lines") and not report.get("vector_paths"):
        ambiguous_regions.append(
            {
                "object_id": "reference_pdf:ambiguous_visual_region_1",
                "object_type": "unknown",
                "semantic": {"reason": "PDF vector/path details unavailable in existing report"},
                "geometry": {"page": 1},
                "confidence": 0.25,
                "requires_visual_review": True,
            }
        )

    return text_items, detected_labels, ambiguous_regions


def read_reference_pdf(report_path: str | Path = DEFAULT_PDF_REPORT) -> dict[str, Any]:
    path = Path(report_path)
    report = _load_json(path)
    text_items, label_items, ambiguous_items = _extract_pdf_items(report) if report else ([], [], [])
    objects = [
        semantic_object_from_pdf_item(item, index=index)
        for index, item in enumerate(text_items + label_items + ambiguous_items)
    ]
    return {
        "phase": "MVP-1",
        "mode": "dry_run_gpt_fallback",
        "source": str(path),
        "reference_pdf_loaded": bool(report),
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "pdf_text_count": len(text_items),
        "pdf_vector_count": len(report.get("vector_lines", [])) + len(report.get("vector_paths", [])) if report else 0,
        "detected_labels": label_items,
        "ambiguous_visual_regions": ambiguous_items,
        "objects": objects,
        "warnings": [] if report else [f"reference PDF report not found: {path}"],
    }


def main() -> None:
    print(json.dumps(read_reference_pdf(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
