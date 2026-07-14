from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from mcp.diagnostics.input_graph import run_input_graph_diagnostics


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run read-only input graph diagnostics.")
    parser.add_argument("--target-dwg", required=True)
    parser.add_argument("--reference-pdf", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scope-json", default="")
    parser.add_argument("--manual-anchors-json", default="")
    args = parser.parse_args(argv)

    scope = _loads_json_argument(args.scope_json) if args.scope_json else None
    manual_anchors = _loads_json_argument(args.manual_anchors_json) if args.manual_anchors_json else None
    if scope is None and manual_anchors is None:
        result = run_input_graph_diagnostics(args.target_dwg, args.reference_pdf)
    else:
        result = run_input_graph_diagnostics(args.target_dwg, args.reference_pdf, scope=scope, manual_anchor_pairs=manual_anchors)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _loads_json_argument(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return json.loads(value.replace('\\"', '"'))


if __name__ == "__main__":
    raise SystemExit(main())
