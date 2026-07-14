import logging
from typing import Any

from cad.connection import default_manager


logger = logging.getLogger(__name__)


def connect_cad() -> dict[str, Any]:
    """连接当前已经打开的 AutoCAD，不自动启动 AutoCAD。"""
    logger.info("connect_cad called")
    return default_manager.connect()
