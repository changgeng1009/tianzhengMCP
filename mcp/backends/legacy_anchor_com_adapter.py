from __future__ import annotations

from typing import Callable

from .errors import BackendError


def build_com_anchor_provider(reference_index: int, sandbox_index: int) -> Callable[[str, int], list[float] | None]:
    """显式 legacy interactive adapter；Stage 2 不构造或调用。"""
    try:
        import win32com.client

        application = win32com.client.GetActiveObject("AutoCAD.Application")
        documents = {
            "reference": application.Documents.Item(reference_index),
            "sandbox": application.Documents.Item(sandbox_index),
        }
    except Exception as exc:
        raise BackendError("anchor_adapter_connect_failed", str(exc), backend_id="legacy_anchor_com_adapter") from exc

    def provider(role: str, index: int) -> list[float] | None:
        document = documents[role]
        selection_name = f"__AnchorSelect_{role}_{index}__"
        try:
            try:
                document.SelectionSets.Item(selection_name).Delete()
            except Exception:
                pass
            selection = document.SelectionSets.Add(selection_name)
            selection.SelectOnScreen()
            if int(selection.Count) < 1:
                return None
            entity = selection.Item(0)
            minimum, maximum = entity.GetBoundingBox(None, None)
            return [(float(minimum[0]) + float(maximum[0])) / 2, (float(minimum[1]) + float(maximum[1])) / 2]
        except Exception as exc:
            raise BackendError("anchor_selection_failed", str(exc), backend_id="legacy_anchor_com_adapter") from exc
        finally:
            try:
                selection.Delete()
            except Exception:
                pass

    return provider
