from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from mcp.acceptance.models import ConfirmedSchemaSet


def load_and_validate_manual_confirmation(path: str) -> dict:
    confirmation_path = Path(path)
    if not confirmation_path.exists():
        return {"status": "failed", "manual_confirmation": {}, "warnings": [], "errors": [f"manual confirmation not found: {path}"]}
    try:
        payload = json.loads(confirmation_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "failed", "manual_confirmation": {}, "warnings": [], "errors": [str(exc)]}
    errors: list[str] = []
    if not isinstance(payload, dict):
        errors.append("manual confirmation must be a JSON object")
    for key, item in payload.items() if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            errors.append(f"confirmation item must be object: {key}")
        elif "confirmed" not in item:
            errors.append(f"confirmation item missing confirmed flag: {key}")
    return {
        "status": "success" if not errors else "failed",
        "manual_confirmation": payload if isinstance(payload, dict) else {},
        "warnings": [],
        "errors": errors,
    }


def build_confirmed_schema_set(
    probe_result: dict,
    manual_confirmation: dict,
) -> ConfirmedSchemaSet:
    capabilities = {
        f"{capability.get('object_type')}.{capability.get('method_name')}": capability
        for capability in probe_result.get("capabilities", [])
    }
    schemas: list[dict] = []
    confirmed_object_types: list[str] = []
    unconfirmed_object_types: list[str] = []
    warnings: list[str] = []
    all_keys = list(dict.fromkeys(list(capabilities.keys()) + list(manual_confirmation.keys())))
    for key in all_keys:
        capability = dict(capabilities.get(key) or {})
        confirmation = dict(manual_confirmation.get(key) or {})
        object_type = str(capability.get("object_type") or confirmation.get("object_type") or key.split(".")[0])
        method_name = str(capability.get("method_name") or confirmation.get("method_name") or key.split(".")[-1])
        parameters = list(confirmation.get("parameters") or [])
        can_confirm = (
            bool(capability)
            and capability.get("probe_status") == "confirmed"
            and capability.get("available") is True
            and confirmation.get("confirmed") is True
            and bool(parameters)
            and any(param.get("required") for param in parameters)
        )
        if can_confirm:
            required_fields = [str(param["name"]) for param in parameters if param.get("required")]
            optional_fields = [str(param["name"]) for param in parameters if not param.get("required")]
            schemas.append(
                {
                    "object_type": object_type,
                    "method_name": method_name,
                    "parameters": {str(param["name"]): param.get("type", "unknown") for param in parameters},
                    "required_fields": required_fields,
                    "optional_fields": optional_fields,
                    "defaults": {},
                    "confidence": 1.0,
                    "source": "manual_probe",
                    "warnings": [],
                }
            )
            confirmed_object_types.append(object_type)
        else:
            unconfirmed_object_types.append(object_type)
            warnings.append(f"schema not confirmed: {key}")
    return ConfirmedSchemaSet(
        schema_set_id=f"schema_set_{uuid4().hex}",
        schemas=schemas,
        confirmed_object_types=_unique(confirmed_object_types),
        unconfirmed_object_types=_unique(unconfirmed_object_types),
        warnings=warnings,
        errors=[],
        metadata={"total_capabilities": len(capabilities)},
    )


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result

