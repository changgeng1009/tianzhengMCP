from __future__ import annotations

import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from cad.commands import CommandService
from cad.connection import default_manager
from cad.document import DocumentService
from cad.entities import EntityService
from logging_config import configure_logging


logger = logging.getLogger(__name__)


LINE_COMMAND = "LINE\n0,0\n5000,0\n\n"


def main() -> int:
    configure_logging()
    logger.info("开始 AutoCAD Communication Layer 手动集成测试")

    connection_result = default_manager.connect()
    logger.info("连接结果: %s", connection_result)
    if not connection_result.get("connected"):
        logger.error("AutoCAD 连接失败，请确认 AutoCAD 2026 已打开并有活动 DWG")
        return 1

    document_service = DocumentService(default_manager)
    documents_result = document_service.list_documents()
    logger.info("打开图纸列表: %s", documents_result)

    active_document_result = document_service.get_active_document()
    logger.info("当前活动图纸: %s", active_document_result)

    command_result = CommandService(default_manager).send_command(LINE_COMMAND)
    logger.info("SendCommand LINE 结果: %s", command_result)
    if not command_result.get("success"):
        logger.error("SendCommand 测试失败")
        return 1

    draw_result = EntityService(default_manager).draw_line(0, 1000, 5000, 1000)
    logger.info("ModelSpace.AddLine 结果: %s", draw_result)
    if not draw_result.get("success"):
        logger.error("AddLine 测试失败")
        return 1

    logger.info("AutoCAD Communication Layer 手动集成测试完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
