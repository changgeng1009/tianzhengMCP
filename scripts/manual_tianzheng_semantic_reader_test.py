from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cad.connection import default_manager
from cad.document_resolver import (
    document_diagnostic_summary,
    prompt_for_document_choice,
    resolve_active_document,
)
from logging_config import configure_logging
from tianzheng.environment import NOT_DETECTED_MESSAGE, TianzhengEnvironmentDetector
from tianzheng.semantic_reader import (
    read_selected_tianzheng_semantic_model,
    semantic_model_diagnostics,
)
from tianzheng.selection_utils import run_selection_with_retry
from tools.connect import connect_cad


logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 6.2.1 天正对象语义读取增强与属性深度探测")
    logger.info("本脚本只读，不写入 CAD，不调用天正绘图命令。")

    connection = connect_cad()
    logger.info("AutoCAD COM 连接结果: %s", json.dumps(connection, ensure_ascii=False, indent=2))
    if not connection.get("connected"):
        return 1

    environment = TianzhengEnvironmentDetector(default_manager).detect()
    environment_summary = _environment_summary(environment)
    logger.info("天正环境检测摘要: %s", json.dumps(environment_summary, ensure_ascii=False, indent=2))
    if not environment.get("detected"):
        logger.error(NOT_DETECTED_MESSAGE)
        return 2

    app = default_manager.require_application()
    resolved_document = resolve_active_document(app)
    resolved_document = prompt_for_document_choice(app, resolved_document)
    document_summary = document_diagnostic_summary(app, resolved_document)
    logger.info("AutoCAD Document 解析结果: %s", json.dumps(document_summary, ensure_ascii=False, indent=2))
    if not resolved_document.get("success"):
        print("无法获取有效 AutoCAD Document。请确认当前 AutoCAD 已打开 DWG，图纸窗口处于激活状态，并且从天正 T30 启动。")
        print(json.dumps(document_summary, ensure_ascii=False, indent=2))
        return 3

    document = resolved_document["document"]
    active_document = resolved_document.get("document_name")
    logger.info("Using active document: %s", active_document)
    logger.info("请在 AutoCAD 中框选水泵房区域对象；脚本只读并生成语义模型。")

    try:
        model = run_selection_with_retry(
            lambda: read_selected_tianzheng_semantic_model(document),
            active_document=active_document,
        )
        if model.get("success") is False:
            print(json.dumps(model, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        logger.exception("读取天正语义对象失败")
        print(f"读取天正语义对象失败：{exc}")
        return 3

    diagnostics = semantic_model_diagnostics(model)
    diagnostics["tianzheng_detected"] = bool(environment.get("detected"))
    output = {
        "environment_summary": environment_summary,
        "document_diagnostic": document_summary,
        "diagnostics": diagnostics,
        "model": model,
    }
    output_path = PROJECT_ROOT / "artifacts" / "local_diagnostics" / "tianzheng_semantic_model_sample.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    logger.info("TianzhengSemanticModel 已导出: %s", output_path)
    logger.info("Phase 6.2.1 完成：仅语义读取增强，不写入 CAD。")
    return 0


def _environment_summary(environment: dict[str, Any]) -> dict[str, Any]:
    signals = environment.get("signals", {})
    return {
        "detected": environment.get("detected", False),
        "message": environment.get("message"),
        "caption": signals.get("caption"),
        "version": signals.get("version"),
        "active_document": signals.get("active_document"),
        "menu_groups": signals.get("menu_groups", []),
    }


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
