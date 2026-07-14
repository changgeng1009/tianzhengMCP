from __future__ import annotations

from mcp.vision_templates.models import VisionTemplate
from mcp.vision_templates.template_store import VisionTemplateStore


def build_default_legend_template_store() -> VisionTemplateStore:
    store = VisionTemplateStore()
    for template_id, name in [
        ("legend_sprinkler_pipe", "喷淋管"),
        ("legend_fire_hydrant_pipe", "消火栓管"),
        ("legend_domestic_water_pipe", "给水管"),
        ("legend_drainage_pipe", "排水管"),
        ("legend_valve", "阀门图例"),
        ("legend_sprinkler", "喷头图例"),
    ]:
        store.register_template(
            VisionTemplate(
                template_id=template_id,
                template_type="legend",
                name=name,
                expected_symbol_type="legend_candidate",
                metadata={"status": "metadata_only", "warnings": ["real template image not provided"]},
                enabled=False,
            )
        )
    return store

