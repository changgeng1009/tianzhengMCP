"""MCP 安全门控 — Phase M3-prep。

所有 MCP 工具默认返回安全字段，禁止真实执行。
d1_allowed、production_d1_allowed、source_modification_allowed 永为 false。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp.safety.mcp_errors import (
    MCPBlockedError,
    MCPErrorCode,
    scan_for_forbidden_flags,
)


# ════════════════════════════════════════════════════════════════
# 默认安全字段 (所有 MCP tool 必须返回)
# ════════════════════════════════════════════════════════════════

DEFAULT_SAFETY_FLAGS: dict[str, bool] = {
    "autocad_connected": False,
    "dwg_opened": False,
    "source_dwg_opened": False,
    "sendcommand_used": False,
    "tianzheng_command_executed": False,
    "source_write_attempted": False,
    "save_called_on_source": False,
    "saveas_called": False,
    "copyobjects_called": False,
    "http_bridge_called": False,
    "d1_allowed": False,
    "production_d1_allowed": False,
    "production_d1_executed": False,
    "source_modification_allowed": False,
    "real_execution_allowed": False,
}


@dataclass
class MCPToolResponse:
    """MCP 工具统一响应格式。"""
    success: bool = True
    tool_name: str = ""
    error_code: str | None = None
    error_message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    safety_flags: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_SAFETY_FLAGS))
    warnings: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "data": dict(self.data),
            "safety_flags": dict(self.safety_flags),
            "warnings": list(self.warnings),
            "blocking_issues": list(self.blocking_issues),
        }


class MCPGate:
    """MCP 安全门控 — Phase M3-prep 专用。

    所有 MCP 工具在接收请求后、执行业务逻辑前，必须先通过此门控。
    """

    @staticmethod
    def check_forbidden_input(payload: dict[str, Any]) -> None:
        """检查 payload 中是否包含禁止字段。"""
        violations = scan_for_forbidden_flags(payload)
        if violations:
            flags_str = ", ".join(violations)
            raise MCPBlockedError(
                MCPErrorCode.MCP_UNSAFE_FLAG_DETECTED,
                detail=f"检测到禁止标志: {flags_str}",
            )

    @staticmethod
    def build_response(
        tool_name: str,
        data: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        blocking_issues: list[str] | None = None,
    ) -> MCPToolResponse:
        """构建标准 MCP 响应（全部安全字段为 false）。"""
        return MCPToolResponse(
            success=True,
            tool_name=tool_name,
            data=data or {},
            warnings=warnings or [],
            blocking_issues=blocking_issues or [],
        )

    @staticmethod
    def build_error_response(
        tool_name: str,
        error_code: MCPErrorCode,
        error_detail: str = "",
    ) -> MCPToolResponse:
        """构建标准 MCP 错误响应。"""
        from mcp.safety.mcp_errors import ERROR_MESSAGES
        msg = ERROR_MESSAGES.get(error_code, str(error_code))
        if error_detail:
            msg = f"{msg} 详情: {error_detail}"
        return MCPToolResponse(
            success=False,
            tool_name=tool_name,
            error_code=error_code.value,
            error_message=msg,
            blocking_issues=[msg],
        )

    @staticmethod
    def get_safety_status() -> dict[str, bool]:
        """获取当前安全门状态（全部 false）。"""
        return dict(DEFAULT_SAFETY_FLAGS)


def ensure_safety_flags(result: dict[str, Any]) -> dict[str, Any]:
    """确保结果中包含完整的默认安全字段。"""
    if "safety_flags" not in result:
        result["safety_flags"] = dict(DEFAULT_SAFETY_FLAGS)
    else:
        for key, default_value in DEFAULT_SAFETY_FLAGS.items():
            result["safety_flags"].setdefault(key, default_value)
    return result
