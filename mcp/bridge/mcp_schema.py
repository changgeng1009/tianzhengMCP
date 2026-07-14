"""MCP Bridge — Phase M3-prep: request/response schema 定义。

纯数据结构，不含 CAD 连接、不含 HTTP 调用。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPActionPayload:
    """MCP 工具 action 输入格式。"""
    action_type: str = ""
    object_type: str = ""
    target_handle: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    geometry: dict[str, Any] = field(default_factory=dict)
    system: str | None = None
    dn: str | None = None
    layer: str | None = None
    confidence: float = 0.5
    source_evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "object_type": self.object_type,
            "target_handle": self.target_handle,
            "parameters": self.parameters,
            "geometry": self.geometry,
            "system": self.system,
            "dn": self.dn,
            "layer": self.layer,
            "confidence": self.confidence,
            "source_evidence": self.source_evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MCPActionPayload":
        return cls(
            action_type=str(data.get("action_type", "")),
            object_type=str(data.get("object_type", "")),
            target_handle=str(data.get("target_handle", "")),
            parameters=dict(data.get("parameters", {})),
            geometry=dict(data.get("geometry", {})),
            system=data.get("system"),
            dn=data.get("dn"),
            layer=data.get("layer"),
            confidence=float(data.get("confidence", 0.5)),
            source_evidence=str(data.get("source_evidence", "")),
        )


@dataclass
class MCPValidateActionRequest:
    """validate_action 请求。"""
    action: dict[str, Any] = field(default_factory=dict)

    def to_action_payload(self) -> MCPActionPayload:
        return MCPActionPayload.from_dict(self.action)


@dataclass
class MCPBatchRequest:
    """批量操作请求。"""
    batch_id: str = ""
    actions: list[dict[str, Any]] = field(default_factory=list)

    def to_action_payloads(self) -> list[MCPActionPayload]:
        return [MCPActionPayload.from_dict(a) for a in self.actions]

    def __post_init__(self):
        if not self.batch_id:
            self.batch_id = str(uuid.uuid4())


@dataclass
class MCPScanReportRequest:
    """build_scan_report 请求。"""
    scan_result_json: str = ""
    output_format: str = "markdown"  # markdown / json / both


@dataclass
class MCPManualReviewRequest:
    """manual_review_intake 请求。"""
    decision: str = "INCONCLUSIVE"  # PASS_VISUAL_ONLY / FAIL_VISUAL / INCONCLUSIVE
    reviewer_notes: str = ""
    phase: str = "M3-prep"


@dataclass
class MCPExplainBlockersRequest:
    """explain_blockers 请求。"""
    phase_report: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPSafetyGateRequest:
    """safety_gate_status 请求。"""
    phase: str = "M3-prep"
