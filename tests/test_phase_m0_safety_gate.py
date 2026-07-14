"""Phase M0: safety gate 测试。

验证 safety gate 在禁止/非安全状态下的行为：
- 执行器在未验证状态下拒绝 apply
- real_com_mode=False 阻止真实 CAD 连接
- 不支持的动作类型被拒绝
- dry-run 不产生真实执行
- schema registry 确认阈值
"""
from __future__ import annotations

import pytest


class TestRepairPlanExecutorSafetyGate:
    """验证 RepairPlanExecutor 的安全门行为。"""

    def test_executor_defaults_to_mock_mode(self) -> None:
        """Executor 默认使用 real_com_mode=False 的 mock adapter。"""
        from mcp.executor import RepairPlanExecutor
        executor = RepairPlanExecutor()
        assert executor.adapter.real_com_mode is False

    def test_executor_accepts_explicit_mock_mode(self) -> None:
        """Executor 接受显式 real_com_mode=False。"""
        from mcp.adapter_t30 import T30WritebackAdapter
        from mcp.executor import RepairPlanExecutor
        adapter = T30WritebackAdapter(real_com_mode=False)
        executor = RepairPlanExecutor(adapter=adapter)
        assert executor.adapter.real_com_mode is False

    def test_apply_without_valid_plan_fails_validation(self) -> None:
        """包含不支持动作类型的 plan 直接 apply 会触发验证并失败。"""
        from mcp.executor import RepairPlanExecutor
        from mcp.session import MCPSession
        executor = RepairPlanExecutor()
        session = MCPSession()
        session.repair_plan = {
            "actions": [{"action_id": "bad-1", "type": "unsupported_type"}],
        }
        result = executor.apply(session)
        assert result["success"] is False
        assert result["status"] == "validation_failed"
        assert "validation" in result

    def test_apply_with_explicit_validation_failure(self) -> None:
        """validation 标记为 invalid 时 apply 被阻止。"""
        from mcp.executor import RepairPlanExecutor
        from mcp.session import MCPSession
        executor = RepairPlanExecutor()
        session = MCPSession()
        session.repair_plan = {
            "actions": [],
            "validation": {
                "valid": False,
                "errors": [{"code": "test_error", "message": "test"}],
            },
        }
        result = executor.apply(session)
        assert result["success"] is False
        assert result["status"] == "validation_failed"

    def test_unsupported_action_type_rejected(self) -> None:
        """不支持的动作类型被 executor 拒绝。"""
        from mcp.executor import RepairPlanExecutor
        result = RepairPlanExecutor()._execute_action({
            "type": "delete_pipe",
            "action_id": "bad-1",
        })
        assert result["success"] is False
        assert result["status"] == "unsupported_action"


class TestMockAdapterSafetyGate:
    """验证 mock adapter 不连接真实 CAD。"""

    def test_mock_adapter_capabilities_are_mock(self) -> None:
        """mock 模式的 capabilities 带 source=mock。"""
        from mcp.adapter_t30 import T30WritebackAdapter
        adapter = T30WritebackAdapter(real_com_mode=False)
        assert adapter.capabilities.get("source") == "mock"
        assert "notes" in adapter.capabilities

    def test_mock_adapter_action_log_is_recorded(self) -> None:
        """mock adapter 记录所有操作到 action_log。"""
        from mcp.adapter_t30 import T30WritebackAdapter
        adapter = T30WritebackAdapter(real_com_mode=False)
        adapter.insert_pipe("a1", [0, 0, 0], [100, 0, 0], 50, "PIPE-给水")
        assert len(adapter.action_log) == 1
        entry = adapter.action_log[0]
        assert entry["action_id"] == "a1"
        assert entry["status"] == "mock_inserted"

    def test_mock_adapter_no_real_connection(self) -> None:
        """mock 模式下不应该连接到真实 AutoCAD。"""
        from mcp.adapter_t30 import T30WritebackAdapter
        adapter = T30WritebackAdapter(real_com_mode=False)
        capabilities = adapter.capabilities
        assert capabilities.get("source") == "mock"
        assert adapter.com_objects is None


