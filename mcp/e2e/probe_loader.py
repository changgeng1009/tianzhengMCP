from __future__ import annotations

import json
from pathlib import Path


def load_manual_probe_result(path: str) -> dict:
    probe_path = Path(path)
    if not probe_path.exists():
        return {"status": "failed", "capabilities": [], "confirmed_capabilities": [], "candidate_methods": [], "errors": [f"probe result not found: {path}"], "warnings": []}
    try:
        payload = json.loads(probe_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "failed", "capabilities": [], "confirmed_capabilities": [], "candidate_methods": [], "errors": [str(exc)], "warnings": []}

    capabilities = list(payload.get("capabilities") or [])
    confirmed: list[str] = []
    candidates: list[dict] = []
    for capability in capabilities:
        method = f"{capability.get('object_type')}.{capability.get('method_name')}"
        if capability.get("probe_status") == "confirmed" and capability.get("available"):
            confirmed.append(method)
        candidates.append(
            {
                "method": method,
                "probe_status": capability.get("probe_status"),
                "signature": dict(capability.get("signature") or {}),
            }
        )
    return {
        "status": "success",
        "capabilities": capabilities,
        "confirmed_capabilities": confirmed,
        "candidate_methods": candidates,
        "errors": [],
        "warnings": [],
        "metadata": {"path": str(probe_path)},
    }

