from __future__ import annotations

from mcp.t30_writeback.models import T30ParameterSchema


CONFIRMED_SCHEMA_SOURCES = {"manual_probe", "fake_com"}


class T30ParameterSchemaRegistry:
    def __init__(self) -> None:
        self._schemas: dict[tuple[str, str], T30ParameterSchema] = {}

    def register_schema(self, schema: T30ParameterSchema) -> None:
        self._schemas[(schema.object_type, schema.method_name)] = schema

    def get_schema(self, object_type: str, method_name: str) -> T30ParameterSchema | None:
        return self._schemas.get((object_type, method_name))

    def is_schema_confirmed(self, object_type: str, method_name: str) -> bool:
        schema = self.get_schema(object_type, method_name)
        if schema is None:
            return False
        return schema.source in CONFIRMED_SCHEMA_SOURCES and schema.confidence >= 0.85

    def load_from_probe_result(self, probe_result: dict) -> None:
        for item in probe_result.get("schemas", []):
            self.register_schema(
                T30ParameterSchema(
                    object_type=str(item.get("object_type") or "Unknown"),
                    method_name=str(item.get("method_name") or "Insert"),
                    parameters=dict(item.get("parameters") or {}),
                    required_fields=list(item.get("required_fields") or []),
                    optional_fields=list(item.get("optional_fields") or []),
                    defaults=dict(item.get("defaults") or {}),
                    confidence=float(item.get("confidence") or 0.0),
                    source=str(item.get("source") or "unknown"),
                    warnings=list(item.get("warnings") or []),
                )
            )

    def export_schema_json(self) -> dict:
        return {"schemas": [schema.to_dict() for schema in self._schemas.values()]}


def build_fake_schema_registry() -> T30ParameterSchemaRegistry:
    registry = T30ParameterSchemaRegistry()
    schemas = {
        "TDbPipe": ["geometry", "system", "dn", "layer"],
        "TDbPipeValve": ["geometry", "system", "layer"],
        "TDbSprinkler": ["geometry", "system", "layer"],
        "TDbPipeFitting": ["geometry", "system", "layer"],
    }
    for object_type, required in schemas.items():
        registry.register_schema(
            T30ParameterSchema(
                object_type=object_type,
                method_name="Insert",
                parameters={field: "json" for field in required},
                required_fields=required,
                optional_fields=["metadata"],
                defaults={},
                confidence=1.0,
                source="fake_com",
            )
        )
    return registry

