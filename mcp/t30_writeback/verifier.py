from __future__ import annotations

from mcp.t30_writeback.models import T30Transaction


def verify_created_entities(
    transaction: T30Transaction,
    target_graph_before: dict | None = None,
    options: dict | None = None,
) -> dict:
    executed = list(transaction.metadata.get("executed_actions", []))
    failed = list(transaction.metadata.get("failed_actions", []))
    created = list(transaction.metadata.get("created_entities", []))
    errors: list[str] = []
    for entity in created:
        if not entity.get("handle"):
            errors.append("created entity missing handle")
    if len(created) != len(executed) - len(failed):
        errors.append("created entity count mismatch")
    return {
        "valid": not errors,
        "executed_count": len(executed),
        "failed_count": len(failed),
        "created_count": len(created),
        "created_entities": created,
        "errors": errors,
        "warnings": [],
        "options": dict(options or {}),
        "target_graph_before_present": target_graph_before is not None,
    }

