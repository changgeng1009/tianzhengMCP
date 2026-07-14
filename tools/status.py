import logging
from typing import Any

from cad.connection import default_manager


logger = logging.getLogger(__name__)


def status() -> dict[str, Any]:
    """返回 AutoCAD COM 连接状态。"""
    logger.info("status called")
    return default_manager.status()
