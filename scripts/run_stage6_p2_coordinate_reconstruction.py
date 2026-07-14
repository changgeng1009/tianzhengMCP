# -*- coding: utf-8 -*-
"""Entry point for Stage 6-P2: Correct Sample Coordinate Reconstruction.

Run:
    python scripts/run_stage6_p2_coordinate_reconstruction.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.orchestration.stage6_p2_coordinate_reconstruction import (
    RUNS_ROOT,
    REPORTS_DIR,
    run_stage6_p2,
)


def main() -> None:
    ts = datetime.now().strftime("stage6_p2_%Y%m%d_%H%M%S")
    output_dir = RUNS_ROOT / ts
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "alignment_reports").mkdir(parents=True, exist_ok=True)

    ref_path = Path(r"D:\ExampleWorkspace\天正\图纸\reference_sample_t8_t8_t8.dwg")
    tgt_path = Path(r"D:\ExampleWorkspace\天正\图纸\target_sample_t8.dwg")

    # Verify files exist
    for path, role in [(ref_path, "reference"), (tgt_path, "target")]:
        if not path.is_file():
            print(f"[FATAL] {role} not found: {path}")
            return

    print(f"[Stage 6-P2] Starting coordinate reconstruction")
    print(f"  Reference: {ref_path}")
    print(f"  Target:    {tgt_path}")
    print(f"  Output:    {output_dir}")

    manifest = run_stage6_p2(run_id=ts, ref_path=ref_path, tgt_path=tgt_path, output_dir=output_dir)

    print(f"\n[Stage 6-P2] Complete")
    print(f"  Status: {manifest.get('ready_for_missing_detection', 'UNKNOWN')}")
    print(f"  Verified transforms: {manifest.get('verified_transform_count', 0)}")
    print(f"  Low confidence:      {manifest.get('low_confidence_transform_count', 0)}")
    print(f"  Rejected:            {manifest.get('rejected_transform_count', 0)}")
    print(f"  Protected regions:   {manifest.get('protected_region_count', 0)}")
    print(f"  Conflicts:           {manifest.get('mapping_conflict_count', 0)}")
    print(f"  Hashes unchanged:    {manifest.get('reference_hash_unchanged', False)}")
    print(f"  Old plan reused:     {manifest.get('old_plan_reused', 'UNKNOWN')}")
    print(f"  Ready for missing:   {manifest.get('ready_for_missing_detection', False)}")

    if manifest.get("blocking_reasons"):
        print("\n[Blocking Reasons]")
        for r in manifest["blocking_reasons"]:
            print(f"  - {r}")

    report_json = REPORTS_DIR / "stage6_p2_coordinate_reconstruction.json"
    report_md = REPORTS_DIR / "stage6_p2_coordinate_reconstruction.md"
    print(f"\n  Reports: {report_json}, {report_md}")
    print(f"  All outputs: {output_dir}")


if __name__ == "__main__":
    main()
