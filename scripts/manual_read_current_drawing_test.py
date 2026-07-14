from __future__ import annotations

import json
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logging_config import configure_logging
from tools.connect import connect_cad
from tools.reader import read_current_drawing, summarize_current_drawing


logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 5 当前 AutoCAD 图纸只读测试")

    connection_result = connect_cad()
    logger.info("AutoCAD 连接结果: %s", connection_result)
    if not connection_result.get("connected"):
        logger.error("AutoCAD 未连接。请先手动打开 AutoCAD 2026 和测试 DWG。")
        return 1

    summary = summarize_current_drawing()
    logger.info("当前图纸对象统计: %s", json.dumps(summary, ensure_ascii=False, indent=2))

    result = read_current_drawing()
    if not result.get("success"):
        logger.error("读取当前图纸失败: %s", result)
        return 1

    output_path = PROJECT_ROOT / "artifacts" / "local_diagnostics" / "current_cad_model_from_real_sample.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result["model"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("CurrentCADModel 示例已导出: %s", output_path)
    logger.info("本脚本只读当前 CAD，不写入、不修改、不删除任何对象。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
