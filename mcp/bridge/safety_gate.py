"""天正给排水 MCP Bridge — 安全门模块
所有 bridge 操作在允许执行前必须通过安全门校验。
分层：操作级校验 / 请求级校验 / 模式级校验。"""
from __future__ import annotations
from typing import Any
from mcp.bridge.schemas import (
    BridgeMode,
    BridgeOperation,
    BridgeOperationType,
    BridgeRequest,
    BridgeRiskLevel,
    SafetyCheckResult,
    SafetyGateResult,
)
_PERMANENTLY_BLOCKED_OPERATIONS = frozenset({
    BridgeOperationType.DELETE_ENTITY,
    BridgeOperationType.TIANZHENG_DELETE_OBJECT,
})
_HIGH_RISK_OPERATIONS = frozenset({
    BridgeOperationType.MODIFY_ENTITY,
    BridgeOperationType.TIANZHENG_MODIFY_DIAMETER,
    BridgeOperationType.TIANZHENG_MODIFY_ELEVATION,
    BridgeOperationType.TIANZHENG_MODIFY_SYSTEM,
})
_CRITICAL_RISK_OPERATIONS = frozenset({
    BridgeOperationType.DELETE_ENTITY,
    BridgeOperationType.TIANZHENG_DELETE_OBJECT,
})
_ALL_OPS = list(BridgeOperationType)
_MODE_ALLOWED_OPERATIONS = {
    BridgeMode.MOCK: frozenset(_ALL_OPS),
    BridgeMode.DRY_RUN: frozenset(_ALL_OPS),
    BridgeMode.REAL: frozenset(),
}
class SafetyConfig:
    real_execution_enabled: bool = False
    max_operations_per_request: int = 100
    require_operation_confirm: bool = True
    allow_high_risk: bool = False
    _instance: SafetyConfig | None = None
    def __new__(cls) -> SafetyConfig:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    @classmethod
    def reset(cls) -> None:
        cls._instance = None
def get_safety_config() -> SafetyConfig:
    return SafetyConfig()
def enable_real_execution() -> None:
    cfg = get_safety_config()
    cfg.real_execution_enabled = True
def disable_real_execution() -> None:
    cfg = get_safety_config()
    cfg.real_execution_enabled = False
