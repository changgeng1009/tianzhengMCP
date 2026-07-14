from __future__ import annotations

import json
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logging_config import configure_logging
from tools import execution as execution_tools
from tools.connect import connect_cad


logger = logging.getLogger(__name__)


def _add_phase46_smoke_operations(plan: dict) -> dict:
    operations = list(plan.get("operations", []))
    operations.extend(
        [
            {
                "id": "op_phase46_smoke_line",
                "action": "add_line",
                "entity_type": "Line",
                "geometry": {
                    "coordinate_system": "cad_world",
                    "start": [0.0, 6000.0, 0.0],
                    "end": [5000.0, 6000.0, 0.0],
                },
                "layer": "0",
                "reason": "Phase 4.6 手动集成测试：验证 mapped cad_world add_line。",
                "source_diff_id": "manual_phase46_line",
                "risk_level": "low",
                "requires_confirmation": True,
                "mapping_confidence": 1.0,
                "calibration_id": "manual_phase46_cad_world",
                "transform_type": "manual_cad_world",
            },
            {
                "id": "op_phase46_smoke_text",
                "action": "add_text",
                "entity_type": "Text",
                "geometry": {
                    "coordinate_system": "cad_world",
                    "text": "Phase 4.6 Mapped Execution",
                    "position": [0.0, 6600.0, 0.0],
                    "height": 250.0,
                },
                "layer": "0",
                "reason": "Phase 4.6 手动集成测试：验证 mapped cad_world add_text。",
                "source_diff_id": "manual_phase46_text",
                "risk_level": "low",
                "requires_confirmation": True,
                "mapping_confidence": 1.0,
                "calibration_id": "manual_phase46_cad_world",
                "transform_type": "manual_cad_world",
            },
        ]
    )
    plan = dict(plan)
    plan["operations"] = operations
    plan["operation_count"] = len(operations)
    return plan


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 4.6 mapped execution 手动集成测试")

    connection_result = connect_cad()
    logger.info("AutoCAD 连接结果: %s", connection_result)
    if not connection_result.get("connected"):
        logger.error("AutoCAD 未连接，停止执行。请先手动打开 AutoCAD 2026 和测试 DWG。")
        return 1

    plan_path = PROJECT_ROOT / "examples" / "mapped_execution_plan_sample.json"
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_payload = _add_phase46_smoke_operations(plan_payload)

    preview = execution_tools.execute_mapped_execution_plan(plan_payload)
    logger.info("mapped execution plan 预览: %s", json.dumps(preview, ensure_ascii=False, indent=2))
    if not preview.get("success"):
        logger.error("预览或坐标校验失败，停止执行。")
        return 1

    answer = input("确认执行 mapped cad_world 计划？输入 YES 后执行：").strip()
    if answer != "YES":
        logger.info("用户未确认，已停止执行。")
        return 0

    execution_result = execution_tools.execute_mapped_execution_plan(plan_payload, confirmed=True)
    logger.info("mapped execution 执行结果: %s", json.dumps(execution_result, ensure_ascii=False, indent=2))
    logger.info("请在 AutoCAD 中执行 ZOOM EXTENTS，并肉眼确认线、多段线、文字是否出现。")
    return 0 if execution_result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
