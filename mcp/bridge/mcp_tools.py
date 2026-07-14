"""MCP Tools — Phase M3-prep 干运行工具实现。

7 个 MCP 工具:
1. tianzheng_validate_action
2. tianzheng_validate_action_batch
3. tianzheng_dry_run_action_batch
4. tianzheng_build_scan_report
5. tianzheng_manual_review_intake
6. tianzheng_safety_gate_status
7. tianzheng_explain_blockers

所有工具: dry-run only | 禁止 AutoCAD | 禁止 DWG | 禁止 HTTP Bridge
"""

from __future__ import annotations

import json
from typing import Any

from tianzheng_interface.action_schema import (
    ActionDefinition,
    ActionBatch,
    VALID_ACTION_TYPES,
    ConflictType,
)
from tianzheng_interface.dry_run_engine import (
    DryRunEngine,
    EnhancedDryRunEngine,
    ConflictDetector,
)
from tianzheng_interface.scanner import DWGScanner, scan_empty
from tianzheng_interface.report_builder import build_markdown_report, build_json_report
from tianzheng_interface.model import DWGScanResult

from mcp.safety.mcp_errors import MCPErrorCode, MCPBlockedError
from mcp.safety.mcp_safety import (
    DEFAULT_SAFETY_FLAGS,
    MCPGate,
    MCPToolResponse,
    ensure_safety_flags,
)


# 单例引擎
_dry_run_engine = DryRunEngine()
_enhanced_engine = EnhancedDryRunEngine()
_detector = ConflictDetector()

# 有效手动审核决策
VALID_REVIEW_DECISIONS = frozenset({"PASS_VISUAL_ONLY", "FAIL_VISUAL", "INCONCLUSIVE"})


# ════════════════════════════════════════════════════════════════
# Tool 1: tianzheng_validate_action
# ════════════════════════════════════════════════════════════════

def tianzheng_validate_action(action_payload: dict[str, Any]) -> dict[str, Any]:
    """验证单个 action。

    输入: action payload dict
    输出: validation result + safety flags
    限制: 不得真实执行
    """
    gate = MCPGate()
    try:
        gate.check_forbidden_input(action_payload)
    except MCPBlockedError as e:
        return gate.build_error_response(
            "tianzheng_validate_action", e.code, e.detail
        ).to_dict()

    action_type = action_payload.get("action_type", "")

    if not action_type or action_type not in VALID_ACTION_TYPES:
        return gate.build_error_response(
            "tianzheng_validate_action",
            MCPErrorCode.MCP_INVALID_ACTION_TYPE,
            f"未知的 action_type: {action_type!r}",
        ).to_dict()

    try:
        action = ActionDefinition.from_dict(action_payload)
        action.ready_to_execute = False
        action.requires_confirmation = True
        errors = _dry_run_engine.validate_schema(action)
        return gate.build_response(
            "tianzheng_validate_action",
            data={
                "valid": len(errors) == 0,
                "action_id": action.action_id,
                "action_type": action.action_type,
                "risk_level": action.risk_level.value,
                "errors": errors,
                "warnings": action.warnings,
            },
        ).to_dict()
    except Exception as exc:
        return gate.build_error_response(
            "tianzheng_validate_action",
            MCPErrorCode.MCP_INVALID_ACTION_PAYLOAD,
            str(exc),
        ).to_dict()


# ════════════════════════════════════════════════════════════════
# Tool 2: tianzheng_validate_action_batch
# ════════════════════════════════════════════════════════════════

def tianzheng_validate_action_batch(
    batch_payload: dict[str, Any],
) -> dict[str, Any]:
    """验证批量 action 并返回冲突摘要。

    输入: ActionBatch dict
    输出: batch validation + conflict summary + safety flags
    限制: 不得真实执行
    """
    gate = MCPGate()
    try:
        gate.check_forbidden_input(batch_payload)
    except MCPBlockedError as e:
        return gate.build_error_response(
            "tianzheng_validate_action_batch", e.code, e.detail
        ).to_dict()

    raw_actions = batch_payload.get("actions", [])
    if not raw_actions:
        return gate.build_response(
            "tianzheng_validate_action_batch",
            data={"total": 0, "valid": 0, "invalid": 0, "conflicts": []},
        ).to_dict()

    try:
        actions = [ActionDefinition.from_dict(a) for a in raw_actions]
    except Exception as exc:
        return gate.build_error_response(
            "tianzheng_validate_action_batch",
            MCPErrorCode.MCP_INVALID_ACTION_PAYLOAD,
            str(exc),
        ).to_dict()

    valid_count = 0
    invalid_count = 0
    all_errors: dict[str, list[str]] = {}

    for a in actions:
        errors = _dry_run_engine.validate_schema(a)
        if errors:
            invalid_count += 1
            all_errors[a.action_id] = errors
        else:
            valid_count += 1

    conflicts = _detector.detect_all(actions)
    conflict_summaries = [c.to_dict() for c in conflicts]

    return gate.build_response(
        "tianzheng_validate_action_batch",
        data={
            "total": len(actions),
            "valid": valid_count,
            "invalid": invalid_count,
            "conflict_count": len(conflicts),
            "conflicts": conflict_summaries,
            "errors": all_errors,
        },
    ).to_dict()


