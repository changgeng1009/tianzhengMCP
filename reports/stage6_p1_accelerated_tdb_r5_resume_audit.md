# R5 Resume Evidence Audit — Read-Only

**Phase**: STAGE6-P1-ACCELERATED-TDB-R5  
**Audit type**: RESUME_EVIDENCE_REPAIR_READ_ONLY  
**Date**: 2026-07-12  
**Status**: **R5_RESUME_BLOCKED**

---

## 1. Audit Scope

This audit assesses whether the R4 execution checkpoint data is sufficient to
safely resume TDb component processing in an R5 accelerated executor.  All
checks are read-only: no AutoCAD connection, no DWG operations, no R4
interruption.

## 2. Frozen Plan Verification

| Field | Value |
|-------|-------|
| frozen_plan_task_count | 4343 |
| ordinary task count | 3245 |
| TDb task count | 1098 |
| Plan SHA256 (file) | 2196a39fb9328323... (verified) |
| Plan SHA256 (embedded) | 574cf4c00c345333... (verified) |

## 3. Checkpoint Data Assessment

### 3.1 Checkpoint File Inventory

- Total checkpoint files: 103
- Batch checkpoints (Stage 1 ordinary): 33 files (batch_0001 through batch_0033)
- Component checkpoints (Stage 2 TDb): 69 files (component_0001 through component_0069)
- Initial checkpoint: 1 file (0000_initial.json)

### 3.2 Checkpoint Data Format

**Every single checkpoint file is count-only.**  Each file contains exactly
five fields:

```json
{"checkpoint": "component_0056", "ts": "2026-07-12T22:34:46.767153", "completed": 3818, "skipped": 0, "calls": 72}
```

No checkpoint file anywhere contains:
- `completed_task_ids` (task-level identity)
- `pending_task_ids`
- `source_to_target_handle_map`
- `created_handles`
- Task IDs of any kind
- Source or target handles
- ModelSpace scan snapshots
- Document entity counts

### 3.3 CopyObjects Trace Data

The `copyobjects_calls/` directory contains **zero files**.  No per-call trace
data was recorded.  IDPair data, handle mappings, and per-call task attribution
are all absent.

### 3.4 Component Completion Ambiguity

Of 69 component checkpoints with recorded data:

| Category | Count | Description |
|----------|-------|-------------|
| Fully identified | 46 | delta == component_size: all tasks definitely completed |
| Partial/ambiguous | 2 | delta < component_size: individual task completion unknown |
| Zero-delta (no work) | 21 | component processed but no tasks newly completed |

The two partially-matched components are:

1. **stage6_p1_reference_region_0001_component_0001**: 501 tasks, delta=+498
   (3 tasks cannot be attributed to completed or pending)
2. **stage6_p1_reference_region_0004_component_0001**: 10 tasks, delta=+7
   (3 tasks cannot be attributed)

Without task-level data, these 6 tasks have unknown completion status.

## 4. Exact Task Set Analysis

### 4.1 Completed Tasks

- **exact_completed_task_ids**: 3322 (precisely identified)
  - Ordinary: 3245 (all confirmed via batch plan + 33 batch checkpoints)
  - TDb: 77 (from 46 fully-matched components, delta == component_size)
- **ambiguously_completed_by_count**: 505 tasks in 2 partial components
  whose exact identity cannot be determined

### 4.2 Pending Tasks

- **exact_pending_task_ids**: 1021 (all tasks not in exact_completed)
  - This includes the 6 ambiguous tasks from partial components
  - TDb total pending: 516 (3827 count suggests 582 TDb completed)
  - Actual gap: 6 tasks in unknown state

### 4.3 Hard Acceptance Criteria

