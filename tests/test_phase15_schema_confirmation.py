from __future__ import annotations

import json


def _probe_result() -> dict:
    return {
        "capabilities": [
            {
                "capability_id": "TDbPipe.Insert",
                "object_type": "TDbPipe",
                "method_name": "Insert",
                "available": True,
                "probe_status": "confirmed",
            },
            {
                "capability_id": "TDbSprinkler.Insert",
                "object_type": "TDbSprinkler",
                "method_name": "Insert",
                "available": True,
                "probe_status": "unconfirmed",
            },
        ]
    }


def test_load_and_validate_manual_confirmation(tmp_path) -> None:
    from mcp.acceptance.schema_confirmation import load_and_validate_manual_confirmation

    path = tmp_path / "manual_confirmation.json"
    path.write_text(json.dumps({"TDbPipe.Insert": {"confirmed": False, "parameters": []}}), encoding="utf-8")

    result = load_and_validate_manual_confirmation(str(path))

    assert result["status"] == "success"
    assert result["manual_confirmation"]["TDbPipe.Insert"]["confirmed"] is False


def test_schema_confirmation_requires_probe_and_manual_confirmation() -> None:
    from mcp.acceptance.schema_confirmation import build_confirmed_schema_set

    manual = {
        "TDbPipe.Insert": {
            "confirmed": True,
            "parameters": [
                {"name": "geometry", "type": "json", "required": True},
                {"name": "dn", "type": "string", "required": True},
                {"name": "system", "type": "string", "required": True},
                {"name": "layer", "type": "string", "required": True},
            ],
        },
        "TDbSprinkler.Insert": {
            "confirmed": True,
            "parameters": [{"name": "geometry", "type": "json", "required": True}],
        },
        "TDbPipeValve.Insert": {
            "confirmed": True,
            "parameters": [{"name": "geometry", "type": "json", "required": True}],
        },
    }

    schema_set = build_confirmed_schema_set(_probe_result(), manual)

    assert schema_set.confirmed_object_types == ["TDbPipe"]
    assert "TDbSprinkler" in schema_set.unconfirmed_object_types
    assert "TDbPipeValve" in schema_set.unconfirmed_object_types


def test_probe_only_and_manual_only_do_not_confirm_schema() -> None:
    from mcp.acceptance.schema_confirmation import build_confirmed_schema_set

    probe_only = build_confirmed_schema_set(_probe_result(), {})
    manual_only = build_confirmed_schema_set(
        {"capabilities": []},
        {"TDbPipe.Insert": {"confirmed": True, "parameters": [{"name": "geometry", "required": True}]}},
    )

    assert probe_only.confirmed_object_types == []
    assert manual_only.confirmed_object_types == []

