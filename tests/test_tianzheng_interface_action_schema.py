"""测试 tianzheng_interface.action_schema — ActionDefinition 强制规则。

Phase 1 约束:
- 不导入 win32com
- 不访问 AutoCAD
- 不打开 DWG
"""

import json
import pytest
from tianzheng_interface.action_schema import (
    ActionDefinition,
    RiskLevel,
    VALID_ACTION_TYPES,
    CONFIDENCE_THRESHOLD,
)


class TestActionDefinitionDefaults:
    def test_default_ready_to_execute_false(self):
        a = ActionDefinition()
        assert a.ready_to_execute is False

    def test_default_requires_confirmation_true(self):
        a = ActionDefinition()
        assert a.requires_confirmation is True

    def test_action_id_auto_generated(self):
        a = ActionDefinition()
        assert a.action_id != ""
        assert len(a.action_id) == 36  # UUID

    def test_action_id_preserved_when_provided(self):
        a = ActionDefinition(action_id="custom-id-123")
        assert a.action_id == "custom-id-123"


class TestPhase1Rules:
    def test_ready_to_execute_forced_false(self):
        a = ActionDefinition(
            action_type="add_pipe",
            ready_to_execute=True,  # 尝试设为 True
        )
        assert a.ready_to_execute is False

    def test_requires_confirmation_forced_true(self):
        a = ActionDefinition(
            action_type="add_pipe",
            requires_confirmation=False,  # 尝试设为 False
        )
        assert a.requires_confirmation is True

    def test_delete_candidate_auto_high_risk(self):
        a = ActionDefinition(action_type="delete_candidate")
        assert a.risk_level == RiskLevel.HIGH
        assert any("high risk" in w for w in a.warnings)

    def test_move_candidate_auto_high_risk(self):
        a = ActionDefinition(action_type="move_candidate")
        assert a.risk_level == RiskLevel.HIGH

    def test_unknown_object_type_auto_high_risk(self):
        a = ActionDefinition(
            action_type="add_pipe",
            object_type="SomeUnknownType",
        )
        assert a.risk_level == RiskLevel.HIGH
        assert any("未知 object_type" in w for w in a.warnings)

    def test_known_object_type_not_auto_high_risk(self):
        a = ActionDefinition(
            action_type="add_pipe",
            object_type="TDbPipe",
        )
        # TDbPipe is known, so default MEDIUM should remain
        assert a.risk_level == RiskLevel.MEDIUM

    def test_low_confidence_requires_confirmation(self):
        a = ActionDefinition(
            action_type="add_pipe",
            confidence=0.3,  # < 0.75
            requires_confirmation=False,  # 尝试设为 False
        )
        assert a.requires_confirmation is True
        assert a.ready_to_execute is False

    def test_high_confidence_still_requires_confirmation(self):
        a = ActionDefinition(
            action_type="add_pipe",
            confidence=0.95,
            requires_confirmation=False,
        )
        # Phase 1: always True
        assert a.requires_confirmation is True

    def test_unknown_action_type_downgraded(self):
        a = ActionDefinition(action_type="unknown_action_xyz")
        assert a.action_type == "review_only"
        assert any("降级为 review_only" in w for w in a.warnings)


class TestRiskLevel:
    def test_risk_level_enum(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"


class TestActionDefinitionSerialization:
    def test_to_dict(self):
        a = ActionDefinition(
            action_type="add_pipe",
            object_type="TDbPipe",
            dn="DN100",
            system="给水",
            confidence=0.9,
        )
        d = a.to_dict()
        assert d["action_type"] == "add_pipe"
        assert d["dn"] == "DN100"
        assert d["ready_to_execute"] is False
        assert d["requires_confirmation"] is True

    def test_from_dict(self):
        d = {
            "action_id": "test-001",
            "action_type": "add_valve",
            "object_type": "TDbPipeValve",
            "dn": "DN150",
            "risk_level": "low",
            "confidence": 0.85,
            "ready_to_execute": False,
            "requires_confirmation": True,
        }
        a = ActionDefinition.from_dict(d)
        assert a.action_id == "test-001"
        assert a.action_type == "add_valve"
        assert a.risk_level == RiskLevel.LOW
        # Phase 1 enforcement still applies
        assert a.ready_to_execute is False

    def test_to_json(self):
        a = ActionDefinition(
            action_type="add_pipe",
            object_type="TDbPipe",
            dn="DN50",
        )
        j = a.to_json()
        parsed = json.loads(j)
        assert parsed["action_type"] == "add_pipe"
        assert parsed["ready_to_execute"] is False

    def test_json_roundtrip_via_from_dict(self):
        a = ActionDefinition(
            action_type="update_diameter",
            object_type="TDbPipe",
            dn="DN200",
            system="消防",
            confidence=0.88,
        )
        j_str = a.to_json()
        d = json.loads(j_str)
        restored = ActionDefinition.from_dict(d)
        assert restored.action_type == "update_diameter"
        assert restored.dn == "DN200"
        assert restored.ready_to_execute is False


class TestActionTypeEnumeration:
    def test_add_pipe(self):
        a = ActionDefinition(action_type="add_pipe")
        assert a.action_type == "add_pipe"
        assert a.risk_level == RiskLevel.MEDIUM

    def test_add_valve(self):
        a = ActionDefinition(action_type="add_valve")
        assert a.action_type == "add_valve"

    def test_update_diameter(self):
        a = ActionDefinition(action_type="update_diameter")
        assert a.action_type == "update_diameter"

    def test_review_only(self):
        a = ActionDefinition(action_type="review_only")
        assert a.action_type == "review_only"


class TestNoRealCADAccess:
    """验证 Phase 1 安全性: 无 win32com 导入。"""

    def test_no_win32com_import(self):
        from tianzheng_interface import action_schema

        assert "win32com" not in action_schema.__dict__, "action_schema 不应导入 win32com"

    def test_no_pywin32_import(self):
        import sys
        assert "pywin32" not in sys.modules, "不应导入 pywin32"
