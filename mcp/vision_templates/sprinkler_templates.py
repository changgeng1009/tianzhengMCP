from __future__ import annotations

from mcp.vision_templates.models import VisionTemplate
from mcp.vision_templates.template_store import VisionTemplateStore


def build_default_sprinkler_template_store() -> VisionTemplateStore:
    store = VisionTemplateStore()
    for template_id, name in [
        ("sprinkler_upright", "直立型喷头"),
        ("sprinkler_pendent", "下垂型喷头"),
        ("sprinkler_sidewall", "边墙型喷头"),
    ]:
        store.register_template(
            VisionTemplate(
                template_id=template_id,
                template_type="sprinkler",
                name=name,
                expected_symbol_type="sprinkler_candidate",
                metadata={"status": "metadata_only", "warnings": ["real template image not provided"]},
                enabled=False,
            )
        )
    return store

