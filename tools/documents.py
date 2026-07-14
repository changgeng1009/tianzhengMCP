import logging
from typing import Any

from cad.connection import default_manager
from cad.document import DocumentService


logger = logging.getLogger(__name__)


def list_documents() -> dict[str, Any]:
    """列出当前 AutoCAD 中打开的 DWG。"""
    logger.info("list_documents called")
    return DocumentService(default_manager).list_documents()


def get_active_document() -> dict[str, Any]:
    """返回当前活动图纸信息。"""
    logger.info("get_active_document called")
    return DocumentService(default_manager).get_active_document()
