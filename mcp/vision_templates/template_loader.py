from __future__ import annotations

from pathlib import Path

from mcp.vision_templates.models import VisionTemplate
from mcp.vision_templates.template_store import VisionTemplateStore, template_from_dict


def load_template_library(path: str) -> VisionTemplateStore:
    store = VisionTemplateStore()
    library_path = Path(path)
    if not library_path.exists():
        store.warnings.append(f"template library not found: {path}")
        return store
    try:
        import json

        data = json.loads(library_path.read_text(encoding="utf-8"))
    except Exception as exc:
        store.warnings.append(f"template library load failed: {exc}")
        return store
    for item in data.get("templates", []):
        try:
            template = template_from_dict(item)
            warnings = list(template.metadata.get("warnings", []))
            if template.image_path and not Path(template.image_path).exists():
                warnings.append(f"template image missing: {template.image_path}")
                template = VisionTemplate(
                    template_id=template.template_id,
                    template_type=template.template_type,
                    name=template.name,
                    image_path=template.image_path,
                    bbox=list(template.bbox),
                    keypoints=[list(point) for point in template.keypoints],
                    expected_symbol_type=template.expected_symbol_type,
                    metadata={**dict(template.metadata), "warnings": warnings},
                    confidence_baseline=template.confidence_baseline,
                    enabled=False,
                )
            store.register_template(template)
        except Exception as exc:
            store.warnings.append(f"template skipped: {exc}")
    return store