class SafetyGate:
    def validate_operation(self, operation: BridgeOperation, config: SafetyConfig | None = None) -> SafetyCheckResult:
        cfg = config or get_safety_config()
        checks: list[SafetyCheckResult] = []
        if operation.operation_type in _PERMANENTLY_BLOCKED_OPERATIONS:
            checks.append(SafetyCheckResult(check_name="blocked_operation", passed=False, severity="critical", message=f"操作类型 {operation.operation_type.value} 被永久禁止", detail="DELETE 操作不允许在当前系统架构中执行"))
        if operation.operation_type in _CRITICAL_RISK_OPERATIONS:
            checks.append(SafetyCheckResult(check_name="critical_risk", passed=False, severity="critical", message=f"操作 {operation.operation_type.value} 被标记为严重风险，已阻止", detail=""))
        if operation.operation_type in _HIGH_RISK_OPERATIONS and not cfg.allow_high_risk:
            checks.append(SafetyCheckResult(check_name="high_risk", passed=False, severity="high", message=f"操作 {operation.operation_type.value} 为高风险操作，当前不允许执行", detail="如需执行，请设置 allow_high_risk=True"))
        if operation.operation_type.value.startswith("tianzheng_") and not operation.tianzheng_object_name:
            checks.append(SafetyCheckResult(check_name="tianzheng_object_name_missing", passed=False, severity="medium", message=f"天正操作 {operation.operation_type.value} 缺少 tianzheng_object_name", detail="天正操作必须指定对象类型名称"))
        if operation.risk_level in (BridgeRiskLevel.HIGH, BridgeRiskLevel.CRITICAL) and not operation.requires_confirmation:
            checks.append(SafetyCheckResult(check_name="high_risk_no_confirm", passed=False, severity="high", message=f"高风险/严重操作 {operation.operation_id} 禁用了确认要求", detail="高风险操作不能跳过确认步骤"))
        all_passed = all(c.passed for c in checks)
        failed = [c for c in checks if not c.passed]
        message = "所有检查通过" if all_passed else f"{len(failed)} 项检查未通过"
        if not all_passed:
            critical = [c for c in failed if c.severity == "critical"]
            high = [c for c in failed if c.severity == "high"]
            worst = (critical or high or failed)[0]
            return SafetyCheckResult(check_name="operation_validation", passed=False, severity=worst.severity, message=message, detail="; ".join(c.message for c in failed))
        return SafetyCheckResult(check_name="operation_validation", passed=True, severity="low", message=message, detail="")
    def validate_request(self, request: BridgeRequest, config: SafetyConfig | None = None) -> SafetyGateResult:
        cfg = config or get_safety_config()
        checks: list[SafetyCheckResult] = []
        blocked: list[str] = []
        warnings: list[str] = []
        if request.mode == BridgeMode.REAL and not cfg.real_execution_enabled:
            checks.append(SafetyCheckResult(check_name="real_execution_disabled", passed=False, severity="critical", message="真实执行模式未启用", detail="默认禁用真实执行，请调用 enable_real_execution() 显式启用"))
            blocked.append("真实执行模式未启用")
        if len(request.operations) > cfg.max_operations_per_request:
            checks.append(SafetyCheckResult(check_name="operation_count_exceeded", passed=False, severity="high", message=f"操作数量 {len(request.operations)} 超过上限 {cfg.max_operations_per_request}", detail="请减少单次请求的操作数量"))
            blocked.append(f"操作数量超限: {len(request.operations)}/{cfg.max_operations_per_request}")
        if request.skip_confirmation:
            checks.append(SafetyCheckResult(check_name="skip_confirmation", passed=False, severity="high", message="请求试图跳过确认环节", detail="skip_confirmation 不可用于生产请求"))
            blocked.append("skip_confirmation 未允许")
        allowed_set = _MODE_ALLOWED_OPERATIONS.get(request.mode, frozenset())
        disallowed_ops = []
        for op in request.operations:
            if op.operation_type not in allowed_set:
                disallowed_ops.append(f"{op.operation_id}: {op.operation_type.value}")
        if disallowed_ops:
            checks.append(SafetyCheckResult(check_name="mode_operation_mismatch", passed=False, severity="high", message=f"模式 {request.mode.value} 不允许以下操作: {', '.join(disallowed_ops)}", detail=f"当前模式仅允许: {sorted(o.value for o in allowed_set)}"))
            blocked.append(f"模式不匹配: {len(disallowed_ops)} 个操作被拒绝")
        for op in request.operations:
            result = self.validate_operation(op, cfg)
            checks.append(SafetyCheckResult(check_name=f"op:{op.operation_id[:8]}", passed=result.passed, severity=result.severity, message=result.message, detail=result.detail))
        all_passed = all(c.passed for c in checks)
        if not all_passed:
            failed_ck = [c for c in checks if not c.passed]
            warnings.append(f"{len(failed_ck)}/{len(checks)} 项检查未通过")
        return SafetyGateResult(passed=all_passed, checks=checks, blocked_reasons=blocked, warnings=warnings)
    def validate_read_only(self, request: BridgeRequest) -> SafetyGateResult:
        checks: list[SafetyCheckResult] = []
        blocked: list[str] = []
        readonly_ops = frozenset({BridgeOperationType.READ_ENTITY, BridgeOperationType.READ_DOCUMENT, BridgeOperationType.QUERY_STATUS, BridgeOperationType.LIST_DOCUMENTS})
        for op in request.operations:
            if op.operation_type not in readonly_ops:
                checks.append(SafetyCheckResult(check_name=f"readonly_violation:{op.operation_id[:8]}", passed=False, severity="high", message=f"操作 {op.operation_type.value} 不是只读操作", detail="只读校验要求所有操作均为 READ_ENTITY/READ_DOCUMENT/QUERY_STATUS/LIST_DOCUMENTS"))
                blocked.append(f"非只读操作: {op.operation_id}")
            else:
                checks.append(SafetyCheckResult(check_name=f"readonly_ok:{op.operation_id[:8]}", passed=True, severity="low", message="只读操作通过", detail=""))
        all_passed = all(c.passed for c in checks)
        return SafetyGateResult(passed=all_passed, checks=checks, blocked_reasons=blocked, warnings=[])
_default_gate = SafetyGate()
def validate_operation(operation: BridgeOperation) -> SafetyCheckResult:
    return _default_gate.validate_operation(operation)
def validate_request(request: BridgeRequest) -> SafetyGateResult:
    return _default_gate.validate_request(request)
def validate_read_only(request: BridgeRequest) -> SafetyGateResult:
    return _default_gate.validate_read_only(request)
__all__ = ["SafetyConfig", "SafetyGate", "get_safety_config", "enable_real_execution", "disable_real_execution", "validate_operation", "validate_request", "validate_read_only"]
