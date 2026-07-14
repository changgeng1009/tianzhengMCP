import logging
from typing import Any

from cad.connection import default_manager


logger = logging.getLogger(__name__)


def disconnect() -> dict[str, Any]:
    """清除当前 AutoCAD COM 连接缓存，不关闭 AutoCAD。"""
    logger.info("disconnect called")
    return default_manager.disconnect()
