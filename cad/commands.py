from __future__ import annotations

import logging
from typing import Any

from cad.connection import AutoCADConnectionManager


logger = logging.getLogger(__name__)


class CommandService:
    def __init__(self, manager: AutoCADConnectionManager) -> None:
        self.manager = manager

    def send_command(self, command: str) -> dict[str, Any]:
        logger.info("准备发送 AutoCAD 命令: %r", command)
        if not command:
            return {
                "success": False,
                "command_sent": False,
                "message": "command is required",
            }

        try:
            document = self.manager.require_active_document()
            document.SendCommand(command)
            active_document = getattr(document, "Name", None)
            logger.info("AutoCAD 命令已发送: active_document=%s command=%r", active_document, command)
            return {
                "success": True,
                "command_sent": True,
                "active_document": active_document,
            }
        except Exception as exc:
            logger.exception("发送 AutoCAD 命令失败: %r", command)
            return {
                "success": False,
                "command_sent": False,
                "error": str(exc),
            }
