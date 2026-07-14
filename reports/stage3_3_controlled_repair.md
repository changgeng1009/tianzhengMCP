# Stage 3.3 Controlled Repair

- status: PASS_CONTROLLED_REPAIR_PERSISTED
- stage3_3_entered: true
- approved / rejected: 16 / 347
- attempted / successful / skipped / failed: 16 / 16 / 0 / 0
- created_handles: ['14EF', '14F0', '14F1', '14F2', '14F3', '14F4', '14F5', '14F6', '14F7', '14F8', '14F9', '14FA', '14FB', '14FC', '14FD', '14FE']
- geometry_match: true
- layer_match: true
- sandbox_saved: true
- sandbox_closed_and_reopened: true
- persisted_task_count: 16
- source_hashes_unchanged: true
- real_sample_repair_completed: true
- stage4_allowed: true
- stage4_executed: false
- production_d1_allowed: false

## Safety
- source_reference_opened: false
- source_target_opened: false
- source_reference_saved: false
- source_target_saved: false
- source_modified: false
- saveas_used: false
- copyobjects_used: false
- explode_used: false
- sendcommand_used: false
- lisp_executed: false
- netload_used: false
- tianzheng_command_executed: false
- tdb_modified: false
- existing_entities_modified: false
- existing_entities_deleted: false
- automatic_fallback_used: false
- production_d1_allowed: false
- stage4_executed: false
- autocad_connected: true
- new_autocad_instance_created: false
- repair_sandbox_opened: true
- repair_sandbox_saved: true
- repair_sandbox_reopened: true

## Tests
- stage3_2_targeted: 10 passed in 0.34s (tests only; Stage 3.2 not re-executed)
- stage3_3_targeted: 33 passed in 0.37s
- backend_safety_regression: 67 passed in 0.82s
- stage3_1_series_regression: 53 passed in 0.68s
- stage1_regression: 21 passed in 0.34s
- full_pytest: 1162 passed, 1 warning in 4.58s
- warning: PyPDF2 deprecation only
