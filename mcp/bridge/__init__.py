"""天正给排水 MCP Bridge 模块
分层 bridge 架构：
  Layer 1 — Mock Bridge: 纯模拟，不连接 AutoCAD
  Layer 2 — Dry-Run Bridge: 输出预期命令但不执行
  Layer 3 — Real Bridge: 真实执行（默认禁用，需 SafetyGate 放行）
  Safety Gate: 跨所有层的安全校验
使用方式：
  from mcp.bridge import BridgeFactory
  bridge = BridgeFactory.create(BridgeMode.MOCK)
  response = bridge.execute(request)
"""
from __future__ import annotations
import logging
from typing import Any
from mcp.bridge.schemas import (
    BridgeMode,
    BridgeOperation,
    BridgeOperationType,
    BridgeEntityType,
    BridgeRiskLevel,
    BridgeRequest,
    BridgeResponse,
    BridgeStatusResponse,
    BridgeStats,
    OperationResult,
    SafetyCheckResult,
    SafetyGateResult,
    BRIDGE_ENDPOINTS,
)
from mcp.bridge.mock_bridge import MockBridge, get_mock_bridge
from mcp.bridge.dry_run_bridge import (
    DryRunBridge,
    DryRunTrace,
    get_dry_run_bridge,
    generate_dry_run_report,
)
from mcp.bridge.real_bridge import (
    RealBridgeInterface,
    RealBridgeStub,
    RealExecutionConfig,
    get_real_bridge,
)
from mcp.bridge.safety_gate import (
    SafetyGate,
    SafetyConfig,
    get_safety_config,
    enable_real_execution,
    disable_real_execution,
    validate_operation,
    validate_request,
    validate_read_only,
)
logger = logging.getLogger(__name__)
class BridgeFactory:
    """Bridge 工厂 — 根据模式创建对应的 Bridge 实例。"""
    _instances: dict[BridgeMode, Any] = {}
    @classmethod
    def create(cls, mode: BridgeMode = BridgeMode.MOCK):
        """创建或获取对应模式的 Bridge 实例。"""
        if mode in cls._instances:
            return cls._instances[mode]
        if mode == BridgeMode.MOCK:
            instance = MockBridge()
        elif mode == BridgeMode.DRY_RUN:
            instance = DryRunBridge()
        elif mode == BridgeMode.REAL:
            cfg = get_safety_config()
            if not cfg.real_execution_enabled:
                logger.warning("Real execution 未启用，返回 RealBridgeStub")
            instance = get_real_bridge()
        else:
            raise ValueError(f"未知的 Bridge 模式: {mode}")
        cls._instances[mode] = instance
        return instance
    @classmethod
    def get_default(cls):
        """获取默认的 Bridge 实例（Mock 模式）。"""
        return cls.create(BridgeMode.MOCK)
    @classmethod
    def reset(cls) -> None:
        """重置所有已缓存的实例。"""
        cls._instances.clear()
class BridgeDispatcher:
    """统一请求分发器 — 承担 HTTP endpoint 的本地实现。
    模拟 HTTP Bridge 的行为：接收 BridgeRequest，返回 BridgeResponse。"""
    def __init__(self, mode: BridgeMode = BridgeMode.MOCK) -> None:
        self._bridge = BridgeFactory.create(mode)
        self._mode = mode
    def execute(self, request: BridgeRequest) -> BridgeResponse:
        """分发执行请求。"""
        try:
            return self._bridge.execute(request)
        except Exception as e:
            logger.exception("Bridge execute failed")
            return BridgeResponse(
                request_id=getattr(request, 'request_id', ''),
                mode=self._mode.value,
                success=False,
                executed=False,
                errors=[str(e)],
                safety_passed=False,
            )
    def status(self) -> BridgeStatusResponse:
        """获取 bridge 状态。"""
        try:
            return self._bridge.status()
        except Exception as e:
            return BridgeStatusResponse(
                mode=self._mode.value,
                warnings=[str(e)],
            )
    def preview(self, request: BridgeRequest):
        """预览操作（仅 dry-run 模式支持）。"""
        if hasattr(self._bridge, 'preview'):
            return self._bridge.preview(request)
        return []
    def get_mode(self) -> BridgeMode:
        return self._mode
    def get_stats(self) -> BridgeStats:
        try:
            return self._bridge.get_stats()
        except Exception:
            return BridgeStats()
_default_dispatcher: BridgeDispatcher | None = None
def get_dispatcher(mode: BridgeMode = BridgeMode.MOCK) -> BridgeDispatcher:
    global _default_dispatcher
    if _default_dispatcher is None or _default_dispatcher.get_mode() != mode:
        _default_dispatcher = BridgeDispatcher(mode)
    return _default_dispatcher
__all__ = [
    "BridgeMode",
    "BridgeOperation",
    "BridgeOperationType",
    "BridgeEntityType",
    "BridgeRiskLevel",
    "BridgeRequest",
    "BridgeResponse",
    "BridgeStatusResponse",
    "BridgeStats",
    "OperationResult",
    "SafetyCheckResult",
    "SafetyGateResult",
    "BRIDGE_ENDPOINTS",
    "MockBridge",
    "DryRunBridge",
    "DryRunTrace",
    "RealBridgeInterface",
    "RealBridgeStub",
    "RealExecutionConfig",
    "SafetyGate",
    "SafetyConfig",
    "BridgeFactory",
    "BridgeDispatcher",
    "get_mock_bridge",
    "get_dry_run_bridge",
    "get_real_bridge",
    "get_safety_config",
    "get_dispatcher",
    "enable_real_execution",
    "disable_real_execution",
    "validate_operation",
    "validate_request",
    "validate_read_only",
    "generate_dry_run_report",
]
