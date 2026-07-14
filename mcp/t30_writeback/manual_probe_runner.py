from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mcp.t30_writeback.com_probe import T30COMProbe


def run_manual_probe(
    output_path: str = "artifacts/t30_probe_result.json",
    target_dwg_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict:
    probe = T30COMProbe(target_dwg_path=target_dwg_path, options=options)
    environment = probe.probe_environment()
    capabilities = [capability.to_dict() for capability in probe.probe_insert_methods()]
    result = {
        "status": "success" if environment.get("status") == "success" else "failed",
        "environment": environment,
        "autocad": dict(environment.get("autocad") or {}),
        "document_resolution": dict(environment.get("document_resolution") or {}),
        "capabilities": capabilities,
        "readonly": True,
        "warnings": list(environment.get("warnings", [])),
        "errors": list(environment.get("errors", [])),
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run readonly T30 COM capability probe.")
    parser.add_argument("--output", default="artifacts/t30_probe_result.json")
    parser.add_argument("--target-dwg", default=None)
    parser.add_argument("--allow-open-document", action="store_true", default=False)
    args = parser.parse_args()
    print(
        json.dumps(
            run_manual_probe(
                output_path=args.output,
                target_dwg_path=args.target_dwg,
                options={"allow_open_document": bool(args.allow_open_document)},
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
