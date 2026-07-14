from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any


logger = logging.getLogger(__name__)


VERSIONED_PROGIDS = ("AutoCAD.Application.25.1", "AutoCAD.Application.25")
GENERIC_PROGIDS = ("AutoCAD.Application",)
DEFAULT_PROGIDS = VERSIONED_PROGIDS + GENERIC_PROGIDS


class AutoCADConnectionManager:
    """管理当前运行中的 AutoCAD COM 实例连接，不自动启动 AutoCAD。"""

    def __init__(
        self,
        prog_ids: tuple[str, ...] = DEFAULT_PROGIDS,
        com_get_object: Callable[[str], Any] | None = None,
    ) -> None:
        self.prog_ids = prog_ids
        self._com_get_object = com_get_object
        self._app: Any | None = None
        self._prog_id: str | None = None

    def connect(self) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        for prog_id in self.prog_ids:
            logger.info("尝试连接 AutoCAD COM ProgID: %s", prog_id)
            try:
                app = self._get_object(prog_id)
                self._app = app
                self._prog_id = prog_id
                active_document = self._safe_active_document_name(app)
                version = self._safe_get(app, "Version")
                attempts.append({"progid": prog_id, "success": True})
                logger.info(
                    "AutoCAD COM 连接成功: prog_id=%s version=%s active_document=%s",
                    prog_id,
                    version,
                    active_document,
                )
                return {
                    "connected": True,
                    "successful_progid": prog_id,
                    "version": version,
                    "active_document": active_document,
                    "attempts": attempts,
                }
            except Exception as exc:  # COM 异常类型在未安装 pywin32 时不可静态引用。
                logger.exception("AutoCAD COM 连接失败: prog_id=%s", prog_id)
                attempts.append(
                    {
                        "progid": prog_id,
                        "success": False,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )

        self._app = None
        self._prog_id = None
        logger.error("未找到正在运行的 AutoCAD 实例: attempted=%s", self.prog_ids)
        return {
            "connected": False,
            "message": "AutoCAD is not running or COM object is not available.",
            "attempts": attempts,
        }

    def disconnect(self) -> dict[str, Any]:
        logger.info("清除当前 AutoCAD COM 连接缓存，不关闭 AutoCAD")
        was_connected = self._app is not None
        self._app = None
        self._prog_id = None
        return {
            "success": True,
            "was_connected": was_connected,
            "message": "AutoCAD connection cache cleared. AutoCAD was not closed.",
        }

    def status(self) -> dict[str, Any]:
        if self._app is None:
            return {
                "connected": False,
                "autocad_visible": None,
                "version": None,
                "active_document": None,
                "documents_count": 0,
                "successful_progid": None,
            }

        try:
            result = {
                "connected": True,
                "autocad_visible": bool(self._safe_get(self._app, "Visible")),
                "version": self._safe_get(self._app, "Version"),
                "active_document": self._safe_active_document_name(self._app),
                "documents_count": self._documents_count(self._app),
                "successful_progid": self._prog_id,
            }
            logger.info("AutoCAD 状态: %s", result)
            return result
        except Exception as exc:
            logger.exception("读取 AutoCAD 状态失败")
            return {
                "connected": False,
                "autocad_visible": None,
                "version": None,
                "active_document": None,
                "documents_count": 0,
                "successful_progid": self._prog_id,
                "error": str(exc),
            }

    def get_application(self) -> Any | None:
        return self._app

    def require_application(self) -> Any:
        if self._app is None:
            raise RuntimeError("AutoCAD is not connected. Call connect_cad first.")
        return self._app

    def require_active_document(self) -> Any:
        app = self.require_application()
        try:
            document = app.ActiveDocument
        except Exception as exc:
            logger.exception("读取 AutoCAD ActiveDocument 失败")
            raise RuntimeError("AutoCAD has no active document.") from exc
        if document is None:
            raise RuntimeError("AutoCAD has no active document.")
        return document

    def _get_object(self, prog_id: str) -> Any:
        if self._com_get_object is not None:
            return self._com_get_object(prog_id)
        try:
            import win32com.client
        except ImportError as exc:
            raise RuntimeError(
                "pywin32 is required for AutoCAD COM. Install requirements.txt on Windows."
            ) from exc
        return win32com.client.GetObject(Class=prog_id)

    def _safe_active_document_name(self, app: Any) -> str | None:
        try:
            document = app.ActiveDocument
            if document is None:
                return None
            return self._safe_get(document, "Name")
        except Exception:
            logger.exception("读取 ActiveDocument.Name 失败")
            return None

    def _documents_count(self, app: Any) -> int:
        documents = self._safe_get(app, "Documents")
        if documents is None:
            return 0
        count = self._safe_get(documents, "Count")
        return int(count or 0)

    def _safe_get(self, obj: Any, attr: str) -> Any:
        try:
            return getattr(obj, attr)
        except Exception:
            logger.exception("读取 COM 属性失败: %s", attr)
            return None


default_manager = AutoCADConnectionManager()
