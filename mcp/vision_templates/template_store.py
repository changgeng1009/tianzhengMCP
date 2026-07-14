from __future__ import annotations

import json
from pathlib import Path

from mcp.vision_templates.models import VisionTemplate


class VisionTemplateStore:
    def __init__(self) -> None:
        self._templates: dict[str, VisionTemplate] = {}
        self.warnings: list[str] = []

    def register_template(self, template: VisionTemplate) -> None:
        self._templates[template.template_id] = template

    def list_templates(self, template_type: str | None = None) -> list[VisionTemplate]:
        templates = list(self._templates.values())
        if template_type:
            templates = [template for template in templates if template.template_type == template_type]
        return templates

    def get_template(self, template_id: str) -> VisionTemplate | None:
        template = self._templates.get(template_id)
        if template is None:
            self.warnings.append(f"template not found: {template_id}")
        return template

    def enable_template(self, template_id: str) -> None:
        self._set_enabled(template_id, True)

    def disable_template(self, template_id: str) -> None:
        self._set_enabled(template_id, False)

    def export_templates_json(self) -> dict:
        return {
            "templates": [template.to_dict() for template in self._templates.values()],
            "warnings": list(self.warnings),
        }

    def load_templates_json(self, path: str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in data.get("templates", []):
            self.register_template(template_from_dict(item))

    def _set_enabled(self, template_id: str, enabled: bool) -> None:
        template = self.get_template(template_id)
        if template is None:
            return
        self._templates[template_id] = VisionTemplate(
            template_id=template.template_id,
            template_type=template.template_type,
            name=template.name,
            image_path=template.image_path,
            bbox=list(template.bbox),
            keypoints=[list(point) for point in template.keypoints],
            expected_symbol_type=template.expected_symbol_type,
            metadata=dict(template.metadata),
            confidence_baseline=template.confidence_baseline,
            enabled=enabled,
        )


def template_from_dict(data: dict) -> VisionTemplate:
    return VisionTemplate(
        template_id=str(data.get("template_id") or ""),
        template_type=str(data.get("template_type") or ""),
        name=str(data.get("name") or ""),
        image_path=data.get("image_path"),
        bbox=list(data.get("bbox") or []),
        keypoints=[list(point) for point in data.get("keypoints") or []],
        expected_symbol_type=data.get("expected_symbol_type"),
        metadata=dict(data.get("metadata") or {}),
        confidence_baseline=float(data.get("confidence_baseline") or 0.5),
        enabled=bool(data.get("enabled", True)),
    )

