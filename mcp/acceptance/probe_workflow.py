from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from mcp.acceptance.models import T30ProbeWorkflowResult
from mcp.e2e.probe_loader import load_manual_probe_result
from mcp.t30_writeback.manual_probe_runner import run_manual_probe


def run_probe_workflow(
    output_dir: str,
    options: dict | None = None,
) -> T30ProbeWorkflowResult:
    options = dict(options or {})
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    probe_path = output / "t30_probe_result.json"
    try:
        if options.get("fake_mode"):
            probe_result = _fake_probe_result()
            probe_path.write_text(json.dumps(probe_result, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            probe_result = run_manual_probe(
                str(probe_path),
                target_dwg_path=options.get("target_dwg_path"),
                options={"allow_open_document": bool(options.get("allow_open_document", False))},
            )
        loaded = load_manual_probe_result(str(probe_path))
        status = "success" if loaded.get("status") == "success" and probe_result.get("status") == "success" else "failed"
        return T30ProbeWorkflowResult(
            workflow_id=f"probe_wf_{uuid4().hex}",
            probe_result_path=str(probe_path),
            status=status,
            capabilities=list(loaded.get("capabilities", [])),
            candidate_methods=list(loaded.get("candidate_methods", [])),
            warnings=list(loaded.get("warnings", [])) + list(probe_result.get("warnings", [])),
            errors=list(loaded.get("errors", [])) + list(probe_result.get("errors", [])),
            metadata={"readonly": True, "fake_mode": bool(options.get("fake_mode"))},
        )
    except Exception as exc:
        return T30ProbeWorkflowResult(
            workflow_id=f"probe_wf_{uuid4().hex}",
            probe_result_path=str(probe_path),
            status="failed",
            capabilities=[],
            candidate_methods=[],
            errors=[str(exc)],
            metadata={"readonly": True},
        )


def _fake_probe_result() -> dict:
    capabilities = []
    for object_type in ["TDbPipe", "TDbPipeValve", "TDbPipeFitting", "TDbSprinkler"]:
        capabilities.append(
            {
                "capability_id": f"{object_type}.Insert",
                "object_type": object_type,
                "method_name": "Insert",
                "available": True,
                "confidence": 1.0,
                "signature": {"parameters": ["geometry", "system", "dn", "layer"]},
                "probe_status": "confirmed",
                "metadata": {"mode": "fake"},
            }
        )
    return {"status": "success", "capabilities": capabilities, "readonly": True, "warnings": [], "errors": []}
