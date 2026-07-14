import json

from execution.models import Operation, OperationType, RiskLevel
from execution.queue import OperationQueue
from tools import execution as execution_tools


class FakeCADExecutor:
    def __init__(self) -> None:
        self.calls: list[Operation] = []

    def execute(self, operation: Operation) -> dict:
        self.calls.append(operation)
        if operation.action == OperationType.ADD_LINE:
            return {"success": True, "handle": "2CF", "object_name": "AcDbLine"}
        return {"success": False, "status": "not_implemented"}


def test_generate_preview_confirm_and_execute_plan_with_fake_executor() -> None:
    queue = OperationQueue()
    execution_tools.operation_queue = queue
    execution_tools.cad_executor = FakeCADExecutor()
    diff_result = {
        "items": [
            {
                "operation": "add",
                "entity_type": "pipe",
                "reference_entity_id": "ref_pipe_1",
                "reason": "新增线段。",
                "entity": {
                    "id": "ref_pipe_1",
                    "type": "pipe",
                    "geometry": {
                        "coordinate_system": "cad_world",
                        "points": [{"x": 0, "y": 0}, {"x": 5000, "y": 0}],
                    },
                    "properties": {"layer": "A-PIPE"},
                },
            }
        ]
    }

    generated = execution_tools.generate_execution_plan(json.dumps(diff_result))
    preview = execution_tools.preview_execution_plan(generated["plan_id"])
    blocked = execution_tools.execute_execution_plan(generated["plan_id"])
    plan = queue.get_plan(generated["plan_id"])
    plan.operations[0].mapping_confidence = 0.99
    plan.operations[0].calibration_id = "cal_test"
    plan.operations[0].transform_type = "affine"
    confirmed = execution_tools.confirm_execution_plan(generated["plan_id"])
    executed = execution_tools.execute_execution_plan(generated["plan_id"])

    assert preview["plan"]["operations"][0]["action"] == "add_line"
    assert blocked["success"] is False
    assert "not confirmed" in blocked["message"]
    assert confirmed["confirmed"] is True
    assert executed["success"] is True
    assert executed["results"][0]["handle"] == "2CF"


def test_delete_suggestion_is_never_executed() -> None:
    queue = OperationQueue()
    execution_tools.operation_queue = queue
    execution_tools.cad_executor = FakeCADExecutor()
    plan = queue.create_plan(
        [
            Operation(
                id="op_delete",
                action=OperationType.DELETE_SUGGESTION,
                entity_type="valve",
                geometry={},
                layer="0",
                reason="仅建议删除。",
                source_diff_id="diff_delete",
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
            )
        ]
    )
    queue.preview_plan(plan.id)
    queue.mark_confirmed(plan.id)

    result = execution_tools.execute_execution_plan(plan.id)

    assert result["success"] is True
    assert result["results"][0]["status"] == "not_executable"
    assert result["results"][0]["action"] == "delete_suggestion"


def test_reference_coordinates_cannot_execute_without_mapping() -> None:
    queue = OperationQueue()
    execution_tools.operation_queue = queue
    execution_tools.cad_executor = FakeCADExecutor()
    plan = queue.create_plan(
        [
            Operation(
                id="op_reference_line",
                action=OperationType.ADD_LINE,
                entity_type="pipe",
                geometry={
                    "coordinate_system": "normalized",
                    "start": [0.0, 0.0, 0.0],
                    "end": [1.0, 0.0, 0.0],
                },
                layer="0",
                reason="尚未映射的 reference 坐标。",
                source_diff_id="diff_reference",
                risk_level=RiskLevel.LOW,
                requires_confirmation=True,
            )
        ]
    )
    queue.preview_plan(plan.id)
    queue.mark_confirmed(plan.id)

    result = execution_tools.execute_execution_plan(plan.id)

    assert result["success"] is False
    assert result["message"] == "Coordinate mapping is not calibrated."
