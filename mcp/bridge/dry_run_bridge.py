"""天正给排水 MCP Bridge — Dry-Run Bridge 实现
Dry-Run 模式：分析并输出预期的 AutoCAD/天正 操作命令，但不执行任何真实的 CAD 操作。
适用场景：命令预览、变更审核、前置验证。"""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import time
import uuid
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
@dataclass
class DryRunTrace:
    """记录单次 dry-run 操作的预期命令轨迹。"""
    operation_id: str = ""
    operation_type: str = ""
    expected_command: str = ""
    expected_geometry: dict = field(default_factory=dict)
    expected_properties: dict = field(default_factory=dict)
    risk_level: str = "low"
    warnings: list = field(default_factory=list)
    would_modify_dwg: bool = False
    def to_dict(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "expected_command": self.expected_command,
            "expected_geometry": dict(self.expected_geometry),
            "expected_properties": dict(self.expected_properties),
            "risk_level": self.risk_level,
            "warnings": list(self.warnings),
            "would_modify_dwg": self.would_modify_dwg,
        }
class _DryRunCommandGenerator:
    """将 BridgeOperation 转换为预期命令字符串。"""
    @staticmethod
    def generate(op: BridgeOperation) -> tuple:
        op_type = op.operation_type
        if op_type == BridgeOperationType.CREATE_ENTITY:
            entity_label = op.entity_type.value.upper()
            cmd = f"[预期] 创建 {entity_label} — 图层={op.layer}"
            if op.geometry:
                cmd += f"  几何数据={json.dumps(op.geometry, ensure_ascii=False)}"
            return cmd, True
        if op_type == BridgeOperationType.MODIFY_ENTITY:
            cmd = f"[预期] 修改实体 handle={op.handle or 'N/A'} — {op.reason or '无原因'}"
            if op.properties:
                cmd += f"  属性={json.dumps(op.properties, ensure_ascii=False)}"
            return cmd, True
        if op_type == BridgeOperationType.DELETE_ENTITY:
            return f"[预期] 删除实体 handle={op.handle or 'N/A'}", True
        if op_type == BridgeOperationType.SET_LAYER:
            return f"[预期] 设置图层 — handle={op.handle or 'N/A'} -> layer={op.layer}", True
        if op_type == BridgeOperationType.SET_PROPERTY:
            cmd = f"[预期] 设置属性 — handle={op.handle or 'N/A'}"
            if op.properties:
                cmd += f"  属性={json.dumps(op.properties, ensure_ascii=False)}"
            return cmd, True
        if op_type == BridgeOperationType.SEND_COMMAND:
            cmd_text = op.properties.get("command", "")
            return f"[预期] 执行命令: {cmd_text}", True
        if op_type == BridgeOperationType.TIANZHENG_ADD_PIPE:
            return (f"[预期] 天正-添加管道 — 系统={op.tianzheng_system or 'N/A'} 管径={op.tianzheng_dn or 'N/A'} 图层={op.layer}", True)
        if op_type == BridgeOperationType.TIANZHENG_ADD_VALVE:
            return (f"[预期] 天正-添加阀门 — 系统={op.tianzheng_system or 'N/A'} 管径={op.tianzheng_dn or 'N/A'}", True)
        if op_type == BridgeOperationType.TIANZHENG_ADD_FITTING:
            return (f"[预期] 天正-添加管件 — 类型={op.entity_type.value} 图层={op.layer}", True)
        if op_type == BridgeOperationType.TIANZHENG_MODIFY_DIAMETER:
            return (f"[预期] 天正-修改管径 — handle={op.handle or 'N/A'} 新管径={op.tianzheng_dn or 'N/A'}", True)
        if op_type == BridgeOperationType.TIANZHENG_MODIFY_ELEVATION:
            new_elev = op.properties.get("elevation", "N/A")
            return f"[预期] 天正-修改标高 — handle={op.handle or 'N/A'} 新标高={new_elev}", True
        if op_type == BridgeOperationType.TIANZHENG_MODIFY_SYSTEM:
            return (f"[预期] 天正-修改系统类型 — handle={op.handle or 'N/A'} 新系统={op.tianzheng_system or 'N/A'}", True)
        if op_type == BridgeOperationType.TIANZHENG_CONNECT_PIPE:
            return f"[预期] 天正-管道连接 — 几何={json.dumps(op.geometry, ensure_ascii=False)}", True
        if op_type == BridgeOperationType.TIANZHENG_DELETE_OBJECT:
            return f"[预期] 天正-删除对象 — handle={op.handle or 'N/A'}", True
        if op_type == BridgeOperationType.READ_ENTITY:
            return f"[只读] 读取实体 — handle={op.handle or 'N/A'}", False
        if op_type == BridgeOperationType.READ_DOCUMENT:
            return "[只读] 读取当前文档", False
        if op_type == BridgeOperationType.QUERY_STATUS:
            return "[只读] 查询 AutoCAD 状态", False
        if op_type == BridgeOperationType.LIST_DOCUMENTS:
            return "[只读] 列出文档", False
        if op_type == BridgeOperationType.CONNECT:
            return "[管理] 连接 AutoCAD", False
        if op_type == BridgeOperationType.DISCONNECT:
            return "[管理] 断开 AutoCAD", False
        return f"[未知] {op_type.value}", False
