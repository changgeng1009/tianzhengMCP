from __future__ import annotations

from math import dist
from typing import Any


class ConfidenceAwareRepairEngine:
    def generate(self, diff_result: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        for bucket in ("true_missing", "design_variation", "uncertain"):
            for item in diff_result.get(bucket, []):
                actions.append(_action_from_diff_item(item, bucket))
        return {
            "status": "generated",
            "actions": actions,
            "policy": {
                "auto_execute": "confidence > 0.85",
                "needs_review": "0.6 < confidence < 0.85",
                "blocked": "confidence < 0.6",
            },
        }


class RepairPlanOptimizer:
    def optimize(self, repair_plan: dict[str, Any]) -> dict[str, Any]:
        best_by_signature: dict[tuple[Any, ...], dict[str, Any]] = {}
        removed: list[str] = []
        for action in repair_plan.get("actions", []):
            signature = _optimization_signature(action)
            existing = best_by_signature.get(signature)
            if existing is None:
                best_by_signature[signature] = action
                continue
            if _path_length(action) < _path_length(existing):
                removed.append(str(existing.get("action_id")))
                best_by_signature[signature] = action
            else:
                removed.append(str(action.get("action_id")))

        optimized_actions = list(best_by_signature.values())
        optimized_actions.sort(key=lambda action: str(action.get("action_id")))
        return {
            **repair_plan,
            "actions": optimized_actions,
            "optimization": {
                "removed_duplicates": removed,
                "strategy": "deduplicate_by_type_dn_system_start_keep_shortest_path",
            },
        }


def _action_from_diff_item(item: dict[str, Any], bucket: str) -> dict[str, Any]:
    pipe = item.get("entity", {})
    confidence = float(item.get("confidence", 0.0))
    decision = _execution_decision(confidence)
    return {
        "action_id": f"repair_{item.get('reference_id')}",
        "source_id": item.get("reference_id"),
        "source_bucket": bucket,
        "type": "add_pipe",
        "start": list(pipe.get("start", [0.0, 0.0, 0.0])),
        "end": list(pipe.get("end", [0.0, 0.0, 0.0])),
        "dn": pipe.get("dn"),
        "layer": pipe.get("layer") or f"PIPE-{pipe.get('system_type', 'unknown')}",
        "system_type": pipe.get("system_type"),
        "confidence": confidence,
        "auto_execute": decision == "auto_execute",
        "execution_decision": decision,
    }


def _execution_decision(confidence: float) -> str:
    if confidence > 0.85:
        return "auto_execute"
    if confidence > 0.6:
        return "needs_review"
    return "blocked"


def _optimization_signature(action: dict[str, Any]) -> tuple[Any, ...]:
    return (
        action.get("type"),
        action.get("dn"),
        action.get("system_type"),
        tuple(action.get("start", [])),
    )


def _path_length(action: dict[str, Any]) -> float:
    start = [float(value) for value in action.get("start", [0.0, 0.0, 0.0])]
    end = [float(value) for value in action.get("end", [0.0, 0.0, 0.0])]
    return dist(start[:3], end[:3])
