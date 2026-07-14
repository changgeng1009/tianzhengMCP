from execution.models import Operation, OperationType, RiskLevel
from execution.queue import OperationQueue


def _operation(operation_id: str = "op_1") -> Operation:
    return Operation(
        id=operation_id,
        action=OperationType.ADD_LINE,
        entity_type="pipe",
        geometry={"start": [0, 0, 0], "end": [5000, 0, 0]},
        layer="0",
        reason="测试操作。",
        source_diff_id="diff_1",
        risk_level=RiskLevel.LOW,
        requires_confirmation=True,
    )


def test_queue_tracks_operation_lifecycle() -> None:
    queue = OperationQueue()
    plan = queue.create_plan([_operation()])

    assert queue.preview_plan(plan.id)["confirmed"] is False

    queue.mark_confirmed(plan.id)
    queue.mark_executed(plan.id, "op_1", {"handle": "2CF"})

    summary = queue.summarize(plan.id)

    assert summary["confirmed"] is True
    assert summary["operations"]["executed"] == 1


def test_queue_records_failed_operation() -> None:
    queue = OperationQueue()
    plan = queue.create_plan([_operation()])
    queue.mark_confirmed(plan.id)

    queue.mark_failed(plan.id, "op_1", "COM failure")

    operation = queue.get_plan(plan.id).operations[0]
    assert operation.status.value == "failed"
    assert operation.result["error"] == "COM failure"
