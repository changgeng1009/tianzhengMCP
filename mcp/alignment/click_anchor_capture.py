from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


AnchorProvider = Callable[[str, int], list[float] | None]


def capture_anchors_no_stdin(
    ref_idx: int = 2,
    sbx_idx: int = 1,
    count: int = 3,
    *,
    anchor_provider: AnchorProvider | None = None,
) -> dict[str, Any]:
    """采集 anchor；交互实现必须由 backend adapter 注入。"""
    del ref_idx, sbx_idx
    reference_points: list[list[float]] = []
    sandbox_points: list[list[float]] = []
    if anchor_provider is not None:
        for index in range(count):
            reference = anchor_provider("reference", index)
            sandbox = anchor_provider("sandbox", index)
            if reference is None or sandbox is None:
                break
            reference_points.append([float(reference[0]), float(reference[1])])
            sandbox_points.append([float(sandbox[0]), float(sandbox[1])])

    return {
        "phase": "D4.6.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "READY" if len(reference_points) >= 2 else "BLOCKED",
        "stdin_used": False,
        "input_function_used": False,
        "anchor_count": len(reference_points),
        "reference_anchor_points": reference_points,
        "sandbox_anchor_points": sandbox_points,
        "anchor_provider_injected": anchor_provider is not None,
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "sendcommand_used": False,
        "tianzheng_command_executed": False,
        "d1_allowed": False,
        "production_d1_allowed": False,
    }


def _select_entity_center(bounds: dict[str, list[float]] | tuple[list[float], list[float]] | None) -> list[float] | None:
    """对 backend 返回的 bbox 求中心；保留旧函数名以兼容调用方。"""
    if bounds is None:
        return None
    if isinstance(bounds, dict):
        minimum = bounds.get("min") or bounds.get("minimum")
        maximum = bounds.get("max") or bounds.get("maximum")
    else:
        minimum, maximum = bounds
    if not minimum or not maximum or len(minimum) < 2 or len(maximum) < 2:
        return None
    return [(float(minimum[0]) + float(maximum[0])) / 2, (float(minimum[1]) + float(maximum[1])) / 2]
