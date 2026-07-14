from __future__ import annotations


GENERIC_CAPABILITIES = {
    "open_working_copy",
    "scan_acdb_entities",
    "create_acdb_line",
    "create_acdb_text",
    "create_acdb_polyline",
    "save_working_copy",
    "close_reopen",
    "persistence_qa",
    "command_completion_tracking",
    "in_process_transaction",
    "document_lock",
}

WATER_CAPABILITIES = {
    "scan_tianzheng_water_objects",
    "scan_tdb_pipe",
    "scan_tdb_valve",
    "scan_tdb_fitting",
    "scan_tianzheng_water_equipment",
    "create_tdb_pipe",
    "create_tdb_valve",
    "create_tdb_fitting",
    "create_tianzheng_water_equipment",
    "validate_water_pipe_network",
    "validate_water_equipment_connection",
    "official_tianzheng_api",
}

HVAC_RESERVED_CAPABILITIES = {
    "scan_tianzheng_hvac_objects",
    "create_tianzheng_hvac_object",
}

ALL_CAPABILITIES = GENERIC_CAPABILITIES | WATER_CAPABILITIES | HVAC_RESERVED_CAPABILITIES


def capability_map(**enabled: bool) -> dict[str, bool]:
    unknown = set(enabled) - ALL_CAPABILITIES
    if unknown:
        raise ValueError("unknown capabilities: " + ", ".join(sorted(unknown)))
    return {name: bool(enabled.get(name, False)) for name in sorted(ALL_CAPABILITIES)}
