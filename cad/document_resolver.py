from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def resolve_active_document(acad_app: Any) -> dict[str, Any]:
    documents = _documents_info(acad_app)
    documents_count = len(documents)
    diagnostic: dict[str, Any] = {
        "active_document_validation": None,
        "fallback_document_validation": [],
    }

    active_document = _safe_get(acad_app, "ActiveDocument")
    active_validation = validate_autocad_document(active_document)
    diagnostic["active_document_validation"] = active_validation
    if active_validation["success"]:
        return _success_result(active_document, documents_count, documents, diagnostic)

    for index, document in enumerate(_iter_documents(acad_app)):
        validation = validate_autocad_document(document)
        diagnostic["fallback_document_validation"].append(
            {
                "index": index,
                "name": _safe_get(document, "Name"),
                "success": validation["success"],
                "errors": validation["errors"],
            }
        )
        if validation["success"]:
            return _success_result(document, documents_count, documents, diagnostic)

    return {
        "success": False,
        "document": None,
        "document_name": None,
        "document_full_name": None,
        "documents_count": documents_count,
        "documents": documents,
        "reason": "No valid AutoCAD Document is active or available in Documents.",
        "document_validation": active_validation,
        "diagnostic": diagnostic,
    }


def is_autocad_document(obj: Any) -> bool:
    return validate_autocad_document(obj)["success"]


def validate_autocad_document(obj: Any) -> dict[str, Any]:
    errors: list[str] = []
    available: list[str] = []
    if obj is None:
        return {"success": False, "errors": ["document is None"], "available": []}

    _require_property(obj, "Name", available, errors)
    has_model_space = _optional_property(obj, "ModelSpace", available)
    has_paper_space = _optional_property(obj, "PaperSpace", available)
    if not (has_model_space or has_paper_space):
        errors.append("Document has no ModelSpace or PaperSpace")
    _require_property(obj, "SelectionSets", available, errors)
    _require_property(obj, "Utility", available, errors)
    _optional_property(obj, "Application", available)
    _optional_property(obj, "Database", available)
    return {"success": not errors, "errors": errors, "available": available}


def document_diagnostic_summary(app: Any, resolved: dict[str, Any]) -> dict[str, Any]:
    return {
        "app_caption": _safe_get(app, "Caption"),
        "app_version": _safe_get(app, "Version"),
        "documents_count": resolved.get("documents_count", 0),
        "active_document_name": resolved.get("document_name"),
        "active_document_full_name": resolved.get("document_full_name"),
        "document_validation": resolved.get("document_validation")
        or resolved.get("diagnostic", {}).get("active_document_validation", {}),
        "documents": resolved.get("documents", []),
    }


def prompt_for_document_choice(
    acad_app: Any,
    resolved: dict[str, Any],
    input_func: Any = input,
    print_func: Any = print,
) -> dict[str, Any]:
    if not _active_document_invalid_with_multiple_documents(resolved):
        return resolved

    documents = resolved.get("documents", [])
    print_func("ActiveDocument 无效，当前 AutoCAD 中打开了多个 DWG：")
    for item in documents:
        display_index = int(item.get("index", 0)) + 1
        print_func(f"[{display_index}] {item.get('name')} | {item.get('full_name')}")

    raw = input_func("请输入要使用的图纸编号，直接按 Enter 使用自动解析结果：").strip()
    if not raw:
        return resolved

    try:
        number = int(raw)
    except ValueError:
        selected = dict(resolved)
        selected["choice_error"] = f"Invalid document number: {raw}"
        return selected

    return resolve_document_by_number(acad_app, number)


def resolve_document_by_number(acad_app: Any, number: int) -> dict[str, Any]:
    documents = _iter_documents(acad_app)
    documents_info = _documents_info(acad_app)
    documents_count = len(documents_info)
    index = number - 1
    if index < 0 or index >= len(documents):
        return {
            "success": False,
            "document": None,
            "document_name": None,
            "document_full_name": None,
            "documents_count": documents_count,
            "documents": documents_info,
            "reason": f"Document number out of range: {number}",
            "document_validation": {"success": False, "errors": ["document number out of range"]},
            "diagnostic": {},
        }

    document = documents[index]
    validation = validate_autocad_document(document)
    if not validation["success"]:
        return {
            "success": False,
            "document": None,
            "document_name": _safe_get(document, "Name"),
            "document_full_name": _safe_get(document, "FullName"),
            "documents_count": documents_count,
            "documents": documents_info,
            "reason": "Selected object is not a valid AutoCAD Document.",
            "document_validation": validation,
            "diagnostic": {},
        }
    return _success_result(document, documents_count, documents_info, {"selected_number": number})


def _active_document_invalid_with_multiple_documents(resolved: dict[str, Any]) -> bool:
    active_validation = resolved.get("diagnostic", {}).get("active_document_validation", {})
    return (
        not active_validation.get("success", False)
        and int(resolved.get("documents_count") or 0) > 1
    )


def _success_result(
    document: Any,
    documents_count: int,
    documents: list[dict[str, Any]],
    diagnostic: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_autocad_document(document)
    return {
        "success": True,
        "document": document,
        "document_name": _safe_get(document, "Name"),
        "document_full_name": _safe_get(document, "FullName"),
        "documents_count": documents_count,
        "documents": documents,
        "document_validation": validation,
        "diagnostic": diagnostic,
    }


def _documents_info(acad_app: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, document in enumerate(_iter_documents(acad_app)):
        result.append(
            {
                "index": index,
                "name": _safe_get(document, "Name"),
                "full_name": _safe_get(document, "FullName"),
            }
        )
    return result


def _iter_documents(acad_app: Any) -> list[Any]:
    documents = _safe_get(acad_app, "Documents")
    if documents is None:
        return []
    try:
        return list(documents)
    except Exception:
        pass

    count = int(_safe_get(documents, "Count") or 0)
    zero_based = _items_by_index_base(documents, count, 0)
    if len(zero_based) == count:
        return zero_based

    one_based = _items_by_index_base(documents, count, 1)
    if one_based:
        return one_based

    result: list[Any] = []
    for index in range(count):
        document = _collection_item(documents, index)
        if document is not None:
            result.append(document)
    return result


def _items_by_index_base(collection: Any, count: int, index_base: int) -> list[Any]:
    result: list[Any] = []
    for offset in range(count):
        index = offset + index_base
        try:
            result.append(collection.Item(index))
        except Exception:
            return result
    return result


def _collection_item(collection: Any, index: int) -> Any:
    try:
        return collection.Item(index)
    except Exception:
        try:
            return collection.Item(index + 1)
        except Exception:
            logger.info("COM collection Item lookup failed: index=%s", index, exc_info=True)
            return None


def _require_property(obj: Any, attr: str, available: list[str], errors: list[str]) -> None:
    try:
        getattr(obj, attr)
        available.append(attr)
    except Exception as exc:
        errors.append(f"Document has no {attr}: {exc}")


def _optional_property(obj: Any, attr: str, available: list[str]) -> bool:
    try:
        getattr(obj, attr)
        available.append(attr)
        return True
    except Exception:
        return False


def _safe_get(obj: Any, attr: str) -> Any:
    if obj is None:
        return None
    try:
        return getattr(obj, attr)
    except Exception:
        return None
