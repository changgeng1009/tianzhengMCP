from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from mcp.state import PipelineState


@dataclass
class MCPSession:
    session_id: str = field(default_factory=lambda: f"sess_{uuid4().hex}")
    dwg_path: str | None = None
    png_path: str | None = None
    cad_connection: dict[str, Any] = field(default_factory=dict)
    dwg_graph: dict[str, Any] = field(default_factory=dict)
    png_graph: dict[str, Any] = field(default_factory=dict)
    alignment_map: dict[str, Any] = field(default_factory=dict)
    missing_result: dict[str, Any] = field(default_factory=dict)
    repair_plan: dict[str, Any] = field(default_factory=dict)
    applied_actions: list[dict[str, Any]] = field(default_factory=list)
    pipeline_state: PipelineState = field(default_factory=PipelineState)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "dwg_path": self.dwg_path,
            "png_path": self.png_path,
            "cad_connection": dict(self.cad_connection),
            "dwg_graph": dict(self.dwg_graph),
            "png_graph": dict(self.png_graph),
            "alignment_map": dict(self.alignment_map),
            "missing_result": dict(self.missing_result),
            "repair_plan": dict(self.repair_plan),
            "applied_actions": list(self.applied_actions),
            "pipeline_state": self.pipeline_state.to_dict(),
        }

