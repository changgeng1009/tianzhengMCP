from __future__ import annotations

import tools.execution as execution_tools
from execution.models import ExecutionPlan, Operation
from execution.queue import OperationQueue


class FakeCADExecutor:
    def __init__(self) -> None:
        self.executed_operation_ids: list[str] = []

    def execute(self, operation: Operation) -> dict:
        self.executed_operation_ids.append(operation.id)
        return {
            "success": True,
            "entity_type": operation.entity_type,
            "object_name": "AcDbLine",
            "handle": "FAKE1",
        }


def _mapped_line_operation(**overrides):
    data = {
        "id": "op_line",
        "action": "add_line",
        "entity_type": "Line",
        "geometry": {
            "coordinate_system": "cad_world",
            "start": [0.0, 0.0, 0.0],
            "end": [5000.0, 0.0, 0.0],
        },
        "layer": "0",
        "reason": "mapped cad_world line",
        "source_diff_id": "diff_line",
        "risk_level": "low",
        "requires_confirmation": True,
        "mapping_confidence": 0.99,
        "calibration_id": "cal_test",
        "transform_type": "affine",
    }
    data.update(overrides)
    return Operation(**data)


def _install_fake_queue_and_executor(monkeypatch, plan: ExecutionPlan, executor: FakeCADExecutor):
    queue = OperationQueue()
    queue.add_plan(plan)
    monkeypatch.setattr(execution_tools, "operation_queue", queue)
    monkeypatch.setattr(execution_tools, "cad_executor", executor)
    monkeypatch.setattr(
        execution_tools.default_manager,
        "status",
        lambda: {"active_document": "FakeDrawing.dwg"},
    )
    return queue


def test_unconfirmed_mapped_plan_cannot_execute(monkeypatch):
    plan = ExecutionPlan(id="plan_unconfirmed", operations=[_mapped_line_operation()])
    queue = _install_fake_queue_and_executor(monkeypatch, plan, FakeCADExecutor())
    queue.preview_plan(plan.id)

    result = execution_tools.execute_execution_plan(plan.id)

    assert result["success"] is False
    assert "not confirmed" in result["message"]


def test_confirmed_mapped_cad_world_plan_executes_with_fake_cad(monkeypatch):
    executor = FakeCADExecutor()
    plan = ExecutionPlan(id="plan_confirmed", operations=[_mapped_line_operation()])
    queue = _install_fake_queue_and_executor(monkeypatch, plan, executor)
    queue.preview_plan(plan.id)
    queue.mark_confirmed(plan.id)

    result = execution_tools.execute_execution_plan(plan.id)

    assert result["success"] is True
    assert result["results"][0]["handle"] == "FAKE1"
    assert executor.executed_operation_ids == ["op_line"]


def test_delete_suggestion_is_not_executed_even_when_plan_is_confirmed(monkeypatch):
    executor = FakeCADExecutor()
    delete_operation = _mapped_line_operation(
        id="op_delete",
        action="delete_suggestion",
        entity_type="Valve",
        reason="obsolete entity suggestion",
    )
    plan = ExecutionPlan(id="plan_delete", operations=[delete_operation])
    queue = _install_fake_queue_and_executor(monkeypatch, plan, executor)
    queue.preview_plan(plan.id)
    queue.mark_confirmed(plan.id)

    result = execution_tools.execute_execution_plan(plan.id)

    assert result["success"] is True
    assert result["results"][0]["status"] == "not_executable"
    assert executor.executed_operation_ids == []


def test_execute_mapped_execution_plan_returns_preview_until_confirmed(monkeypatch):
    executor = FakeCADExecutor()
    monkeypatch.setattr(execution_tools, "operation_queue", OperationQueue())
    monkeypatch.setattr(execution_tools, "cad_executor", executor)
    payload = ExecutionPlan(
        id="plan_tool_preview",
        operations=[_mapped_line_operation()],
    ).to_dict()

    result = execution_tools.execute_mapped_execution_plan(payload)

    assert result["success"] is True
    assert result["executed"] is False
    assert result["plan"]["previewed"] is True
    assert executor.executed_operation_ids == []


def test_execute_mapped_execution_plan_executes_after_confirmation(monkeypatch):
    executor = FakeCADExecutor()
    monkeypatch.setattr(execution_tools, "operation_queue", OperationQueue())
    monkeypatch.setattr(execution_tools, "cad_executor", executor)
    monkeypatch.setattr(
        execution_tools.default_manager,
        "status",
        lambda: {"active_document": "FakeDrawing.dwg"},
    )
    payload = ExecutionPlan(
        id="plan_tool_execute",
        operations=[_mapped_line_operation()],
    ).to_dict()

    result = execution_tools.execute_mapped_execution_plan(payload, confirmed=True)

    assert result["success"] is True
    assert result["results"][0]["handle"] == "FAKE1"
    assert executor.executed_operation_ids == ["op_line"]
