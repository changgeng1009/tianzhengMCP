"""天正给排水接口层 — Action Schema 定义

Phase 1: 只定义 action 结构，所有 action 强制 ready_to_execute=False。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """Action 风险等级。"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Phase 1 允许的 action_type 枚举
VALID_ACTION_TYPES = frozenset({
    "add_pipe",
    "add_valve",
    "add_fitting",
    "add_label",
    "connect_pipe",
    "update_diameter",
    "update_elevation",
    "update_system_type",
    "move_candidate",
    "delete_candidate",
    "review_only",
})

# 默认高风险 action
HIGH_RISK_ACTION_TYPES = frozenset({
    "delete_candidate",
    "move_candidate",
})

# 已知天正 object_type
KNOWN_TIANZHENG_OBJECT_TYPES = frozenset({
    "TDbPipe",
    "TDbPipeValve",
    "TDbPipeFitting",
    "TDbDimension2",
})

# 置信度阈值
CONFIDENCE_THRESHOLD = 0.75


@dataclass
class ActionDefinition:
    """Phase 1 dry-run action 定义。

    强制规则 (Phase 1):
    - ready_to_execute 永远为 False
    - requires_confirmation 永远为 True
    - delete_candidate 默认 risk_level=HIGH
    - confidence < 0.75 自动 requires_confirmation=True
    - 未知 object_type 自动 risk_level=HIGH
    """
    action_id: str = ""
    action_type: str = "review_only"
    object_type: str = ""
    target_handle: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    geometry: dict[str, Any] = field(default_factory=dict)
    system: str | None = None
    dn: str | None = None
    layer: str | None = None
    confidence: float = 0.5
    source_evidence: str = ""
    ready_to_execute: bool = False
    requires_confirmation: bool = True
    risk_level: RiskLevel = RiskLevel.MEDIUM
    warnings: list[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        """构造后自动校验并应用 Phase 1 强制规则。"""
        # 自动生成 action_id
        if not self.action_id:
            self.action_id = str(uuid.uuid4())

        # Phase 1 强制规则 1: ready_to_execute 永远为 False
        self.ready_to_execute = False

        # 校验 action_type
        if self.action_type not in VALID_ACTION_TYPES:
            self.warnings.append(
                f"未知 action_type: {self.action_type}，已降级为 review_only"
            )
            self.action_type = "review_only"

        # 强制规则 3: delete_candidate 默认 high risk
        if self.action_type in HIGH_RISK_ACTION_TYPES:
            if self.risk_level == RiskLevel.MEDIUM:
                self.risk_level = RiskLevel.HIGH
            self.warnings.append(
                f"action_type={self.action_type} 自动标记为 high risk"
            )

        # 强制规则 5: 未知 object_type 自动 high risk
        if self.object_type and self.object_type not in KNOWN_TIANZHENG_OBJECT_TYPES:
            self.risk_level = RiskLevel.HIGH
            self.warnings.append(
                f"未知 object_type: {self.object_type}，自动标记为 high risk"
            )

        # 强制规则 4: confidence < 0.75 自动 requires_confirmation
        if self.confidence < CONFIDENCE_THRESHOLD:
            self.requires_confirmation = True

        # Phase 1 强制规则 2: requires_confirmation 永远为 True
        self.requires_confirmation = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "object_type": self.object_type,
            "target_handle": self.target_handle,
            "parameters": dict(self.parameters),
            "geometry": dict(self.geometry),
            "system": self.system,
            "dn": self.dn,
            "layer": self.layer,
            "confidence": float(self.confidence),
            "source_evidence": self.source_evidence,
            "ready_to_execute": bool(self.ready_to_execute),
            "requires_confirmation": bool(self.requires_confirmation),
            "risk_level": self.risk_level.value,
            "warnings": list(self.warnings),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionDefinition":
        risk_raw = data.get("risk_level", "medium")
        try:
            risk_level = RiskLevel(risk_raw)
        except ValueError:
            risk_level = RiskLevel.MEDIUM

        return cls(
            action_id=str(data.get("action_id", "")),
            action_type=str(data.get("action_type", "review_only")),
            object_type=str(data.get("object_type", "")),
            target_handle=str(data.get("target_handle", "")),
            parameters=dict(data.get("parameters", {})),
            geometry=dict(data.get("geometry", {})),
            system=data.get("system"),
            dn=data.get("dn"),
            layer=data.get("layer"),
            confidence=float(data.get("confidence", 0.5)),
            source_evidence=str(data.get("source_evidence", "")),
            ready_to_execute=bool(data.get("ready_to_execute", False)),
            requires_confirmation=bool(data.get("requires_confirmation", True)),
            risk_level=risk_level,
            warnings=list(data.get("warnings", [])),
            notes=str(data.get("notes", "")),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)# ════════════════════════════════════════════════════════════════
# Phase M2 增强: 批量操作 / 冲突检测 / 依赖追踪
# ════════════════════════════════════════════════════════════════

# 六种核心操作类别
ACTION_CATEGORIES = {
    "add": frozenset({"add_pipe", "add_valve", "add_fitting", "add_label"}),
    "modify": frozenset({"update_diameter", "update_elevation", "update_system_type"}),
    "connect": frozenset({"connect_pipe"}),
    "move": frozenset({"move_candidate"}),
    "delete": frozenset({"delete_candidate"}),
    "review": frozenset({"review_only"}),
}

class ConflictType(str, Enum):
    """Action 冲突类型。"""
    SPATIAL_OVERLAP = "spatial_overlap"
    LAYER_MISMATCH = "layer_mismatch"
    DIAMETER_MISMATCH = "diameter_mismatch"
    CONNECTION_BROKEN = "connection_broken"
    ELEVATION_CLASH = "elevation_clash"
    SYSTEM_MISMATCH = "system_mismatch"
    DUPLICATE_ENTITY = "duplicate_entity"


@dataclass
class ActionConflict:
    """两个 Action 之间的冲突 (dry-run only)。"""
    conflict_id: str = ""
    action_a_id: str = ""
    action_b_id: str = ""
    conflict_type: str = ""
    description: str = ""
    severity: str = "medium"
    resolution_suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "action_a_id": self.action_a_id,
            "action_b_id": self.action_b_id,
            "conflict_type": self.conflict_type,
            "description": self.description,
            "severity": self.severity,
            "resolution_suggestion": self.resolution_suggestion,
        }


