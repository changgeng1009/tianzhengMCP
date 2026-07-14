from __future__ import annotations

from typing import Any

from mcp.adapter_t30 import T30WritebackAdapter
from mcp.session import MCPSession
from mcp.validator import RepairPlanValidator


class RepairPlanExecutor:
    def __init__(
        self,
        adapter: T30WritebackAdapter | None = None,
        validator: RepairPlanValidator | None = None,
    ) -> None:
        self.adapter = adapter or T30WritebackAdapter(real_com_mode=False)
        self.validator = validator or RepairPlanValidator()

    def validate(self, session: MCPSession) -> dict[str, Any]:
        validation = self.validator.validate(
            session.repair_plan,
            session.dwg_graph,
            session.png_graph,
        )
        session.repair_plan["validation"] = validation
        return validation

    def apply(self, session: MCPSession) -> dict[str, Any]:
        validation = session.repair_plan.get("validation")
        if not validation:
            validation = self.validate(session)
        if not validation.get("valid"):
            return {
                "success": False,
                "status": "validation_failed",
                "validation": validation,
                "applied_actions": [],
            }

        applied: list[dict[str, Any]] = []
        for action in session.repair_plan.get("actions", []):
            result = self._execute_action(action)
            applied_item = {
                "action_id": action.get("action_id"),
                "type": action.get("type"),
                "status": "committed" if result.get("success") else "failed",
                "result": result,
            }
            applied.append(applied_item)

        session.applied_actions = applied
        return {
            "success": all(item["status"] == "committed" for item in applied),
            "status": "committed",
            "applied_actions": applied,
            "adapter_action_log": list(self.adapter.action_log),
        }

    def _execute_action(self, action: dict[str, Any]) -> dict[str, Any]:
        action_type = action.get("type")
        if action_type == "add_pipe":
            return self.adapter.insert_pipe(
                action_id=str(action.get("action_id")),
                start=list(action.get("start", [0.0, 0.0, 0.0])),
                end=list(action.get("end", [0.0, 0.0, 0.0])),
                dn=int(action.get("dn")),
                layer=str(action.get("layer") or "0"),
                system_type=action.get("system_type"),
            )
        if action_type == "add_valve":
            return self.adapter.insert_valve(
                action_id=str(action.get("action_id")),
                position=list(action.get("position", [0.0, 0.0, 0.0])),
                on_pipe=str(action.get("on_pipe") or ""),
                valve_type=str(action.get("valve_type") or "unknown"),
                layer=str(action.get("layer") or "0"),
            )
        if action_type == "add_sprinkler":
            return self.adapter.insert_sprinkler(
                action_id=str(action.get("action_id")),
                position=list(action.get("position", [0.0, 0.0, 0.0])),
                layer=str(action.get("layer") or "0"),
                sprinkler_type=action.get("sprinkler_type"),
            )
        if action_type == "add_fitting":
            return self.adapter.insert_fitting(
                action_id=str(action.get("action_id")),
                position=list(action.get("position", [0.0, 0.0, 0.0])),
                fitting_type=str(action.get("fitting_type") or "unknown"),
                layer=str(action.get("layer") or "0"),
            )
        return {
            "success": False,
            "status": "unsupported_action",
            "action_id": action.get("action_id"),
            "type": action_type,
        }
