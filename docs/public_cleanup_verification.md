# Current-tree cleanup verification

Base: 1da7a302879f71ac25f9bcfbc68eee7c45699b9f. This is a current-tree privacy/material cleanup, not a history rewrite or production certification.

## Changes

Removed 7 real DWG inputs, one reference PDF, five reference images and the real-input scenario. Added an original synthetic scenario with no bundled CAD input. Replaced identity-bearing paths in scripts/configuration/reports; retained functional Python logic. Removed third-party title-block quotations from historical reports. Replaced the previous 119-command compilation with six original fictional, execution-disabled fixtures and empty not-scanned discovery records.

## Test environment and results

Cloud Linux, Python 3.12; pytest 9.1.1, mcp 1.30.0, PyPDF2 3.0.1, pydantic 2.14.1. The newest MCP 2.x was incompatible with the pre-existing test guard; no guard was disabled. These environment dependencies were not added to repository files.

Command: `python -m pytest -q -m 'not real_dwg and not external_integration and not autocad_required and not tianzheng_required and not com_required and not production_only'`

- Unmodified base: 1654 passed, 25 failed.
- Cleaned tree: 1722 passed, 17 failed. All remaining failed test IDs also failed at the base. No new failure IDs. Fixture-oriented parameterizations changed, so collected test counts are not identical.
- External skill suite: 52 passed, 12 failed both before and after; identical failed IDs.
- Registry-focused suite: 67 passed.
- Synthetic PDF extraction/alignment: 9 passed, using a PDF generated inside the test temporary directory.
- Changed Python files preserve program structure except explicit sample/test updates. Two pre-existing syntax errors remain in `_fix_proxy.py` and `mcp_service/server.py`; this cleanup does not repair unrelated business code.
- `git diff --check` passed.

## Remaining default-suite failures

- `tests/acceptance/test_stage3_3_controlled_repair.py::test_frozen_stage3_3_resume_keeps_all_sixteen_task_ids`
- `tests/acceptance/test_stage4_mvp.py::test_stage3_baseline_semantic_task_set_is_stable`
- `tests/alignment/test_d4_6_2_anchor_json_loader.py::TestD462Loader::test_load_sample`
- `tests/alignment/test_d4_6_2_anchor_json_loader.py::TestD462Loader::test_runner_calibrates`
- `tests/bridge/test_r7_persistence_report_schema.py::TestPersistenceSchema::test_r6_persistence_loaded`
- `tests/config_driven/test_defaults_merge.py::test_req_021_allowlist_is_intersection`
- `tests/integration/test_d1_persistence_policy.py::TestD1PersistencePolicy::test_sandbox_save_policy_exists`
- `tests/integration/test_d1_persistence_policy.py::TestD1PersistencePolicy::test_source_never_saved`
- `tests/integration/test_d1_persistence_policy.py::TestD1PersistencePolicy::test_persistence_successful`
- `tests/mcp_service/test_h0_pipeline_status.py::TestH0Status::test_state_exists`
- `tests/mcp_service/test_h0_pipeline_status.py::TestH0Status::test_state_fields`
- `tests/mvp/test_mvp_pdf_region_extractor.py::test_render_pdf_page_to_png`
- `tests/mvp/test_mvp_pdf_region_extractor.py::test_crop_pdf_region_handles_missing_bbox_as_page_crop`
- `tests/safety/test_d4_6_2_no_execution.py::TestD462NoExec::test_runner_no_production`
- `tests/safety/test_r7_source_protection.py::TestSourceProtection::test_r6_no_source_save`
- `tests/safety/test_r7_source_protection.py::TestSourceProtection::test_r5_1_no_source`
- `tests/test_tianzheng_interface_dry_run_engine.py::TestNoRealCADAccess::test_no_autocad`

These include absent historical artifacts, environment/tool dependencies and existing consistency assertions. No real CAD/COM validation was performed.

## Privacy and scope

Known identity variants, student filename identifiers and original machine paths were rescanned with zero remaining matches. This is not a guarantee against unknown personal information. Historical report geometry, object handles and native-property tables were subsequently redacted; these reports are explicitly not rerun and cannot establish current acceptance. The source rights of removed material are not established by anonymization. No blanket MIT license is added in this cleanup. Old commits and other branches/tags remain unchanged and may retain removed material.

## Diagnostic sample hardening

Real-machine diagnostic examples were additionally replaced by original empty synthetic structures, explicitly marked not_run. The original template document name was replaced with a neutral synthetic name. No real diagnostic geometry is represented as newly verified synthetic evidence.

## Subsequent geometry redaction

Two captured CAD model exports were replaced with an original single-line fixture; their derived diff and execution plan are empty not-run schemas. Seven manual diagnostic exporters now write to ignored local artifacts rather than overwrite public examples. Historical report coordinates and native object evidence were removed while preserving historical result labels with explicit redacted/not_rerun notices. Those labels are not fresh test results.

The legacy `_f1_f3.py` report generator can emit PASS labels without executing corresponding checks; it was not executed and its generated labels are not used as cleanup validation evidence. This independent behavior issue remains outside the cleanup.

## External run configuration validation

Private historical translations, input fingerprints and region bindings now require explicit external run configuration. Missing or invalid configuration fails closed before affected copy/CAD operations. Dependency handles come from complete one-to-one PoC mapping evidence, rather than bundled historical identifiers. Evidence self-consistency is checked; this is not authentication of a forged external evidence file.

Configuration and pre-write gate tests: 36 passed, including six affected entry points with missing configuration, missing translation and incorrect hashes; copy/CAD-connect spies were not called. Model/diagnostic fixture and export guards: 19 passed. Report-redaction checks: 5 passed. Two historical-report schema checks and the page-level PDF task test now use explicitly original offline fixtures; this does not restore real-machine integration coverage.
