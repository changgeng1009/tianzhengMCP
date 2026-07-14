from __future__ import annotations

from pathlib import Path


def verify_sandbox_dwg_after_writeback(
    sandbox_dwg_path: str,
    writeback_result: dict,
    target_graph_before: dict | None = None,
    options: dict | None = None,
) -> dict:
    options = dict(options or {})
    warnings: list[str] = []
    errors: list[str] = []
    if not Path(sandbox_dwg_path).exists():
        return {"status": "failed", "confirmed_entities": [], "unconfirmed_actions": [], "warnings": [], "errors": [f"sandbox DWG not found: {sandbox_dwg_path}"], "metrics": {}}

    created_entities = list(writeback_result.get("created_entities") or [])
    executed_actions = list(writeback_result.get("executed_actions") or [])
    mode = writeback_result.get("metadata", {}).get("mode")
    verification_mode = options.get("verification_mode", "fake")
    if verification_mode == "fake" or mode == "fake":
        confirmed = [entity for entity in created_entities if entity.get("handle")]
        unconfirmed = executed_actions[len(confirmed) :]
        status = "verified" if created_entities and len(confirmed) == len(created_entities) else "unverified"
        if status != "verified":
            warnings.append("fake verification did not confirm all entities")
        return {
            "status": status,
            "confirmed_entities": confirmed,
            "unconfirmed_actions": unconfirmed,
            "warnings": warnings,
            "errors": errors,
            "metrics": {"confirmed_count": len(confirmed), "created_count": len(created_entities)},
            "target_graph_before_present": target_graph_before is not None,
        }

    warnings.append("real DWG reread verifier hook is not configured")
    return {
        "status": "unverified",
        "confirmed_entities": [],
        "unconfirmed_actions": executed_actions,
        "warnings": warnings,
        "errors": errors,
        "metrics": {"confirmed_count": 0, "created_count": len(created_entities)},
    }

