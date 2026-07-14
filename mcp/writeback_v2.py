from __future__ import annotations

from typing import Any

from mcp.adapter_t30 import T30WritebackAdapter


TRANSACTION_STAGES = ["validate", "simulate", "execute", "verify", "commit"]


class SafeT30WritebackV2:
    def __init__(self, adapter: T30WritebackAdapter | None = None) -> None:
        self.adapter = adapter or T30WritebackAdapter(real_com_mode=False)

    def safe_apply(self, repair_plan: dict[str, Any], target_graph: dict[str, Any]) -> dict[str, Any]:
        blocked_actions: list[dict[str, Any]] = []
        validation = self._validate(repair_plan, blocked_actions)
        simulation = self._simulate(validation["executable_actions"], target_graph, blocked_actions)
        execution = self._execute(simulation["executable_actions"])
        verification = self._verify(execution["executed_actions"])
        committed = self._commit(verification["verified_actions"])

        return {
            "status": "success",
            "transaction_stages": list(TRANSACTION_STAGES),
            "validated_actions": validation["validated_actions"],
            "simulated_actions": simulation["simulated_actions"],
            "committed_actions": committed,
            "blocked_actions": blocked_actions,
            "rollback_plan": _rollback_plan(committed),
            "warnings": validation["warnings"] + simulation["warnings"] + verification["warnings"],
        }

    def _validate(
        self,
        repair_plan: dict[str, Any],
        blocked_actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        warnings: list[str] = []
        validated: list[dict[str, Any]] = []
        executable: list[dict[str, Any]] = []
        for action in repair_plan.get("actions", []):
            if not action.get("auto_execute"):
                blocked_actions.append(
                    {
                        "action_id": action.get("action_id"),
                        "reason": "confidence_gate_blocked",
                        "confidence": action.get("confidence"),
                    }
                )
                continue
            if action.get("type") == "add_pipe" and (
                not action.get("start") or not action.get("end") or not action.get("dn")
            ):
                blocked_actions.append(
                    {
                        "action_id": action.get("action_id"),
                        "reason": "geometry_validation_failed",
                    }
                )
                continue
            validated.append(action)
            executable.append(action)
        return {
            "validated_actions": validated,
            "executable_actions": executable,
            "warnings": warnings,
        }

    def _simulate(
        self,
        actions: list[dict[str, Any]],
        target_graph: dict[str, Any],
        blocked_actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        warnings: list[str] = []
        simulated: list[dict[str, Any]] = []
        executable: list[dict[str, Any]] = []
        existing_signatures = {_pipe_signature(pipe) for pipe in target_graph.get("pipes", [])}
        seen_signatures: set[tuple[Any, ...]] = set()
        for action in actions:
            signature = _pipe_signature(action)
            if signature in existing_signatures or signature in seen_signatures:
                blocked_actions.append(
                    {
                        "action_id": action.get("action_id"),
                        "reason": "duplicate_or_collision_detected",
                    }
                )
                continue
            seen_signatures.add(signature)
            simulated.append({**action, "simulation": "pass"})
            executable.append(action)
        return {
            "simulated_actions": simulated,
            "executable_actions": executable,
            "warnings": warnings,
        }

    def _execute(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        executed: list[dict[str, Any]] = []
        for action in actions:
            if action.get("type") == "add_pipe":
                result = self.adapter.insert_pipe(
                    action_id=str(action.get("action_id")),
                    start=list(action.get("start", [0.0, 0.0, 0.0])),
                    end=list(action.get("end", [0.0, 0.0, 0.0])),
                    dn=int(action.get("dn")),
                    layer=str(action.get("layer") or "0"),
                    system_type=action.get("system_type"),
                )
            else:
                result = {
                    "success": False,
                    "status": "unsupported_action",
                    "action_id": action.get("action_id"),
                    "type": action.get("type"),
                }
            executed.append({**action, "result": result})
        return {"executed_actions": executed}

    def _verify(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        warnings: list[str] = []
        verified = [action for action in actions if action.get("result", {}).get("success")]
        for action in actions:
            if not action.get("result", {}).get("success"):
                warnings.append(f"writeback failed: {action.get('action_id')}")
        return {"verified_actions": verified, "warnings": warnings}

    def _commit(self, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "action_id": action.get("action_id"),
                "type": action.get("type"),
                "status": "committed",
                "result": action.get("result"),
            }
            for action in actions
        ]


def _rollback_plan(committed_actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "available": bool(committed_actions),
        "actions": [
            {
                "action_id": action.get("action_id"),
                "rollback_type": "delete_inserted_object",
                "handle": action.get("result", {}).get("handle"),
            }
            for action in committed_actions
        ],
    }


def _pipe_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("dn"),
        item.get("system_type"),
        tuple(item.get("start", [])),
        tuple(item.get("end", [])),
    )

