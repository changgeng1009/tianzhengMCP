from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.t30_writeback.models import T30Capability


T30_OBJECT_TYPES = ["TDbPipe", "TDbPipeValve", "TDbPipeFitting", "TDbSprinkler"]


class T30COMProbe:
    def __init__(
        self,
        com_environment: Any | None = None,
        fake_mode: bool = False,
        target_dwg_path: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.com_environment = com_environment
        self.fake_mode = bool(fake_mode)
        self.target_dwg_path = target_dwg_path
        self.options = dict(options or {})
        self.resolved_document: Any | None = None

    def probe_environment(self, target_dwg_path: str | None = None, options: dict[str, Any] | None = None) -> dict:
        probe_options = dict(self.options)
        probe_options.update(dict(options or {}))
        target_path = target_dwg_path if target_dwg_path is not None else self.target_dwg_path
        app_errors: list[str] = []
        app_warnings: list[str] = []
        acad = self.com_environment
        if self.com_environment is not None:
            mode = "fake" if self.fake_mode else "provided_com"
        else:
            mode = "real_probe"
            acad = self._get_active_autocad_application(app_errors)
            self.com_environment = acad

        if acad is None:
            document_resolution = self._empty_document_resolution(target_path)
            document_resolution["errors"].extend(app_errors)
            return {
                "status": "failed",
                "autocad_available": False,
                "active_document_available": False,
                "t30_detected": False,
                "mode": mode,
                "warnings": app_warnings,
                "errors": app_errors,
                "autocad": {
                    "application_available": False,
                    "application_name": "",
                    "version": "",
                    "visible": None,
                    "documents_count": 0,
                    "active_document_available": False,
                    "documents": [],
                },
                "document_resolution": document_resolution,
            }

        autocad, documents = self._inspect_autocad_application(acad, app_warnings)
        document_resolution = self._resolve_document(acad, documents, target_path, probe_options)
        self.resolved_document = document_resolution.pop("_document", None)
        warnings = app_warnings + list(document_resolution.get("warnings", []))
        errors = app_errors + list(document_resolution.get("errors", []))
        return {
            "status": "success",
            "autocad_available": True,
            "active_document_available": bool(autocad["active_document_available"]),
            "t30_detected": any(self._has_member(acad, name) for name in T30_OBJECT_TYPES),
            "mode": mode,
            "warnings": warnings,
            "errors": errors,
            "autocad": autocad,
            "document_resolution": document_resolution,
        }

    def probe_object_capabilities(self) -> list[T30Capability]:
        return self.probe_insert_methods()

    def probe_insert_methods(self) -> list[T30Capability]:
        capabilities: list[T30Capability] = []
        env = self.com_environment
        for object_type in T30_OBJECT_TYPES:
            obj = getattr(env, object_type, None) if env is not None else None
            available = obj is not None and hasattr(obj, "Insert")
            capabilities.append(
                T30Capability(
                    capability_id=f"{object_type}.Insert",
                    object_type=object_type,
                    method_name="Insert",
                    available=available,
                    confidence=1.0 if available and self.fake_mode else 0.0,
                    signature={"parameters": ["parameters"]} if available else {},
                    probe_status="confirmed" if available and self.fake_mode else ("unconfirmed" if available else "not_available"),
                    metadata={"mode": "fake" if self.fake_mode else "probe"},
                )
            )
        return capabilities

    def dump_com_object_info(self, obj: Any) -> dict:
        try:
            names = [name for name in dir(obj) if not name.startswith("_")]
            return {"status": "success", "members": names, "errors": []}
        except Exception as exc:
            return {"status": "failed", "members": [], "errors": [str(exc)]}

    def _get_active_autocad_application(self, errors: list[str]) -> Any | None:
        try:
            import win32com.client  # type: ignore
        except Exception as exc:
            errors.append(f"win32com.client import failed: {exc}")
            return None

        get_active = getattr(win32com.client, "GetActiveObject", None)
        if get_active is not None:
            try:
                return get_active("AutoCAD.Application")
            except Exception as exc:
                errors.append(f'GetActiveObject("AutoCAD.Application") failed: {exc}')

        get_object = getattr(win32com.client, "GetObject", None)
        if get_object is not None:
            try:
                return get_object(Class="AutoCAD.Application")
            except Exception as exc:
                errors.append(f'GetObject(Class="AutoCAD.Application") failed: {exc}')
        return None

    def _inspect_autocad_application(self, acad: Any, warnings: list[str]) -> tuple[dict, list[dict[str, Any]]]:
        documents: list[dict[str, Any]] = []
        documents_obj = None
        documents_count = 0
        try:
            documents_obj = getattr(acad, "Documents")
            documents_count = int(getattr(documents_obj, "Count", 0) or 0)
        except Exception as exc:
            warnings.append(f"Documents enumeration unavailable: {exc}")

        active_document = None
        active_document_available = False
        try:
            active_document = getattr(acad, "ActiveDocument")
            active_document_available = active_document is not None
        except Exception as exc:
            warnings.append(f"ActiveDocument unavailable: {exc}")

        if documents_obj is not None:
            for index in range(documents_count):
                document = self._get_document_item(documents_obj, index)
                if document is None:
                    warnings.append(f"Documents.Item({index}) unavailable")
                    continue
                info = self._document_info(document)
                info["Active"] = self._same_document(document, active_document)
                info["_document"] = document
                documents.append(info)

        autocad = {
            "application_available": True,
            "application_name": self._safe_attr(acad, "Name", ""),
            "version": self._safe_attr(acad, "Version", ""),
            "visible": self._safe_attr(acad, "Visible", None),
            "documents_count": documents_count,
            "active_document_available": active_document_available,
            "documents": [{key: value for key, value in item.items() if key != "_document"} for item in documents],
        }
        return autocad, documents

    def _resolve_document(
        self,
        acad: Any,
        documents: list[dict[str, Any]],
        target_dwg_path: str | None,
        options: dict[str, Any],
    ) -> dict:
        resolution = self._empty_document_resolution(target_dwg_path)
        target_norm = self._normalize_path(target_dwg_path)
        if target_norm:
            for item in documents:
                if self._normalize_path(str(item.get("FullName") or "")) == target_norm:
                    self._apply_resolved_document(resolution, "matched_target_path", item)
                    return resolution

        active_item = next((item for item in documents if item.get("Active")), None)
        if active_item is not None:
            self._apply_resolved_document(resolution, "active_document", active_item)
            return resolution

        if documents:
            self._apply_resolved_document(resolution, "documents_first", documents[0])
            return resolution

        if target_dwg_path and options.get("allow_open_document") is True:
            try:
                documents_obj = getattr(acad, "Documents")
                opened = documents_obj.Open(target_dwg_path)
                item = self._document_info(opened)
                item["_document"] = opened
                self._apply_resolved_document(resolution, "opened_target_path", item)
                return resolution
            except Exception as exc:
                resolution["errors"].append(f"Documents.Open failed: {exc}")
        elif target_dwg_path:
            resolution["warnings"].append("allow_open_document=false; target DWG was not opened automatically")

        resolution["errors"].append("No AutoCAD Document could be resolved")
        return resolution

    def _empty_document_resolution(self, target_dwg_path: str | None) -> dict:
        return {
            "strategy": "failed",
            "target_dwg_path": target_dwg_path or "",
            "resolved_document_name": "",
            "resolved_document_path": "",
            "warnings": [],
            "errors": [],
        }

    def _apply_resolved_document(self, resolution: dict, strategy: str, item: dict[str, Any]) -> None:
        resolution["strategy"] = strategy
        resolution["resolved_document_name"] = str(item.get("Name") or "")
        resolution["resolved_document_path"] = str(item.get("FullName") or "")
        resolution["_document"] = item.get("_document")

    def _document_info(self, document: Any) -> dict[str, Any]:
        return {
            "Name": self._safe_attr(document, "Name", ""),
            "FullName": self._safe_attr(document, "FullName", ""),
            "Path": self._safe_attr(document, "Path", ""),
            "ReadOnly": self._safe_attr(document, "ReadOnly", None),
            "Active": False,
        }

    def _get_document_item(self, documents_obj: Any, index: int) -> Any | None:
        item = getattr(documents_obj, "Item", None)
        if item is None:
            return None
        for candidate_index in (index, index + 1):
            try:
                return item(candidate_index)
            except Exception:
                continue
        return None

    def _safe_attr(self, obj: Any, name: str, default: Any) -> Any:
        try:
            value = getattr(obj, name)
        except Exception:
            return default
        return value if value is not None else default

    def _has_member(self, obj: Any, name: str) -> bool:
        try:
            getattr(obj, name)
            return True
        except Exception:
            return False

    def _same_document(self, left: Any, right: Any) -> bool:
        if left is None or right is None:
            return False
        if left is right:
            return True
        return self._normalize_path(str(self._safe_attr(left, "FullName", ""))) == self._normalize_path(
            str(self._safe_attr(right, "FullName", ""))
        )

    def _normalize_path(self, path: str | None) -> str:
        if not path:
            return ""
        return os.path.normcase(os.path.abspath(str(Path(path))))
