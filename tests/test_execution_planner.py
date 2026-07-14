from execution.models import OperationType
from execution.planner import ExecutionPlanner


def test_diff_add_with_two_points_becomes_add_line() -> None:
    diff_result = {
        "items": [
            {
                "operation": "add",
                "entity_type": "pipe",
                "reference_entity_id": "ref_pipe_1",
                "reason": "Reference 中新增管线。",
                "entity": {
                    "id": "ref_pipe_1",
                    "type": "pipe",
                    "geometry": {
                        "coordinate_system": "cad_world",
                        "points": [
                            {"x": 0, "y": 0},
                            {"x": 5000, "y": 0},
                        ],
                    },
                    "properties": {"layer": "A-PIPE"},
                },
            }
        ]
    }

    plan = ExecutionPlanner().build_plan(diff_result)

    assert plan.operations[0].action == OperationType.ADD_LINE
    assert plan.operations[0].geometry == {
        "coordinate_system": "cad_world",
        "start": [0.0, 0.0, 0.0],
        "end": [5000.0, 0.0, 0.0],
    }
    assert plan.operations[0].layer == "A-PIPE"


def test_diff_move_becomes_move_entity_not_executed_in_mvp() -> None:
    diff_result = {
        "items": [
            {
                "operation": "move",
                "entity_type": "fixture",
                "reference_entity_id": "ref_fixture",
                "current_entity_id": "cad_fixture",
                "reason": "位置不同。",
                "changes": {"from": {"x_min": 0, "y_min": 0}, "to": {"x_min": 10, "y_min": 10}},
            }
        ]
    }

    plan = ExecutionPlanner().build_plan(diff_result)

    assert plan.operations[0].action == OperationType.MOVE_ENTITY
    assert plan.operations[0].executable is False


def test_delete_suggestion_is_preview_only() -> None:
    diff_result = {
        "items": [
            {
                "operation": "delete_suggestion",
                "entity_type": "valve",
                "current_entity_id": "cad_valve",
                "reason": "Reference 中未找到。",
                "entity": {"id": "cad_valve", "type": "valve"},
            }
        ]
    }

    plan = ExecutionPlanner().build_plan(diff_result)

    assert plan.operations[0].action == OperationType.DELETE_SUGGESTION
    assert plan.operations[0].executable is False
    assert plan.operations[0].requires_confirmation is True
