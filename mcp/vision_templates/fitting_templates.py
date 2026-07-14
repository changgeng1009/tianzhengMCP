from __future__ import annotations

from mcp.vision_templates.models import VisionTemplate
from mcp.vision_templates.template_store import VisionTemplateStore


def build_default_fitting_template_store() -> VisionTemplateStore:
    store = VisionTemplateStore()
    for template_id, name in [
        ("fitting_elbow", "弯头"),
        ("fitting_tee", "三通"),
        ("fitting_cross", "四通"),
        ("fitting_reducer", "变径"),
        ("fitting_cap", "管帽"),
    ]:
        store.register_template(
            VisionTemplate(
                template_id=template_id,
                template_type="fitting",
                name=name,
                expected_symbol_type="fitting_candidate",
                metadata={"status": "metadata_only", "warnings": ["real template image not provided"]},
                enabled=False,
            )
        )
    return store