class DryRunBridge:
    """Dry-Run Bridge — 输出预期命令但不执行。"""
    def __init__(self) -> None:
        self._stats = BridgeStats()
        self._safety_gate = SafetyGate()
        self._command_gen = _DryRunCommandGenerator()
        self._start_time = time.time()
        self._session_id = str(uuid.uuid4())
        self._traces: list[DryRunTrace] = []
    def execute(self, request: BridgeRequest) -> BridgeResponse:
        start_time = time.time()
        self._stats.total_requests += 1
        self._stats.dry_run_requests += 1
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
        traces: list[DryRunTrace] = []
        would_modify = 0
        read_only_ops = 0
        for op in request.operations:
            cmd, modifies = self._command_gen.generate(op)
            trace = DryRunTrace(
                operation_id=op.operation_id,
                operation_type=op.operation_type.value,
                expected_command=cmd,
                expected_geometry=op.geometry,
                expected_properties=op.properties,
                risk_level=op.risk_level.value,
                warnings=[f"Dry-run: 操作不会实际执行，预期命令: {cmd[:80]}..."],
                would_modify_dwg=modifies,
            )
            traces.append(trace)
            if modifies:
                would_modify += 1
            else:
                read_only_ops += 1
            results.append(OperationResult(
                operation_id=op.operation_id,
                operation_type=op.operation_type.value,
                success=True,
                executed=False,
                status="executed",
                message=f"[dry-run] {cmd[:120]}",
                simulated_geometry=op.geometry,
                warnings=["操作不会实际执行，预期命令已生成，需确认后才可执行。"],
            ))
        self._traces.extend(traces)
        self._stats.total_operations += len(request.operations)
        warnings = [f"Dry-Run 模式: {len(request.operations)} 个操作已分析，均未执行", f"会修改 DWG 的操作: {would_modify}", f"只读操作: {read_only_ops}"]
        if would_modify > 0:
            warnings.append("包含写操作，请审核 dry-run 追踪记录后再确认执行")
        return BridgeResponse(
            request_id=request.request_id,
            mode=request.mode.value,
            success=True,
            executed=False,
            total_operations=len(request.operations),
            succeeded_operations=len(request.operations),
            failed_operations=0,
            skipped_operations=0,
            blocked_operations=0,
            results=results,
            safety_passed=True,
            safety_checks=[c.to_dict() for c in safety_result.checks],
            safety_blocked_reasons=[],
            warnings=warnings,
            errors=[],
            metadata={"bridge": "dry_run", "session_id": self._session_id, "would_modify_dwg": would_modify, "traces_count": len(traces)},
            total_duration_ms=(time.time() - start_time) * 1000,
        )
    def preview(self, request: BridgeRequest) -> list[DryRunTrace]:
        traces: list[DryRunTrace] = []
        for op in request.operations:
            cmd, modifies = self._command_gen.generate(op)
            traces.append(DryRunTrace(
                operation_id=op.operation_id,
                operation_type=op.operation_type.value,
                expected_command=cmd,
                expected_geometry=op.geometry,
                expected_properties=op.properties,
                risk_level=op.risk_level.value,
                would_modify_dwg=modifies,
            ))
        return traces
    def status(self) -> BridgeStatusResponse:
        return BridgeStatusResponse(
            connected=False,
            mode=BridgeMode.DRY_RUN.value,
            active_document=None,
            document_count=0,
            real_execution_enabled=False,
            session_id=self._session_id,
            uptime_seconds=time.time() - self._start_time,
            warnings=["Dry-Run 模式: 不连接 AutoCAD, 所有操作仅生成预期命令"],
        )
    def get_traces(self) -> list[DryRunTrace]:
        return list(self._traces)
    def get_stats(self) -> BridgeStats:
        return self._stats
    @staticmethod
    def traces_to_dict_list(traces: list[DryRunTrace]) -> list[dict]:
        return [t.to_dict() for t in traces]
def generate_dry_run_report(traces, request_id=""):
    total = len(traces)
    would_modify = sum(1 for t in traces if t.would_modify_dwg)
    high_risk = sum(1 for t in traces if t.risk_level in ("high", "critical"))
    return {
        "request_id": request_id,
        "total_operations": total,
        "would_modify_dwg": would_modify,
        "read_only_operations": total - would_modify,
        "high_risk_operations": high_risk,
        "traces": [t.to_dict() for t in traces],
        "summary": f"共 {total} 个操作, {would_modify} 个会修改 DWG, {high_risk} 个高风险。所有操作均为 dry-run，未执行。",
    }
_default_dry_run_bridge = None
def get_dry_run_bridge():
    global _default_dry_run_bridge
    if _default_dry_run_bridge is None:
        _default_dry_run_bridge = DryRunBridge()
    return _default_dry_run_bridge
__all__ = ["DryRunTrace", "DryRunBridge", "get_dry_run_bridge", "generate_dry_run_report"]
