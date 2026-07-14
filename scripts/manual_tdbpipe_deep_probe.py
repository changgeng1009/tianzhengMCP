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
from tianzheng.selection_utils import (
    SELECTION_INSTRUCTIONS,
    delete_selection_set_if_exists,
    safe_delete_selection_set,
    selection_set_item,
)
from tianzheng.tdbpipe_deep_probe import probe_tdbpipe
from tools.connect import connect_cad


logger = logging.getLogger(__name__)

TEMP_SELECTION_SET_NAME = "__TDbPipeDeepProbeTemp__"


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 6.2.3 TDbPipe 管径 / 标签深度探测")
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
    resolved_document = prompt_for_document_choice(app, resolve_active_document(app))
    document_summary = document_diagnostic_summary(app, resolved_document)
    logger.info("AutoCAD Document 解析结果: %s", json.dumps(document_summary, ensure_ascii=False, indent=2))
    if not resolved_document.get("success"):
        print("无法获取有效 AutoCAD Document。请确认当前 AutoCAD 已打开 DWG，图纸窗口处于激活状态，并且从天正 T30 启动。")
        print(json.dumps(document_summary, ensure_ascii=False, indent=2))
        return 3

    document = resolved_document["document"]
    active_document = resolved_document.get("document_name")
    results: list[dict[str, Any]] = []
    index = 1

    while True:
        command = input("按 Enter 选择一根带 DN 标注的 TDbPipe；输入 q / quit 退出：").strip().lower()
        if command in {"q", "quit"}:
            break

        entity = _pick_one_entity(document)
        if entity is None:
            continue

        object_name = _safe_get(entity, "ObjectName")
        if str(object_name or "") != "TDbPipe":
            print(f"当前选择对象不是 TDbPipe：object_name={object_name}。请重新选择 TDbPipe 管线。")
            continue

        result = probe_tdbpipe(entity)
        entry = {
            "index": index,
            "active_document": active_document,
            "summary": _probe_summary(result),
            "probe": result,
        }
        results.append(entry)
        print(json.dumps(entry["summary"], ensure_ascii=False, indent=2))
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        _save_results(active_document, environment_summary, document_summary, results)

        index += 1

    output_path = _save_results(active_document, environment_summary, document_summary, results)
    logger.info("TDbPipe 深度探测结果已保存: %s", output_path)
    logger.info("Phase 6.2.3 完成：只读探测，不写入 CAD。")
    return 0


def _pick_one_entity(document: Any) -> Any | None:
    delete_selection_set_if_exists(document, TEMP_SELECTION_SET_NAME)
    selection_set = None
    try:
        selection_set = document.SelectionSets.Add(TEMP_SELECTION_SET_NAME)
        print(SELECTION_INSTRUCTIONS)
        selection_set.SelectOnScreen()
        count = int(_safe_get(selection_set, "Count") or 0)
        if count < 1:
            print("No entity selected. Please select objects in AutoCAD and press Enter.")
            return None
        if count > 1:
            print(f"已选择 {count} 个对象，本次只探测第一个对象。")
        return selection_set_item(selection_set, 0)
    except Exception as exc:
        logger.exception("选择 TDbPipe 对象失败")
        print(f"选择对象失败：{exc}")
        return None
    finally:
        safe_delete_selection_set(document, TEMP_SELECTION_SET_NAME, selection_set)


def _save_results(
    active_document: str | None,
    environment_summary: dict[str, Any],
    document_summary: dict[str, Any],
    results: list[dict[str, Any]],
) -> Path:
    output = {
        "phase": "Phase 6.2.3",
        "source": "tdbpipe_deep_probe",
        "active_document": active_document,
        "environment_summary": environment_summary,
        "document_diagnostic": document_summary,
        "probe_count": len(results),
        "items": results,
    }
    output_path = PROJECT_ROOT / "artifacts" / "local_diagnostics" / "tdbpipe_deep_probe_sample.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _probe_summary(result: dict[str, Any]) -> dict[str, Any]:
    properties = result.get("known_properties", {})
    return {
        "object_name": result.get("object_name"),
        "handle": result.get("handle"),
        "layer": result.get("layer"),
        "DNDiameter": properties.get("DNDiameter"),
        "normalized_diameter": result.get("normalized_diameter"),
        "diameter_source": result.get("diameter_source"),
        "diameter_confidence": result.get("diameter_confidence"),
        "SysType": properties.get("SysType"),
        "SElevation": properties.get("SElevation"),
        "EElevation": properties.get("EElevation"),
        "ModelType": properties.get("ModelType"),
        "Label": properties.get("Label"),
        "DrawLabel": properties.get("DrawLabel"),
        "SysLabel": properties.get("SysLabel"),
        "Radius": properties.get("Radius"),
        "Length": properties.get("Length"),
        "diameter_candidates": result.get("diameter_candidates", []),
    }


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
