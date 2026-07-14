from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

from .errors import BackendSafetyError
from .models import RepairTask


EXECUTABLE_CLASSIFICATIONS = {"confirmed_direct_com", "controlled_tianzheng_execution"}
ISOLATED_CLASSIFICATIONS = {"review_only", "blocked", "blocked_geometry", "blocked_invalid_task", "manual_tianzheng"}
DANGEROUS_TOKENS = {"sendcommand", "hsxg", "hzgx", "gxlj", "tsaveas", "tgbatplots", "dcsz"}


@dataclass(frozen=True)
class BackendSafetyPolicy:
    production_d1_allowed: bool = False
    sendcommand_allowed: bool = False
    tianzheng_execution_allowed: bool = False
    source_open_allowed: bool = False
    allow_automatic_fallback: bool = False


class BackendSafetyEnforcer:
    """位于 router 之上，backend 不能覆盖这里的结论。"""

    def __init__(self, policy: BackendSafetyPolicy | None = None) -> None:
        self.policy = policy or BackendSafetyPolicy()

    def validate_common(self, task: RepairTask, *, source_path: str | None, working_copy: str | None) -> None:
        if task.professional_domain != "water_supply_and_drainage":
            raise BackendSafetyError("only water_supply_and_drainage tasks are active in Stage 2")
        if task.classification in ISOLATED_CLASSIFICATIONS:
            raise BackendSafetyError(f"classification is isolated from execution: {task.classification}")
        if task.classification not in EXECUTABLE_CLASSIFICATIONS or not task.execution_allowed:
            raise BackendSafetyError("task is not authorized for backend execution")
        if source_path and working_copy and _same_path(source_path, working_copy):
            raise BackendSafetyError("source path cannot be used as working copy")
        if not working_copy:
            raise BackendSafetyError("working copy path is required")
        serialized = json.dumps(task.to_dict(), ensure_ascii=False).lower()
        if any(token in serialized for token in DANGEROUS_TOKENS):
            raise BackendSafetyError("dangerous command marker is forbidden")
        if task.classification == "controlled_tianzheng_execution" and not self.policy.tianzheng_execution_allowed:
            raise BackendSafetyError("controlled Tianzheng execution is disabled")
        if not task.required_capabilities:
            raise BackendSafetyError("required_capabilities must not be empty")
        if not _geometry_complete(task):
            raise BackendSafetyError("task geometry is incomplete")


def _geometry_complete(task: RepairTask) -> bool:
    geometry = task.geometry or {}
    object_type = task.object_type.lower()
    if object_type in {"line", "acdbline"}:
        start = geometry.get("start_point")
        end = geometry.get("end_point")
        return _point(start) and _point(end) and list(start) != list(end)
    if object_type in {"polyline", "acdbpolyline"}:
        vertices = geometry.get("vertices") or []
        return len(vertices) >= 2 and all(_point(item) for item in vertices)
    if object_type in {"text", "acdbtext", "acdbmtext"}:
        return _point(geometry.get("insert_point") or geometry.get("position"))
    if object_type.lower().startswith("tdb") or object_type in {"tdb_pipe", "tdb_valve", "tdb_fitting", "equipment"}:
        return any(geometry.get(name) for name in ("start_point", "end_point", "vertices", "insert_point", "center", "bbox"))
    return any(geometry.get(name) for name in ("insert_point", "center", "bbox", "start_point", "vertices"))


def _point(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) in {2, 3} and all(isinstance(item, (int, float)) for item in value)


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))
