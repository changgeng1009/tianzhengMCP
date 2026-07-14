from __future__ import annotations

from uuid import uuid4

from mcp.t30_writeback.models import T30WritebackAction
from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry


ACTION_TO_OBJECT_TYPE = {
    "add_pipe": "TDbPipe",
    "add_valve": "TDbPipeValve",
    "add_sprinkler": "TDbSprinkler",
    "add_fitting": "TDbPipeFitting",
}


def translate_repair_plan_to_t30_actions(
    repair_plan_v2: dict,
    schema_registry: T30ParameterSchemaRegistry,
    options: dict | None = None,
) -> list[T30WritebackAction]:
    actions: list[T30WritebackAction] = []
    for repair_action in repair_plan_v2.get("actions", []):
        if not repair_action.get("auto_execute"):
            continue
        action_type = repair_action.get("action_type") or repair_action.get("type")
        object_type = ACTION_TO_OBJECT_TYPE.get(str(action_type))
        if object_type is None:
            continue
        method_name = "Insert"
        schema = schema_registry.get_schema(object_type, method_name)
        warnings: list[str] = []
        if repair_action.get("target_space") != "cad_modelspace":
            warnings.append("geometry_not_cad_modelspace")
        geometry = dict(repair_action.get("geometry") or {})
        if object_type == "TDbPipe" and not (_has_pipe_geometry(geometry)):
            warnings.append("invalid_pipe_geometry")
        if schema is None:
            warnings.append("schema_missing")
            required_fields: list[str] = []
        else:
            required_fields = list(schema.required_fields)
            if not schema_registry.is_schema_confirmed(object_type, method_name):
                warnings.append("schema_not_confirmed")

        parameters = {
            "geometry": geometry,
            "system": repair_action.get("system") or repair_action.get("system_type"),
            "dn": repair_action.get("dn"),
            "layer": repair_action.get("layer"),
            "source_repair_action": repair_action,
        }
        for field in required_fields:
            if not parameters.get(field):
                warnings.append(f"missing_required_field:{field}")
        ready = not warnings
        actions.append(
            T30WritebackAction(
                action_id=f"t30_{uuid4().hex}",
                source_repair_action_id=str(repair_action.get("action_id") or ""),
                object_type=object_type,
                method_name=method_name,
                parameters=parameters,
                geometry=geometry,
                system=parameters["system"],
                dn=parameters["dn"],
                layer=parameters["layer"],
                confidence=float(repair_action.get("confidence") or 0.0),
                capability_status="confirmed" if schema_registry.is_schema_confirmed(object_type, method_name) else "unconfirmed",
                ready_to_execute=ready,
                warnings=warnings,
                metadata={"action_type": action_type, "options": dict(options or {})},
            )
        )
    return actions


def _has_pipe_geometry(geometry: dict) -> bool:
    return bool((geometry.get("start") and geometry.get("end")) or geometry.get("points"))

