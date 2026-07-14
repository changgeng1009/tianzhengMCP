from __future__ import annotations

import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cad.connection import default_manager
from cad.entities import EntityService
from logging_config import configure_logging


logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    logger.info("开始最小真实画线测试：0,0 -> 5000,0")

    connection_result = default_manager.connect()
    logger.info("连接结果: %s", connection_result)
    if not connection_result.get("connected"):
        logger.error("连接失败，请先运行 scripts/diagnose_autocad_com.py 查看具体 ProgID 结果。")
        return 1

    logger.info("successful_progid: %s", connection_result.get("successful_progid"))
    logger.info("attach method: win32com.client.GetObject(Class=ProgID)")
    logger.info("active_document: %s", connection_result.get("active_document"))
    logger.info("AddLine 参数构造方式: VARIANT(VT_ARRAY | VT_R8)")

    draw_result = EntityService(default_manager).draw_line(0, 0, 5000, 0)
    logger.info("画线结果: %s", draw_result)
    logger.info("AddLine 是否成功: %s", draw_result.get("success"))
    logger.info("handle: %s", draw_result.get("handle"))
    logger.info("object_name: %s", draw_result.get("object_name"))
    if not draw_result.get("success"):
        logger.error("画线失败。")
        return 1

    logger.info("画线命令已完成。请肉眼确认 AutoCAD 当前屏幕中是否出现 0,0 -> 5000,0 的线段。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
