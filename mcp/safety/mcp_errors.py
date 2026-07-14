"""MCP 错误码定义 — Phase M3-prep。

所有 MCP 工具在遇到不安全操作时返回 blocking error。
禁止进入 Production D1、禁止连接 AutoCAD、禁止真实执行。
"""

from enum import Enum


class MCPErrorCode(str, Enum):
    """MCP 标准化错误码。"""
    MCP_BLOCKED_REAL_EXECUTION = "MCP_BLOCKED_REAL_EXECUTION"
    MCP_BLOCKED_AUTOCAD_CONNECT = "MCP_BLOCKED_AUTOCAD_CONNECT"
    MCP_BLOCKED_DWG_OPEN = "MCP_BLOCKED_DWG_OPEN"
    MCP_BLOCKED_SOURCE_WRITE = "MCP_BLOCKED_SOURCE_WRITE"
    MCP_BLOCKED_PRODUCTION_D1 = "MCP_BLOCKED_PRODUCTION_D1"
    MCP_INVALID_ACTION_TYPE = "MCP_INVALID_ACTION_TYPE"
    MCP_INVALID_ACTION_PAYLOAD = "MCP_INVALID_ACTION_PAYLOAD"
    MCP_ACTION_CONFLICT = "MCP_ACTION_CONFLICT"
    MCP_MANUAL_REVIEW_REQUIRED = "MCP_MANUAL_REVIEW_REQUIRED"
    MCP_SCANNER_DIAGNOSIS_REQUIRED = "MCP_SCANNER_DIAGNOSIS_REQUIRED"
    MCP_BASELINE_TEST_FAILURE_EXISTS = "MCP_BASELINE_TEST_FAILURE_EXISTS"
    MCP_UNSAFE_FLAG_DETECTED = "MCP_UNSAFE_FLAG_DETECTED"
    MCP_HTTP_BRIDGE_BLOCKED = "MCP_HTTP_BRIDGE_BLOCKED"
    MCP_SENDCOMMAND_BLOCKED = "MCP_SENDCOMMAND_BLOCKED"
    MCP_SOURCE_DWG_PROTECTED = "MCP_SOURCE_DWG_PROTECTED"


ERROR_MESSAGES: dict[MCPErrorCode, str] = {
    MCPErrorCode.MCP_BLOCKED_REAL_EXECUTION:
        "真实执行被阻止: 当前处于 Phase M3-prep，禁止连接 AutoCAD 或执行 CAD 操作。",
    MCPErrorCode.MCP_BLOCKED_AUTOCAD_CONNECT:
        "AutoCAD 连接被阻止: 当前阶段不允许连接 AutoCAD COM 接口。",
    MCPErrorCode.MCP_BLOCKED_DWG_OPEN:
        "DWG 打开被阻止: 当前阶段不允许打开任何 DWG 文件。",
    MCPErrorCode.MCP_BLOCKED_SOURCE_WRITE:
        "源 DWG 写入被阻止: 禁止修改源 DWG 文件。",
    MCPErrorCode.MCP_BLOCKED_PRODUCTION_D1:
        "Production D1 被阻止: d1_allowed=false，当前不可进入生产阶段。",
    MCPErrorCode.MCP_INVALID_ACTION_TYPE:
        "无效的 action_type: 请检查 action_type 是否在 VALID_ACTION_TYPES 中。",
    MCPErrorCode.MCP_INVALID_ACTION_PAYLOAD:
        "无效的 action payload: 缺少必要参数或参数格式错误。",
    MCPErrorCode.MCP_ACTION_CONFLICT:
        "Action 冲突检测: 存在空间/管径/系统/标高冲突。",
    MCPErrorCode.MCP_MANUAL_REVIEW_REQUIRED:
        "需要人工审核: 当前操作必须经过人工视觉验证后才能继续。",
    MCPErrorCode.MCP_SCANNER_DIAGNOSIS_REQUIRED:
        "需要扫描器诊断: 请先运行 tianzheng_interface.scanner 获取完整扫描结果。",
    MCPErrorCode.MCP_BASELINE_TEST_FAILURE_EXISTS:
        "基線测试失败: 存在未通过的测试，请先修复后再继续。",
    MCPErrorCode.MCP_UNSAFE_FLAG_DETECTED:
        "检测到不安全标志: 输入中含有 execute/real/production 等禁止字段。",
    MCPErrorCode.MCP_HTTP_BRIDGE_BLOCKED:
        "HTTP Bridge 调用被阻止: 当前阶段不允许调用本地 HTTP Bridge 或 localhost。",
    MCPErrorCode.MCP_SENDCOMMAND_BLOCKED:
        "SendCommand 被阻止: 禁止通过 SendCommand 执行 AutoCAD 命令。",
    MCPErrorCode.MCP_SOURCE_DWG_PROTECTED:
        "源 DWG 受保护: source DWG 为只读基准，不可修改。",
}


class MCPBlockedError(Exception):
    """MCP 阻塞错误 — 当检测到不安全操作时抛出。"""
    def __init__(self, code: MCPErrorCode, detail: str = ""):
        self.code = code
        self.detail = detail
        msg = ERROR_MESSAGES.get(code, str(code))
        if detail:
            msg = f"{msg} 详情: {detail}"
        super().__init__(msg)


FORBIDDEN_FLAGS = frozenset({
    "execute", "real", "production", "d1_allowed",
    "production_d1_allowed", "source_write_allowed",
    "source_modification_allowed", "open_dwg", "connect_autocad",
    "sendcommand", "save_dwg", "http_bridge_called",
})

FORBIDDEN_TRUE_VALUES = frozenset({True, "true", "True", "1", 1, "yes", "YES"})


def is_forbidden_flag(key: str, value: object) -> bool:
    """检查是否为被禁止的安全标志。"""
    key_lower = str(key).lower().strip()
    return key_lower in FORBIDDEN_FLAGS and value in FORBIDDEN_TRUE_VALUES


def scan_for_forbidden_flags(payload: dict) -> list[str]:
    """扫描 payload 中是否存在禁止的安全标志。"""
    violations: list[str] = []
    for key, value in payload.items():
        if is_forbidden_flag(key, value):
            violations.append(f"{key}={value}")
    return violations
