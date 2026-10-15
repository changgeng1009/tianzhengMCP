> Privacy cleanup: Historical report retained for context. Personal identifiers and machine-specific paths were anonymized; paths are illustrative and referenced private inputs are not distributed. Original outcomes were not rerun or revalidated by this privacy cleanup, and are not evidence of synthetic-sample or current real-CAD acceptance.

# Stage 4 MVP Integration and Repeatability Acceptance

- status: PASS_MVP_END_TO_END_REPEATABLE
- run_id: stage4_20260711_094721
- reference: D:\ExampleWorkspace\天正\artifacts\stage3_1_r1\stage3_1_r1_20260711_002112\copies\reference_working_copy.dwg
- target: E:\SampleDrawings\target_sample.dwg
- baseline reproduced: true
- existing / missing / review / ambiguous: 95 / 353 / 10 / 0
- approved / attempted / successful / persisted: 16 / 16 / 16 / 16
- second pass safe tasks: 0
- idempotency passed: true
- source hashes unchanged: true
- stage5_allowed: true
- stage5_executed: false
- production_d1_allowed: false

## Safety
- source_reference_opened: false
- source_target_opened: false
- source_reference_saved: false
- source_target_saved: false
- source_modified: false
- analysis_copies_saved: false
- saveas_used: false
- copyobjects_used: false
- explode_used: false
- sendcommand_used: false
- lisp_executed: false
- netload_used: false
- tianzheng_command_executed: false
- tdb_modified: false
- automatic_fallback_used: false
- new_autocad_instance_created: false
- automatic_unattended_alignment: false
- stage5_executed: false
- production_d1_allowed: false
- autocad_connected: true
- analysis_copies_opened: true
- repair_sandbox_opened: true
- repair_sandbox_saved: true
- repair_sandbox_reopened: true

## Tests
- stage4_and_stage3_3: 65 passed in 0.57s
- stage3_2_stage3_1_backend_safety_stage1: 151 passed in 1.00s
- full_pytest: 1197 passed, 1 warning in 5.11s
