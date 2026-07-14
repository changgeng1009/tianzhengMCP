"""
MCP Bridge — 请求/响应 schema 定义

定义 Python MCP wrapper → Local HTTP Bridge → AutoCAD/天正 接口间
所有通信协议的请求体、响应体、操作类型和运行模式。

注意：所有 schema 纯数据，不依赖 AutoCAD COM、不导入 win32com。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Literal


# ═══════════════════════════════════════════════════════════════
# 运行模式
# ═══════════════════════════════════════════════════════════════

class BridgeMode(str, Enum):
    """Bridge 运行模式。

    - MOCK: 完全模拟，不连接 AutoCAD
    - DRY_RUN: 输出预期命令但不执行
    - REAL: 真实执行（默认禁用）
    """
    MOCK = "mock"
    DRY_RUN = "dry_run"
    REAL = "real"


# ═══════════════════════════════════════════════════════════════
# 操作类型
# ═══════════════════════════════════════════════════════════════

class BridgeOperationType(str, Enum):
    """Bridge 操作类型 — 映射到 AutoCAD/天正 操作。"""
    # 实体操作
    CREATE_ENTITY = "create_entity"
    MODIFY_ENTITY = "modify_entity"
    DELETE_ENTITY = "delete_entity"

    # CAD 基础
    SET_LAYER = "set_layer"
    SET_PROPERTY = "set_property"
    SEND_COMMAND = "send_command"

    # 天正给排水
    TIANZHENG_ADD_PIPE = "tianzheng_add_pipe"
    TIANZHENG_ADD_VALVE = "tianzheng_add_valve"
    TIANZHENG_ADD_FITTING = "tianzheng_add_fitting"
    TIANZHENG_MODIFY_DIAMETER = "tianzheng_modify_diameter"
    TIANZHENG_MODIFY_ELEVATION = "tianzheng_modify_elevation"
    TIANZHENG_MODIFY_SYSTEM = "tianzheng_modify_system"
    TIANZHENG_CONNECT_PIPE = "tianzheng_connect_pipe"
    TIANZHENG_DELETE_OBJECT = "tianzheng_delete_object"

    # 查询操作（只读）
    READ_ENTITY = "read_entity"
    READ_DOCUMENT = "read_document"
    QUERY_STATUS = "query_status"
    LIST_DOCUMENTS = "list_documents"

    # 管理操作
    CONNECT = "connect"
    DISCONNECT = "disconnect"


# ═══════════════════════════════════════════════════════════════
# 实体类型
# ═══════════════════════════════════════════════════════════════

class BridgeEntityType(str, Enum):
    """Bridge 实体类型 — 通用 AutoCAD + 天正专用分类。"""
    # AutoCAD 基础
    LINE = "line"
    POLYLINE = "polyline"
    CIRCLE = "circle"
    ARC = "arc"
    TEXT = "text"
    MTEXT = "mtext"
    BLOCK_REF = "block_reference"
    DIMENSION = "dimension"

    # 天正给排水
    PIPE = "pipe"
    VALVE = "valve"
    FITTING = "fitting"
    LABEL = "label"
    DIMENSION_TZ = "tianzheng_dimension"

    # 通用未知
    UNKNOWN = "unknown"


# ═══════════════════════════════════════════════════════════════
# 风险等级
# ═══════════════════════════════════════════════════════════════

class BridgeRiskLevel(str, Enum):
    """操作风险等级。"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ═══════════════════════════════════════════════════════════════
# Bridge 请求体
# ═══════════════════════════════════════════════════════════════

