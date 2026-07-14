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
from tianzheng.object_inspector import inspect_entity, summarize_inspection
from tianzheng.selection_utils import (
    delete_selection_set_if_exists,
    safe_delete_selection_set,
    selection_set_item,
)
from tools.connect import connect_cad


logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 6.1 交互式天正对象检查")
    logger.info("本脚本只读，不写入 CAD，不调用天正绘图命令。")

    connection = connect_cad()
    logger.info("AutoCAD COM 连接结果: %s", json.dumps(connection, ensure_ascii=False, indent=2))
    if not connection.get("connected"):
        return 1

    environment = TianzhengEnvironmentDetector(default_manager).detect()
    logger.info("天正环境检测摘要: %s", json.dumps(_environment_summary(environment), ensure_ascii=False, indent=2))
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
    logger.info("请在 AutoCAD 中保持图纸窗口可操作。每次按 Enter 后，在 CAD 中点击一个对象。")

    results: list[dict[str, Any]] = []
    index = 1
    while True:
        command = input("按 Enter 开始选择对象；输入 q / quit 退出：").strip().lower()
        if command in {"q", "quit"}:
            break

        try:
            entity = get_entity_by_selection_set(document)
        except Exception as exc:
            logger.exception("用户选择对象失败")
            print(f"对象选择失败：{exc}")
            continue

        result = inspect_entity(entity)
        entry = summarize_inspection(result, index=index, active_document=active_document)
        results.append(entry)
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        _save_results(active_document, environment, results, document_summary)

        index += 1
        again = input("继续检查下一个对象？按 Enter 继续；输入 q / quit 退出：").strip().lower()
        if again in {"q", "quit"}:
            break

    output_path = _save_results(active_document, environment, results, document_summary)
    logger.info("对象检查结果已保存: %s", output_path)
    logger.info("Phase 6.1 完成：仅对象诊断，不写入 CAD。")
    return 0


def get_entity_by_selection_set(document: Any) -> Any:
    selection_set_name = "__TianzhengObjectInspectTemp__"
    delete_selection_set_if_exists(document, selection_set_name)

    selection_set = None
    try:
        selection_set = document.SelectionSets.Add(selection_set_name)
        print("请在 AutoCAD 中选择一个对象，然后按 Enter。")
        selection_set.SelectOnScreen()

        count = int(_safe_get(selection_set, "Count") or 0)
        if count < 1:
            raise RuntimeError("未选择任何对象。")
        return selection_set_item(selection_set, 0)
    finally:
        safe_delete_selection_set(document, selection_set_name, selection_set)


def _save_results(
    active_document: str | None,
    environment: dict[str, Any],
    results: list[dict[str, Any]],
    document_summary: dict[str, Any],
) -> Path:
    output = {
        "phase": "Phase 6.1",
        "active_document": active_document,
        "environment_summary": _environment_summary(environment),
        "document_diagnostic": document_summary,
        "inspection_count": len(results),
        "items": results,
    }
    output_path = PROJECT_ROOT / "artifacts" / "local_diagnostics" / "tianzheng_object_inspection_sample.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


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
