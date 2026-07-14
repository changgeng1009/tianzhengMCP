"""Bridge 测试 — Mock Bridge
验证 MockBridge 在不连接 AutoCAD 的前提下各项功能正确。"""
from __future__ import annotations
import json
import pytest
from mcp.bridge.schemas import (
    BridgeMode,
    BridgeOperation,
    BridgeOperationType,
    BridgeEntityType,
    BridgeRiskLevel,
    BridgeRequest,
    BridgeResponse,
    BridgeStatusResponse,
    OperationResult,
)
from mcp.bridge.mock_bridge import MockBridge
from mcp.bridge.safety_gate import SafetyGate, SafetyConfig
class TestMockBridge:
    """MockBridge 核心功能测试。"""
    def test_create_mock_bridge(self):
        bridge = MockBridge()
        assert bridge is not None
        assert bridge._connected is False
    def test_status_not_connected(self):
        bridge = MockBridge()
        status = bridge.status()
        assert isinstance(status, BridgeStatusResponse)
        assert status.connected is False
        assert status.real_execution_enabled is False
        assert status.mode == BridgeMode.MOCK.value
    def test_connect_and_disconnect(self):
        bridge = MockBridge()
        status = bridge.connect()
        assert status.connected is True
        status = bridge.disconnect()
        assert status.connected is False
    def test_execute_read_entity(self):
        bridge = MockBridge()
        op = BridgeOperation(
            operation_type=BridgeOperationType.READ_ENTITY,
            entity_type=BridgeEntityType.LINE,
            layer="0",
            reason="测试读取",
        )
        request = BridgeRequest(operations=[op], mode=BridgeMode.MOCK)
        response = bridge.execute(request)
        assert isinstance(response, BridgeResponse)
        assert response.success is True
        assert response.executed is False
        assert response.total_operations == 1
        assert response.succeeded_operations == 1
        assert len(response.results) == 1
        result = response.results[0]
        assert result.success is True
        assert result.status == "executed"
    def test_execute_batch_operations(self):
        bridge = MockBridge()
        ops = [
            BridgeOperation(operation_type=BridgeOperationType.QUERY_STATUS),
            BridgeOperation(operation_type=BridgeOperationType.LIST_DOCUMENTS),
            BridgeOperation(operation_type=BridgeOperationType.CREATE_ENTITY, entity_type=BridgeEntityType.CIRCLE, layer="pipe"),
        ]
        request = BridgeRequest(operations=ops, mode=BridgeMode.MOCK)
        response = bridge.execute(request)
        assert response.total_operations == 3
        assert response.succeeded_operations == 3
        assert response.executed is False
    def test_blocked_delete_operation(self):
        bridge = MockBridge()
        op = BridgeOperation(
            operation_type=BridgeOperationType.DELETE_ENTITY,
            entity_type=BridgeEntityType.LINE,
            reason="测试删除",
        )
        request = BridgeRequest(operations=[op], mode=BridgeMode.MOCK)
        response = bridge.execute(request)
        assert response.success is False
        assert response.safety_passed is False
    def test_high_risk_blocked(self):
        bridge = MockBridge()
        op = BridgeOperation(
            operation_type=BridgeOperationType.TIANZHENG_MODIFY_DIAMETER,
            tianzheng_object_name="TDbPipe",
            risk_level=BridgeRiskLevel.HIGH,
            reason="修改管径",
        )
        request = BridgeRequest(operations=[op], mode=BridgeMode.MOCK)
        response = bridge.execute(request)
        assert response.safety_passed is False
    def test_stats_tracking(self):
        bridge = MockBridge()
        op = BridgeOperation(operation_type=BridgeOperationType.QUERY_STATUS)
        request = BridgeRequest(operations=[op], mode=BridgeMode.MOCK)
        bridge.execute(request)
        stats = bridge.get_stats()
        assert stats.total_requests >= 1
        assert stats.total_operations >= 1
        assert stats.mock_requests >= 1
    def test_response_has_timestamp(self):
        bridge = MockBridge()
        op = BridgeOperation(operation_type=BridgeOperationType.QUERY_STATUS)
        request = BridgeRequest(operations=[op], mode=BridgeMode.MOCK)
        response = bridge.execute(request)
        assert response.timestamp
        assert response.total_duration_ms >= 0
    def test_tianzheng_operations_mock(self):
        bridge = MockBridge()
        ops = [
            BridgeOperation(operation_type=BridgeOperationType.TIANZHENG_ADD_PIPE, tianzheng_object_name="TDbPipe", tianzheng_system="给水", tianzheng_dn="DN100"),
            BridgeOperation(operation_type=BridgeOperationType.TIANZHENG_ADD_VALVE, tianzheng_object_name="TDbPipeValve"),
            BridgeOperation(operation_type=BridgeOperationType.TIANZHENG_ADD_FITTING, entity_type=BridgeEntityType.FITTING, tianzheng_object_name="TDbPipeFitting"),
        ]
        request = BridgeRequest(operations=ops, mode=BridgeMode.MOCK)
        response = bridge.execute(request)
        assert response.succeeded_operations == 3
        assert response.executed is False
        for r in response.results:
            assert r.entity_handle is not None
    def test_to_dict_roundtrip(self):
        bridge = MockBridge()
        op = BridgeOperation(operation_type=BridgeOperationType.READ_ENTITY)
        request = BridgeRequest(operations=[op], mode=BridgeMode.MOCK)
        response = bridge.execute(request)
        d = response.to_dict()
        assert isinstance(d, dict)
        assert d["request_id"] == request.request_id
        assert d["mode"] == BridgeMode.MOCK.value
    def test_bridge_response_empty(self):
        r = BridgeResponse.empty("test-001", BridgeMode.MOCK.value)
        assert r.success is True
        assert r.executed is False
        assert r.total_operations == 0
