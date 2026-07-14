from __future__ import annotations

from typing import Any


DOMAIN_ID = "water_supply_and_drainage"

CAPABILITY_BY_OBJECT = {
    "line": ["create_acdb_line"],
    "acdbline": ["create_acdb_line"],
    "text": ["create_acdb_text"],
    "acdbtext": ["create_acdb_text"],
    "polyline": ["create_acdb_polyline"],
    "acdbpolyline": ["create_acdb_polyline"],
    "tdbpipe": ["create_tdb_pipe", "persistence_qa"],
    "tdb_pipe": ["create_tdb_pipe", "persistence_qa"],
    "tdbpipevalve": ["create_tdb_valve", "persistence_qa"],
    "tdb_valve": ["create_tdb_valve", "persistence_qa"],
    "tdbpipefitting": ["create_tdb_fitting", "persistence_qa"],
    "tdb_fitting": ["create_tdb_fitting", "persistence_qa"],
    "equipment": ["create_tianzheng_water_equipment", "persistence_qa"],
    "tdbpump": ["create_tianzheng_water_equipment", "persistence_qa"],
    "tdbwatertank": ["create_tianzheng_water_equipment", "persistence_qa"],
}

SUPPORTED_SYSTEM_TYPES = {
    "water_supply",
    "drainage",
    "fire_protection",
    "sprinkler",
    "hydrant",
    "unknown_water_system",
}


class WaterSupplyAndDrainageDomain:
    domain_id = DOMAIN_ID
    status = "active"

    def capability_requirements(self, task: dict[str, Any]) -> list[str]:
        existing = list(task.get("required_capabilities") or [])
        if existing:
            return existing
        key = str(task.get("domain_object_type") or task.get("object_type") or "").replace(" ", "").lower()
        return list(CAPABILITY_BY_OBJECT.get(key, []))

    def enrich_task(self, task: dict[str, Any]) -> dict[str, Any]:
        result = dict(task)
        object_type = str(result.get("object_type") or "unknown")
        result["professional_domain"] = DOMAIN_ID
        result["system_type"] = str(result.get("system_type") or (result.get("semantic") or {}).get("system_type") or "unknown_water_system")
        result["domain_object_type"] = str(result.get("domain_object_type") or object_type)
        result["required_capabilities"] = self.capability_requirements(result)
        if not result.get("fallback_policy"):
            result["fallback_policy"] = "manual_tianzheng" if object_type.lower().startswith("tdb") else "blocked"
        return result

    def validate_task(self, task: dict[str, Any]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if task.get("professional_domain", DOMAIN_ID) != DOMAIN_ID:
            errors.append("professional_domain must be water_supply_and_drainage")
        system_type = str(task.get("system_type") or "unknown_water_system")
        if system_type not in SUPPORTED_SYSTEM_TYPES:
            errors.append("unsupported water system_type")
        if not self.capability_requirements(task):
            errors.append("no capability mapping for domain object type")
        return not errors, errors
