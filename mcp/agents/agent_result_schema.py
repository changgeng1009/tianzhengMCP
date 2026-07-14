from __future__ import annotations

from copy import deepcopy
from typing import Any


VALID_STATUSES = {"PASS", "PARTIAL", "FAIL", "BLOCKED"}

DEFAULT_SAFETY_RESULT: dict[str, bool] = {
    "api_key_logged": False,
    "full_chat_sent": False,
    "opened_source_dwg": False,
    "saved_source_dwg": False,
    "used_sendcommand": False,
    "executed_tianzheng_command": False,
}

RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "phase",
        "status",
        "files_modified",
        "tests_run",
        "test_result",
        "safety_result",
        "notes",
        "next_recommendation",
    ],
    "properties": {
        "phase": {"type": "string"},
        "status": {"type": "string", "enum": sorted(VALID_STATUSES)},
        "files_modified": {"type": "array", "items": {"type": "string"}},
        "tests_run": {"type": "array", "items": {"type": "string"}},
        "test_result": {"type": "string"},
        "safety_result": {
            "type": "object",
            "required": list(DEFAULT_SAFETY_RESULT.keys()),
            "properties": {key: {"type": "boolean"} for key in DEFAULT_SAFETY_RESULT},
        },
        "notes": {"type": "array", "items": {"type": "string"}},
        "next_recommendation": {"type": "string"},
    },
}


def default_result(phase: str, status: str = "BLOCKED", note: str | None = None) -> dict[str, Any]:
    result = {
        "phase": phase,
        "status": status,
        "files_modified": [],
        "tests_run": [],
        "test_result": "",
        "safety_result": deepcopy(DEFAULT_SAFETY_RESULT),
        "notes": [],
        "next_recommendation": "",
    }
    if note:
        result["notes"].append(note)
    return result


def validate_agent_result(result: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for key in RESULT_SCHEMA["required"]:
        if key not in result:
            errors.append(f"missing result field: {key}")

    if result.get("status") not in VALID_STATUSES:
        errors.append("invalid status")

    for list_key in ("files_modified", "tests_run", "notes"):
        if list_key in result and not isinstance(result[list_key], list):
            errors.append(f"{list_key} must be a list")

    safety_result = result.get("safety_result")
    if not isinstance(safety_result, dict):
        errors.append("safety_result must be an object")
    else:
        for key in DEFAULT_SAFETY_RESULT:
            if key not in safety_result:
                errors.append(f"missing safety_result field: {key}")
            elif not isinstance(safety_result[key], bool):
                errors.append(f"safety_result.{key} must be boolean")

    return not errors, errors

