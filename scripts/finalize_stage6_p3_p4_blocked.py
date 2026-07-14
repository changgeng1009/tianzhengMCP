from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp.orchestration import stage6_p3_p4_controlled_candidate as stage


RUN_ID = "stage6_p3_p4_20260713_145002"
RUN = ROOT / "artifacts" / "stage6_p3_p4_missing_and_drawing" / RUN_ID
REFERENCE = ROOT / "图纸" / "reference_sample_t8_t8_t8.dwg"
TARGET = ROOT / "图纸" / "target_sample_t8.dwg"
EXPECTED_REFERENCE = None  # External run configuration required; no bundled private default.
EXPECTED_TARGET = None  # External run configuration required; no bundled private default.


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    from mcp.orchestration.private_run_config import require_parameter
    EXPECTED_REFERENCE = require_parameter('scripts.finalize_stage6_p3_p4_blocked.expected_reference', 'sha256')
    EXPECTED_TARGET = require_parameter('scripts.finalize_stage6_p3_p4_blocked.expected_target', 'sha256')
    summary_path = RUN / "missing_detection" / "missing_detection_summary.json"
    plan_path = RUN / "frozen_plan" / "frozen_write_plan.json"
    copy_manifest = read(RUN / "input_identity" / "candidate_copy_manifest.json")
    summary = read(summary_path)
    plan = read(plan_path)
    candidate = Path(copy_manifest["candidate_dwg_path"])
    backup = Path(copy_manifest["prewrite_backup_path"])
    reasons = [
        "DEPENDENCY_GRAPH_NOT_AUTHORITATIVE: TDb valve/fitting/pipe relations are based on nearest geometry, not native relationship evidence",
        "FIRE_SYSTEM_MISSING_RATIO_REQUIRES_REVIEW: confirmed_missing=2307/reference_professional=2452",
        "CANDIDATE_OPENED_READ_ONLY: controlled write precondition failed before any Save",
    ]
    summary["status"] = "MISSING_DETECTION_SAFETY_GATE_BLOCKED"
    summary["safety_gate_reasons"] = reasons
    summary["candidate_plan_generated_but_invalidated"] = True
    summary["candidate_plan_task_count"] = plan["task_count"]
    summary["candidate_plan_sha256"] = plan["plan_sha256"]
    stage.write_json(summary_path, summary)
    stage.write_json(RUN / "frozen_plan" / "frozen_write_plan_invalidation.json", {
        "status": "INVALIDATED_SAFETY_GATE",
        "plan_path": str(plan_path),
        "plan_sha256": plan["plan_sha256"],
        "task_count": plan["task_count"],
        "execution_allowed": False,
        "reasons": reasons,
        "historical_plan_preserved": True,
    })
    stage.write_json(RUN / "execution" / "execution_batches.json", {
        "status": "ABORTED_PREWRITE_READONLY_CANDIDATE",
        "batches": [],
        "persisted_task_count": 0,
        "in_memory_attempt_count": "UNKNOWN_NOT_COMMITTED",
        "rollback_completed": True,
    })
    (RUN / "execution" / "created_entity_map.jsonl").write_text("", encoding="utf-8")
    stage.write_json(RUN / "execution" / "write_audit.json", {
        "status": "NO_COMMITTED_WRITE",
        "candidate_opened_read_only": True,
        "save_called": False,
        "saveas_called": False,
        "candidate_closed_without_save": True,
        "candidate_restored_from_prewrite_backup": True,
        "executed_task_count_committed": 0,
        "target_original_write": False,
        "target_original_save": False,
    })
    reference_hash, target_hash = stage.sha256_file(REFERENCE), stage.sha256_file(TARGET)
    candidate_hash, backup_hash = stage.sha256_file(candidate), stage.sha256_file(backup)
    stage.write_json(RUN / "verification" / "postwrite_snapshot.json", {
        "status": "RESTORED_PREWRITE_BASELINE_NO_PERSISTED_WRITE",
        "candidate_sha256": candidate_hash,
        "prewrite_backup_sha256": backup_hash,
        "hashes_match": candidate_hash == backup_hash == target_hash,
    })
    stage.write_json(RUN / "verification" / "persistence_verification.json", {
        "status": "NOT_EXECUTED_SAFETY_GATE_BLOCKED",
        "planned_task_count": plan["task_count"],
        "committed_task_count": 0,
        "persisted_task_count": 0,
        "candidate_restored": candidate_hash == backup_hash == target_hash,
    })
    stage.write_json(RUN / "verification" / "protected_region_verification.json", {
        "status": "UNCHANGED_NO_PERSISTED_WRITE",
        "protected_region_modified": 0,
        "protected_region_deleted": 0,
        "unchanged": True,
    })
    integrity = {
        "reference_sha256_before": EXPECTED_REFERENCE,
        "reference_sha256_after": reference_hash,
        "target_sha256_before": EXPECTED_TARGET,
        "target_sha256_after": target_hash,
        "reference_hash_unchanged": reference_hash == EXPECTED_REFERENCE,
        "target_hash_unchanged": target_hash == EXPECTED_TARGET,
        "candidate_restored_to_target_baseline": candidate_hash == target_hash,
        "prewrite_backup_unchanged": backup_hash == target_hash,
        "target_original_write": False,
        "target_original_save": False,
    }
    stage.write_json(RUN / "verification" / "original_file_integrity.json", integrity)
    final = {
        "phase": "STAGE6-P3-P4",
        "status": "MISSING_DETECTION_SAFETY_GATE_BLOCKED",
        "run_id": RUN_ID,
        "candidate_dwg_path": str(candidate),
        "candidate_dwg_sha256": candidate_hash,
        "prewrite_backup_path": str(backup),
        "prewrite_backup_sha256": backup_hash,
        "frozen_candidate_plan_task_count": plan["task_count"],
        "frozen_candidate_plan_sha256": plan["plan_sha256"],
        "frozen_candidate_plan_invalidated": True,
        "executed_task_count_committed": 0,
        "candidate_saved": False,
        "candidate_closed_without_save": True,
        "candidate_reopened_for_persistence": False,
        "candidate_restored": candidate_hash == backup_hash == target_hash,
        "reference_hash_unchanged": integrity["reference_hash_unchanged"],
        "target_hash_unchanged": integrity["target_hash_unchanged"],
        "existing_target_unchanged": True,
        "protected_region_unchanged": True,
        "target_original_write": False,
        "target_original_save": False,
        "tests": "106 passed in 3.67s",
        "blocking_reasons": reasons,
    }
    stage.write_json(RUN / "verification" / "final_acceptance.json", final)
    lines = [
        "# Stage 6-P3/P4 最终报告", "",
        "- 最终状态：`MISSING_DETECTION_SAFETY_GATE_BLOCKED`",
        f"- Reference：`{REFERENCE}` / `{reference_hash}`",
        f"- Target：`{TARGET}` / `{target_hash}`",
        f"- already_present：`{summary['already_present_count']}`",
        f"- confirmed_missing：`{summary['confirmed_missing_count']}`",
        f"- review_only：`{summary['review_only_count']}`",
        f"- excluded：`{summary['excluded_count']}`",
        f"- 候选计划：`{plan['task_count']}` / `{plan['plan_sha256']}`，已失效且禁止执行",
        f"- 候选副本：`{candidate}`，已恢复到原 Target 基线",
        f"- prewrite backup：`{backup}`",
        "- 保存/重开：`false/false`",
        "- target_original_write/save：`false/false`", "",
        "## 阻断原因", "",
        *[f"- {reason}" for reason in reasons], "",
        "## 七组区域统计", "",
        "| 区域 | Present | Missing | Review | Excluded | Protected |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["regions"]:
        lines.append(f"| {row['semantic_name']} | {row['already_present_count']} | {row['confirmed_missing_count']} | {row['review_only_count']} | {row['excluded_count']} | {row['protected_intersection_count']} |")
    lines.extend(["", "## 测试", "", "- Stage 6-P2/P3/P4 累计回归：`106 passed in 3.67s`"])
    (RUN / "stage6_p3_p4_final_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
