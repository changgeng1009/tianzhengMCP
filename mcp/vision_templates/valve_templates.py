from __future__ import annotations

from mcp.vision_templates.models import VisionTemplate
from mcp.vision_templates.template_store import VisionTemplateStore


def build_default_valve_template_store() -> VisionTemplateStore:
    store = VisionTemplateStore()
    for template_id, name in [
        ("valve_gate", "闸阀"),
        ("valve_stop", "截止阀"),
        ("valve_check", "止回阀"),
        ("valve_butterfly", "蝶阀"),
        ("valve_signal", "信号阀"),
        ("valve_wet_alarm", "湿式报警阀"),
    ]:
        store.register_template(
            VisionTemplate(
                template_id=template_id,
                template_type="valve",
                name=name,
                expected_symbol_type="valve_candidate",
                metadata={"status": "metadata_only", "warnings": ["real template image not provided"]},
                enabled=False,
            )
        )
    return store

