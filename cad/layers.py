from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def read_layers(document: Any) -> list[dict[str, Any]]:
    layers = _safe_get(document, "Layers")
    if layers is None:
        return []
    result: list[dict[str, Any]] = []
    for layer in _iter_collection(layers):
        result.append(
            {
                "name": _safe_get(layer, "Name"),
                "color": _safe_get(layer, "Color"),
                "linetype": _safe_get(layer, "Linetype"),
            }
        )
    return result


def _iter_collection(collection: Any) -> list[Any]:
    try:
        return list(collection)
    except Exception:
        logger.info("Layer collection is not directly iterable; trying Count/Item", exc_info=True)

    count = int(_safe_get(collection, "Count") or 0)
    result: list[Any] = []
    for index in range(count):
        try:
            result.append(collection.Item(index))
        except Exception:
            try:
                result.append(collection.Item(index + 1))
            except Exception:
                logger.info("Layer Item lookup failed: index=%s", index, exc_info=True)
    return result


def _safe_get(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        logger.info("Failed to read layer attribute: %s", attr, exc_info=True)
        return None