| Criterion | Result | Status |
|-----------|--------|--------|
| completed ∩ pending = 0 | 0 overlap | PASS |
| completed ∪ pending = 4343 | 4343 | PASS |
| missing_task_ids = [] | 0 missing | PASS |
| duplicate_task_ids = [] | 0 duplicates | PASS |
| partial_or_ambiguous_component_ids = [] | 2 ambiguous | **FAIL** |
| ordinary_completed_count = 3245 | 3245 | PASS |
| resume_safe = true | false | **FAIL** |

## 5. Blocking Reasons

1. **COUNT_ONLY_CHECKPOINT**: All 103 checkpoint files store only
   (checkpoint, ts, completed, skipped, calls).  No task_id, handle, or
   source-target mapping data exists in any checkpoint.  R5 cannot
   distinguish which specific tasks completed vs. pending.

2. **EMPTY_COPYOBJECTS_TRACES**: The copyobjects_calls directory is empty.
   Zero IDPair records, zero handle mappings, zero per-call task attribution.
   R5 cannot verify handle uniqueness or prevent duplicate creation.

3. **PARTIAL_COMPONENTS**: Component_0001 (501 tasks, 498 delta) and
   component_0007 (10 tasks, 7 delta) have ambiguous completion.  Without
   task-level data, R5 could either skip tasks that were already done or
   re-execute tasks that would create duplicates.

4. **R4_ACTIVE**: R4 execution is actively writing to the work file.  A
   safe snapshot cannot be taken during active execution.  The work file
   SHA256 cannot be computed or verified.

5. **NO_DOCUMENT_SNAPSHOT**: No initial or intermediate ModelSpace scan
   data exists in checkpoints.  Document identity and entity count cannot
   be established for resume verification.

6. **NO_HANDLE_DATA**: created_target_handles and source_target_map are
   not recorded.  R5 cannot prevent handle collisions, duplicate clones,
   or wrong-region writes due to missing mapping data.

## 6. Required Remediation

For R5 resume to be safe, R4 must be configured to record:

### In each checkpoint file:
```json
{
  "checkpoint": "component_0056",
  "ts": "...",
  "completed": 3818,
  "skipped": 0,
  "calls": 72,
  "completed_task_ids": ["stage6_p1_...", ...],
  "pending_task_ids": ["stage6_p1_...", ...],
  "skipped_task_ids": [],
  "source_to_target_handle_map": {"A4FFB": "NEW001", ...},
  "created_handles": ["NEW001", ...]
}
```

### In each CopyObjects trace file:
```json
{
  "call_id": "copyobjects_0001",
  "task_ids": ["stage6_p1_...", ...],
  "primary_pairs": [{"source_handle": "A4FFB", "target_handle": "NEW001", "IsCloned": true}],
  "completed_task_ids": ["stage6_p1_...", ...]
}
```

### Work file snapshot:
After R4 reaches a safe boundary or completes, save a read-only copy of the
work file with its SHA256 recorded in the checkpoint.

## 7. Corrected Startup Instructions

When R4 has written task-level checkpoint data and reached a safe boundary:

1. Wait for R4 to reach a safe component boundary and release execution
2. Save the current R4 work file in AutoCAD
3. Close and reopen the file to verify integrity
4. Record the SHA256 of the saved work file
5. Copy the verified saved file to a new R5 work file
6. Verify the copy SHA256 matches the recorded checkpoint SHA256
7. Only then launch R5 with `--work-file <path>`
8. R5 must verify document identity == checkpoint identity before executing

**Do NOT** copy from the prewrite backup — the prewrite does not contain
R4's completed work.

## 8. Conclusion

**Status: R5_RESUME_BLOCKED**

R5 cannot safely resume TDb execution from the current R4 checkpoint data.
The count-only checkpoint format provides no task-level or handle-level
identity data.  Until R4 is configured to write rich checkpoint data
including completed_task_ids, source_to_target_handle_map, and per-call
CopyObjects traces, R5 acceleration is unsafe and must not proceed.

The frozen plan, batch plan, and component dependency plan are all intact
and verified.  Once R4 produces task-level checkpoint data, R5 can
immediately build a safe accelerated resume plan.
