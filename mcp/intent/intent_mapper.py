"""MCP Intent Mapper — Phase M3-prep mock。

将自然语言意图映射到 MCP 工具调用链。
意图 → MCP tool → command_registry (dry-run only)
不得绕过安全门控，不得直接触发真实执行。
"""

from __future__ import annotations

from typing import Any

from tianzheng_interface.action_schema import VALID_ACTION_TYPES
from mcp.safety.mcp_safety import MCPGate
from mcp.safety.mcp_errors import MCPErrorCode

# ════════════════════════════════════════════════════════════════
# 意图模板 — 自然语言 → 结构化命令
# ════════════════════════════════════════════════════════════════

INTENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "add_pipe": {
        "patterns": ["新增管道", "添加管道", "画管", "加管", "增加管段"],
        "tool": "tianzheng_validate_action",
        "action_type": "add_pipe",
        "confidence": 0.85,
    },
    "add_valve": {
        "patterns": ["新增阀门", "添加阀门", "加阀", "加阀门"],
        "tool": "tianzheng_validate_action",
        "action_type": "add_valve",
        "confidence": 0.85,
    },
    "add_fitting": {
        "patterns": ["新增管件", "添加管件", "加弯头", "加三通"],
        "tool": "tianzheng_validate_action",
        "action_type": "add_fitting",
        "confidence": 0.80,
    },
    "update_diameter": {
        "patterns": ["修改管径", "改管径", "变更管径", "调整管径", "DN"],
        "tool": "tianzheng_validate_action",
        "action_type": "update_diameter",
        "confidence": 0.75,
    },
    "update_elevation": {
        "patterns": ["修改标高", "改标高", "调整标高", "变更标高"],
        "tool": "tianzheng_validate_action",
        "action_type": "update_elevation",
        "confidence": 0.70,
    },
    "delete_candidate": {
        "patterns": ["删除管道", "删除阀门", "删除管件", "移除", "去掉"],
        "tool": "tianzheng_validate_action",
        "action_type": "delete_candidate",
        "confidence": 0.60,
    },
    "scan_dwg": {
        "patterns": ["扫描图纸", "扫描DWG", "分析图纸", "检查图纸"],
        "tool": "tianzheng_build_scan_report",
        "confidence": 0.90,
    },
    "validate_batch": {
        "patterns": ["验证批量操作", "批量检查", "检查所有操作"],
        "tool": "tianzheng_validate_action_batch",
        "confidence": 0.85,
    },
    "dry_run": {
        "patterns": ["干运行", "模拟执行", "dryrun", "预览操作"],
        "tool": "tianzheng_dry_run_action_batch",
        "confidence": 0.85,
    },
    "review_status": {
        "patterns": ["审核状态", "审核决定", "PASS_VISUAL_ONLY", "FAIL_VISUAL", "INCONCLUSIVE"],
        "tool": "tianzheng_manual_review_intake",
        "confidence": 0.90,
    },
    "safety_check": {
        "patterns": ["安全检查", "安全门状态", "能执行吗", "可以真实执行吗"],
        "tool": "tianzheng_safety_gate_status",
        "confidence": 0.90,
    },
}


class IntentMapper:
    """Phase M3-prep: 基于规则的意图映射器 mock。

    输入: 自然语言文本
    输出: 建议的 MCP 工具调用 (dry-run only)
    """

    def parse(self, natural_language: str) -> dict[str, Any]:
        """解析自然语言意图。"""
        text = str(natural_language or "").strip().lower()

        best_match = None
        best_score = 0.0

        for intent_key, template in INTENT_TEMPLATES.items():
            for pattern in template["patterns"]:
                if pattern.lower() in text:
                    score = template["confidence"]
                    if score > best_score:
                        best_score = score
                        best_match = template

        if not best_match:
            return self._no_match_result()

        return {
            "intent_found": True,
            "confidence": best_match["confidence"],
            "suggested_tool": best_match["tool"],
            "suggested_action_type": best_match.get("action_type"),
            "ready_to_execute": False,
            "requires_safety_gate": True,
            "d1_allowed": False,
            "safety_flags": {
                "d1_allowed": False,
                "production_d1_allowed": False,
                "source_modification_allowed": False,
            },
        }

    def parse_to_mcp_call(
        self, natural_language: str
    ) -> dict[str, Any]:
        """解析自然语言并生成 MCP 调用建议。

        Returns: MCP 调用链，始终 dry-run only。
        """
        intent_result = self.parse(natural_language)

        if not intent_result.get("intent_found"):
            return {
                "success": False,
                "error": "未找到匹配的意图。",
                "suggested_next": "请使用更具体的操作描述。",
                "safety_flags": MCPGate.get_safety_status(),
            }

        tool_name = intent_result["suggested_tool"]
        mcp_call_chain = [
            {"step": 1, "tool": "tianzheng_safety_gate_status", "purpose": "检查安全门状态"},
            {"step": 2, "tool": tool_name, "purpose": f"执行 {tool_name}"},
        ]

        return {
            "success": True,
            "intent": intent_result,
            "mcp_call_chain": mcp_call_chain,
            "execution_mode": "dry_run_only",
            "safety_flags": MCPGate.get_safety_status(),
        }

    @staticmethod
    def _no_match_result() -> dict[str, Any]:
        return {
            "intent_found": False,
            "confidence": 0.0,
            "suggested_tool": None,
            "ready_to_execute": False,
            "requires_safety_gate": True,
            "d1_allowed": False,
            "safety_flags": {
                "d1_allowed": False,
                "production_d1_allowed": False,
                "source_modification_allowed": False,
            },
        }


def map_intent(natural_language: str) -> dict[str, Any]:
    """便捷函数：映射自然语言到 MCP 工具。"""
    return IntentMapper().parse(natural_language)
