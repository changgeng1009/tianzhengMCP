from __future__ import annotations

import logging
from typing import Any

from cad.connection import AutoCADConnectionManager
from cad.reader import CADReader


logger = logging.getLogger(__name__)


class ReferenceDWGReader:
    def __init__(self, manager: AutoCADConnectionManager) -> None:
        self.manager = manager

    def read_reference_document(self) -> dict[str, Any]:
        try:
            document = self.manager.require_active_document()
            return self.read_document(document, source_kind="reference_dwg")
        except Exception as exc:
            logger.exception("读取 Reference DWG 失败")
            return {"success": False, "error": str(exc)}

    def read_document(self, document: Any, source_kind: str = "reference_dwg") -> dict[str, Any]:
        try:
            model = CADReader(self.manager).read_document(
                document,
                source_kind=source_kind,
                reader_name="reference_dwg_reader_mvp",
            )
            for entity in model["entities"]:
                entity["source"] = source_kind
            return {"success": True, "model": model}
        except Exception as exc:
            logger.exception("读取指定 Reference Document 失败")
            return {"success": False, "error": str(exc)}
