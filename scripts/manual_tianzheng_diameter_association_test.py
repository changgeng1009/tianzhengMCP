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
from tianzheng.pipe_label_association import build_pipe_diameter_association_model
from tianzheng.semantic_reader import read_selected_tianzheng_semantic_model
from tianzheng.selection_utils import run_selection_with_retry
from tools.connect import connect_cad


logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 6.2.2 DN 管径标注识别与管线候选关联")
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
    logger.info("请在 AutoCAD 中框选包含管线和 DN / De / Φ 管径文字的区域。")

    semantic_model = run_selection_with_retry(
        lambda: read_selected_tianzheng_semantic_model(document),
        active_document=active_document,
    )
    if semantic_model.get("success") is False:
        print(json.dumps(semantic_model, ensure_ascii=False, indent=2))
        return 0

    try:
        association_model = build_pipe_diameter_association_model(semantic_model)
    except Exception as exc:
        logger.exception("DN 管径标注识别与关联失败")
        print(f"DN 管径标注识别与关联失败：{exc}")
        return 3

    diagnostics = {
        "active_document": association_model.get("active_document"),
        "tianzheng_detected": bool(environment.get("detected")),
        "selection_count": association_model.get("selection_count", 0),
        "pipe_count": association_model.get("summary", {}).get("pipes", 0),
        "diameter_label_count": association_model.get("summary", {}).get("diameter_labels", 0),
        "association_count": association_model.get("summary", {}).get("associations", 0),
        "unmatched_pipe_count": association_model.get("summary", {}).get("unmatched_pipes", 0),
        "unmatched_label_count": association_model.get("summary", {}).get("unmatched_labels", 0),
        "need_user_confirmation_count": association_model.get("summary", {}).get(
            "need_user_confirmation", 0
        ),
        "diameter_labels_sample": association_model.get("diameter_labels", [])[:20],
        "pipe_associations_sample": association_model.get("pipe_associations", [])[:20],
    }
    output = {
        "environment_summary": environment_summary,
        "document_diagnostic": document_summary,
        "diagnostics": diagnostics,
        "semantic_model": semantic_model,
        "association_model": association_model,
    }
    output_path = PROJECT_ROOT / "artifacts" / "local_diagnostics" / "tianzheng_diameter_association_sample.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    logger.info("PipeDiameterAssociationModel 已导出: %s", output_path)
    logger.info("Phase 6.2.2 完成：仅识别和候选关联，不写入 CAD。")
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
