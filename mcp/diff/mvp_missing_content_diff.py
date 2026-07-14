from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.recognition.mvp_reference_dwg_reader import read_reference_dwg
from mcp.recognition.mvp_reference_pdf_reader import read_reference_pdf
from mcp.recognition.mvp_target_dwg_reader import read_target_dwg


def _key(obj: dict[str, Any]) -> tuple[str, str, str]:
    semantic = obj.get("semantic", {})
    return (
        str(obj.get("object_type", "")),
        str(obj.get("layer", "")).strip().lower(),
        str(semantic.get("object_name") or semantic.get("label") or semantic.get("text") or "")[:80],
    )


def compare_missing_content(
    reference_objects: list[dict[str, Any]],
    target_objects: list[dict[str, Any]],
    *,
    include_review_only: bool = True,
) -> dict[str, Any]:
    target_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for target in target_objects:
        target_by_key.setdefault(_key(target), []).append(target)

    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    used_targets: set[str] = set()

    for ref in reference_objects:
        if ref.get("requires_visual_review") or ref.get("confidence", 0) < 0.5:
            uncertain.append({"reference_object": ref, "reason": "low confidence or visual review required"})
            continue
        candidates = target_by_key.get(_key(ref), [])
        if candidates:
            target = candidates.pop(0)
            used_targets.add(str(target.get("object_id")))
            matched.append({"reference_object_id": ref["object_id"], "target_object_id": target["object_id"], "confidence": 0.75})
        elif include_review_only and not ref.get("geometry"):
            uncertain.append({"reference_object": ref, "reason": "missing geometry prevents reliable diff"})
        else:
            missing.append({"reference_object": ref, "reason": "no matching target object"})

    extra = [target for target in target_objects if str(target.get("object_id")) not in used_targets]
    return {
        "phase": "MVP-1",
        "mode": "dry_run_gpt_fallback",
        "matched_objects": matched,
        "missing_objects": missing,
        "extra_objects": extra,
        "changed_objects": [],
        "uncertain_objects": uncertain,
        "review_only": uncertain,
        "matched_count": len(matched),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "changed_count": 0,
        "uncertain_count": len(uncertain),
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "sendcommand_used": False,
        "tianzheng_command_executed": False,
        "dangerous_command_executed": False,
        "production_d1_allowed": False,
    }


def run_default_diff() -> dict[str, Any]:
    ref_dwg = read_reference_dwg()
    ref_pdf = read_reference_pdf()
    target = read_target_dwg()
    reference_objects = ref_dwg["objects"] + ref_pdf["objects"]
    return compare_missing_content(reference_objects, target["objects"])


def main() -> None:
    print(json.dumps(run_default_diff(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

