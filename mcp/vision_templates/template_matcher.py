from __future__ import annotations

from uuid import uuid4

from mcp.vision_templates.models import TemplateMatch
from mcp.vision_templates.template_store import VisionTemplateStore


def match_templates(
    image,
    template_store: VisionTemplateStore,
    template_type: str | None = None,
    options: dict | None = None,
) -> list[TemplateMatch]:
    options = dict(options or {})
    warnings = options.setdefault("warnings", [])
    templates = [template for template in template_store.list_templates(template_type) if template.enabled]
    if not templates:
        warnings.append("no enabled templates available")
        return []

    fixture_matches = list(options.get("fixture_matches") or image.get("metadata", {}).get("template_fixture_matches", []) if isinstance(image, dict) else [])
    if fixture_matches:
        by_id = {template.template_id: template for template in templates}
        matches: list[TemplateMatch] = []
        threshold = float(options.get("threshold", 0.0))
        for item in fixture_matches:
            template = by_id.get(item.get("template_id"))
            confidence = float(item.get("confidence", template.confidence_baseline if template else 0.0))
            if template is None or confidence < threshold:
                continue
            bbox = [float(value) for value in item.get("bbox", template.bbox or [0, 0, 0, 0])]
            matches.append(
                TemplateMatch(
                    match_id=str(item.get("match_id") or f"match_{uuid4().hex}"),
                    template_id=template.template_id,
                    template_type=template.template_type,
                    bbox=bbox,
                    center=_center(bbox),
                    confidence=confidence,
                    method="fixture",
                    source_image=str(image.get("image_path", "")) if isinstance(image, dict) else "",
                    metadata={"expected_symbol_type": template.expected_symbol_type},
                )
            )
        return matches

    try:
        __import__("cv2")
    except ImportError:
        warnings.append("OpenCV not available; template matching skipped")
        return []
    warnings.append("OpenCV template matching requires real template images; skipped in conservative mode")
    return []


def _center(bbox: list[float]) -> list[float]:
    if len(bbox) < 4:
        return [0.0, 0.0]
    return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]