class TestDryRunSafetyGate:
    """验证 dry-run 不产生真实执行。"""

    def test_dry_run_produces_no_real_entities(self) -> None:
        """dry-run 所有 simulated_entities 都标记 dry_run=True。"""
        from mcp.repair_actions.dry_run import dry_run_repair_plan
        from mcp.repair_actions.models import RepairAction, RepairPlanV2
        action = RepairAction(
            action_id="a1",
            action_type="add_pipe",
            target_space="cad_modelspace",
            geometry={"type": "polyline", "points": [[0, 0], [100, 0]]},
            system="给水",
            dn="DN50",
            layer="PIPE-给水",
            source_element_id="p1",
            source_type="vision",
            confidence=0.9,
            auto_execute=True,
            reason="missing",
            validation_status="valid",
        )
        plan = RepairPlanV2("plan", "ref", "tgt", [action], [], [], 0.9, [], [], {})
        result = dry_run_repair_plan(plan, {})
        assert result.valid is True
        for entity in result.simulated_entities:
            assert entity["dry_run"] is True

    def test_dry_run_review_action_not_executable(self) -> None:
        """置信度 0.7 + auto_execute=False 的动作进入 review 而非 auto_execute。"""
        from mcp.repair_actions.dry_run import dry_run_repair_plan
        from mcp.repair_actions.models import RepairAction, RepairPlanV2
        action = RepairAction(
            action_id="a2",
            action_type="add_valve",
            target_space="cad_modelspace",
            geometry={"type": "point", "position": [50, 50]},
            system="消火栓",
            dn="DN100",
            layer="VALVE-消火栓",
            source_element_id="v2",
            source_type="vision",
            confidence=0.7,
            auto_execute=False,
            reason="unknown",
            validation_status="pending",
        )
        plan = RepairPlanV2("plan2", "ref", "tgt", [action], [], [], 0.5, [], [], {})
        result = dry_run_repair_plan(plan, {})
        assert result.valid is True
        assert result.metrics["auto_executable"] == 0
        assert result.metrics["review_required"] == 1


class TestValidatorSafetyGate:
    """验证 RepairPlanValidator 的安全门检查。"""

    def test_validator_rejects_unsupported_action_type(self) -> None:
        """不支持的动作类型被 validator 拒绝。"""
        from mcp.validator import RepairPlanValidator
        validator = RepairPlanValidator()
        plan = {
            "actions": [
                {"action_id": "a1", "type": "delete_pipe"},
            ],
        }
        result = validator.validate(plan, {}, {})
        assert result["valid"] is False
        assert len(result["errors"]) == 1
        assert result["errors"][0]["code"] == "unsupported_action"

    def test_validator_rejects_invalid_dn(self) -> None:
        """无效 DN 被 validator 拒绝。"""
        from mcp.validator import RepairPlanValidator
        validator = RepairPlanValidator()
        plan = {
            "actions": [
                {
                    "action_id": "a1",
                    "type": "add_pipe",
                    "start_node": "n1",
                    "end_node": "n2",
                    "dn": "invalid_dn",
                    "system_type": "给水",
                },
            ],
        }
        result = validator.validate(plan, {}, {"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": []})
        assert result["valid"] is False
        error_codes = [e["code"] for e in result["errors"]]
        assert "invalid_dn" in error_codes

    def test_validator_rejects_duplicate_pipe_in_new_actions(self) -> None:
        """同一 plan 中重复的 add_pipe 被拒绝。"""
        from mcp.validator import RepairPlanValidator
        validator = RepairPlanValidator()
        plan = {
            "actions": [
                {
                    "action_id": "a1",
                    "type": "add_pipe",
                    "start_node": "n1",
                    "end_node": "n2",
                    "dn": 50,
                    "system_type": "给水",
                },
                {
                    "action_id": "a2",
                    "type": "add_pipe",
                    "start_node": "n1",
                    "end_node": "n2",
                    "dn": 50,
                    "system_type": "给水",
                },
            ],
        }
        result = validator.validate(plan, {}, {"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": []})
        assert result["valid"] is False
        error_codes = [e["code"] for e in result["errors"]]
        assert "duplicate_repair_action" in error_codes

    def test_validator_rejects_conflict_with_existing_pipe(self) -> None:
        """与现有管道冲突的补图动作被拒绝。"""
        from mcp.validator import RepairPlanValidator
        validator = RepairPlanValidator()
        plan = {
            "actions": [
                {
                    "action_id": "a1",
                    "type": "add_pipe",
                    "start_node": "n1",
                    "end_node": "n2",
                    "dn": 50,
                    "system_type": "给水",
                },
            ],
        }
        dwg_graph = {
            "nodes": [{"id": "n1"}, {"id": "n2"}],
            "edges": [
                {
                    "semantic_type": "pipe",
                    "start_node_id": "n1",
                    "end_node_id": "n2",
                    "diameter": "DN50",
                    "system_type": "给水",
                },
            ],
        }
        result = validator.validate(plan, dwg_graph, {"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": []})
        assert result["valid"] is False
        error_codes = [e["code"] for e in result["errors"]]
        assert "conflicts_existing_pipe" in error_codes

    def test_validator_accepts_valid_pipe_action(self) -> None:
        """有效的 add_pipe 动作通过验证。"""
        from mcp.validator import RepairPlanValidator
        validator = RepairPlanValidator()
        plan = {
            "actions": [
                {
                    "action_id": "a1",
                    "type": "add_pipe",
                    "start_node": "n1",
                    "end_node": "n2",
                    "dn": 50,
                    "system_type": "给水",
                },
            ],
        }
        ref_graph = {"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": []}
        result = validator.validate(plan, {"nodes": [], "edges": []}, ref_graph)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validator_rejects_same_start_end_node(self) -> None:
        """起点和终点相同的管道被拒绝。"""
        from mcp.validator import RepairPlanValidator
        validator = RepairPlanValidator()
        plan = {
            "actions": [
                {
                    "action_id": "a1",
                    "type": "add_pipe",
                    "start_node": "n1",
                    "end_node": "n1",
                    "dn": 50,
                    "system_type": "给水",
                },
            ],
        }
        ref_graph = {"nodes": [{"id": "n1"}], "edges": []}
        result = validator.validate(plan, {}, ref_graph)
        assert result["valid"] is False
        error_codes = [e["code"] for e in result["errors"]]
        assert "invalid_pipe_connection" in error_codes

    def test_validator_rejects_missing_endpoint_node(self) -> None:
        """不存在的端点 node 被拒绝。"""
        from mcp.validator import RepairPlanValidator
        validator = RepairPlanValidator()
        plan = {
            "actions": [
                {
                    "action_id": "a1",
                    "type": "add_pipe",
                    "start_node": "n1",
                    "end_node": "nonexistent",
                    "dn": 50,
                    "system_type": "给水",
                },
            ],
        }
        ref_graph = {"nodes": [{"id": "n1"}], "edges": []}
        result = validator.validate(plan, {}, ref_graph)
        assert result["valid"] is False
        error_codes = [e["code"] for e in result["errors"]]
        assert "missing_end_node" in error_codes

    def test_validator_rejects_missing_position_for_non_pipe(self) -> None:
        """非 pipe 动作缺少 position 字段被拒绝。"""
        from mcp.validator import RepairPlanValidator
        validator = RepairPlanValidator()
        plan = {
            "actions": [
                {
                    "action_id": "a1",
                    "type": "add_valve",
                },
            ],
        }
        result = validator.validate(plan, {}, {})
        assert result["valid"] is False
        error_codes = [e["code"] for e in result["errors"]]
        assert "missing_position" in error_codes


