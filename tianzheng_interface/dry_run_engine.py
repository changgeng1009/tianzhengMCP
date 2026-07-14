"""天正给排水接口层 — Dry-Run 模拟执行引擎

Phase 1: 纯模拟，不执行任何 CAD 操作。
- 不导入 win32com
- 不访问 AutoCAD
- 不打开 DWG
- 所有 executable_actions 始终为 0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tianzheng_interface.action_schema import (
    ActionDefinition,
    RiskLevel,
    CONFIDENCE_THRESHOLD,
)


@dataclass
class DryRunResult:
    """Dry-run 模拟执行结果。"""
    total_actions: int = 0
    executable_actions: int = 0
    review_required_actions: int = 0
    high_risk_actions: int = 0
    unsupported_actions: int = 0
    estimated_added_objects: int = 0
    estimated_modified_objects: int = 0
    estimated_deleted_objects: int = 0
    warnings: list[str] = field(default_factory=list)
    action_summaries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_actions": self.total_actions,
            "executable_actions": self.executable_actions,
            "review_required_actions": self.review_required_actions,
            "high_risk_actions": self.high_risk_actions,
            "unsupported_actions": self.unsupported_actions,
            "estimated_added_objects": self.estimated_added_objects,
            "estimated_modified_objects": self.estimated_modified_objects,
            "estimated_deleted_objects": self.estimated_deleted_objects,
            "warnings": list(self.warnings),
            "action_summaries": list(self.action_summaries),
        }


class DryRunEngine:
    """干运行引擎 — 模拟执行但不操作 CAD。"""

    ADD_ACTION_TYPES = frozenset({
        "add_pipe", "add_valve", "add_fitting", "add_label",
    })
    MODIFY_ACTION_TYPES = frozenset({
        "update_diameter", "update_elevation", "update_system_type",
        "connect_pipe", "move_candidate",
    })
    DELETE_ACTION_TYPES = frozenset({"delete_candidate"})
    REVIEW_ACTION_TYPES = frozenset({"review_only"})

    def simulate(self, actions: list[ActionDefinition]) -> DryRunResult:
        """模拟执行 action 列表。"""
        total = len(actions)
        high_risk = 0
        unsupported = 0
        added = 0
        modified = 0
        deleted = 0
        all_warnings: list[str] = []
        summaries: list[dict[str, Any]] = []

        for action in actions:
            if action.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                high_risk += 1

            action_type = action.action_type

            # 估算实体变更 (add/modify/delete/review 互斥)
            if action_type in self.REVIEW_ACTION_TYPES:
                unsupported += 1
            elif action_type in self.ADD_ACTION_TYPES:
                added += 1
            elif action_type in self.MODIFY_ACTION_TYPES:
                modified += 1
            elif action_type in self.DELETE_ACTION_TYPES:
                deleted += 1
            else:
                unsupported += 1

            for w in action.warnings:
                all_warnings.append(
                    f"[{action.action_id[:8]}] {action_type}: {w}"
                )

            summaries.append({
                "action_id": action.action_id,
                "action_type": action_type,
                "object_type": action.object_type,
                "risk_level": action.risk_level.value,
                "confidence": action.confidence,
                "ready_to_execute": False,
                "requires_confirmation": True,
            })

        # 低置信度警告
        low_conf = sum(
            1 for a in actions if a.confidence < CONFIDENCE_THRESHOLD
        )
        if low_conf > 0:
            all_warnings.append(
                f"Phase 1: {low_conf}/{total} actions 置信度 < {CONFIDENCE_THRESHOLD}"
            )

        all_warnings.append(
            "Phase 1 限制: 所有 action 均为 dry-run only，不可执行"
        )

        return DryRunResult(
            total_actions=total,
            executable_actions=0,
            review_required_actions=total,
            high_risk_actions=high_risk,
            unsupported_actions=unsupported,
            estimated_added_objects=added,
            estimated_modified_objects=modified,
            estimated_deleted_objects=deleted,
            warnings=all_warnings,
            action_summaries=summaries,
        )

    def validate_schema(self, action: ActionDefinition) -> list[str]:
        """校验单个 action schema 完整性。"""
        errors: list[str] = []

        if not action.action_id:
            errors.append("action_id 缺失")
        if not action.action_type:
            errors.append("action_type 缺失")
        if action.confidence < 0.0 or action.confidence > 1.0:
            errors.append(
                f"confidence 超出范围 [0, 1]: {action.confidence}"
            )
        if action.ready_to_execute:
            errors.append("Phase 1 违规: ready_to_execute 必须为 False")
        if not action.requires_confirmation:
            errors.append("Phase 1 违规: requires_confirmation 必须为 True")

        return errors

    def batch_validate(self, actions: list[ActionDefinition]) -> dict[str, list[str]]:
        """批量校验 action schema。"""
        result: dict[str, list[str]] = {}
        for action in actions:
            errors = self.validate_schema(action)
            if errors:
                result[action.action_id] = errors
        return result
# ════════════════════════════════════════════════════════════════
import uuid

# Phase M2 增强: 冲突检测器 + 增强模拟
# ════════════════════════════════════════════════════════════════

from math import hypot
from tianzheng_interface.action_schema import (
    ActionConflict,
    ConflictType,
    ACTION_CATEGORIES,
)


class ConflictDetector:
    """Action 冲突检测器 — 空间/图层/管径/连接/标高/系统/重复。

    Phase M2: dry-run only，所有检测基于 action 参数。
    """

    SPATIAL_TOLERANCE = 50.0
    ELEVATION_TOLERANCE = 100.0
    DIAMETER_TOLERANCE_MM = 5.0

    def detect_all(self, actions: list[ActionDefinition]) -> list[ActionConflict]:
        """执行全部冲突检测。"""
        conflicts: list[ActionConflict] = []
        conflicts.extend(self.detect_spatial(actions))
        conflicts.extend(self.detect_diameter(actions))
        conflicts.extend(self.detect_elevation(actions))
        conflicts.extend(self.detect_system_mismatch(actions))
        return conflicts

    def detect_spatial(
        self, actions: list[ActionDefinition]
    ) -> list[ActionConflict]:
        """检测空间重叠 — 新增管道是否与已有管道空间重叠。"""
        conflicts: list[ActionConflict] = []
        add_pipes = [
            a for a in actions
            if a.action_type in ACTION_CATEGORIES["add"]
            and "x" in a.geometry
        ]
        for i in range(len(add_pipes)):
            for j in range(i + 1, len(add_pipes)):
                a, b = add_pipes[i], add_pipes[j]
                dist = _point_distance(a.geometry, b.geometry)
                if dist < self.SPATIAL_TOLERANCE:
                    conflicts.append(
                        ActionConflict(
                            conflict_id=str(uuid.uuid4()),
                            action_a_id=a.action_id,
                            action_b_id=b.action_id,
                            conflict_type=ConflictType.SPATIAL_OVERLAP.value,
                            description=f"空间重叠: {a.action_type} 与 {b.action_type} 距离 {dist:.1f} < {self.SPATIAL_TOLERANCE}",
                            severity="medium",
                            resolution_suggestion="调整新增实体位置或合并操作",
                        )
                    )
        return conflicts

    def detect_diameter(
        self, actions: list[ActionDefinition]
    ) -> list[ActionConflict]:
        """检测管径冲突 — 连接的管道管径不一致。"""
        conflicts: list[ActionConflict] = []
        pipes = [a for a in actions if a.dn]
        for i in range(len(pipes)):
            for j in range(i + 1, len(pipes)):
                a, b = pipes[i], pipes[j]
                if a.dn and b.dn and a.dn != b.dn:
                    try:
                        adn = int("".join(c for c in a.dn if c.isdigit()))
                        bdn = int("".join(c for c in b.dn if c.isdigit()))
                        if abs(adn - bdn) > self.DIAMETER_TOLERANCE_MM:
                            conflicts.append(
                                ActionConflict(
                                    conflict_id=str(uuid.uuid4()),
                                    action_a_id=a.action_id,
                                    action_b_id=b.action_id,
                                    conflict_type=ConflictType.DIAMETER_MISMATCH.value,
                                    description=f"管径不匹配: {a.dn} vs {b.dn}",
                                    severity="medium",
                                    resolution_suggestion="确认管径是否应一致，或使用变径管件",
                                )
                            )
                    except (ValueError, TypeError):
                        pass
        return conflicts

    def detect_elevation(
        self, actions: list[ActionDefinition]
    ) -> list[ActionConflict]:
        """检测标高冲突 — 新增管道标高不一致。"""
        conflicts: list[ActionConflict] = []
        add_pipes = [
            a for a in actions
            if a.action_type in ("add_pipe",) and "elevation" in a.parameters
        ]
        for i in range(len(add_pipes)):
            for j in range(i + 1, len(add_pipes)):
                a, b = add_pipes[i], add_pipes[j]
                ae = a.parameters.get("elevation")
                be = b.parameters.get("elevation")
                if ae is not None and be is not None:
                    try:
                        if abs(float(ae) - float(be)) > self.ELEVATION_TOLERANCE:
                            conflicts.append(
                                ActionConflict(
                                    conflict_id=str(uuid.uuid4()),
                                    action_a_id=a.action_id,
                                    action_b_id=b.action_id,
                                    conflict_type=ConflictType.ELEVATION_CLASH.value,
                                    description=f"标高冲突: {ae} vs {be} (差 {abs(float(ae) - float(be)):.0f})",
                                    severity="high",
                                    resolution_suggestion="调整管道标高或添加立管连接",
                                )
                            )
                    except (ValueError, TypeError):
                        pass
        return conflicts

    def detect_system_mismatch(
        self, actions: list[ActionDefinition]
    ) -> list[ActionConflict]:
        """检测系统类型不匹配 — 不同系统的管道被错误连接。"""
        conflicts: list[ActionConflict] = []
        connect_actions = [a for a in actions if a.action_type == "connect_pipe"]
        for ca in connect_actions:
            pipe_a = ca.parameters.get("pipe_a_system")
            pipe_b = ca.parameters.get("pipe_b_system")
            if pipe_a and pipe_b and pipe_a != pipe_b:
                conflicts.append(
                    ActionConflict(
                        conflict_id=str(uuid.uuid4()),
                        action_a_id=ca.action_id,
                        action_b_id=ca.action_id,
                        conflict_type=ConflictType.SYSTEM_MISMATCH.value,
                        description=f"系统类型不匹配: {pipe_a} vs {pipe_b}",
                        severity="high",
                        resolution_suggestion="不同系统管道不应直接连接，请确认是否需要隔离",
                    )
                )
        return conflicts


def _point_distance(geom_a: dict[str, Any], geom_b: dict[str, Any]) -> float:
    """计算两个几何位置的二维距离。"""
    ax = float(geom_a.get("x", 0))
    ay = float(geom_a.get("y", 0))
    bx = float(geom_b.get("x", 0))
    by = float(geom_b.get("y", 0))
    return hypot(ax - bx, ay - by)


class EnhancedDryRunEngine(DryRunEngine):
    """Phase M2 增强版 Dry-run 引擎 — 含冲突检测和变更预估。"""

    def __init__(self):
        super().__init__()
        self.detector = ConflictDetector()

    def simulate_with_conflicts(
        self, actions: list[ActionDefinition]
    ) -> tuple[DryRunResult, list[ActionConflict]]:
        """模拟执行 + 冲突检测。"""
        result = self.simulate(actions)
        conflicts = self.detector.detect_all(actions)
        result.conflict_count = len(conflicts)
        return result, conflicts

    def estimate_changes(self, actions: list[ActionDefinition]) -> dict[str, int]:
        """增强变更预估 — 按操作类别细分。"""
        estimates = {
            "add_pipe": 0,
            "add_valve": 0,
            "add_fitting": 0,
            "add_label": 0,
            "update_diameter": 0,
            "update_elevation": 0,
            "update_system_type": 0,
            "connect_pipe": 0,
            "move_candidate": 0,
            "delete_candidate": 0,
            "review_only": 0,
        }
        for a in actions:
            at = a.action_type
            if at in estimates:
                estimates[at] += 1
        return estimates