# ════════════════════════════════════════════════════════════════
# Tool 3: tianzheng_dry_run_action_batch
# ════════════════════════════════════════════════════════════════

def tianzheng_dry_run_action_batch(
    batch_payload: dict[str, Any],
) -> dict[str, Any]:
    """对 ActionBatch 执行 EnhancedDryRunEngine 模拟。

    输入: ActionBatch dict
    输出: EnhancedDryRunEngine result + safety flags
    限制: 不得连接 AutoCAD，不得打开 DWG
    """
    gate = MCPGate()
    try:
        gate.check_forbidden_input(batch_payload)
    except MCPBlockedError as e:
        return gate.build_error_response(
            "tianzheng_dry_run_action_batch", e.code, e.detail
        ).to_dict()

    raw_actions = batch_payload.get("actions", [])
    try:
        actions = [ActionDefinition.from_dict(a) for a in raw_actions]
    except Exception as exc:
        return gate.build_error_response(
            "tianzheng_dry_run_action_batch",
            MCPErrorCode.MCP_INVALID_ACTION_PAYLOAD,
            str(exc),
        ).to_dict()

    result, conflicts = _enhanced_engine.simulate_with_conflicts(actions)
    estimates = _enhanced_engine.estimate_changes(actions)

    return gate.build_response(
        "tianzheng_dry_run_action_batch",
        data={
            "total_actions": result.total_actions,
            "executable_actions": 0,
            "review_required_actions": result.review_required_actions,
            "high_risk_actions": result.high_risk_actions,
            "conflict_count": len(conflicts),
            "conflicts": [c.to_dict() for c in conflicts],
            "change_estimates": estimates,
            "warnings": result.warnings,
        },
    ).to_dict()


# ════════════════════════════════════════════════════════════════
# Tool 4: tianzheng_build_scan_report
# ════════════════════════════════════════════════════════════════

def tianzheng_build_scan_report(
    report_payload: dict[str, Any],
) -> dict[str, Any]:
    """从 scan result JSON 生成 Markdown / JSON 报告。

    输入: scan_result_json + output_format
    输出: report content
    限制: 不得打开 DWG
    """
    gate = MCPGate()
    try:
        gate.check_forbidden_input(report_payload)
    except MCPBlockedError as e:
        return gate.build_error_response(
            "tianzheng_build_scan_report", e.code, e.detail
        ).to_dict()

    scan_json = report_payload.get("scan_result_json", "")
    output_format = report_payload.get("output_format", "markdown")

    try:
        scan_result = DWGScanResult.from_json(scan_json) if scan_json and isinstance(scan_json, str) else scan_empty()
        if scan_json and isinstance(scan_json, str):
            scan_result = DWGScanResult.from_dict(json.loads(scan_json))
        else:
            scan_result = scan_empty()
    except Exception:
        scan_result = scan_empty()

    report_data: dict[str, Any] = {}
    if output_format in ("markdown", "both"):
        report_data["markdown"] = build_markdown_report(scan_result)
    if output_format in ("json", "both"):
        report_data["json"] = build_json_report(scan_result)

    return gate.build_response(
        "tianzheng_build_scan_report",
        data={
            "output_format": output_format,
            "report": report_data,
        },
    ).to_dict()


# ════════════════════════════════════════════════════════════════
# Tool 5: tianzheng_manual_review_intake
# ════════════════════════════════════════════════════════════════

def tianzheng_manual_review_intake(
    review_payload: dict[str, Any],
) -> dict[str, Any]:
    """处理人工审核结果。

    输入: decision (PASS_VISUAL_ONLY / FAIL_VISUAL / INCONCLUSIVE) + reviewer_notes
    输出: manual review result + next phase recommendation
    限制: PASS_VISUAL_ONLY 不得允许 Production D1
    """
    gate = MCPGate()
    try:
        gate.check_forbidden_input(review_payload)
    except MCPBlockedError as e:
        return gate.build_error_response(
            "tianzheng_manual_review_intake", e.code, e.detail
        ).to_dict()

    decision = review_payload.get("decision", "INCONCLUSIVE")
    notes = review_payload.get("reviewer_notes", "")

    if decision not in VALID_REVIEW_DECISIONS:
        return gate.build_error_response(
            "tianzheng_manual_review_intake",
            MCPErrorCode.MCP_INVALID_ACTION_PAYLOAD,
            f"无效的 decision: {decision!r}，只允许 PASS_VISUAL_ONLY / FAIL_VISUAL / INCONCLUSIVE",
        ).to_dict()

    next_phase_recommendation: dict[str, Any] = {
        "decision": decision,
        "d1_allowed": False,
        "production_d1_allowed": False,
        "source_modification_allowed": False,
    }

    blocking_issues: list[str] = []

    if decision == "PASS_VISUAL_ONLY":
        next_phase_recommendation["next_phase"] = "M4 — 文档化与工程基础设施"
        blocking_issues.append(
            "PASS_VISUAL_ONLY 仅表示视觉验证通过，不授权 Production D1。"
        )
    elif decision == "FAIL_VISUAL":
        next_phase_recommendation["next_phase"] = "M3-prep (重新准备)"
        blocking_issues.append(
            "FAIL_VISUAL: 视觉验证未通过，禁止进入后续阶段。"
        )
    else:
        next_phase_recommendation["next_phase"] = "M3-prep (补充验证)"
        blocking_issues.append(
            "INCONCLUSIVE: 无法确定状态，需要补充验证后重新评估。"
        )

    return gate.build_response(
        "tianzheng_manual_review_intake",
        data={
            "decision": decision,
            "reviewer_notes": notes,
            "next_phase_recommendation": next_phase_recommendation,
        },
        blocking_issues=blocking_issues,
    ).to_dict()


