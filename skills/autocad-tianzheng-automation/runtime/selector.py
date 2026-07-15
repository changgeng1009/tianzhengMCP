from __future__ import annotations

from collections.abc import Mapping

from .contracts import RuntimeMode, RuntimeSelection, RuntimeSelectionResult
from .routing import RuntimeRouter

PRODUCT_BY_MODE = {
    RuntimeMode.PLAIN_AUTOCAD: "autocad",
    RuntimeMode.TIANZHENG_WATER: "tianzheng_water",
    RuntimeMode.TIANZHENG_HVAC: "tianzheng_hvac",
    RuntimeMode.OFFLINE_ANALYSIS: "offline",
}


def select_runtime(
    manifest: Mapping[str, object],
    *,
    user_mode: str | None = None,
    context_mode: str | None = None,
    detected_product: str | None = None,
) -> RuntimeSelection:
    """旧兼容入口；委托可解释、fail-closed 的新路由器。"""
    result = select_runtime_explained(
        manifest,
        user_mode=user_mode,
        context_mode=context_mode,
        detected_product=detected_product,
    )
    legacy_product = {
        "generic_autocad": "autocad",
        "unknown": "offline",
    }.get(result.product, result.product)
    return RuntimeSelection(result.mode, legacy_product, result.source)


def select_runtime_explained(
    manifest: Mapping[str, object],
    *,
    user_mode: str | None = None,
    context_mode: str | None = None,
    detected_product: str | None = None,
) -> RuntimeSelectionResult:
    return RuntimeRouter().select(
        manifest,
        user_mode=user_mode,
        context_mode=context_mode,
        detected_product=detected_product,
    )
