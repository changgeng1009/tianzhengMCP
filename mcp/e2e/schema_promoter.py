from __future__ import annotations


def promote_probe_to_confirmed_schema(
    probe_result: dict,
    manual_confirmation: dict | None = None,
) -> dict:
    manual_confirmation = dict(manual_confirmation or {})
    schemas: list[dict] = []
    warnings: list[str] = []
    for capability in probe_result.get("capabilities", []):
        object_type = str(capability.get("object_type") or "Unknown")
        method_name = str(capability.get("method_name") or "Insert")
        key = f"{object_type}.{method_name}"
        confirmation = dict(manual_confirmation.get(key) or {})
        confirmed = (
            capability.get("probe_status") == "confirmed"
            and capability.get("available") is True
            and confirmation.get("confirmed") is True
        )
        if confirmed:
            parameters = list(confirmation.get("parameters") or [])
            required_fields = [str(item["name"]) for item in parameters if item.get("required")]
            optional_fields = [str(item["name"]) for item in parameters if not item.get("required")]
            schema_parameters = {str(item["name"]): item.get("type", "unknown") for item in parameters}
            source = "manual_probe"
            confidence = 1.0
        else:
            signature_parameters = list((capability.get("signature") or {}).get("parameters") or [])
            schema_parameters = {str(name): "unknown" for name in signature_parameters}
            required_fields = []
            optional_fields = list(schema_parameters)
            source = "inferred"
            confidence = 0.5 if capability.get("probe_status") == "confirmed" else 0.0
            warnings.append(f"schema not confirmed by manual confirmation: {key}")
        schemas.append(
            {
                "object_type": object_type,
                "method_name": method_name,
                "parameters": schema_parameters,
                "required_fields": required_fields,
                "optional_fields": optional_fields,
                "defaults": {},
                "confidence": confidence,
                "source": source,
                "warnings": [] if confirmed else ["manual_confirmation_required"],
            }
        )
    return {"status": "success", "schemas": schemas, "warnings": warnings, "errors": []}

