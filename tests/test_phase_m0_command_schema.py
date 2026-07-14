"""Phase M0: command schema 合法性验证测试。

验证 mcp 中所有命令相关 dataclass/schema 的结构合法性，
包括字段类型、必需字段、to_dict 输出格式、schema registry 等。
"""
from __future__ import annotations

import pytest


class TestRepairActionSchema:
    """验证 RepairAction dataclass 的 schema 合法性。"""

    def test_repair_action_construction_valid(self) -> None:
        """合法构造不会抛出异常。"""
        from mcp.repair_actions.models import RepairAction
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
        assert action.action_id == "a1"
        assert action.confidence == 0.9
        assert action.auto_execute is True

    def test_repair_action_to_dict_contains_all_fields(self) -> None:
        """to_dict 输出包含所有字段且类型正确。"""
        from mcp.repair_actions.models import RepairAction
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
            confidence=0.85,
            auto_execute=False,
            reason="missing",
            validation_status="valid",
        )
        d = action.to_dict()
        assert d["action_id"] == "a2"
        assert d["action_type"] == "add_valve"
        assert isinstance(d["confidence"], float)
        assert isinstance(d["auto_execute"], bool)
        assert isinstance(d["warnings"], list)
        assert isinstance(d["metadata"], dict)

    def test_repair_action_default_warnings_and_metadata(self) -> None:
        """默认的 warnings 和 metadata 为空列表和空字典。"""
        from mcp.repair_actions.models import RepairAction
        action = RepairAction(
            action_id="a3",
            action_type="add_sprinkler",
            target_space="cad_modelspace",
            geometry={},
            system=None,
            dn=None,
            layer=None,
            source_element_id="s3",
            source_type="vision",
            confidence=0.5,
            auto_execute=False,
            reason="unknown",
            validation_status="pending",
        )
        assert action.warnings == []
        assert action.metadata == {}

    def test_repair_action_to_dict_immutable_warnings(self) -> None:
        """to_dict 返回的 warnings 应为独立副本。"""
        from mcp.repair_actions.models import RepairAction
        action = RepairAction(
            action_id="a4",
            action_type="add_pipe",
            target_space="cad_modelspace",
            geometry={},
            system=None,
            dn=None,
            layer=None,
            source_element_id="p4",
            source_type="vision",
            confidence=0.8,
            auto_execute=True,
            reason="missing",
            validation_status="valid",
            warnings=["test_warning"],
        )
        d = action.to_dict()
        d["warnings"].append("should_not_affect_original")
        assert len(action.warnings) == 1
        assert action.warnings == ["test_warning"]


class TestRepairPlanV2Schema:
    """验证 RepairPlanV2 dataclass 的 schema 合法性。"""

    def test_empty_plan_construction(self) -> None:
        """空 plan 可以正常构造。"""
        from mcp.repair_actions.models import RepairPlanV2
        plan = RepairPlanV2(
            plan_id="plan-1",
            source_reference_graph_id="ref-1",
            target_graph_id="tgt-1",
            actions=[],
            review_actions=[],
            rejected_actions=[],
            confidence=1.0,
        )
        assert plan.plan_id == "plan-1"
        assert len(plan.actions) == 0

    def test_plan_to_dict_serializes_nested_actions(self) -> None:
        """to_dict 可以正确序列化嵌套的 RepairAction 列表。"""
        from mcp.repair_actions.models import RepairAction, RepairPlanV2
        action = RepairAction(
            action_id="a1",
            action_type="add_pipe",
            target_space="cad_modelspace",
            geometry={"type": "line"},
            system="给水",
            dn="DN25",
            layer="PIPE-给水",
            source_element_id="p1",
            source_type="vision",
            confidence=0.95,
            auto_execute=True,
            reason="missing",
            validation_status="valid",
        )
        plan = RepairPlanV2(
            plan_id="plan-2",
            source_reference_graph_id="ref-1",
            target_graph_id="tgt-1",
            actions=[action],
            review_actions=[],
            rejected_actions=[],
            confidence=0.9,
            warnings=["low_confidence"],
            errors=[],
        )
        d = plan.to_dict()
        assert d["plan_id"] == "plan-2"
        assert len(d["actions"]) == 1
        assert d["actions"][0]["action_id"] == "a1"
        assert d["actions"][0]["dn"] == "DN25"
        assert d["warnings"] == ["low_confidence"]
        assert isinstance(d["confidence"], float)


