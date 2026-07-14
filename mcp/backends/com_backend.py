from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import time
from typing import Any

from .capabilities import capability_map
from .errors import BackendError, BackendUnavailableError
from .models import (
    BackendCapabilities,
    BackendConfig,
    BackendProbeResult,
    BackendSession,
    CloseResult,
    CommandStateResult,
    DocumentResult,
    ExecutionResult,
    RepairTask,
    SaveResult,
    ScanRequest,
    ScanResult,
)


class ComCadBackend:
    """现有 Python + COM 能力的 adapter；业务层不得导入本模块的 COM 类型。"""

    backend_id = "com"

    def __init__(self, *, enabled: bool = True, prog_id: str = "AutoCAD.Application.25.1") -> None:
        self.enabled = enabled
        self.prog_id = prog_id

    def probe(self) -> BackendProbeResult:
        installed = importlib.util.find_spec("win32com.client") is not None
        return BackendProbeResult(
            backend_id=self.backend_id,
            available=self.enabled and installed,
            backend_version="stage2-adapter-v1",
            evidence=["pywin32 import available" if installed else "pywin32 import unavailable", "no AutoCAD connection attempted"],
            error_code=None if installed else "pywin32_unavailable",
            error_message=None if installed else "pywin32 is not installed",
            real_cad_connection_attempted=False,
        )

    def get_capabilities(self) -> BackendCapabilities:
        available = self.probe().available
        capabilities = capability_map(
            open_working_copy=True,
            scan_acdb_entities=True,
            create_acdb_line=True,
            create_acdb_text=True,
            create_acdb_polyline=True,
            save_working_copy=True,
            close_reopen=True,
            persistence_qa=True,
            scan_tianzheng_water_objects=True,
            scan_tdb_pipe=True,
            scan_tdb_valve=True,
            scan_tdb_fitting=True,
            scan_tianzheng_water_equipment=True,
        )
        verified = [
            "open_working_copy",
            "scan_acdb_entities",
            "create_acdb_line",
            "save_working_copy",
            "close_reopen",
            "persistence_qa",
            "scan_tianzheng_water_objects",
            "scan_tdb_pipe",
            "scan_tdb_valve",
            "scan_tdb_fitting",
            "scan_tianzheng_water_equipment",
        ]
        return BackendCapabilities(
            backend_id=self.backend_id,
            backend_version="stage2-adapter-v1",
            available=available,
            capabilities=capabilities,
            capability_evidence={
                "create_acdb_line": "Stage 1 controlled fixture: draw_delta=1 and persisted_delta=1",
                "scan_acdb_entities": "Stage 1 semantic scans completed",
                "scan_tianzheng_water_objects": "existing sandbox scan exposed TDb metadata; create capability not inferred",
                "create_tdb_pipe": "unsupported and unverified",
                "create_tdb_valve": "unsupported and unverified",
                "create_tdb_fitting": "unsupported and unverified",
            },
            sandbox_verified_capabilities=verified,
            professional_domains={"water_supply_and_drainage": "active", "hvac": "deferred"},
        )

    def connect(self, config: BackendConfig) -> BackendSession:
        if not self.enabled or not config.enabled or not config.execution_allowed:
            raise BackendUnavailableError(self.backend_id, "COM backend connection is disabled by configuration")
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            try:
                application = win32com.client.GetActiveObject(config.settings.get("prog_id", self.prog_id))
            except Exception:
                if config.settings.get("attach_only") is True:
                    raise
                application = win32com.client.Dispatch(config.settings.get("prog_id", self.prog_id))
        except Exception as exc:
            raise BackendError("com_connect_failed", str(exc), backend_id=self.backend_id) from exc
        return BackendSession(
            backend_id=self.backend_id,
            connected=True,
            metadata={"prog_id": config.settings.get("prog_id", self.prog_id), "pythoncom_initialized": True},
            native_handle=application,
        )

    def disconnect(self, session: BackendSession) -> None:
        if session.document_path:
            raise BackendError("document_still_open", "close document before disconnect", backend_id=self.backend_id)
        session.connected = False
        session.native_handle = None
        if session.metadata.get("pythoncom_initialized"):
            try:
                import pythoncom

                pythoncom.CoUninitialize()
            except Exception:
                pass

    def open_working_copy(self, session: BackendSession, path: str, read_only: bool = False) -> DocumentResult:
        app = self._app(session)
        try:
            document = app.Documents.Open(str(Path(path).resolve()), bool(read_only))
            time.sleep(0.5)
            session.native_handle = {"application": app, "document": document}
            session.document_path = str(Path(path).resolve())
            session.read_only = read_only
            return DocumentResult(self.backend_id, True, session.document_path, read_only)
        except Exception as exc:
            raise BackendError("open_working_copy_failed", str(exc), backend_id=self.backend_id) from exc

    def scan_entities(self, session: BackendSession, request: ScanRequest) -> ScanResult:
        document = self._document(session)
        entities: list[dict[str, Any]] = []
        try:
            modelspace = _retry_com(lambda: document.ModelSpace, label="ModelSpace")
            count = int(_retry_com(lambda: modelspace.Count, label="ModelSpace.Count"))
            for index in range(count):
                entity = _retry_com(lambda index=index: modelspace.Item(index), label=f"ModelSpace.Item({index})")
                object_name = str(_retry_com(lambda: entity.ObjectName, label="entity.ObjectName"))
                is_tdb = object_name.startswith("TDb")
                if is_tdb and not request.include_tianzheng_water_objects:
                    continue
                if not is_tdb and not request.include_acdb:
                    continue
                record = {
                    "object_name": object_name,
                    "handle": str(_retry_com(lambda: entity.Handle, label="entity.Handle")),
                    "layer": str(_retry_com(lambda: entity.Layer, label="entity.Layer")),
                }
                for source_name, target_name in (("StartPoint", "start_point"), ("EndPoint", "end_point"), ("InsertionPoint", "insert_point"), ("DNDiameter", "diameter"), ("SysType", "system_type")):
                    try:
                        value = _retry_com(lambda source_name=source_name: getattr(entity, source_name), label=f"entity.{source_name}")
                        record[target_name] = list(value) if isinstance(value, tuple) else value
                    except Exception:
                        continue
                entities.append(record)
            return ScanResult(self.backend_id, True, entities, ["scan_acdb_entities", "scan_tianzheng_water_objects"])
        except Exception as exc:
            raise BackendError("scan_failed", str(exc), backend_id=self.backend_id) from exc

    def create_entity(self, session: BackendSession, task: RepairTask) -> ExecutionResult:
        document = self._document(session)
        geometry = task.geometry
        object_type = task.object_type.lower()
        try:
            if object_type in {"line", "acdbline"}:
                entity = document.ModelSpace.AddLine(self._variant(geometry["start_point"]), self._variant(geometry["end_point"]))
            elif object_type in {"text", "acdbtext"}:
                text = str(task.metadata.get("text") or task.metadata.get("content") or "")
                height = float(task.metadata.get("height") or 2.5)
                entity = document.ModelSpace.AddText(text, self._variant(geometry["insert_point"]), height)
            elif object_type in {"polyline", "acdbpolyline"}:
                flat = [coordinate for point in geometry["vertices"] for coordinate in point[:2]]
                entity = document.ModelSpace.AddLightWeightPolyline(self._variant(flat))
            else:
                raise BackendError("unsupported_entity", f"COM backend cannot create {task.object_type}", backend_id=self.backend_id)
            layer = task.metadata.get("layer")
            if layer:
                _retry_com(lambda: setattr(entity, "Layer", str(layer)), label="entity.Layer assignment")
            return ExecutionResult(
                backend_id=self.backend_id,
                success=True,
                task_id=task.task_id,
                created_object_ids=[str(_retry_com(lambda: entity.ObjectID, label="entity.ObjectID"))],
                created_handles=[str(_retry_com(lambda: entity.Handle, label="entity.Handle"))],
                draw_delta=1,
                capability_evidence=task.required_capabilities,
                real_cad_execution=True,
                real_dwg_modified=True,
            )
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError("create_entity_failed", str(exc), backend_id=self.backend_id) from exc

    def save_working_copy(self, session: BackendSession) -> SaveResult:
        if session.read_only:
            raise BackendError("readonly_document", "read-only document cannot be saved", backend_id=self.backend_id)
        document = self._document(session)
        try:
            _retry_com(lambda: document.Save(), label="document.Save")
            return SaveResult(self.backend_id, True, True, session.document_path, True)
        except Exception as exc:
            raise BackendError("save_failed", str(exc), backend_id=self.backend_id) from exc

    def close_document(self, session: BackendSession, save: bool = False) -> CloseResult:
        if save:
            raise BackendError("implicit_save_forbidden", "save must be an explicit save_working_copy call", backend_id=self.backend_id)
        document = self._document(session)
        try:
            _retry_com(lambda: document.Close(False), label="document.Close(False)")
            session.document_path = None
            session.native_handle = self._app(session)
            return CloseResult(self.backend_id, True, True, False)
        except Exception as exc:
            raise BackendError("close_failed", str(exc), backend_id=self.backend_id) from exc

    def reopen_working_copy(self, session: BackendSession, path: str) -> DocumentResult:
        return self.open_working_copy(session, path, read_only=False)

    def get_command_state(self, session: BackendSession) -> CommandStateResult:
        return CommandStateResult(self.backend_id, supported=False)

    def _app(self, session: BackendSession) -> Any:
        handle = session.native_handle
        if isinstance(handle, dict):
            return handle["application"]
        if handle is None or not session.connected:
            raise BackendUnavailableError(self.backend_id, "COM session is not connected")
        return handle

    def _document(self, session: BackendSession) -> Any:
        if not isinstance(session.native_handle, dict) or "document" not in session.native_handle:
            raise BackendError("document_not_open", "working copy is not open", backend_id=self.backend_id)
        return session.native_handle["document"]

    @staticmethod
    def _variant(values: list[float]) -> Any:
        import pythoncom
        import win32com.client

        if not values or not all(math.isfinite(float(value)) for value in values):
            raise ValueError("coordinates must be finite")
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(value) for value in values])


def _retry_com(call: Any, *, label: str, attempts: int = 12, delay: float = 0.25) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            retryable = any(token in message for token in ("-2147418111", "rejected by callee", "拒绝接收呼叫"))
            if not retryable or attempt == attempts - 1:
                raise
            try:
                import pythoncom

                pythoncom.PumpWaitingMessages()
            except Exception:
                pass
            time.sleep(delay)
    raise RuntimeError(f"{label} failed after retries") from last_error
