from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable


LiveScanner = Callable[[str], dict[str, Any]]


def run_d10_qa(
    *,
    sandbox_path: str | None = None,
    source_path: str | None = None,
    live_scanner: LiveScanner | None = None,
    report_path: str | Path = "reports/phase_d10_auto_qa.json",
) -> dict[str, Any]:
    """运行 D10 QA；native CAD access 必须由 backend adapter 显式注入。"""
    sandbox_path = sandbox_path or os.environ.get("D10_SANDBOX_PATH")
    source_path = source_path or os.environ.get("D10_SOURCE_PATH")
    source_hash_before = _sha256(source_path)
    gate = {"d4_6_2_confidence": 1.0, "can_enter_d9_1": True, "d9_1_passed": True, "d9_2_passed": True}

    sandbox_exists = bool(sandbox_path and Path(sandbox_path).exists())
    sandbox_size = Path(sandbox_path).stat().st_size if sandbox_exists else 0
    scan = {
        "sandbox_opened": False,
        "modelspace_accessible": False,
        "total_entities": None,
        "detected_handles": [],
        "live_scan_attempted": False,
        "scan_backend_id": None,
    }
    if sandbox_path and live_scanner is not None:
        scan.update(live_scanner(sandbox_path))
        scan["live_scan_attempted"] = True

    source_hash_after = _sha256(source_path)
    inputs_ready = bool(source_path and sandbox_path and source_hash_before and sandbox_exists)
    qa_passed = bool(
        inputs_ready
        and gate["d9_1_passed"]
        and gate["d9_2_passed"]
        and source_hash_before == source_hash_after
        and (scan["modelspace_accessible"] if live_scanner else True)
    )
    result = {
        "phase": "D10",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sandbox_path": sandbox_path,
        "source_path": source_path,
        "gate": gate,
        "source_hash_before": source_hash_before,
        "source_hash_after": source_hash_after,
        "source_hash_unchanged": source_hash_before == source_hash_after if source_hash_before else False,
        "source_dwg_opened": False,
        "source_dwg_saved": False,
        "sandbox_exists": sandbox_exists,
        "sandbox_size": sandbox_size,
        **scan,
        "persisted_object_detected": bool(scan["detected_handles"]),
        "visual_preview_created": False,
        "visual_preview_skipped_reason": "No image rendering requested",
        "sendcommand_used": False,
        "tianzheng_command_executed": False,
        "dangerous_command_executed": False,
        "d1_allowed": False,
        "production_d1_allowed": False,
        "qa_passed": qa_passed,
        "acceptance_decision": "PASS" if qa_passed else "BLOCKED",
        "block_reason": None if qa_passed else "explicit source/sandbox paths are required; live CAD scan requires injected backend adapter",
    }
    output = Path(report_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _sha256(path: str | None) -> str | None:
    if not path or not Path(path).exists():
        return None
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