class TestSafetyGate:
    """SafetyGate 独立测试。"""
    def test_blocked_delete(self):
        gate = SafetyGate()
        op = BridgeOperation(operation_type=BridgeOperationType.DELETE_ENTITY)
        result = gate.validate_operation(op)
        assert result.passed is False
        assert result.severity == "critical"
    def test_tianzheng_without_object_name(self):
        gate = SafetyGate()
        op = BridgeOperation(operation_type=BridgeOperationType.TIANZHENG_ADD_PIPE)
        result = gate.validate_operation(op)
        assert result.passed is False
        assert "tianzheng_object_name" in result.detail
    def test_readonly_operation_passes(self):
        gate = SafetyGate()
        op = BridgeOperation(operation_type=BridgeOperationType.READ_DOCUMENT)
        result = gate.validate_operation(op)
        assert result.passed is True
    def test_real_mode_disabled_by_default(self):
        gate = SafetyGate()
        op = BridgeOperation(operation_type=BridgeOperationType.READ_ENTITY)
        request = BridgeRequest(operations=[op], mode=BridgeMode.REAL)
        result = gate.validate_request(request)
        assert result.passed is False
        assert any("未启用" in r for r in result.blocked_reasons)
    def test_operation_count_limit(self):
        gate = SafetyGate()
        ops = [BridgeOperation(operation_type=BridgeOperationType.READ_ENTITY) for _ in range(200)]
        request = BridgeRequest(operations=ops, mode=BridgeMode.MOCK)
        result = gate.validate_request(request)
        assert result.passed is False
    def test_skip_confirmation_blocked(self):
        gate = SafetyGate()
        op = BridgeOperation(operation_type=BridgeOperationType.READ_ENTITY)
        request = BridgeRequest(operations=[op], mode=BridgeMode.MOCK, skip_confirmation=True)
        result = gate.validate_request(request)
        assert result.passed is False
    def test_validate_read_only(self):
        gate = SafetyGate()
        ops = [
            BridgeOperation(operation_type=BridgeOperationType.READ_ENTITY),
            BridgeOperation(operation_type=BridgeOperationType.READ_DOCUMENT),
        ]
        request = BridgeRequest(operations=ops, mode=BridgeMode.MOCK)
        result = gate.validate_read_only(request)
        assert result.passed is True
    def test_validate_read_only_violation(self):
        gate = SafetyGate()
        ops = [
            BridgeOperation(operation_type=BridgeOperationType.READ_ENTITY),
            BridgeOperation(operation_type=BridgeOperationType.CREATE_ENTITY),
        ]
        request = BridgeRequest(operations=ops, mode=BridgeMode.MOCK)
        result = gate.validate_read_only(request)
        assert result.passed is False
