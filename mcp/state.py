from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PipelineStage(str, Enum):
    LOAD_DWG = "load_dwg"
    LOAD_PNG = "load_png"
    BUILD_SEMANTIC_GRAPH = "build_semantic_graph"
    ALIGN_BUILDINGS = "align_buildings"
    DETECT_MISSING_ELEMENTS = "detect_missing_elements"
    GENERATE_REPAIR_PLAN = "generate_repair_plan"
    VALIDATE_REPAIR_PLAN = "validate_repair_plan"
    APPLY_TO_CAD = "apply_to_cad"
    GENERATE_REPORT = "generate_report"


STAGE_ORDER = [stage.value for stage in PipelineStage]


@dataclass
class PipelineState:
    current_stage: str | None = None
    completed_stages: list[str] = field(default_factory=list)
    failed_stage: str | None = None
    checkpoint_index: int = 0
    action_log: list[dict[str, Any]] = field(default_factory=list)

    def next_stage_index(self) -> int:
        if self.failed_stage:
            return STAGE_ORDER.index(self.failed_stage)
        return self.checkpoint_index

    def record_success(self, stage: str, data: dict[str, Any]) -> None:
        self.current_stage = stage
        self.failed_stage = None
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.checkpoint_index = max(self.checkpoint_index, STAGE_ORDER.index(stage) + 1)
        self.action_log.append(
            {
                "stage": stage,
                "status": "success",
                "checkpoint_index": self.checkpoint_index,
                "data_keys": sorted(data.keys()),
            }
        )

    def record_failure(self, stage: str, error: str) -> None:
        self.current_stage = stage
        self.failed_stage = stage
        self.action_log.append(
            {
                "stage": stage,
                "status": "failed",
                "checkpoint_index": self.checkpoint_index,
                "error": error,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_stage": self.current_stage,
            "completed_stages": list(self.completed_stages),
            "failed_stage": self.failed_stage,
            "checkpoint_index": self.checkpoint_index,
            "action_log": list(self.action_log),
        }

