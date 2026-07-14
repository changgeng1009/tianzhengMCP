import json
import logging
from typing import Any

from cad.connection import default_manager
from execution.executor import CADOperationExecutor
from execution.models import ExecutionPlan, ExecutionResult, Operation
from execution.planner import ExecutionPlanner
from execution.queue import OperationQueue
from execution.validation import validate_mapped_execution_plan


logger = logging.getLogger(__name__)


operation_queue = OperationQueue()
cad_executor = CADOperationExecutor()


def generate_execution_plan(diff_result_json: str) -> dict[str, Any]:
    """从 Diff Result JSON 生成安全执行计划。"""
    logger.info("generate_execution_plan called")
    diff_result = json.loads(diff_result_json)
    plan = ExecutionPlanner().build_plan(diff_result)
    operation_queue.add_plan(plan)
    return {
        "success": True,
        "plan_id": plan.id,
        "plan": plan.to_dict(),
    }


def preview_execution_plan(plan_id: str) -> dict[str, Any]:
    """预览执行计划，不执行任何 CAD 操作。"""
    logger.info("preview_execution_plan called: plan_id=%s", plan_id)
    try:
        return {
            "success": True,
            "plan": operation_queue.preview_plan(plan_id),
        }
    except Exception as exc:
        logger.exception("preview_execution_plan failed")
        return {"success": False, "error": str(exc)}


def confirm_execution_plan(plan_id: str) -> dict[str, Any]:
    """确认执行计划。未确认计划禁止执行。"""
    logger.info("confirm_execution_plan called: plan_id=%s", plan_id)
    try:
        plan = operation_queue.mark_confirmed(plan_id)
        return {
            "success": True,
            "confirmed": True,
            "plan_id": plan.id,
            "summary": operation_queue.summarize(plan.id),
        }
    except Exception as exc:
        logger.exception("confirm_execution_plan failed")
        return {"success": False, "confirmed": False, "error": str(exc)}


def execute_execution_plan(plan_id: str, allow_high_risk: bool = False) -> dict[str, Any]:
    """执行已预览且已确认的安全执行计划。"""
    logger.info("execute_execution_plan called: plan_id=%s", plan_id)
    try:
        plan = operation_queue.get_plan(plan_id)
        if not plan.previewed:
            return {
                "success": False,
                "message": "Execution plan has not been previewed. Preview is required before execution.",
            }
        if not plan.confirmed:
            return {
                "success": False,
                "message": "Execution plan is not confirmed. Confirmation is required before execution.",
            }
        validation = validate_mapped_execution_plan(plan, allow_high_risk=allow_high_risk)
        if not validation["valid"]:
            return {
                "success": False,
                "message": validation["message"],
                "validation": validation,
            }

        plan.active_document = default_manager.status().get("active_document")
        results: list[dict[str, Any]] = []
        for operation in plan.operations:
            if not operation.executable:
                result = {
                    "operation_id": operation.id,
                    "action": operation.action.value,
                    "success": False,
                    "status": "not_executable",
                    "message": f"{operation.action.value} cannot be automatically executed in Phase 4.",
                }
                operation_queue.mark_skipped(plan.id, operation.id, result)
                results.append(result)
                continue

            result = cad_executor.execute(operation)
            result = {"operation_id": operation.id, "action": operation.action.value, **result}
            if result.get("success"):
                operation_queue.mark_executed(plan.id, operation.id, result)
            else:
                operation_queue.mark_failed(plan.id, operation.id, result)
            results.append(result)

        return ExecutionResult(
            plan_id=plan.id,
            success=True,
            active_document=plan.active_document,
            results=results,
        ).to_dict()
    except Exception as exc:
        logger.exception("execute_execution_plan failed")
        return {"success": False, "error": str(exc)}


def execute_mapped_execution_plan(
    plan_json: str | dict[str, Any],
    confirmed: bool = False,
    allow_high_risk: bool = False,
) -> dict[str, Any]:
    """加载 mapped ExecutionPlan；默认只预览，确认后才执行真实 CAD 操作。"""
    logger.info(
        "execute_mapped_execution_plan called: confirmed=%s allow_high_risk=%s",
        confirmed,
        allow_high_risk,
    )
    try:
        payload = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
        plan = _plan_from_dict(payload)
        operation_queue.add_plan(plan)
        preview = operation_queue.preview_plan(plan.id)

        validation = validate_mapped_execution_plan(plan, allow_high_risk=allow_high_risk)
        if not validation["valid"]:
            return {
                "success": False,
                "executed": False,
                "plan_id": plan.id,
                "message": validation["message"],
                "validation": validation,
                "plan": preview,
            }

        if not confirmed:
            return {
                "success": True,
                "executed": False,
                "plan_id": plan.id,
                "message": "Execution plan previewed. Confirmation is required before execution.",
                "validation": validation,
                "plan": preview,
            }

        operation_queue.mark_confirmed(plan.id)
        return execute_execution_plan(plan.id, allow_high_risk=allow_high_risk)
    except Exception as exc:
        logger.exception("execute_mapped_execution_plan failed")
        return {"success": False, "executed": False, "error": str(exc)}


def _plan_from_dict(payload: dict[str, Any]) -> ExecutionPlan:
    plan_id = payload.get("id") or payload.get("plan_id")
    mapping = payload.get("coordinate_mapping") or {}
    operations = [
        _operation_from_dict(operation_payload, mapping)
        for operation_payload in payload.get("operations", [])
    ]
    return ExecutionPlan(
        id=plan_id,
        operations=operations,
        confirmed=bool(payload.get("confirmed", False)),
        previewed=bool(payload.get("previewed", False)),
        active_document=payload.get("active_document"),
        risk_level=payload.get("risk_level", "low"),
    )


def _operation_from_dict(payload: dict[str, Any], mapping: dict[str, Any]) -> Operation:
    return Operation(
        id=payload["id"],
        action=payload["action"],
        entity_type=payload.get("entity_type", ""),
        geometry=payload.get("geometry", {}),
        layer=payload.get("layer", "0"),
        reason=payload.get("reason", ""),
        source_diff_id=payload.get("source_diff_id", ""),
        risk_level=payload.get("risk_level", "low"),
        requires_confirmation=bool(payload.get("requires_confirmation", True)),
        mapping_confidence=payload.get("mapping_confidence", mapping.get("mapping_confidence")),
        calibration_id=payload.get("calibration_id", mapping.get("calibration_id")),
        transform_type=payload.get("transform_type", mapping.get("transform_type")),
        status=payload.get("status", "pending"),
        result=payload.get("result", {}),
    )
