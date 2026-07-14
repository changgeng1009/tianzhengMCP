from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cad.connection import default_manager
from cad.reader import CADReader
from cad_compare.diff_engine import CADToCADDiffEngine
from logging_config import configure_logging
from reference.dwg_reader import ReferenceDWGReader
from reference.filters import ReferenceEntityFilter
from reference.pipe_diameter import PipeDiameterExtractor
from roi.filter import filter_model_by_roi
from roi.models import ROIRegion
from roi.selector import find_text_entities_by_keyword
from tools.connect import connect_cad


logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    logger.info("开始 Phase 5.5.1 ROI Reference DWG Diff 手动测试")

    connection = connect_cad()
    logger.info("AutoCAD 连接结果: %s", connection)
    if not connection.get("connected"):
        logger.error("AutoCAD 未连接。请先打开 current 和 reference 两个 DWG。")
        return 1

    documents = _open_documents()
    if len(documents) < 2:
        logger.error("当前至少需要打开两个 DWG：current 和 reference。")
        return 1

    _print_documents(documents)
    current_doc = documents[_read_index("请选择 current document 编号: ", len(documents))]
    reference_doc = documents[_read_index("请选择 reference document 编号: ", len(documents))]
    if current_doc is reference_doc:
        logger.error("current 和 reference 不能选择同一个 document。")
        return 1

    current_roi = _read_roi("current", "pump_room_current_roi")
    reference_roi = _read_roi("reference", "pump_room_reference_roi")

    current_model_full = CADReader(default_manager).read_document(current_doc, source_kind="current_autocad")
    reference_model_raw = ReferenceDWGReader(default_manager).read_document(reference_doc)["model"]
    reference_model_full = ReferenceEntityFilter.from_json_file(
        PROJECT_ROOT / "config" / "reference_filter_rules.json"
    ).filter_model(reference_model_raw)

    _log_keyword_matches("current", current_model_full, "水泵房大样图")
    _log_keyword_matches("reference", reference_model_full, "水泵房大样图")

    current_model = filter_model_by_roi(current_model_full, current_roi)
    reference_model = filter_model_by_roi(reference_model_full, reference_roi)

    pipe_diameters = PipeDiameterExtractor().extract_from_model(reference_model)
    engine = CADToCADDiffEngine()
    diff = engine.compare(reference_model, current_model)
    execution_plan_preview = engine.build_execution_plan_preview(diff)

    _log_model_diagnostics("Current Document", current_doc, current_model_full, current_model)
    _log_model_diagnostics("Reference Document", reference_doc, reference_model_full, reference_model)
    logger.info("Current ROI: %s", json.dumps(current_roi.to_dict(), ensure_ascii=False))
    logger.info("Reference ROI: %s", json.dumps(reference_roi.to_dict(), ensure_ascii=False))
    _log_diff_diagnostics(diff)

    _write_json("reference_cad_model_sample.json", reference_model)
    _write_json("pipe_diameter_extraction_sample.json", {"items": pipe_diameters})
    _write_json("real_current_vs_reference_diff_sample.json", diff)
    _write_json("cad_to_cad_execution_plan_sample.json", execution_plan_preview)

    logger.info("管径识别结果: %s", json.dumps(pipe_diameters, ensure_ascii=False, indent=2))
    logger.info("ExecutionPlan Preview 已生成，未执行 CAD 写入。")
    logger.info("本脚本只读 current/reference ROI，不复制、不导入、不绑定、不写入 CAD。")
    return 0


def _read_roi(label: str, roi_id: str) -> ROIRegion:
    print(f"请输入 {label} ROI 坐标，单位为 CAD world：")
    min_x = _read_float("  min_x: ")
    min_y = _read_float("  min_y: ")
    max_x = _read_float("  max_x: ")
    max_y = _read_float("  max_y: ")
    return ROIRegion(
        id=roi_id,
        name=f"{label} 水泵房大样图区域",
        coordinate_system="cad_world",
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
    )


def _read_float(prompt: str) -> float:
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print("请输入数字。")


def _open_documents() -> list[Any]:
    app = default_manager.require_application()
    documents = app.Documents
    try:
        return list(documents)
    except Exception:
        pass

    result: list[Any] = []
    count = int(getattr(documents, "Count", 0) or 0)
    for index in range(count):
        try:
            result.append(documents.Item(index))
        except Exception:
            result.append(documents.Item(index + 1))
    return result


def _print_documents(documents: list[Any]) -> None:
    for index, document in enumerate(documents, start=1):
        logger.info(
            "[%s] %s | %s",
            index,
            getattr(document, "Name", None),
            getattr(document, "FullName", None),
        )


def _read_index(prompt: str, count: int) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            index = int(raw)
        except ValueError:
            print("请输入数字编号。")
            continue
        if 1 <= index <= count:
            return index - 1
        print(f"请输入 1 到 {count} 之间的编号。")


def _log_keyword_matches(label: str, model: dict[str, Any], keyword: str) -> None:
    matches = find_text_entities_by_keyword(model, keyword)
    if matches:
        logger.info("%s keyword matches for %r: %s", label, keyword, json.dumps(matches, ensure_ascii=False, indent=2))


def _log_model_diagnostics(
    title: str,
    document: Any,
    full_model: dict[str, Any],
    roi_model: dict[str, Any],
) -> None:
    logger.info("## %s", title)
    logger.info("document name: %s", getattr(document, "Name", None))
    logger.info("full name: %s", getattr(document, "FullName", None))
    logger.info("total entities before ROI: %s", len(full_model.get("entities", [])))
    logger.info("total entities after ROI: %s", len(roi_model.get("entities", [])))
    logger.info("excluded entities count: %s", roi_model.get("roi_summary", {}).get("excluded_entities_count"))
    logger.info("entity type summary after ROI: %s", _entity_type_summary(roi_model))


def _entity_type_summary(model: dict[str, Any]) -> dict[str, int]:
    return dict(Counter(entity.get("type", "unknown") for entity in model.get("entities", [])))


def _log_diff_diagnostics(diff: dict[str, Any]) -> None:
    summary = diff.get("summary", {})
    logger.info("## Diff 信息")
    logger.info("add: %s", summary.get("add", 0))
    logger.info("modify: %s", summary.get("modify", 0))
    logger.info("move: %s", summary.get("move", 0))
    logger.info("delete_suggestion: %s", summary.get("delete_suggestion", 0))
    add_items = [item for item in diff.get("items", []) if item.get("operation") == "add"][:20]
    logger.info("前 20 条 add 摘要: %s", json.dumps([_add_summary(item) for item in add_items], ensure_ascii=False, indent=2))


def _add_summary(item: dict[str, Any]) -> dict[str, Any]:
    entity = item.get("entity", {})
    return {
        "entity_type": entity.get("type"),
        "layer": entity.get("layer") or entity.get("properties", {}).get("layer"),
        "geometry": entity.get("geometry"),
    }


def _write_json(filename: str, data: dict[str, Any]) -> None:
    path = PROJECT_ROOT / "artifacts" / "local_diagnostics" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已导出: %s", path)


if __name__ == "__main__":
    sys.exit(main())
