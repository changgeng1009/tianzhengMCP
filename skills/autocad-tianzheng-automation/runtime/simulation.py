from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import BackendNotAvailable
from .execution_plan import verify_execution_plan


_SIMULATION_BACKENDS = {"offline", "nextgen_mock"}


def simulate_plan(plan: Mapping[str, Any], *, backend: str | None = None) -> dict[str, Any]:
    """纯内存模拟；不导入执行器、不启动子进程、不访问文档。"""
    verify_execution_plan(plan)
    selected = str(backend or plan.get("backend") or "offline")
    if selected not in _SIMULATION_BACKENDS:
        raise BackendNotAvailable(
            f"backend {selected} 不允许离线模拟",
            field="backend",
            details={"allowed": sorted(_SIMULATION_BACKENDS)},
        )
    if selected != plan.get("backend"):
        raise BackendNotAvailable(
            "模拟 backend 必须与计划显式 backend 一致；不自动替代",
            field="backend",
            details={"plan_backend": plan.get("backend"), "requested_backend": selected},
        )
    blocked = list(plan.get("blocked_reasons") or [])
    stage_results = [
        {
            "index": item.get("index"),
            "stage_id": item.get("stage_id"),
            "status": "BLOCKED" if blocked else "SIMULATED",
        }
        for item in plan.get("stages", ())
    ]
    return {
        "ok": not blocked,
        "status": "BLOCKED" if blocked else "SIMULATION_COMPLETE",
        "backend": selected,
        "simulation_kind": "NEXTGEN_MOCK_ONLY" if selected == "nextgen_mock" else "OFFLINE_ONLY",
        "real_execution": False,
        "real_cad_capability": False,
        "cad_connected": False,
        "com_connected": False,
        "tianzheng_connected": False,
        "subprocess_started": False,
        "documents_opened": 0,
        "blocked_reasons": blocked,
        "plan_hash": plan.get("plan_hash"),
        "stage_results": stage_results,
    }


def simulate_offline(plan: Mapping[str, Any]) -> dict[str, Any]:
    return simulate_plan(plan, backend="offline")


def simulate_nextgen_mock(plan: Mapping[str, Any]) -> dict[str, Any]:
    return simulate_plan(plan, backend="nextgen_mock")
