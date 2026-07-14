from __future__ import annotations

import json
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from execution.models import Operation, OperationType, RiskLevel
from tools import execution as execution_tools
from tools.connect import connect_cad
from logging_config import configure_logging


logger = logging.getLogger(__name__)


def _add_manual_smoke_operations(plan_id: str) -> None:
    plan = execution_tools.operation_queue.get_plan(plan_id)
    execution_tools.operation_queue.add_operation(
        plan.id,
        Operation(
            id="op_manual_smoke_line",
            action=OperationType.ADD_LINE,
            entity_type="manual_smoke_line",
            geometry={
                "coordinate_system": "cad_world",
                "start": [0.0, 2000.0, 0.0],
                "end": [5000.0, 2000.0, 0.0],
            },
            layer="0",
            reason="Phase 4 手动集成测试：验证 add_line 安全执行。",
            source_diff_id="manual_smoke_line",
            risk_level=RiskLevel.LOW,
            requires_confirmation=True,
        ),
    )
    execution_tools.operation_queue.add_operation(
        plan.id,
        Operation(
            id="op_manual_smoke_text",
            action=OperationType.ADD_TEXT,
            entity_type="manual_smoke_text",
            geometry={
                "coordinate_system": "cad_world",
                "text": "Phase 4 Execution Queue",
                "position": [0.0, 2600.0, 0.0],
                "height": 250.0,
            },
            layer="0",
            reason="Phase 4 手动集成测试：验证 add_text 安全执行。",
            source_diff_id="manual_smoke_text",
            risk_level=RiskLevel.LOW,
            requires_confirmation=True,
        ),
    )


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 4 执行队列手动集成测试")

    connection_result = connect_cad()
    logger.info("AutoCAD 连接结果: %s", connection_result)
    if not connection_result.get("connected"):
        logger.error("AutoCAD 未连接，停止执行。")
        return 1

    diff_path = PROJECT_ROOT / "examples" / "diff_result_sample.json"
    diff_result_json = diff_path.read_text(encoding="utf-8")
    generated = execution_tools.generate_execution_plan(diff_result_json)
    plan_id = generated["plan_id"]
    _add_manual_smoke_operations(plan_id)

    preview = execution_tools.preview_execution_plan(plan_id)
    logger.info("执行计划预览: %s", json.dumps(preview, ensure_ascii=False, indent=2))

    answer = input("确认执行该计划？输入 YES 后执行：").strip()
    if answer != "YES":
        logger.info("用户未确认，已停止执行。")
        return 0

    confirmation = execution_tools.confirm_execution_plan(plan_id)
    logger.info("确认结果: %s", confirmation)
    execution_result = execution_tools.execute_execution_plan(plan_id)
    logger.info("执行结果: %s", json.dumps(execution_result, ensure_ascii=False, indent=2))
    logger.info("请在 AutoCAD 中确认新增 polyline / line / text 是否实时出现。")
    return 0 if execution_result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
