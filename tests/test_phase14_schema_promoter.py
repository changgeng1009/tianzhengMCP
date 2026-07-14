from __future__ import annotations


def _probe_result() -> dict:
    return {
        "status": "success",
        "capabilities": [
            {
                "capability_id": "TDbPipe.Insert",
                "object_type": "TDbPipe",
                "method_name": "Insert",
                "available": True,
                "probe_status": "confirmed",
                "signature": {"parameters": ["start_point", "end_point", "dn", "system"]},
            }
        ],
    }


def test_schema_promoter_without_manual_confirmation_stays_unconfirmed() -> None:
    from mcp.e2e.schema_promoter import promote_probe_to_confirmed_schema

    result = promote_probe_to_confirmed_schema(_probe_result())

    assert result["schemas"][0]["source"] == "inferred"
    assert result["schemas"][0]["confidence"] < 0.85
    assert result["warnings"]


def test_schema_promoter_with_manual_confirmation_generates_confirmed_schema() -> None:
    from mcp.e2e.schema_promoter import promote_probe_to_confirmed_schema

    result = promote_probe_to_confirmed_schema(
        _probe_result(),
        {
            "TDbPipe.Insert": {
                "confirmed": True,
                "parameters": [
                    {"name": "geometry", "type": "json", "required": True},
                    {"name": "dn", "type": "string", "required": True},
                    {"name": "system", "type": "string", "required": True},
                    {"name": "layer", "type": "string", "required": True},
                ],
            }
        },
    )

    assert result["schemas"][0]["source"] == "manual_probe"
    assert "dn" in result["schemas"][0]["required_fields"]