class TestGeometryMatchResultSchema:
    """验证 GeometryMatchResult 的 schema 合法性。"""

    def test_matched_result_to_dict(self) -> None:
        """匹配成功的 to_dict 输出正确。"""
        from mcp.repair_actions.models import GeometryMatchResult
        result = GeometryMatchResult(
            matched=True,
            distance=0.5,
            tolerance=1.0,
            confidence=0.95,
            reason="near_anchor",
            target_element_id="e1",
        )
        d = result.to_dict()
        assert d["matched"] is True
        assert d["distance"] == 0.5
        assert d["target_element_id"] == "e1"

    def test_unmatched_result_to_dict(self) -> None:
        """未匹配的结果 target_element_id 为 None。"""
        from mcp.repair_actions.models import GeometryMatchResult
        result = GeometryMatchResult(
            matched=False,
            distance=100.0,
            tolerance=1.0,
            confidence=0.0,
            reason="too_far",
            target_element_id=None,
        )
        d = result.to_dict()
        assert d["matched"] is False
        assert d["target_element_id"] is None


class TestDryRunResultSchema:
    """验证 DryRunResult 的 schema 合法性。"""

    def test_dry_run_result_to_dict(self) -> None:
        """DryRunResult to_dict 输出完整。"""
        from mcp.repair_actions.models import DryRunResult
        result = DryRunResult(
            valid=True,
            executable_actions=[{"action_id": "a1"}],
            review_actions=[{"action_id": "a2"}],
            rejected_actions=[],
            simulated_entities=[{"dry_run": True}],
            warnings=["low_confidence"],
            errors=[],
            metrics={"auto_executable": 1, "review_required": 1, "rejected": 0},
        )
        d = result.to_dict()
        assert d["valid"] is True
        assert d["metrics"]["auto_executable"] == 1
        assert d["simulated_entities"][0]["dry_run"] is True

    def test_dry_run_result_invalid_plan(self) -> None:
        """无效的 plan 产生 valid=False 的结果。"""
        from mcp.repair_actions.models import DryRunResult
        result = DryRunResult(
            valid=False,
            executable_actions=[],
            review_actions=[],
            rejected_actions=[{"action_id": "bad"}],
            simulated_entities=[],
            warnings=[],
            errors=["validation_failed"],
            metrics={"auto_executable": 0, "review_required": 0, "rejected": 1},
        )
        assert result.valid is False
        assert len(result.errors) == 1


