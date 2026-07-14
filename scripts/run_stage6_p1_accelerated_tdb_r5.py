"""R5 Checkpoint-Aware Accelerated TDb Resume Launcher
==========================================================
Usage:
  python run_stage6_p1_accelerated_tdb_r5.py --preflight-only   # Offline validation
  python run_stage6_p1_accelerated_tdb_r5.py                      # Prepare run
  python run_stage6_p1_accelerated_tdb_r5.py --work-file <path>   # Specify work file

Never auto-connects to AutoCAD. Never modifies R4 state.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(r"D:\ExampleWorkspace\天正")
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.orchestration.stage6_p1_accelerated_tdb_r5 import (
    ROOT,
    R4_CHECKPOINTS,
    PREWRITE_BACKUP,
    _atomic_json,
    r5_preflight,
    prepare_r5_run,
    read_latest_checkpoint,
    compute_completed_from_checkpoints,
)


def main() -> int:
    preflight_only = "--preflight-only" in sys.argv
    sim_mode = "--sim" in sys.argv
    work_file_arg = None
    for i, arg in enumerate(sys.argv):
        if arg == "--work-file" and i + 1 < len(sys.argv):
            work_file_arg = sys.argv[i + 1]
            break

    print("=" * 60)
    print("STAGE6-P1-ACCELERATED-TDB-R5")
    print("Checkpoint-Aware TDb Resume")
    print("=" * 60)
    print(f"  Time: {datetime.now().isoformat()}")
    print(f"  R4 checkpoints: {R4_CHECKPOINTS}")

    # ── Preflight ──
    print("\n[1/3] R5 Preflight")
    pf = r5_preflight(R4_CHECKPOINTS)
    if not pf["passed"]:
        print("\nPREFLIGHT FAILED — cannot proceed")
        return 1
    print("\nPREFLIGHT PASSED")

    if preflight_only:
        print("--preflight-only mode: exiting.")
        return 0

    # ── Determine work file ──
    if work_file_arg:
        work_file = Path(work_file_arg)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        work_file = ROOT / "图纸" / f"target_sample-应急提交版-R5-{ts}.dwg"
    print(f"\n  R5 work file: {work_file}")
    print("  R4 work file is NEVER modified by R5")

    # ── Prepare ──
    print("\n[2/3] Preparing R5 run")
    try:
        manifest = prepare_r5_run(str(work_file))
    except RuntimeError as e:
        print(f"PREPARE FAILED: {e}")
        return 1
    print(f"  Run ID: {manifest['run_id']}")
    print(f"  Completed: {manifest['completed_task_count']}")
    print(f"  Remaining: {manifest['remaining_task_count']}, Plan units: {manifest['plan_units']}")

    # ── Summary ──
    print("\n[3/3] Execution Plan Summary")
    for s in manifest["plan_summary"][:10]:
        tag = " [SERIAL]" if s["serial"] else ""
        print(f"  {s['type']:20s} {s['region']:30s} {s['tasks']:4d} tasks{tag}")
    if len(manifest["plan_summary"]) > 10:
        print(f"  ... and {len(manifest['plan_summary']) - 10} more units")

    s = manifest["plan_summary"]
    total_tasks = sum(u["tasks"] for u in s)
    serial_count = sum(1 for u in s if u["serial"])
    batch_count = len(s) - serial_count

    print(f"\n  Total: {len(s)} units, {total_tasks} tasks")
    print(f"  Batch: {batch_count}, Serial: {serial_count}")
    print(f"  Est CopyObjects calls: ~{batch_count + serial_count}")

    # ── Ready ──
    print("\n" + "=" * 60)
    print("STATUS: R5_TDB_ACCELERATED_RESUME_READY")
    print("=" * 60)
    print("\nR5 is PREPARED. It will NOT connect to AutoCAD automatically.")
    print(f"Manifest: {manifest['run_dir'] / 'manifest.json'}")
    print(f"Execution plan: {manifest['run_dir'] / 'execution_plan.json'}")
    print()
    print("Manual steps before executing R5:")
    print("  1. Ensure R4 is at a safe boundary (batch/component boundary)")
    print("  2. Verify R4 has not been externally interrupted")
    print("  3. Copy the prewrite DWG to R5 work file (if not done)")
    print("  4. Manually start R5 with explicit --work-file parameter")

    report = {
        "phase": "STAGE6-P1-ACCELERATED-TDB-R5",
        "status": "R5_TDB_ACCELERATED_RESUME_READY",
        "preflight_passed": pf["passed"],
        "manifest_skip_details": True,
    }
    report_path = ROOT / "reports" / "stage6_p1_accelerated_tdb_r5.json"
    _atomic_json(report_path, report)
    print(f"\nReport: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
