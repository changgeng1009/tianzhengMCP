from __future__ import annotations

from collections.abc import Mapping

from .contracts import RuntimeMode, RuntimeSelection
from .errors import ProductInstanceConflict, RuntimeModeConflict

PRODUCT_BY_MODE = {
    RuntimeMode.PLAIN_AUTOCAD: "autocad",
    RuntimeMode.TIANZHENG_WATER: "tianzheng_water",
    RuntimeMode.TIANZHENG_HVAC: "tianzheng_hvac",
    RuntimeMode.OFFLINE_ANALYSIS: "offline",
}


def _parse_mode(value: object) -> RuntimeMode | None:
    if value in (None, "", "auto_detect"):
        return None
    try:
        return RuntimeMode(str(value))
    except ValueError as exc:
        raise RuntimeModeConflict(f"未知运行模式: {value}") from exc


def select_runtime(
    manifest: Mapping[str, object],
    *,
    user_mode: str | None = None,
    context_mode: str | None = None,
    detected_product: str | None = None,
) -> RuntimeSelection:
    """按固定优先级选择模式；同一优先级歧义或产品冲突时 fail-closed。"""
    candidates = [
        ("user", _parse_mode(user_mode)),
        ("manifest", _parse_mode(manifest.get("runtime_mode"))),
        ("context", _parse_mode(context_mode)),
    ]
    selected_source, selected_mode = next(((s, m) for s, m in candidates if m), (None, None))
    if selected_mode is None and detected_product:
        detected_map = {
            "autocad": RuntimeMode.PLAIN_AUTOCAD,
            "tianzheng_water": RuntimeMode.TIANZHENG_WATER,
            "tianzheng_hvac": RuntimeMode.TIANZHENG_HVAC,
        }
        selected_mode = detected_map.get(detected_product)
        selected_source = "safe_detection"
    if selected_mode is None:
        raise RuntimeModeConflict("没有足够证据唯一选择运行模式")

    expected_product = PRODUCT_BY_MODE[selected_mode]
    declared_product = str(manifest.get("product") or "")
    if declared_product and declared_product not in (expected_product, "auto"):
        raise ProductInstanceConflict(
            f"模式 {selected_mode.value} 与 Manifest 产品 {declared_product} 冲突"
        )
    if detected_product and selected_mode is not RuntimeMode.OFFLINE_ANALYSIS:
        if detected_product != expected_product:
            raise ProductInstanceConflict(
                f"期望 {expected_product}，检测到 {detected_product}"
            )
    return RuntimeSelection(selected_mode, expected_product, selected_source or "unknown")

