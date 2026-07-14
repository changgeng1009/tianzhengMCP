from __future__ import annotations

import logging
import platform
import sys
import traceback
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cad.connection import DEFAULT_PROGIDS
from cad.entities import make_point_variant
from logging_config import configure_logging


logger = logging.getLogger(__name__)


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception as exc:
        return f"<读取失败: {exc}>"


def _active_document_info(app: Any) -> dict[str, Any]:
    document = _safe_get(app, "ActiveDocument")
    if isinstance(document, str):
        return {"ActiveDocument": document}

    layer = _safe_get(document, "ActiveLayer")
    return {
        "ActiveDocument.Name": _safe_get(document, "Name"),
        "ActiveDocument.FullName": _safe_get(document, "FullName"),
        "ActiveLayer.Name": _safe_get(layer, "Name") if not isinstance(layer, str) else layer,
    }


def _diagnose_pywin32() -> tuple[bool, Any | None]:
    try:
        import win32com.client

        return True, win32com.client
    except Exception:
        logger.exception("pywin32 不可用")
        return False, None


def _try_addline_fallbacks(app: Any) -> None:
    document = _safe_get(app, "ActiveDocument")
    if isinstance(document, str):
        logger.error("无法执行 AddLine fallback：ActiveDocument 不可用: %s", document)
        return

    model_space = _safe_get(document, "ModelSpace")
    if isinstance(model_space, str):
        logger.error("无法执行 AddLine fallback：ModelSpace 不可用: %s", model_space)
        return

    attempts = [
        (
            "VARIANT(VT_ARRAY | VT_R8)",
            lambda: model_space.AddLine(
                make_point_variant(0.0, 0.0, 0.0),
                make_point_variant(5000.0, 0.0, 0.0),
            ),
        ),
        (
            "list[float]",
            lambda: model_space.AddLine(
                [0.0, 0.0, 0.0],
                [5000.0, 0.0, 0.0],
            ),
        ),
        (
            "tuple[float]",
            lambda: model_space.AddLine(
                (0.0, 0.0, 0.0),
                (5000.0, 0.0, 0.0),
            ),
        ),
    ]

    for label, action in attempts:
        logger.info("诊断 AddLine fallback: %s", label)
        try:
            line = action()
            if hasattr(line, "Update"):
                line.Update()
            if hasattr(document, "Regen"):
                document.Regen(1)
            logger.info(
                "AddLine 成功: method=%s object_name=%s handle=%s",
                label,
                _safe_get(line, "ObjectName"),
                _safe_get(line, "Handle"),
            )
            return
        except Exception as exc:
            logger.error("AddLine 失败: method=%s error=%s", label, exc)
            logger.debug("AddLine 失败堆栈:\n%s", traceback.format_exc())


def main() -> int:
    configure_logging()
    logger.info("开始 AutoCAD COM 诊断")
    logger.info("Python: %s", sys.version.replace("\n", " "))
    logger.info("Python executable: %s", sys.executable)
    logger.info("Python architecture: %s", platform.architecture()[0])
    logger.info("Platform: %s", platform.platform())

    pywin32_available, win32com_client = _diagnose_pywin32()
    logger.info("pywin32 available: %s", pywin32_available)
    if not pywin32_available or win32com_client is None:
        logger.error("诊断停止：请先安装 pywin32，并确认使用 64-bit Python。")
        return 1

    any_success = False
    for prog_id in DEFAULT_PROGIDS:
        logger.info("尝试 ProgID: %s", prog_id)
        try:
            app = win32com_client.GetObject(Class=prog_id)
            any_success = True
            documents = _safe_get(app, "Documents")
            logger.info("ProgID 成功: %s", prog_id)
            logger.info("AutoCAD Version: %s", _safe_get(app, "Version"))
            logger.info("Visible: %s", _safe_get(app, "Visible"))
            logger.info("Documents.Count: %s", _safe_get(documents, "Count"))
            for key, value in _active_document_info(app).items():
                logger.info("%s: %s", key, value)
            _try_addline_fallbacks(app)
            break
        except Exception as exc:
            logger.error("ProgID 失败: %s error=%s", prog_id, exc)
            logger.debug("失败堆栈:\n%s", traceback.format_exc())

    if any_success:
        logger.info("AutoCAD COM 诊断成功：至少一个 ProgID 可连接。")
        return 0

    logger.error("AutoCAD COM 诊断失败：所有 ProgID 均不可连接。")
    logger.error("排查清单：")
    logger.error("1. AutoCAD 2026 必须已经手动打开。")
    logger.error("2. 必须已经打开一个 DWG 文件。")
    logger.error("3. AutoCAD 当前不能停留在未结束的命令状态。")
    logger.error("4. Python 和 AutoCAD 尽量使用相同权限运行，不要一个管理员权限一个普通权限。")
    logger.error("5. 使用 64-bit Python。")
    logger.error("6. 已安装 pywin32。")
    logger.error("7. 不要使用 AutoCAD LT 作为测试目标。")
    logger.error("8. 不要只打开天正启动器，必须进入实际 AutoCAD 编辑界面。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
