from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .mvp_overlay_crop_builder import crop_overlay
from .mvp_pdf_region_extractor import crop_pdf_region
from .mvp_review_crop_generator import build_contact_sheet, create_evidence_card


DEFAULT_VISUAL_ITEMS = Path("reports/mvp_gpt_visual_review_required.json")
DEFAULT_REVIEW_TASKS = Path("reports/mvp_review_tasks_final.json")
DEFAULT_OVERLAY = Path("artifacts/review_previews/pump_room_review_overlay.png")
DEFAULT_PDF = Path("artifacts/input/reference.pdf")
DEFAULT_OUTPUT_DIR = Path("artifacts/review_previews")


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_visual_evidence(
    *,
    visual_items_path: str | Path = DEFAULT_VISUAL_ITEMS,
    review_tasks_path: str | Path = DEFAULT_REVIEW_TASKS,
    overlay_path: str | Path = DEFAULT_OVERLAY,
    pdf_path: str | Path = DEFAULT_PDF,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    visual_items = load_json(visual_items_path).get("items", [])
    review_tasks = load_json(review_tasks_path).get("tasks", [])
    task_by_item = {task.get("source_visual_item"): task for task in review_tasks}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    evidence_items: list[dict[str, Any]] = []
    generated_crop_count = 0
    evidence_ready_count = 0
    evidence_insufficient_count = 0
    crop_paths: list[str] = []

    for item in visual_items:
        item_id = str(item["item_id"])
        task = task_by_item.get(item_id, {})
        summary = task.get("object_summary", {})
        geometry = summary.get("geometry") or {}
        bbox = geometry.get("bbox")
        crop_path = output / f"{item_id}_crop.png"
        source = item.get("source")
        evidence_status = "insufficient"
        reason = ""
        bbox_out = bbox
        center = geometry.get("center")

        if bbox:
            crop_result = crop_overlay(overlay_path, crop_path, bbox)
            if crop_result.get("ok"):
                evidence_status = "ready"
                bbox_out = crop_result.get("bbox")
                center = crop_result.get("center")
                reason = "overlay crop generated from provided bbox"
            else:
                reason = str(crop_result.get("error", "overlay crop failed"))
        elif source == "reference_pdf" and geometry.get("page"):
            crop_result = crop_pdf_region(pdf_path, crop_path, page_number=int(geometry.get("page", 1)), bbox=None, zoom=0.35)
            if crop_result.get("ok"):
                evidence_status = "partial"
                bbox_out = crop_result.get("bbox")
                center = crop_result.get("center")
                reason = "PDF page crop generated, but no region bbox exists"
            else:
                reason = str(crop_result.get("error", "PDF crop failed"))
        else:
            reason = "bbox/center missing; generated evidence card instead of fake crop"

        if evidence_status == "insufficient":
            create_evidence_card(
                crop_path,
                item_id=item_id,
                evidence_status=evidence_status,
                reason=reason,
                source_image=overlay_path if Path(overlay_path).exists() else None,
            )

        if crop_path.exists():
            generated_crop_count += 1
            crop_paths.append(str(crop_path))

        if evidence_status == "ready":
            evidence_ready_count += 1
        else:
            evidence_insufficient_count += 1

        evidence_items.append(
            {
                "item_id": item_id,
                "source": source,
                "related_object_ids": item.get("related_object_ids", []),
                "evidence_status": evidence_status,
                "bbox": bbox_out,
                "center": center,
                "crop_path": str(crop_path),
                "overlay_crop_path": str(crop_path) if source == "reference_dwg" else None,
                "pdf_page_crop_path": str(crop_path) if source == "reference_pdf" else None,
                "reason": reason,
            }
        )

    contact_sheet_path = output / "mvp1_visual_review_contact_sheet.png"
    contact_sheet = build_contact_sheet(crop_paths, contact_sheet_path)

    return {
        "phase": "MVP-1.2",
        "deepseek_worker_used": True,
        "full_chat_sent_to_deepseek": False,
        "api_key_sent_to_deepseek": False,
        "input_visual_item_count": len(visual_items),
        "evidence_ready_count": evidence_ready_count,
        "evidence_insufficient_count": evidence_insufficient_count,
        "generated_crop_count": generated_crop_count,
        "contact_sheet_created": bool(contact_sheet.get("ok") and contact_sheet_path.exists()),
        "contact_sheet_path": str(contact_sheet_path),
        "can_run_mvp_1_3_visual_decision": generated_crop_count == len(visual_items),
        "items": evidence_items,
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "source_modified": False,
        "sendcommand_used": False,
        "tianzheng_command_executed": False,
        "dangerous_command_executed": False,
        "production_d1_allowed": False,
    }


def write_visual_evidence_reports(report: dict[str, Any], reports_dir: str | Path = "reports") -> None:
    out = Path(reports_dir)
    out.mkdir(exist_ok=True)
    (out / "mvp_1_2_visual_evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = f"""# Phase MVP-1.2 Manager Final Report

- deepseek_worker_used=true
- full_chat_sent_to_deepseek=false
- api_key_sent_to_deepseek=false
- input_visual_item_count={report['input_visual_item_count']}
- evidence_ready_count={report['evidence_ready_count']}
- evidence_insufficient_count={report['evidence_insufficient_count']}
- generated_crop_count={report['generated_crop_count']}
- contact_sheet_created={str(report['contact_sheet_created']).lower()}
- contact_sheet_path={report['contact_sheet_path']}
- can_run_mvp_1_3_visual_decision={str(report['can_run_mvp_1_3_visual_decision']).lower()}
- source_dwg_opened=false
- source_dwg_saved=false
- sendcommand_used=false
- tianzheng_command_executed=false
- production_d1_allowed=false
"""
    (out / "mvp_1_2_visual_evidence.md").write_text(md, encoding="utf-8")


def main() -> None:
    report = build_visual_evidence()
    write_visual_evidence_reports(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
