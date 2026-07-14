import logging
from typing import Any

from cad.commands import CommandService
from cad.connection import default_manager


logger = logging.getLogger(__name__)


def send_command(command: str) -> dict[str, Any]:
    """向当前活动图纸发送 AutoCAD 命令。"""
    logger.info("send_command called")
    return CommandService(default_manager).send_command(command)
