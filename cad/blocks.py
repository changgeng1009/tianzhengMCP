from __future__ import annotations

from typing import Any

from cad.geometry import normalize_point


def read_block_reference_properties(entity: Any) -> dict[str, Any]:
    return {
        "block_name": _safe_get(entity, "EffectiveName") or _safe_get(entity, "Name"),
        "name": _safe_get(entity, "Name"),
        "insertion_point": _safe_point(_safe_get(entity, "InsertionPoint")),
        "rotation": _safe_get(entity, "Rotation"),
        "x_scale_factor": _safe_get(entity, "XScaleFactor"),
        "y_scale_factor": _safe_get(entity, "YScaleFactor"),
        "z_scale_factor": _safe_get(entity, "ZScaleFactor"),
    }


def _safe_point(value: Any) -> list[float] | None:
    try:
        return normalize_point(value)
    except Exception:
        return None


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return None
