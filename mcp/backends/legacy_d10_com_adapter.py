from __future__ import annotations

import time
from typing import Any

from .errors import BackendError


def legacy_d10_com_scan(sandbox_path: str) -> dict[str, Any]:
    """显式 legacy adapter；仅由后续授权 runner 注入，Stage 2 不调用。"""
    try:
        import win32com.client

        application = win32com.client.GetActiveObject("AutoCAD.Application")
        document = application.Documents.Open(sandbox_path, True)
        try:
            time.sleep(0.5)
            modelspace = document.ModelSpace
            handles = [str(modelspace.Item(index).Handle) for index in range(min(int(modelspace.Count), 20))]
            return {
                "sandbox_opened": True,
                "modelspace_accessible": True,
                "total_entities": int(modelspace.Count),
                "detected_handles": handles,
                "scan_backend_id": "legacy_d10_com_adapter",
            }
        finally:
            document.Close(False)
    except Exception as exc:
        raise BackendError("legacy_d10_scan_failed", str(exc), backend_id="legacy_d10_com_adapter") from exc
