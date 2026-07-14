from __future__ import annotations

import json
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cad.connection import default_manager
from logging_config import configure_logging
from tianzheng.environment import NOT_DETECTED_MESSAGE, TianzhengEnvironmentDetector
from tianzheng.visibility import TianzhengVisibilityDiagnostic
from tools.connect import connect_cad


logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 6.0 天正给排水 T30 V1.0 环境与对象可见性诊断")
    logger.info("本脚本只读，不写入 CAD，不调用天正绘图命令。")

    connection = connect_cad()
    logger.info("AutoCAD COM 连接结果: %s", json.dumps(connection, ensure_ascii=False, indent=2))
    if not connection.get("connected"):
        return 1

    environment = TianzhengEnvironmentDetector(default_manager).detect()
    logger.info("天正环境检测结果: %s", json.dumps(environment, ensure_ascii=False, indent=2))
    if not environment.get("detected"):
        logger.error(NOT_DETECTED_MESSAGE)
        return 2

    diagnostic = TianzhengVisibilityDiagnostic(default_manager)
    visibility = diagnostic.diagnose_current_drawing()
    logger.info("天正对象可见性诊断摘要: %s", json.dumps(visibility.get("summary", {}), ensure_ascii=False, indent=2))

    selected = diagnostic.diagnose_selected_entities()
    logger.info("当前用户选择对象诊断: %s", json.dumps(selected, ensure_ascii=False, indent=2))

    output = {
        "connection": connection,
        "environment": environment,
        "visibility_summary": visibility.get("summary", {}),
        "selected_entities": selected,
        "command_probe": environment.get("command_probe"),
    }
    output_path = PROJECT_ROOT / "examples" / "tianzheng_t30_diagnostic_sample.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("诊断结果已导出: %s", output_path)
    logger.info("Phase 6.0 完成：仅诊断，不写入 CAD。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
