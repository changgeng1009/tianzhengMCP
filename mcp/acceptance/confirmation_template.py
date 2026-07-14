from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


def generate_manual_confirmation_template(
    probe_result: dict,
    output_path: str | None = None,
) -> dict:
    warnings: list[str] = []
    template: dict[str, dict] = {}
    for capability in probe_result.get("capabilities", []):
        object_type = str(capability.get("object_type") or "Unknown")
        method_name = str(capability.get("method_name") or "Insert")
        key = f"{object_type}.{method_name}"
        template[key] = {
            "confirmed": False,
            "object_type": object_type,
            "method_name": method_name,
            "parameters": [],
            "notes": "Fill this after manual T30 COM verification",
            "probe_status": capability.get("probe_status"),
        }
    result = {
        "status": "success",
        "template_id": f"manual_tpl_{uuid4().hex}",
        "generated_from_probe": probe_result.get("metadata", {}).get("path", ""),
        "template": template,
        "warnings": warnings,
        "errors": [],
    }
    if output_path:
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            result["warnings"].append(f"template write failed: {exc}")
    return result

