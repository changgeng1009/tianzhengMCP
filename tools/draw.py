import logging
from typing import Any

from cad.connection import default_manager
from cad.entities import EntityService


logger = logging.getLogger(__name__)


def draw_line(x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]:
    """通过 ModelSpace.AddLine 在当前活动图纸中创建线段。"""
    logger.info("draw_line called")
    return EntityService(default_manager).draw_line(x1, y1, x2, y2)
