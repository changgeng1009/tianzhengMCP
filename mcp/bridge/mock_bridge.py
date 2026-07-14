"""天正给排水 MCP Bridge — Mock Bridge 实现
Mock 模式：完全不连接 AutoCAD，不执行任何 CAD 操作。
- 不导入 win32com / 不访问 COM / 不打开 DWG 文件
适用场景：开发调试、单元测试、CI 环境。"""
from __future__ import annotations
import uuid
import time
from typing import Any
from mcp.bridge.schemas import (
    BridgeMode,
    BridgeOperation,
    BridgeOperationType,
    BridgeRequest,
    BridgeResponse,
    BridgeStatusResponse,
    BridgeStats,
    OperationResult,
)
from mcp.bridge.safety_gate import SafetyGate, get_safety_config
_MOCK_DOCUMENTS = [
    {"name": "Drawing1.dwg", "path": "C:\\Projects\\Drawing1.dwg", "active": True},
    {"name": "ReferencePlan.dwg", "path": "C:\\Projects\\ReferencePlan.dwg", "active": False},
]
_handle_counter: int = 0
def _mock_handle() -> str:
    global _handle_counter
    _handle_counter += 1
    return f"MOCK{_handle_counter:06X}"
class MockBridge:
    """Mock Bridge — 纯模拟，零副作用。"""
    def __init__(self) -> None:
        self._stats = BridgeStats()
        self._safety_gate = SafetyGate()
        self._start_time = time.time()
        self._session_id = str(uuid.uuid4())
        self._connected = False
    def execute(self, request: BridgeRequest) -> BridgeResponse:
        start_time = time.time()
        self._stats.total_requests += 1
        self._stats.mock_requests += 1
        safety_result = self._safety_gate.validate_request(request)
        if not safety_result.passed:
            self._stats.blocked_by_safety += 1
            return BridgeResponse(
                request_id=request.request_id,
                mode=request.mode.value,
                success=False,
                executed=False,
                total_operations=len(request.operations),
                safety_passed=False,
                safety_checks=[c.to_dict() for c in safety_result.checks],
                safety_blocked_reasons=safety_result.blocked_reasons,
                warnings=safety_result.warnings,
                errors=[],
                total_duration_ms=(time.time() - start_time) * 1000,
            )
        results: list[OperationResult] = []
        succeeded = 0
        failed = 0
        skipped = 0
        blocked = 0
        for op in request.operations:
            op_result = self._execute_operation(op)
            results.append(op_result)
            if op_result.status == "executed":
                succeeded += 1
            elif op_result.status == "failed":
                failed += 1
            elif op_result.status == "skipped":
                skipped += 1
            elif op_result.status == "blocked":
                blocked += 1
        self._stats.total_operations += len(request.operations)
        if failed > 0:
            self._stats.failed_requests += 1
        return BridgeResponse(
            request_id=request.request_id,
            mode=request.mode.value,
            success=(failed == 0 and blocked == 0),
            executed=False,
            total_operations=len(request.operations),
            succeeded_operations=succeeded,
            failed_operations=failed,
            skipped_operations=skipped,
            blocked_operations=blocked,
            results=results,
            safety_passed=True,
            safety_checks=[c.to_dict() for c in safety_result.checks],
            safety_blocked_reasons=[],
            warnings=["Mock 模式: 所有操作均为模拟"],
            errors=[],
            total_duration_ms=(time.time() - start_time) * 1000,
        )
    def status(self) -> BridgeStatusResponse:
        return BridgeStatusResponse(
            connected=self._connected,
            mode=BridgeMode.MOCK.value,
            active_document=_MOCK_DOCUMENTS[0]["path"] if self._connected else None,
            document_count=len(_MOCK_DOCUMENTS) if self._connected else 0,
            real_execution_enabled=False,
            session_id=self._session_id,
            uptime_seconds=time.time() - self._start_time,
            warnings=["Mock 模式：所有操作均为模拟"],
        )
    def connect(self) -> BridgeStatusResponse:
        self._connected = True
        return self.status()
    def disconnect(self) -> BridgeStatusResponse:
        self._connected = False
        return self.status()
    def get_stats(self) -> BridgeStats:
        return self._stats
    def _execute_operation(self, op: BridgeOperation) -> OperationResult:
        cfg = get_safety_config()
        safety = self._safety_gate.validate_operation(op, cfg)
        if not safety.passed:
            return OperationResult(
                operation_id=op.operation_id,
                operation_type=op.operation_type.value,
                success=False,
                executed=False,
                status="blocked",
                message=f"安全检查未通过: {safety.message}",
                warnings=[safety.detail] if safety.detail else [],
            )
        op_type = op.operation_type
        if op_type == BridgeOperationType.CONNECT:
            self._connected = True
            return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=True, status="executed", message="[mock] 已连接到 AutoCAD (模拟)")
        if op_type == BridgeOperationType.DISCONNECT:
            self._connected = False
            return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=True, status="executed", message="[mock] 已断开 AutoCAD (模拟)")
        if op_type == BridgeOperationType.QUERY_STATUS:
            return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=True, status="executed", message="[mock] AutoCAD 状态正常")
        if op_type == BridgeOperationType.LIST_DOCUMENTS:
            return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=True, status="executed", message=f"[mock] 已打开 {len(_MOCK_DOCUMENTS)} 个文档")
        if op_type == BridgeOperationType.READ_DOCUMENT:
            return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=True, status="executed", message="[mock] 文档读取完成")
        if op_type == BridgeOperationType.READ_ENTITY:
            h = _mock_handle()
            return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=True, status="executed", message=f"[mock] 实体读取完成, handle={h}", entity_handle=op.handle or h, simulated_geometry={"mock": True, "type": "line"})
        if op_type == BridgeOperationType.CREATE_ENTITY:
            h = _mock_handle()
            return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=False, status="executed", message=f"[mock] 实体创建成功 (模拟), handle={h}", entity_handle=h, simulated_geometry=op.geometry)
        if op_type == BridgeOperationType.MODIFY_ENTITY:
            return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=False, status="executed", message=f"[mock] 实体修改成功 (模拟), handle={op.handle or 'N/A'}", entity_handle=op.handle, simulated_geometry=op.geometry)
        if op_type.value.startswith("tianzheng_"):
            h = _mock_handle()
            return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=False, status="executed", message=f"[mock] 天正操作 {op_type.value} 成功 (模拟), handle={h}", entity_handle=h, simulated_geometry=op.geometry)
        return OperationResult(operation_id=op.operation_id, operation_type=op_type.value, success=True, executed=False, status="executed", message=f"[mock] 操作 {op_type.value} 成功 (模拟)")
_default_mock_bridge: MockBridge | None = None
def get_mock_bridge() -> MockBridge:
    global _default_mock_bridge
    if _default_mock_bridge is None:
        _default_mock_bridge = MockBridge()
    return _default_mock_bridge
__all__ = ["MockBridge", "get_mock_bridge"]
