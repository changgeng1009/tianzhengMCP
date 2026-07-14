"""天正给排水 MCP Bridge — Real Bridge 接口定义
Real Bridge 负责真实的 AutoCAD/天正 COM 操作。
默认禁用 — 需要通过 enable_real_execution() 显式启用。
安全约束：
  - 禁止在未经 SafetyGate 校验的情况下执行任何操作
  - 禁止跳过预览/确认步骤
  - 禁止执行被永久阻止的 DELETE 操作
  - 所有写操作必须记录审计日志
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol
from mcp.bridge.schemas import (
    BridgeMode,
    BridgeOperation,
    BridgeRequest,
    BridgeResponse,
    BridgeStatusResponse,
    BridgeStats,
    OperationResult,
)
from mcp.bridge.safety_gate import SafetyGate, SafetyConfig, get_safety_config
@dataclass
class RealExecutionConfig:
    """真实执行配置。严格控制各项权限。"""
    enabled: bool = False
    allow_send_command: bool = False
    allow_write_operations: bool = False
    allow_tianzheng_commands: bool = False
    require_preview: bool = True
    require_confirmation: bool = True
    max_operations_per_session: int = 50
    audit_log_enabled: bool = True
    dwg_backup_enabled: bool = True
    warnings: list = field(default_factory=list)
    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "allow_send_command": self.allow_send_command,
            "allow_write_operations": self.allow_write_operations,
            "allow_tianzheng_commands": self.allow_tianzheng_commands,
            "require_preview": self.require_preview,
            "require_confirmation": self.require_confirmation,
            "max_operations_per_session": self.max_operations_per_session,
            "audit_log_enabled": self.audit_log_enabled,
            "dwg_backup_enabled": self.dwg_backup_enabled,
            "warnings": list(self.warnings),
        }
class RealBridgeInterface(ABC):
    """真实执行路径抽象接口。
    当前阶段不实现具体逻辑，仅定义接口签名。
    当 enable_real_execution() 被调用且 SafetyGate 通过后，真实实现将被注入。"""
    @abstractmethod
    def execute(self, request: BridgeRequest) -> BridgeResponse:
        """执行真实 CAD 操作。"""
        ...
    @abstractmethod
    def connect(self) -> BridgeStatusResponse:
        """建立 AutoCAD COM 连接。"""
        ...
    @abstractmethod
    def disconnect(self) -> BridgeStatusResponse:
        """断开 AutoCAD COM 连接。"""
        ...
    @abstractmethod
    def status(self) -> BridgeStatusResponse:
        """获取 AutoCAD 连接状态。"""
        ...
    @abstractmethod
    def get_stats(self) -> BridgeStats:
        """获取运行时统计。"""
        ...
class RealBridgeStub(RealBridgeInterface):
    """Real Bridge 桩实现 — 默认禁用状态。
    所有调用均返回 blocked 状态，直到显式启用。"""
    def __init__(self) -> None:
        self._safety_gate = SafetyGate()
        self._config = RealExecutionConfig()
        self._stats = BridgeStats()
    def execute(self, request: BridgeRequest) -> BridgeResponse:
        cfg = get_safety_config()
        if not cfg.real_execution_enabled:
            return BridgeResponse(
                request_id=request.request_id,
                mode=BridgeMode.REAL.value,
                success=False,
                executed=False,
                total_operations=len(request.operations),
                blocked_operations=len(request.operations),
                errors=["Real execution 未启用。请调用 enable_real_execution() 并重启 bridge。"],
                warnings=["当前为 RealBridgeStub，所有操作被阻止"],
                safety_passed=False,
            )
        return BridgeResponse(
            request_id=request.request_id,
            mode=BridgeMode.REAL.value,
            success=False,
            executed=False,
            total_operations=len(request.operations),
            errors=["Real bridge 的具体实现尚未完成，当前不可用。"],
            warnings=["Real execution 已启用但后端实现缺失。"],
        )
    def connect(self) -> BridgeStatusResponse:
        return BridgeStatusResponse(
            connected=False,
            mode=BridgeMode.REAL.value,
            real_execution_enabled=get_safety_config().real_execution_enabled,
            warnings=["RealBridgeStub: 连接功能未实现"],
        )
    def disconnect(self) -> BridgeStatusResponse:
        return BridgeStatusResponse(
            connected=False,
            mode=BridgeMode.REAL.value,
            real_execution_enabled=get_safety_config().real_execution_enabled,
        )
    def status(self) -> BridgeStatusResponse:
        return BridgeStatusResponse(
            connected=False,
            mode=BridgeMode.REAL.value,
            real_execution_enabled=get_safety_config().real_execution_enabled,
            warnings=["RealBridgeStub: 未连接到 AutoCAD"],
        )
    def get_stats(self) -> BridgeStats:
        return self._stats
_default_real_bridge: RealBridgeStub | None = None
def get_real_bridge() -> RealBridgeStub:
    global _default_real_bridge
    if _default_real_bridge is None:
        _default_real_bridge = RealBridgeStub()
    return _default_real_bridge
__all__ = [
    "RealExecutionConfig",
    "RealBridgeInterface",
    "RealBridgeStub",
    "get_real_bridge",
]
