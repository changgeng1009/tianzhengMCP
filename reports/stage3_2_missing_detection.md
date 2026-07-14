# Stage 3.2 Missing Detection

- status: PASS_MISSING_DETECTION_EVIDENCE_READY
- alignment_contradiction: false
- evidence_mode: conditional_geometry_dominant
- existing / missing / review / ambiguous: 95 / 353 / 10 / 0
- high_confidence_ordinary_object_count: 16
- tdb_manual_task_count: 337
- repair_task_draft_count: 16
- source_hashes_unchanged: true
- stage3_3_allowed: true
- stage3_3_entered: false
- production_d1_allowed: false

## Safety
- autocad_connected: false
- dwg_opened: false
- dwg_saved: false
- entities_created: false
- entities_modified: false
- entities_deleted: false
- sendcommand_used: false
- lisp_executed: false
- netload_used: false
- tianzheng_command_executed: false
- repair_task_executed: false
- stage3_3_entered: false
- production_d1_allowed: false

## Tests
- stage3_2_targeted: 10 passed in 0.49s
- stage3_3_targeted: 28 passed in 0.69s
- backend_safety_regression: 65 passed in 1.18s
- stage3_1_series_regression: 53 passed in 0.84s
- stage1_regression: 21 passed in 0.45s
- full_pytest: 1157 passed, 1 warning in 5.29s
- warning: PyPDF2 deprecation only
