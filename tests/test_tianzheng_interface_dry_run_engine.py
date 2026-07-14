"""测试 tianzheng_interface.dry_run_engine — 干运行引擎。

Phase 1 约束:
- 不导入 win32com
- 不访问 AutoCAD
- 不打开 DWG
- executable_actions 始终为 0
"""

import pytest
from tianzheng_interface.action_schema import ActionDefinition, RiskLevel
from tianzheng_interface.dry_run_engine import DryRunEngine, DryRunResult


class TestDryRunEngine:
    def setup_method(self):
        self.engine = DryRunEngine()

    def test_empty_actions(self):
        result = self.engine.simulate([])
        assert result.total_actions == 0
        assert result.executable_actions == 0
        assert result.review_required_actions == 0

    def test_single_add_pipe(self):
        actions = [
            ActionDefinition(
                action_type="add_pipe",
                object_type="TDbPipe",
                dn="DN100",
                system="给水",
                confidence=0.9,
            ),
        ]
        result = self.engine.simulate(actions)
        assert result.total_actions == 1
        assert result.executable_actions == 0
        assert result.review_required_actions == 1
        assert result.estimated_added_objects == 1
        assert result.estimated_modified_objects == 0

    def test_executable_always_zero(self):
        """Phase 1: executable_actions 必须始终为 0。"""
        actions = [
            ActionDefinition(
                action_type="add_pipe",
                object_type="TDbPipe",
                confidence=0.99,
            ),
            ActionDefinition(
                action_type="add_valve",
                object_type="TDbPipeValve",
                confidence=0.99,
            ),
        ]
        result = self.engine.simulate(actions)
        assert result.executable_actions == 0, (
            "Phase 1: executable_actions 必须为 0"
        )

    def test_high_risk_counting(self):
        actions = [
            ActionDefinition(action_type="delete_candidate"),
            ActionDefinition(action_type="add_pipe", object_type="UnknownType"),
            ActionDefinition(action_type="add_pipe", object_type="TDbPipe"),
        ]
        result = self.engine.simulate(actions)
        assert result.high_risk_actions == 2  # delete + unknown type
        assert result.total_actions == 3

    def test_estimated_counts(self):
        actions = [
            ActionDefinition(action_type="add_pipe"),
            ActionDefinition(action_type="add_valve"),
            ActionDefinition(action_type="add_fitting"),
            ActionDefinition(action_type="add_label"),
            ActionDefinition(action_type="update_diameter"),
            ActionDefinition(action_type="update_elevation"),
            ActionDefinition(action_type="delete_candidate"),
            ActionDefinition(action_type="review_only"),
        ]
        result = self.engine.simulate(actions)
        assert result.estimated_added_objects == 4
        assert result.estimated_modified_objects == 2
        assert result.estimated_deleted_objects == 1
        assert result.unsupported_actions >= 1

    def test_warnings_generated(self):
        actions = [
            ActionDefinition(
                action_type="add_pipe",
                confidence=0.3,
                warnings=["low confidence"],
            ),
        ]
        result = self.engine.simulate(actions)
        assert len(result.warnings) >= 1
        assert any("Phase 1" in w for w in result.warnings)

    def test_low_confidence_warning(self):
        actions = [
            ActionDefinition(action_type="add_pipe", confidence=0.3),
            ActionDefinition(action_type="add_pipe", confidence=0.5),
            ActionDefinition(action_type="add_pipe", confidence=0.9),
        ]
        result = self.engine.simulate(actions)
        assert any("0.75" in w for w in result.warnings)

    def test_action_summaries(self):
        actions = [
            ActionDefinition(
                action_type="add_pipe",
                object_type="TDbPipe",
                dn="DN50",
                confidence=0.9,
            ),
        ]
        result = self.engine.simulate(actions)
        assert len(result.action_summaries) == 1
        summary = result.action_summaries[0]
        assert summary["action_type"] == "add_pipe"
        assert summary["ready_to_execute"] is False
        assert summary["requires_confirmation"] is True

    def test_review_only_is_unsupported(self):
        actions = [
            ActionDefinition(action_type="review_only"),
        ]
        result = self.engine.simulate(actions)
        assert result.unsupported_actions == 1


class TestDryRunResult:
    def test_to_dict(self):
        result = DryRunResult(
            total_actions=10,
            executable_actions=0,
            high_risk_actions=3,
            warnings=["Phase 1 test"],
        )
        d = result.to_dict()
        assert d["total_actions"] == 10
        assert d["executable_actions"] == 0
        assert d["high_risk_actions"] == 3

    def test_defaults(self):
        result = DryRunResult()
        assert result.total_actions == 0
        assert result.executable_actions == 0
        assert result.warnings == []


class TestSchemaValidation:
    def setup_method(self):
        self.engine = DryRunEngine()

    def test_valid_action(self):
        a = ActionDefinition(
            action_type="add_pipe",
            object_type="TDbPipe",
            confidence=0.9,
        )
        errors = self.engine.validate_schema(a)
        assert errors == []

    def test_ready_to_execute_true_violation(self):
        a = ActionDefinition(
            action_type="add_pipe",
            object_type="TDbPipe",
            confidence=0.9,
        )
        # 手动覆盖 Phase 1 强制规则 (用于测试 schema 检测)
        a.ready_to_execute = True
        errors = self.engine.validate_schema(a)
        assert any("ready_to_execute" in e for e in errors)

    def test_requires_confirmation_false_violation(self):
        a = ActionDefinition(
            action_type="add_pipe",
            object_type="TDbPipe",
            confidence=0.9,
        )
        a.requires_confirmation = False
        errors = self.engine.validate_schema(a)
        assert any("requires_confirmation" in e for e in errors)

    def test_invalid_confidence(self):
        a = ActionDefinition(
            action_type="add_pipe",
            confidence=1.5,
        )
        errors = self.engine.validate_schema(a)
        assert any("confidence" in e for e in errors)

    def test_batch_validate(self):
        good = ActionDefinition(
            action_type="add_pipe",
            object_type="TDbPipe",
            confidence=0.9,
        )
        bad = ActionDefinition(
            action_type="add_pipe",
            object_type="TDbPipe",
            confidence=0.9,
        )
        bad.ready_to_execute = True
        result = self.engine.batch_validate([good, bad])
        assert bad.action_id in result
        assert good.action_id not in result


class TestNoRealCADAccess:
    """验证 Phase 1 安全性。"""

    def test_no_win32com(self):
        from tianzheng_interface import dry_run_engine

        assert "win32com" not in dry_run_engine.__dict__, "dry_run_engine 不应导入 win32com"

    def test_no_pywin32(self):
        import sys
        assert "pywin32" not in sys.modules, "不应导入 pywin32"

    def test_no_autocad(self):
        import sys
        for mod_name in list(sys.modules.keys()):
            assert "autocad" not in mod_name.lower(), (
                f"不应导入 AutoCAD 相关模块: {mod_name}"
            )
