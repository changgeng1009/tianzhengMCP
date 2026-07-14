from __future__ import annotations

from collections import Counter
from uuid import uuid4

from execution.models import ExecutionPlan, Operation, OperationStatus


class OperationQueue:
    def __init__(self) -> None:
        self._plans: dict[str, ExecutionPlan] = {}

    def create_plan(self, operations: list[Operation], plan_id: str | None = None) -> ExecutionPlan:
        plan = ExecutionPlan(id=plan_id or f"plan_{uuid4().hex}", operations=operations)
        self._plans[plan.id] = plan
        return plan

    def add_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        self._plans[plan.id] = plan
        return plan

    def get_plan(self, plan_id: str) -> ExecutionPlan:
        if plan_id not in self._plans:
            raise KeyError(f"execution plan not found: {plan_id}")
        return self._plans[plan_id]

    def add_operation(self, plan_id: str, operation: Operation) -> None:
        self.get_plan(plan_id).operations.append(operation)

    def list_operations(self, plan_id: str) -> list[dict]:
        return [operation.to_dict() for operation in self.get_plan(plan_id).operations]

    def preview_plan(self, plan_id: str) -> dict:
        plan = self.get_plan(plan_id)
        plan.previewed = True
        for operation in plan.operations:
            if operation.status == OperationStatus.PENDING:
                operation.status = OperationStatus.PREVIEWED
        return plan.to_dict()

    def mark_confirmed(self, plan_id: str) -> ExecutionPlan:
        plan = self.get_plan(plan_id)
        plan.confirmed = True
        for operation in plan.operations:
            if operation.status in {OperationStatus.PENDING, OperationStatus.PREVIEWED}:
                operation.status = OperationStatus.CONFIRMED
        return plan

    def mark_executed(self, plan_id: str, operation_id: str, result: dict) -> None:
        operation = self._operation(plan_id, operation_id)
        operation.status = OperationStatus.EXECUTED
        operation.result = dict(result)

    def mark_failed(self, plan_id: str, operation_id: str, error: str | dict) -> None:
        operation = self._operation(plan_id, operation_id)
        operation.status = OperationStatus.FAILED
        operation.result = error if isinstance(error, dict) else {"error": error}

    def mark_skipped(self, plan_id: str, operation_id: str, result: dict) -> None:
        operation = self._operation(plan_id, operation_id)
        operation.status = OperationStatus.SKIPPED
        operation.result = dict(result)

    def summarize(self, plan_id: str) -> dict:
        plan = self.get_plan(plan_id)
        counter = Counter(operation.status.value for operation in plan.operations)
        return {
            "plan_id": plan.id,
            "confirmed": plan.confirmed,
            "previewed": plan.previewed,
            "risk_level": plan.risk_level.value,
            "operation_count": len(plan.operations),
            "operations": dict(counter),
        }

    def _operation(self, plan_id: str, operation_id: str) -> Operation:
        for operation in self.get_plan(plan_id).operations:
            if operation.id == operation_id:
                return operation
        raise KeyError(f"operation not found: {operation_id}")