# ════════════════════════════════════════════════════════════════
# Tool 6: tianzheng_safety_gate_status
# ════════════════════════════════════════════════════════════════

def tianzheng_safety_gate_status(
    status_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """返回当前安全门状态。

    输入: phase state (可选)
    输出: d1_allowed / production_d1_allowed / source_modification_allowed 等
    限制: 默认全部 false
    """
    gate = MCPGate()
    if status_payload:
        try:
            gate.check_forbidden_input(status_payload)
        except MCPBlockedError as e:
            return gate.build_error_response(
                "tianzheng_safety_gate_status", e.code, e.detail
            ).to_dict()

    return gate.build_response(
        "tianzheng_safety_gate_status",
        data={
            "phase": status_payload.get("phase", "M3-prep") if status_payload else "M3-prep",
            "safety_status": gate.get_safety_status(),
            "d1_readiness": False,
            "production_readiness": False,
            "summary": "所有安全门关闭。Production D1 blocked。",
        },
    ).to_dict()


# ════════════════════════════════════════════════════════════════
# Tool 7: tianzheng_explain_blockers
# ════════════════════════════════════════════════════════════════

def tianzheng_explain_blockers(
    report_payload: dict[str, Any],
) -> dict[str, Any]:
    """解释当前阻塞项。

    输入: phase report dict
    输出: blocking issues list
    限制: 不得执行任何 CAD 操作
    """
    gate = MCPGate()
    try:
        gate.check_forbidden_input(report_payload)
    except MCPBlockedError as e:
        return gate.build_error_response(
            "tianzheng_explain_blockers", e.code, e.detail
        ).to_dict()

    blockers: list[dict[str, str]] = [
        {"blocker": "MCP_BLOCKED_REAL_EXECUTION", "reason": "当前处于 Phase M3-prep，真实执行被阻止。", "status": "active"},
        {"blocker": "MCP_BLOCKED_AUTOCAD_CONNECT", "reason": "AutoCAD 连接未授权。", "status": "active"},
        {"blocker": "MCP_BLOCKED_DWG_OPEN", "reason": "DWG 打开未授权。", "status": "active"},
        {"blocker": "MCP_BLOCKED_PRODUCTION_D1", "reason": "d1_allowed=false，Production D1 被阻止。", "status": "active"},
        {"blocker": "MCP_BLOCKED_SOURCE_WRITE", "reason": "source_modification_allowed=false，源 DWG 写入被阻止。", "status": "active"},
        {"blocker": "MCP_HTTP_BRIDGE_BLOCKED", "reason": "HTTP Bridge 调用被阻止。", "status": "active"},
        {"blocker": "MCP_SENDCOMMAND_BLOCKED", "reason": "SendCommand 被阻止。", "status": "active"},
        {"blocker": "MCP_SOURCE_DWG_PROTECTED", "reason": "源 DWG 受保护，只读不可改。", "status": "active"},
    ]

    return gate.build_response(
        "tianzheng_explain_blockers",
        data={
            "blocker_count": len(blockers),
            "blockers": blockers,
            "d1_allowed": False,
            "production_d1_allowed": False,
        },
        blocking_issues=[b["reason"] for b in blockers],
    ).to_dict()


# ════════════════════════════════════════════════════════════════
# 便捷调用接口
# ════════════════════════════════════════════════════════════════

TOOL_REGISTRY: dict[str, Any] = {
    "tianzheng_validate_action": tianzheng_validate_action,
    "tianzheng_validate_action_batch": tianzheng_validate_action_batch,
    "tianzheng_dry_run_action_batch": tianzheng_dry_run_action_batch,
    "tianzheng_build_scan_report": tianzheng_build_scan_report,
    "tianzheng_manual_review_intake": tianzheng_manual_review_intake,
    "tianzheng_safety_gate_status": tianzheng_safety_gate_status,
    "tianzheng_explain_blockers": tianzheng_explain_blockers,
}


def call_tool(tool_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """通用 MCP 工具调用入口。"""
    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        return MCPGate.build_error_response(
            tool_name, MCPErrorCode.MCP_INVALID_ACTION_TYPE, f"未知工具: {tool_name!r}"
        ).to_dict()
    result = tool(payload or {})
    return ensure_safety_flags(result)
