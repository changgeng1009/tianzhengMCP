from __future__ import annotations


def _confirmed_registry():
    from mcp.t30_writeback.models import T30ParameterSchema
    from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry

    registry = T30ParameterSchemaRegistry()
    for object_type in ["TDbPipe", "TDbPipeValve", "TDbSprinkler", "TDbPipeFitting"]:
        registry.register_schema(
            T30ParameterSchema(
                object_type=object_type,
                method_name="Insert",
                parameters={},
                required_fields=["geometry", "system", "dn", "layer"] if object_type == "TDbPipe" else ["geometry", "system", "layer"],
                optional_fields=[],
                defaults={},
                confidence=1.0,
                source="fake_com",
            )
        )
    return registry


def test_translate_repair_plan_v2_to_ready_t30_actions() -> None:
    from mcp.t30_writeback.action_translator import translate_repair_plan_to_t30_actions

    repair_plan = {
        "actions": [
            {
                "action_id": "repair_pipe_1",
                "action_type": "add_pipe",
                "target_space": "cad_modelspace",
                "geometry": {"start": [0, 0, 0], "end": [100, 0, 0]},
                "system": "给水",
                "dn": "DN50",
                "layer": "PIPE",
                "confidence": 0.91,
                "auto_execute": True,
            }
        ],
        "review_actions": [{"action_id": "review_1", "auto_execute": False}],
        "rejected_actions": [],
    }

    actions = translate_repair_plan_to_t30_actions(repair_plan, _confirmed_registry())

    assert len(actions) == 1
    assert actions[0].object_type == "TDbPipe"
    assert actions[0].ready_to_execute is True


def test_translate_blocks_unconfirmed_schema_and_missing_fields() -> None:
    from mcp.t30_writeback.action_translator import translate_repair_plan_to_t30_actions
    from mcp.t30_writeback.models import T30ParameterSchema
    from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry

    registry = T30ParameterSchemaRegistry()
    registry.register_schema(
        T30ParameterSchema(
            object_type="TDbPipe",
            method_name="Insert",
            parameters={},
            required_fields=["geometry", "system", "dn", "layer"],
            optional_fields=[],
            defaults={},
            confidence=0.5,
            source="inferred",
        )
    )
    repair_plan = {
        "actions": [
            {
                "action_id": "repair_pipe_1",
                "action_type": "add_pipe",
                "target_space": "cad_modelspace",
                "geometry": {"start": [0, 0, 0], "end": [100, 0, 0]},
                "system": "给水",
                "layer": "PIPE",
                "confidence": 0.91,
                "auto_execute": True,
            }
        ]
    }

    actions = translate_repair_plan_to_t30_actions(repair_plan, registry)

    assert actions[0].ready_to_execute is False
    assert "schema_not_confirmed" in actions[0].warnings
    assert "missing_required_field:dn" in actions[0].warnings