class TestSchemaRegistrySafety:
    """验证 T30ParameterSchemaRegistry 的安全门逻辑。"""

    def test_unknown_source_not_confirmed(self) -> None:
        """非 CONFIRMED_SCHEMA_SOURCES 来源始终不确认为真。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        from mcp.t30_writeback.parameter_schema import (
            CONFIRMED_SCHEMA_SOURCES,
            T30ParameterSchemaRegistry,
        )
        registry = T30ParameterSchemaRegistry()
        for source in ["unknown", "half_manual", "inferred", "ai_guess"]:
            if source in CONFIRMED_SCHEMA_SOURCES:
                continue
            schema = T30ParameterSchema(
                object_type="TDbPipe",
                method_name="Insert",
                parameters={},
                required_fields=[],
                optional_fields=[],
                defaults={},
                confidence=1.0,
                source=source,
            )
            registry.register_schema(schema)
            assert registry.is_schema_confirmed("TDbPipe", "Insert") is False

    def test_low_confidence_threshold(self) -> None:
        """置信度低于 0.85 的确认来源也不确认。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry
        registry = T30ParameterSchemaRegistry()

        schema_pass = T30ParameterSchema(
            object_type="TDbPipe",
            method_name="Insert",
            parameters={},
            required_fields=[],
            optional_fields=[],
            defaults={},
            confidence=0.85,
            source="manual_probe",
        )
        registry.register_schema(schema_pass)
        assert registry.is_schema_confirmed("TDbPipe", "Insert") is True

        registry2 = T30ParameterSchemaRegistry()
        schema_fail = T30ParameterSchema(
            object_type="TDbPipeValve",
            method_name="Insert",
            parameters={},
            required_fields=[],
            optional_fields=[],
            defaults={},
            confidence=0.84,
            source="manual_probe",
        )
        registry2.register_schema(schema_fail)
        assert registry2.is_schema_confirmed("TDbPipeValve", "Insert") is False
