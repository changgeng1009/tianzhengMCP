from __future__ import annotations

import logging
from typing import Any

from cad.connection import AutoCADConnectionManager


logger = logging.getLogger(__name__)


AC_ACTIVE_VIEWPORT = 1


def make_point_variant(x: float, y: float, z: float = 0.0) -> Any:
    """构造 AutoCAD ActiveX AddLine 兼容的 3D 点。"""
    import pythoncom
    from win32com.client import VARIANT

    return VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8,
        [float(x), float(y), float(z)],
    )


def make_double_array_variant(values: list[float]) -> Any:
    """构造 AutoCAD ActiveX 兼容的 double SafeArray。"""
    import pythoncom
    from win32com.client import VARIANT

    return VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8,
        [float(value) for value in values],
    )


class EntityService:
    def __init__(self, manager: AutoCADConnectionManager) -> None:
        self.manager = manager

    def draw_line(self, x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]:
        start = [float(x1), float(y1), 0.0]
        end = [float(x2), float(y2), 0.0]
        logger.info(
            "准备通过 ModelSpace.AddLine 创建线段: start=%s end=%s point_variant=%s",
            start,
            end,
            "VARIANT(VT_ARRAY | VT_R8)",
        )
        try:
            document = self.manager.require_active_document()
            model_space = document.ModelSpace
            start_variant = make_point_variant(*start)
            end_variant = make_point_variant(*end)
            line = model_space.AddLine(start_variant, end_variant)
            if hasattr(line, "Update"):
                line.Update()
            document.Regen(AC_ACTIVE_VIEWPORT)
            entity_type = self._entity_type(line)
            object_name = self._object_name(line)
            handle = self._handle(line)
            active_document = getattr(document, "Name", None)
            logger.info(
                (
                    "线段创建成功: active_document=%s entity_type=%s object_name=%s "
                    "handle=%s start=%s end=%s"
                ),
                active_document,
                entity_type,
                object_name,
                handle,
                start,
                end,
            )
            return {
                "success": True,
                "entity_type": entity_type,
                "object_name": object_name,
                "handle": handle,
                "active_document": active_document,
                "start": start,
                "end": end,
                "point_variant": "VARIANT(VT_ARRAY | VT_R8)",
            }
        except Exception as exc:
            logger.exception("通过 ModelSpace.AddLine 创建线段失败")
            return {
                "success": False,
                "entity_type": "Line",
                "start": start,
                "end": end,
                "point_variant": "VARIANT(VT_ARRAY | VT_R8)",
                "error": str(exc),
            }

    def draw_polyline(self, points: list[list[float]]) -> dict[str, Any]:
        normalized_points = [self._xyz(point) for point in points]
        flat_points = [value for point in normalized_points for value in point]
        logger.info("准备通过 ModelSpace.AddPolyline 创建多段线: points=%s", normalized_points)
        try:
            document = self.manager.require_active_document()
            polyline = document.ModelSpace.AddPolyline(make_double_array_variant(flat_points))
            if hasattr(polyline, "Update"):
                polyline.Update()
            document.Regen(AC_ACTIVE_VIEWPORT)
            active_document = getattr(document, "Name", None)
            result = {
                "success": True,
                "entity_type": "Polyline",
                "object_name": self._object_name(polyline),
                "handle": self._handle(polyline),
                "active_document": active_document,
                "points": normalized_points,
                "point_variant": "VARIANT(VT_ARRAY | VT_R8)",
            }
            logger.info("多段线创建成功: %s", result)
            return result
        except Exception as exc:
            logger.exception("通过 ModelSpace.AddPolyline 创建多段线失败")
            return {
                "success": False,
                "entity_type": "Polyline",
                "points": normalized_points,
                "point_variant": "VARIANT(VT_ARRAY | VT_R8)",
                "error": str(exc),
            }

    def add_text(self, text: str, x: float, y: float, height: float) -> dict[str, Any]:
        position = [float(x), float(y), 0.0]
        logger.info("准备通过 ModelSpace.AddText 创建文字: text=%s position=%s height=%s", text, position, height)
        try:
            document = self.manager.require_active_document()
            text_entity = document.ModelSpace.AddText(
                str(text),
                make_point_variant(*position),
                float(height),
            )
            if hasattr(text_entity, "Update"):
                text_entity.Update()
            document.Regen(AC_ACTIVE_VIEWPORT)
            active_document = getattr(document, "Name", None)
            result = {
                "success": True,
                "entity_type": "Text",
                "object_name": self._object_name(text_entity),
                "handle": self._handle(text_entity),
                "active_document": active_document,
                "text": str(text),
                "position": position,
                "height": float(height),
                "point_variant": "VARIANT(VT_ARRAY | VT_R8)",
            }
            logger.info("文字创建成功: %s", result)
            return result
        except Exception as exc:
            logger.exception("通过 ModelSpace.AddText 创建文字失败")
            return {
                "success": False,
                "entity_type": "Text",
                "text": str(text),
                "position": position,
                "height": float(height),
                "point_variant": "VARIANT(VT_ARRAY | VT_R8)",
                "error": str(exc),
            }

    def _entity_type(self, line: Any) -> str:
        raw = getattr(line, "EntityName", None) or getattr(line, "ObjectName", None)
        if raw in {"AcDbLine", "Line"}:
            return "Line"
        return str(raw or "Line")

    def _object_name(self, line: Any) -> str | None:
        raw = getattr(line, "ObjectName", None) or getattr(line, "EntityName", None)
        return str(raw) if raw is not None else None

    def _handle(self, line: Any) -> str | None:
        raw = getattr(line, "Handle", None)
        return str(raw) if raw is not None else None

    def _xyz(self, point: list[float]) -> list[float]:
        values = [float(value) for value in point]
        return values + [0.0] * (3 - len(values))
