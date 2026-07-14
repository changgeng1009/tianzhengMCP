from __future__ import annotations

from typing import Any


WATER_OBJECT_NAMES = {
    "TDbPipe": "pipe",
    "TDbDoubleLinePipe": "pipe",
    "TDbPipeValve": "valve",
    "TDbPipeFitting": "fitting",
    "TDbPump": "equipment",
    "TDbWaterTank": "equipment",
}


def normalize_water_object(entity: dict[str, Any]) -> dict[str, Any]:
    object_name = str(entity.get("object_name") or entity.get("ObjectName") or "")
    return {
        "professional_domain": "water_supply_and_drainage",
        "domain_object_type": WATER_OBJECT_NAMES.get(object_name, str(entity.get("object_type") or "unknown")),
        "system_type": str(entity.get("system_type") or entity.get("SysType") or "unknown_water_system"),
        "object_name": object_name,
        "geometry": dict(entity.get("geometry") or {}),
        "network": dict(entity.get("network") or {}),
    }