class TestT30ParameterSchema:
    """验证 T30ParameterSchema 的结构。"""

    def test_schema_construction_full(self) -> None:
        """完整构造参数 schema。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        schema = T30ParameterSchema(
            object_type="TDbPipe",
            method_name="Insert",
            parameters={"geometry": "json", "system": "str"},
            required_fields=["geometry", "system", "dn", "layer"],
            optional_fields=["metadata"],
            defaults={"layer": "PIPE-给水"},
            confidence=1.0,
            source="fake_com",
            warnings=[],
        )
        assert schema.object_type == "TDbPipe"
        assert schema.method_name == "Insert"
        assert schema.confidence == 1.0
        assert schema.source == "fake_com"

    def test_schema_default_source(self) -> None:
        """source 默认为 unknown。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        schema = T30ParameterSchema(
            object_type="TDbPipeValve",
            method_name="Insert",
            parameters={},
            required_fields=[],
            optional_fields=[],
            defaults={},
            confidence=0.0,
        )
        assert schema.source == "unknown"

    def test_schema_to_dict(self) -> None:
        """to_dict 输出完整。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        schema = T30ParameterSchema(
            object_type="TDbSprinkler",
            method_name="Insert",
            parameters={"pos": "list"},
            required_fields=["geometry", "system", "layer"],
            optional_fields=["sprinkler_type"],
            defaults={"layer": "SPRINKLER"},
            confidence=0.9,
            source="manual_probe",
        )
        d = schema.to_dict()
        assert d["object_type"] == "TDbSprinkler"
        assert isinstance(d["confidence"], float)
        assert isinstance(d["required_fields"], list)


class TestT30ParameterSchemaRegistry:
    """验证 T30ParameterSchemaRegistry 的功能。"""

    def test_register_and_get_schema(self) -> None:
        """注册后可以按 (object_type, method_name) 查找。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry
        registry = T30ParameterSchemaRegistry()
        schema = T30ParameterSchema(
            object_type="TDbPipe",
            method_name="Insert",
            parameters={"geometry": "json"},
            required_fields=["geometry"],
            optional_fields=[],
            defaults={},
            confidence=0.95,
            source="manual_probe",
        )
        registry.register_schema(schema)
        retrieved = registry.get_schema("TDbPipe", "Insert")
        assert retrieved is not None
        assert retrieved.object_type == "TDbPipe"

    def test_get_nonexistent_schema_returns_none(self) -> None:
        """查找不存在的 schema 返回 None。"""
        from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry
        registry = T30ParameterSchemaRegistry()
        assert registry.get_schema("NonExistent", "Insert") is None

    def test_is_schema_confirmed_high_confidence(self) -> None:
        """高置信度 + 确认来源 -> 确认状态。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry
        registry = T30ParameterSchemaRegistry()
        schema = T30ParameterSchema(
            object_type="TDbPipe",
            method_name="Insert",
            parameters={},
            required_fields=[],
            optional_fields=[],
            defaults={},
            confidence=0.90,
            source="manual_probe",
        )
        registry.register_schema(schema)
        assert registry.is_schema_confirmed("TDbPipe", "Insert") is True

    def test_is_schema_not_confirmed_low_confidence(self) -> None:
        """低置信度 -> 非确认状态。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry
        registry = T30ParameterSchemaRegistry()
        schema = T30ParameterSchema(
            object_type="TDbPipeValve",
            method_name="Insert",
            parameters={},
            required_fields=[],
            optional_fields=[],
            defaults={},
            confidence=0.70,
            source="manual_probe",
        )
        registry.register_schema(schema)
        assert registry.is_schema_confirmed("TDbPipeValve", "Insert") is False

    def test_is_schema_not_confirmed_unknown_source(self) -> None:
        """非确认来源的 schema 不是确认状态。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry
        registry = T30ParameterSchemaRegistry()
        schema = T30ParameterSchema(
            object_type="TDbSprinkler",
            method_name="Insert",
            parameters={},
            required_fields=[],
            optional_fields=[],
            defaults={},
            confidence=0.99,
            source="unknown",
        )
        registry.register_schema(schema)
        assert registry.is_schema_confirmed("TDbSprinkler", "Insert") is False

    def test_load_from_probe_result(self) -> None:
        """从 probe 结果中加载 schema 列表。"""
        from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry
        registry = T30ParameterSchemaRegistry()
        probe_result = {
            "schemas": [
                {
                    "object_type": "TDbPipe",
                    "method_name": "Insert",
                    "parameters": {"dn": "int"},
                    "required_fields": ["dn"],
                    "optional_fields": [],
                    "defaults": {},
                    "confidence": 0.95,
                    "source": "fake_com",
                    "warnings": [],
                },
                {
                    "object_type": "TDbPipeFitting",
                    "method_name": "Insert",
                    "parameters": {"type": "str"},
                    "required_fields": ["type"],
                    "optional_fields": ["angle"],
                    "defaults": {"angle": 0},
                    "confidence": 0.88,
                    "source": "fake_com",
                    "warnings": ["low_coverage"],
                },
            ]
        }
        registry.load_from_probe_result(probe_result)
        assert registry.get_schema("TDbPipe", "Insert") is not None
        assert registry.get_schema("TDbPipeFitting", "Insert") is not None
        assert registry.is_schema_confirmed("TDbPipe", "Insert") is True

    def test_export_schema_json(self) -> None:
        """导出 JSON 格式正确。"""
        from mcp.t30_writeback.models import T30ParameterSchema
        from mcp.t30_writeback.parameter_schema import T30ParameterSchemaRegistry
        registry = T30ParameterSchemaRegistry()
        registry.register_schema(T30ParameterSchema(
            object_type="TDbPipe",
            method_name="Insert",
            parameters={},
            required_fields=["geometry"],
            optional_fields=[],
            defaults={},
            confidence=0.95,
            source="fake_com",
        ))
        exported = registry.export_schema_json()
        assert "schemas" in exported
        assert len(exported["schemas"]) == 1
        assert exported["schemas"][0]["object_type"] == "TDbPipe"

    def test_build_fake_schema_registry(self) -> None:
        """build_fake_schema_registry 生成 4 个对象的 schema。"""
        from mcp.t30_writeback.parameter_schema import build_fake_schema_registry
        registry = build_fake_schema_registry()
        schemas = ["TDbPipe", "TDbPipeValve", "TDbSprinkler", "TDbPipeFitting"]
        for obj_type in schemas:
            assert registry.get_schema(obj_type, "Insert") is not None
            assert registry.is_schema_confirmed(obj_type, "Insert") is True


class TestT30CapabilitySchema:
    """验证 T30Capability 的 schema 合法性。"""

    def test_capability_to_dict(self) -> None:
        """to_dict 输出格式正确。"""
        from mcp.t30_writeback.models import T30Capability
        cap = T30Capability(
            capability_id="cap-1",
            object_type="TDbPipe",
            method_name="Insert",
            available=True,
            confidence=0.95,
            signature={"params": {"dn": "int"}},
            probe_status="confirmed",
        )
        d = cap.to_dict()
        assert d["capability_id"] == "cap-1"
        assert d["available"] is True
        assert isinstance(d["confidence"], float)
        assert d["signature"] == {"params": {"dn": "int"}}

    def test_capability_default_probe_status(self) -> None:
        """默认 probe_status 是 unconfirmed。"""
        from mcp.t30_writeback.models import T30Capability
        cap = T30Capability(
            capability_id="cap-2",
            object_type="TDbValve",
            method_name="Insert",
            available=False,
            confidence=0.0,
        )
        assert cap.probe_status == "unconfirmed"


class TestT30WritebackActionSchema:
    """验证 T30WritebackAction 的 schema 合法性。"""

    def test_writeback_action_to_dict(self) -> None:
        """to_dict 输出完整。"""
        from mcp.t30_writeback.models import T30WritebackAction
        action = T30WritebackAction(
            action_id="wa-1",
            source_repair_action_id="ra-1",
            object_type="TDbPipe",
            method_name="Insert",
            parameters={"dn": 50},
            geometry={"start": [0, 0, 0], "end": [100, 0, 0]},
            system="给水",
            dn="DN50",
            layer="PIPE-给水",
            confidence=0.9,
            capability_status="confirmed",
            ready_to_execute=True,
        )
        d = action.to_dict()
        assert d["action_id"] == "wa-1"
        assert d["ready_to_execute"] is True
        assert isinstance(d["parameters"], dict)

    def test_writeback_action_not_ready(self) -> None:
        """未就绪的动作 ready_to_execute=False。"""
        from mcp.t30_writeback.models import T30WritebackAction
        action = T30WritebackAction(
            action_id="wa-2",
            source_repair_action_id="ra-2",
            object_type="TDbPipeFitting",
            method_name="Insert",
            parameters={},
            geometry={},
            system=None,
            dn=None,
            layer=None,
            confidence=0.3,
            capability_status="unconfirmed",
            ready_to_execute=False,
        )
        assert action.ready_to_execute is False
        assert action.capability_status == "unconfirmed"


class TestT30TransactionSchema:
    """验证 T30Transaction 的 schema 合法性。"""

    def test_transaction_default_status(self) -> None:
        """默认 status 为 planned。"""
        from mcp.t30_writeback.models import T30Transaction
        tx = T30Transaction(
            transaction_id="tx-1",
            session_id="sess-1",
            sandbox_dwg_path="/tmp/sandbox.dwg",
            original_dwg_path="/tmp/original.dwg",
            backup_path="/tmp/backup.dwg",
            actions=[],
        )
        assert tx.status == "planned"
        assert tx.transaction_log == []

    def test_transaction_to_dict(self) -> None:
        """to_dict 输出正确序列化。"""
        from mcp.t30_writeback.models import T30Transaction, T30WritebackAction
        action = T30WritebackAction(
            action_id="wa-1",
            source_repair_action_id="ra-1",
            object_type="TDbPipe",
            method_name="Insert",
            parameters={},
            geometry={},
            system=None,
            dn=None,
            layer=None,
            confidence=0.9,
            capability_status="confirmed",
            ready_to_execute=True,
        )
        tx = T30Transaction(
            transaction_id="tx-2",
            session_id="sess-2",
            sandbox_dwg_path="/s/dwg.dwg",
            original_dwg_path="/o/dwg.dwg",
            backup_path="/b/dwg.dwg",
            actions=[action],
            errors=["err1"],
        )
        d = tx.to_dict()
        assert d["transaction_id"] == "tx-2"
        assert len(d["actions"]) == 1
        assert d["errors"] == ["err1"]


class TestT30WritebackResultSchema:
    """验证 T30WritebackResult 的 schema 合法性。"""

    def test_writeback_result_to_dict(self) -> None:
        """to_dict 输出完整。"""
        from mcp.t30_writeback.models import T30WritebackResult
        result = T30WritebackResult(
            transaction_id="tx-1",
            status="committed",
            executed_actions=[{"action_id": "wa-1"}],
            failed_actions=[],
            skipped_actions=[],
            created_entities=[{"handle": "2A3", "type": "TDbPipe"}],
            verification={"passed": True},
            rollback_available=True,
        )
        d = result.to_dict()
        assert d["status"] == "committed"
        assert d["rollback_available"] is True
        assert len(d["created_entities"]) == 1

    def test_writeback_result_failed_status(self) -> None:
        """失败状态的 rollback 仍可能可用。"""
        from mcp.t30_writeback.models import T30WritebackResult
        result = T30WritebackResult(
            transaction_id="tx-2",
            status="partially_committed",
            executed_actions=[],
            failed_actions=[{"action_id": "wa-2", "error": "COM failed"}],
            skipped_actions=[],
            created_entities=[],
            verification={"passed": False},
            rollback_available=True,
            errors=["partially_committed"],
        )
        assert result.status == "partially_committed"
        assert len(result.failed_actions) == 1
