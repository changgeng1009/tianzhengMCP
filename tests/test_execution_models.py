from execution.models import (
    ExecutionPlan,
    Operation,
    OperationStatus,
    OperationType,
    RiskLevel,
)


def test_delete_suggestion_operation_is_preview_only() -> None:
    operation = Operation(
        id="op_delete_1",
        action=OperationType.DELETE_SUGGESTION,
        entity_type="valve",
        geometry={},
        layer="0",
        reason="Current CAD 中存在，Reference 中不存在。",
        source_diff_id="diff_1",
        risk_level=RiskLevel.HIGH,
        requires_confirmation=True,
    )

    assert operation.executable is False
    assert operation.status == OperationStatus.PENDING
    assert operation.to_dict()["action"] == "delete_suggestion"


def test_execution_plan_marks_more_than_ten_operations_high_risk() -> None:
    operations = [
        Operation(
            id=f"op_{index}",
            action=OperationType.ADD_LINE,
            entity_type="pipe",
            geometry={"start": [0, index, 0], "end": [100, index, 0]},
            layer="0",
            reason="测试批量操作。",
            source_diff_id=f"diff_{index}",
            risk_level=RiskLevel.LOW,
            requires_confirmation=True,
        )
        for index in range(11)
    ]

    plan = ExecutionPlan(id="plan_high_risk", operations=operations)

    assert plan.risk_level == RiskLevel.HIGH
    assert all(operation.risk_level == RiskLevel.HIGH for operation in plan.operations)
    assert plan.confirmed is False
