from __future__ import annotations

import json
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from coordinate.calibration import CalibrationSet
from coordinate.mapper import ExecutionPlanCoordinateMapper
from logging_config import configure_logging


logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 4.5 坐标映射手动测试")

    plan_path = PROJECT_ROOT / "examples" / "execution_plan_sample.json"
    calibration_path = PROJECT_ROOT / "examples" / "calibration_points_sample.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    calibration_data = json.loads(calibration_path.read_text(encoding="utf-8"))

    calibration = CalibrationSet.from_dict(calibration_data)
    mapped = ExecutionPlanCoordinateMapper(calibration).map_execution_plan(plan)

    logger.info("校准点: %s", json.dumps(calibration_data, ensure_ascii=False, indent=2))
    logger.info("映射前第一个可映射操作: %s", json.dumps(plan["operations"][2], ensure_ascii=False, indent=2))
    logger.info("映射后第一个可映射操作: %s", json.dumps(mapped["operations"][2], ensure_ascii=False, indent=2))
    logger.info("完整 mapped execution plan: %s", json.dumps(mapped, ensure_ascii=False, indent=2))
    logger.info("本脚本只做坐标映射，不执行 CAD。请人工确认 cad_world 坐标是否合理。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
