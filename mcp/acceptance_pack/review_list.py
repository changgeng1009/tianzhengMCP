from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_manual_review_list(
    acceptance_result: dict,
    output_path: str | None = None,
) -> dict:
    repair_plan = (
        acceptance_result.get("e2e_result", {}).get("repair_plan_v2", {})
        or acceptance_result.get("repair_plan_v2", {})
    )
    groups = {
        "auto_actions": list(repair_plan.get("actions", [])),
        "review_actions": list(repair_plan.get("review_actions", [])),
        "rejected_actions": list(repair_plan.get("rejected_actions", [])),
    }
    writeback = dict(acceptance_result.get("writeback_result") or {})
    reread = dict(acceptance_result.get("reread_verification") or {})
    payload = {
        "status": "success",
        "run_id": acceptance_result.get("run_id"),
        "items": _items(groups, writeback, reread),
        "warnings": list(acceptance_result.get("warnings", [])),
        "writeback_status": writeback.get("status"),
        "reread_status": reread.get("status"),
    }
    if output_path:
        base = Path(output_path)
        json_path = base.with_suffix(".json")
        markdown_path = base.with_suffix(".md")
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(_markdown(payload), encoding="utf-8")
        payload["json_path"] = str(json_path)
        payload["markdown_path"] = str(markdown_path)
    return payload


def _items(groups: dict[str, list[dict]], writeback: dict, reread: dict) -> list[dict[str, Any]]:
    created = list(writeback.get("created_entities", []))
    items: list[dict[str, Any]] = []
    for group, actions in groups.items():
        status = group.replace("_actions", "")
        for index, action in enumerate(actions):
            items.append(
                {
                    "status": status,
                    "action_id": action.get("action_id"),
                    "action_type": action.get("action_type") or action.get("type"),
                    "geometry": action.get("geometry"),
                    "system": action.get("system") or action.get("system_type"),
                    "dn": action.get("dn"),
                    "layer": action.get("layer"),
                    "confidence": action.get("confidence"),
                    "reason": action.get("reason"),
                    "written_to_sandbox": bool(created) and status == "auto" and index < len(created),
                    "reread_verification_status": reread.get("status"),
                }
            )
    return items


def _markdown(payload: dict) -> str:
    lines = [
        f"# 人工审核清单 - {payload.get('run_id')}",
        "",
        f"- Writeback: `{payload.get('writeback_status')}`",
        f"- Re-read: `{payload.get('reread_status')}`",
        "",
        "| status | action_id | type | geometry | system | dn | layer | confidence | reason | sandbox | reread |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in payload["items"]:
        lines.append(
            "| {status} | {action_id} | {action_type} | {geometry} | {system} | {dn} | {layer} | {confidence} | {reason} | {written_to_sandbox} | {reread_verification_status} |".format(
                **{key: item.get(key) for key in [
                    "status",
                    "action_id",
                    "action_type",
                    "geometry",
                    "system",
                    "dn",
                    "layer",
                    "confidence",
                    "reason",
                    "written_to_sandbox",
                    "reread_verification_status",
                ]}
            )
        )
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {warning}" for warning in payload.get("warnings", [])] or ["- 无"])
    return "\n".join(lines) + "\n"

