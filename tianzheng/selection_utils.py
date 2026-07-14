from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


NO_SELECTION_MESSAGE = "No entity selected."
SELECTION_INSTRUCTIONS = (
    "请切换到 AutoCAD 窗口，用鼠标框选对象。\n"
    "看到命令行显示“找到 x 个”后，请在 AutoCAD 中按 Enter / 空格 / 右键确认。\n"
    "不要在 PowerShell 中确认选择。"
)
NO_SELECTION_USER_MESSAGE = (
    "未选择任何对象，请在 AutoCAD 中框选对象后按 Enter。\n"
    "No entity selected. Please select objects in AutoCAD and press Enter."
)


class NoSelectionError(RuntimeError):
    error_code = "NO_SELECTION"

    def __init__(self, message: str = NO_SELECTION_MESSAGE) -> None:
        super().__init__(message)


def safe_delete_selection_set(
    document: Any,
    name: str,
    selection_set: Any | None = None,
) -> None:
    if selection_set is not None and _try_delete(selection_set, "direct selection_set.Delete()"):
        return

    selection_sets = _safe_selection_sets(document)
    if selection_sets is None:
        return

    try:
        named_selection_set = selection_sets.Item(name)
        if _try_delete(named_selection_set, f'SelectionSets.Item("{name}").Delete()'):
            return
    except Exception:
        logger.warning("SelectionSets.Item(name) 删除兜底失败: %s", name, exc_info=True)

    for item in iter_selection_sets(selection_sets):
        if str(_safe_get(item, "Name") or "") != name:
            continue
        if _try_delete(item, f"iterated SelectionSet.Delete(): {name}"):
            return


def delete_selection_set_if_exists(document: Any, name: str) -> None:
    safe_delete_selection_set(document, name)


def iter_selection_sets(selection_sets: Any) -> list[Any]:
    try:
        return list(selection_sets)
    except Exception:
        pass

    count = int(_safe_get(selection_sets, "Count") or 0)
    zero_based = _items_by_index_base(selection_sets, count, 0)
    if len(zero_based) == count:
        return zero_based

    one_based = _items_by_index_base(selection_sets, count, 1)
    if one_based:
        return one_based

    result: list[Any] = []
    for index in range(count):
        try:
            result.append(selection_sets.Item(index))
        except Exception:
            try:
                result.append(selection_sets.Item(index + 1))
            except Exception:
                logger.warning("SelectionSets.Item 读取失败: index=%s", index, exc_info=True)
    return result


def selection_set_item(selection_set: Any, index: int) -> Any:
    try:
        return selection_set.Item(index)
    except Exception:
        return selection_set.Item(index + 1)


def no_selection_result(active_document: str | None = None) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": NoSelectionError.error_code,
        "message": NO_SELECTION_MESSAGE,
        "active_document": active_document,
        "selection_count": 0,
        "entities": [],
        "summary": {},
    }


def run_selection_with_retry(
    operation: Any,
    *,
    active_document: str | None = None,
    input_func: Any = input,
    print_func: Any = print,
) -> dict[str, Any]:
    while True:
        print_func(SELECTION_INSTRUCTIONS)
        try:
            return operation()
        except NoSelectionError:
            print_func(NO_SELECTION_USER_MESSAGE)
            command = input_func("按 Enter 重试，输入 q / quit 退出：").strip().lower()
            if command in {"q", "quit"}:
                return no_selection_result(active_document)


def _items_by_index_base(collection: Any, count: int, index_base: int) -> list[Any]:
    result: list[Any] = []
    for offset in range(count):
        index = offset + index_base
        try:
            result.append(collection.Item(index))
        except Exception:
            return result
    return result


def _try_delete(selection_set: Any, label: str) -> bool:
    try:
        selection_set.Delete()
        return True
    except Exception:
        logger.warning("临时 SelectionSet 删除失败: %s", label, exc_info=True)
        return False


def _safe_selection_sets(document: Any) -> Any | None:
    try:
        return document.SelectionSets
    except Exception:
        logger.warning("读取 SelectionSets 失败", exc_info=True)
        return None


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None
