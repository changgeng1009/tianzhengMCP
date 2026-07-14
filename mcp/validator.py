from __future__ import annotations

import re
from typing import Any


VALID_DN_RANGE = range(15, 501)


class RepairPlanValidator:
    def validate(
        self,
        repair_plan: dict[str, Any],
        dwg_graph: dict[str, Any],
        reference_graph: dict[str, Any],
    ) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        actions = repair_plan.get("actions", [])
        node_ids = {str(node.get("id")) for node in reference_graph.get("nodes", [])}
        existing_pipe_signatures = {
            _pipe_signature(edge)
            for edge in dwg_graph.get("edges", [])
            if edge.get("semantic_type") == "pipe"
        }
        new_pipe_signatures: set[tuple[Any, ...]] = set()

        for action in actions:
            action_id = str(action.get("action_id") or action.get("id") or "")
            action_type = action.get("type")
            if action_type == "add_pipe":
                signature = self._validate_pipe_action(
                    action,
                    action_id,
                    node_ids,
                    existing_pipe_signatures,
                    new_pipe_signatures,
                    errors,
                )
                if signature is not None:
                    new_pipe_signatures.add(signature)
            elif action_type in {"add_valve", "add_sprinkler", "add_fitting"}:
                if not action.get("position"):
                    errors.append(_error(action_id, "missing_position", "新增设备缺少 position。"))
            else:
                errors.append(_error(action_id, "unsupported_action", f"不支持的动作: {action_type}"))

        return {
            "valid": not errors,
            "errors": errors,
        }

    def _validate_pipe_action(
        self,
        action: dict[str, Any],
        action_id: str,
        node_ids: set[str],
        existing_pipe_signatures: set[tuple[Any, ...]],
        new_pipe_signatures: set[tuple[Any, ...]],
        errors: list[dict[str, Any]],
    ) -> tuple[Any, ...] | None:
        start_node = str(action.get("start_node") or "")
        end_node = str(action.get("end_node") or "")
        if start_node not in node_ids:
            errors.append(_error(action_id, "missing_start_node", f"起点 node 不存在: {start_node}"))
        if end_node not in node_ids:
            errors.append(_error(action_id, "missing_end_node", f"终点 node 不存在: {end_node}"))
        if start_node and end_node and start_node == end_node:
            errors.append(_error(action_id, "invalid_pipe_connection", "管线起点和终点不能相同。"))

        dn = _dn_to_int(action.get("dn"))
        if dn is None or dn not in VALID_DN_RANGE:
            errors.append(_error(action_id, "invalid_dn", f"DN 不在允许范围内: {action.get('dn')}"))

        signature = (
            "pipe",
            tuple(sorted([start_node, end_node])),
            dn,
            action.get("system_type"),
        )
        if signature in existing_pipe_signatures:
            errors.append(_error(action_id, "conflicts_existing_pipe", "补图动作与现有管线重复。"))
        if signature in new_pipe_signatures:
            errors.append(_error(action_id, "duplicate_repair_action", "补图动作重复生成。"))
        return signature


def _pipe_signature(edge: dict[str, Any]) -> tuple[Any, ...]:
    dn = _dn_to_int(edge.get("diameter"))
    return (
        "pipe",
        tuple(sorted([str(edge.get("start_node_id")), str(edge.get("end_node_id"))])),
        dn,
        edge.get("system_type"),
    )


def _dn_to_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    text = str(value or "")
    match = re.search(r"(\d+)", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _error(action_id: str, code: str, message: str) -> dict[str, str]:
    return {
        "action_id": action_id,
        "code": code,
        "message": message,
    }