@dataclass
class BridgeOperation:
    """单个 Bridge 操作。

    封装一次 AutoCAD/天正 操作的完整描述。
    """
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operation_type: BridgeOperationType = BridgeOperationType.READ_ENTITY
    entity_type: BridgeEntityType = BridgeEntityType.UNKNOWN

    # 目标定位
    handle: str | None = None                # AutoCAD handle（修改/删除时）
    layer: str = "0"

    # 几何数据
    geometry: dict[str, Any] = field(default_factory=dict)

    # 属性数据
    properties: dict[str, Any] = field(default_factory=dict)

    # 天正专用
    tianzheng_object_name: str | None = None  # 如 TDbPipe
    tianzheng_system: str | None = None       # 给水/排水/消防...
    tianzheng_dn: str | None = None           # 管径

    # 安全标记
    risk_level: BridgeRiskLevel = BridgeRiskLevel.LOW
    requires_confirmation: bool = True

    # 溯源
    reason: str = ""
    source_diff_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type.value,
            "entity_type": self.entity_type.value,
            "handle": self.handle,
            "layer": self.layer,
            "geometry": dict(self.geometry),
            "properties": dict(self.properties),
            "tianzheng_object_name": self.tianzheng_object_name,
            "tianzheng_system": self.tianzheng_system,
            "tianzheng_dn": self.tianzheng_dn,
            "risk_level": self.risk_level.value,
            "requires_confirmation": self.requires_confirmation,
            "reason": self.reason,
            "source_diff_id": self.source_diff_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BridgeOperation:
        return cls(
            operation_id=data.get("operation_id", str(uuid.uuid4())),
            operation_type=BridgeOperationType(data.get("operation_type", "read_entity")),
            entity_type=BridgeEntityType(data.get("entity_type", "unknown")),
            handle=data.get("handle"),
            layer=data.get("layer", "0"),
            geometry=data.get("geometry", {}),
            properties=data.get("properties", {}),
            tianzheng_object_name=data.get("tianzheng_object_name"),
            tianzheng_system=data.get("tianzheng_system"),
            tianzheng_dn=data.get("tianzheng_dn"),
            risk_level=BridgeRiskLevel(data.get("risk_level", "low")),
            requires_confirmation=bool(data.get("requires_confirmation", True)),
            reason=data.get("reason", ""),
            source_diff_id=data.get("source_diff_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class BridgeRequest:
    """HTTP Bridge 请求体。

    POST /bridge/v1/execute 的 JSON body。
    可以包含批量操作。
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mode: BridgeMode = BridgeMode.DRY_RUN

    # 批量操作
    operations: list[BridgeOperation] = field(default_factory=list)

    # 上下文信息
    session_id: str | None = None
    document_path: str | None = None

    # 安全选项
    allow_high_risk: bool = False
    skip_confirmation: bool = False

    # 超时
    timeout_ms: int = 30000

    # 额外元数据
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "mode": self.mode.value,
            "operations": [op.to_dict() for op in self.operations],
            "session_id": self.session_id,
            "document_path": self.document_path,
            "allow_high_risk": self.allow_high_risk,
            "skip_confirmation": self.skip_confirmation,
            "timeout_ms": self.timeout_ms,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BridgeRequest:
        return cls(
            request_id=data.get("request_id", str(uuid.uuid4())),
            mode=BridgeMode(data.get("mode", "dry_run")),
            operations=[BridgeOperation.from_dict(op) for op in data.get("operations", [])],
            session_id=data.get("session_id"),
            document_path=data.get("document_path"),
            allow_high_risk=bool(data.get("allow_high_risk", False)),
            skip_confirmation=bool(data.get("skip_confirmation", False)),
            timeout_ms=int(data.get("timeout_ms", 30000)),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


# ═══════════════════════════════════════════════════════════════
# Bridge 响应体
# ═══════════════════════════════════════════════════════════════

@dataclass
class OperationResult:
    """单个操作的执行结果。"""
    operation_id: str = ""
    operation_type: str = ""

    # 执行结果
    success: bool = False
    executed: bool = False
    status: str = "pending"  # pending, executing, executed, failed, skipped, blocked
    message: str = ""

    # 操作详情
    entity_handle: str | None = None       # 创建/修改后的 handle
    simulated_geometry: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # 耗时
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "success": self.success,
            "executed": self.executed,
            "status": self.status,
            "message": self.message,
            "entity_handle": self.entity_handle,
            "simulated_geometry": dict(self.simulated_geometry),
            "warnings": list(self.warnings),
            "duration_ms": self.duration_ms,
        }


@dataclass
class BridgeResponse:
    """HTTP Bridge 响应体。

    POST /bridge/v1/execute 的 JSON response。
    """
    request_id: str = ""
    mode: str = BridgeMode.DRY_RUN.value

    # 响应状态
    success: bool = False
    executed: bool = False
    total_operations: int = 0
    succeeded_operations: int = 0
    failed_operations: int = 0
    skipped_operations: int = 0
    blocked_operations: int = 0

    # 每个操作的结果
    results: list[OperationResult] = field(default_factory=list)

    # 安全门结果
    safety_passed: bool = False
    safety_checks: list[dict[str, Any]] = field(default_factory=list)
    safety_blocked_reasons: list[str] = field(default_factory=list)

    # 全局警告和错误
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # 元数据和耗时
    metadata: dict[str, Any] = field(default_factory=dict)
    total_duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "mode": self.mode,
            "success": self.success,
            "executed": self.executed,
            "total_operations": self.total_operations,
            "succeeded_operations": self.succeeded_operations,
            "failed_operations": self.failed_operations,
            "skipped_operations": self.skipped_operations,
            "blocked_operations": self.blocked_operations,
            "results": [r.to_dict() for r in self.results],
            "safety_passed": self.safety_passed,
            "safety_checks": list(self.safety_checks),
            "safety_blocked_reasons": list(self.safety_blocked_reasons),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
            "total_duration_ms": self.total_duration_ms,
            "timestamp": self.timestamp,
        }

    @classmethod
    def empty(cls, request_id: str = "", mode: str = BridgeMode.MOCK.value) -> BridgeResponse:
        """返回一个空的成功响应。"""
        return cls(
            request_id=request_id,
            mode=mode,
            success=True,
            executed=False,
        )


# ═══════════════════════════════════════════════════════════════
# 安全门 schema
# ═══════════════════════════════════════════════════════════════

@dataclass
class SafetyCheckResult:
    """单条安全校验结果。"""
    check_name: str = ""
    passed: bool = False
    severity: str = "low"  # low, medium, high, critical
    message: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass
class SafetyGateResult:
    """安全门整体结果。"""
    passed: bool = False
    checks: list[SafetyCheckResult] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "blocked_reasons": list(self.blocked_reasons),
            "warnings": list(self.warnings),
        }


# ═══════════════════════════════════════════════════════════════
# HTTP endpoint 定义
# ═══════════════════════════════════════════════════════════════

@dataclass
class BridgeEndpoint:
    """HTTP endpoint 规范定义。"""
    path: str
    method: str
    description: str
    request_schema: str
    response_schema: str


BRIDGE_ENDPOINTS: list[BridgeEndpoint] = [
    BridgeEndpoint(
        path="/bridge/v1/execute",
        method="POST",
        description="执行一批 Bridge 操作（支持 mock/dry-run/real 模式）",
        request_schema="BridgeRequest",
        response_schema="BridgeResponse",
    ),
    BridgeEndpoint(
        path="/bridge/v1/status",
        method="GET",
        description="获取当前 bridge 连接状态",
        request_schema="— (无请求体)",
        response_schema="BridgeStatusResponse",
    ),
    BridgeEndpoint(
        path="/bridge/v1/preview",
        method="POST",
        description="预览一批操作（等同 dry-run），不执行任何 CAD 操作",
        request_schema="BridgeRequest (mode 自动设为 dry_run)",
        response_schema="BridgeResponse",
    ),
    BridgeEndpoint(
        path="/bridge/v1/validate",
        method="POST",
        description="校验一批操作的 schema 有效性，不执行",
        request_schema="BridgeRequest (mode 自动设为 dry_run)",
        response_schema="BridgeResponse",
    ),
]


# ═══════════════════════════════════════════════════════════════
# HTTP 状态查询
# ═══════════════════════════════════════════════════════════════

@dataclass
class BridgeStatusResponse:
    """GET /bridge/v1/status 响应体。"""
    connected: bool = False
    mode: str = BridgeMode.MOCK.value
    active_document: str | None = None
    document_count: int = 0
    real_execution_enabled: bool = False
    session_id: str | None = None
    uptime_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "mode": self.mode,
            "active_document": self.active_document,
            "document_count": self.document_count,
            "real_execution_enabled": self.real_execution_enabled,
            "session_id": self.session_id,
            "uptime_seconds": self.uptime_seconds,
            "warnings": list(self.warnings),
        }


# ═══════════════════════════════════════════════════════════════
# 统计信息
# ═══════════════════════════════════════════════════════════════

@dataclass
class BridgeStats:
    """Bridge 运行时统计。"""
    total_requests: int = 0
    total_operations: int = 0
    executed_operations: int = 0
    mock_requests: int = 0
    dry_run_requests: int = 0
    real_requests: int = 0
    blocked_by_safety: int = 0
    failed_requests: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_operations": self.total_operations,
            "executed_operations": self.executed_operations,
            "mock_requests": self.mock_requests,
            "dry_run_requests": self.dry_run_requests,
            "real_requests": self.real_requests,
            "blocked_by_safety": self.blocked_by_safety,
            "failed_requests": self.failed_requests,
        }


__all__ = [
    "BridgeMode",
    "BridgeOperationType",
    "BridgeEntityType",
    "BridgeRiskLevel",
    "BridgeOperation",
    "BridgeRequest",
    "OperationResult",
    "BridgeResponse",
    "SafetyCheckResult",
    "SafetyGateResult",
    "BridgeEndpoint",
    "BRIDGE_ENDPOINTS",
    "BridgeStatusResponse",
    "BridgeStats",
]