@dataclass
class ActionBatch:
    """批量 Action 集合，含冲突检测和依赖排序。"""
    batch_id: str = ""
    actions: list[ActionDefinition] = field(default_factory=list)
    conflicts: list[ActionConflict] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    total_count: int = 0
    safe_count: int = 0
    conflict_count: int = 0
    high_risk_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "actions": [a.to_dict() for a in self.actions],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "dependencies": dict(self.dependencies),
            "execution_order": list(self.execution_order),
            "total_count": self.total_count,
            "safe_count": self.safe_count,
            "conflict_count": self.conflict_count,
            "high_risk_count": self.high_risk_count,
        }

    @classmethod
    def from_actions(cls, actions: list[ActionDefinition], batch_id: str = "") -> "ActionBatch":
        if not batch_id:
            batch_id = str(uuid.uuid4())
        high_risk = sum(1 for a in actions if a.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL))
        return cls(
            batch_id=batch_id,
            actions=actions,
            total_count=len(actions),
            high_risk_count=high_risk,
            execution_order=[a.action_id for a in actions],
        )


@dataclass
class DependencyGraph:
    """Action 依赖关系图 — 拓扑排序确保执行顺序。"""
    nodes: dict[str, ActionDefinition] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    topological_order: list[str] = field(default_factory=list)

    def add_node(self, action: ActionDefinition) -> None:
        self.nodes[action.action_id] = action

    def add_dependency(self, before_id: str, after_id: str) -> None:
        self.edges.append((before_id, after_id))

    def resolve_order(self) -> list[str]:
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for src, dst in self.edges:
            if src in adj and dst in in_degree:
                adj[src].append(dst)
                in_degree[dst] += 1
        queue = [nid for nid, d in in_degree.items() if d == 0]
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        if len(order) != len(self.nodes):
            return list(self.nodes.keys())
        self.topological_order = order
        return order

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes.keys()),
            "edges": [list(e) for e in self.edges],
            "topological_order": self.topological_order,
        }
