from __future__ import annotations

import logging
from typing import Any

from cad.connection import default_manager
from cad.reader import CADReader


logger = logging.getLogger(__name__)


def read_current_drawing() -> dict[str, Any]:
    """只读当前 AutoCAD 图纸并返回 CurrentCADModel JSON。"""
    logger.info("read_current_drawing called")
    return CADReader(default_manager).read_current_drawing()


def read_selected_entities() -> dict[str, Any]:
    """只读当前 AutoCAD 选择集；没有选择对象时返回空集合。"""
    logger.info("read_selected_entities called")
    return CADReader(default_manager).read_selected_entities()


def summarize_current_drawing() -> dict[str, Any]:
    """只读当前 AutoCAD 图纸并返回基础对象统计。"""
    logger.info("summarize_current_drawing called")
    return CADReader(default_manager).summarize_current_drawing()
