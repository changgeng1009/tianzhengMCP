from __future__ import annotations

import logging
from typing import Any

from cad.connection import AutoCADConnectionManager


logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, manager: AutoCADConnectionManager) -> None:
        self.manager = manager

    def list_documents(self) -> dict[str, Any]:
        try:
            app = self.manager.require_application()
            active_document = app.ActiveDocument
            documents = [
                {
                    "name": self._safe_get(document, "Name"),
                    "full_name": self._safe_get(document, "FullName"),
                    "is_active": self._is_same_document(document, active_document),
                }
                for document in self._iter_documents(app.Documents)
            ]
            logger.info("列出 AutoCAD 文档: count=%s", len(documents))
            return {"connected": True, "documents": documents}
        except Exception as exc:
            logger.exception("列出 AutoCAD 文档失败")
            return {"connected": False, "documents": [], "error": str(exc)}

    def get_active_document(self) -> dict[str, Any]:
        try:
            document = self.manager.require_active_document()
            result = {
                "connected": True,
                "name": self._safe_get(document, "Name"),
                "full_name": self._safe_get(document, "FullName"),
                "active_layer": self._active_layer_name(document),
                "active_space": self._active_space_name(self._safe_get(document, "ActiveSpace")),
                "model_space_count": self._model_space_count(document),
            }
            logger.info("读取当前活动图纸: %s", result)
            return result
        except Exception as exc:
            logger.exception("读取当前活动图纸失败")
            return {"connected": False, "error": str(exc)}

    def _iter_documents(self, documents: Any) -> list[Any]:
        try:
            return list(documents)
        except Exception:
            logger.exception("直接迭代 Documents 失败，尝试按 Count/Item 读取")

        count = int(self._safe_get(documents, "Count") or 0)
        result: list[Any] = []
        for index in range(count):
            try:
                result.append(documents.Item(index))
                continue
            except Exception:
                logger.debug("Documents.Item(%s) 失败，尝试 1-based", index)
            try:
                result.append(documents.Item(index + 1))
            except Exception:
                logger.exception("Documents.Item(%s) 与 Item(%s) 均失败", index, index + 1)
        return result

    def _is_same_document(self, document: Any, active_document: Any) -> bool:
        return self._safe_get(document, "FullName") == self._safe_get(active_document, "FullName")

    def _active_layer_name(self, document: Any) -> str | None:
        layer = self._safe_get(document, "ActiveLayer")
        return self._safe_get(layer, "Name") if layer is not None else None

    def _active_space_name(self, active_space: Any) -> str:
        if active_space == 1:
            return "model"
        if active_space == 0:
            return "paper"
        return str(active_space)

    def _model_space_count(self, document: Any) -> int:
        model_space = self._safe_get(document, "ModelSpace")
        count = self._safe_get(model_space, "Count") if model_space is not None else 0
        return int(count or 0)

    def _safe_get(self, obj: Any, attr: str) -> Any:
        try:
            return getattr(obj, attr)
        except Exception:
            logger.exception("读取 COM 属性失败: %s", attr)
            return None
