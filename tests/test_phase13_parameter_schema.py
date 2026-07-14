from __future__ import annotations


def test_schema_registry_register_query_and_export() -> None:
    from mcp.t30_writeback.models import T30ParameterSchema
    from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry

    registry = T30ParameterSchemaRegistry()
    schema = T30ParameterSchema(
        object_type="TDbPipe",
        method_name="Insert",
        parameters={"start": "point3d"},
        required_fields=["start", "end", "dn", "system", "layer"],
        optional_fields=[],
        defaults={},
        confidence=1.0,
        source="fake_com",
    )
    registry.register_schema(schema)

    assert registry.get_schema("TDbPipe", "Insert") is schema
    assert registry.export_schema_json()["schemas"][0]["object_type"] == "TDbPipe"


def test_unconfirmed_schema_is_not_executable() -> None:
    from mcp.t30_writeback.models import T30ParameterSchema
    from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry

    registry = T30ParameterSchemaRegistry()
    registry.register_schema(
        T30ParameterSchema(
            object_type="TDbPipe",
            method_name="Insert",
            parameters={},
            required_fields=["start"],
            optional_fields=[],
            defaults={},
            confidence=0.4,
            source="inferred",
        )
    )

    assert registry.is_schema_confirmed("TDbPipe", "Insert") is False

