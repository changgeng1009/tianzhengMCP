> redacted / not_rerun: Historical artifact redacted for redistribution. Captured drawing geometry, native object properties, handles and input fingerprints are withheld. This cleanup did not connect to CAD or rerun/revalidate the original assertions. Historical outcomes are not current acceptance or synthetic-run evidence.

Geometry cleanup: redacted / not_rerun. Original drawing-derived coordinates were removed; remaining historical outcomes are not current acceptance evidence.

# Stage 3.1-R2 Geometry-Only Alignment Acceptance

## 1. Acceptance Amendment
- previous_status: PARTIAL_LOW_CONFIDENCE
- acceptance_rule_changed: true
- evidence_mode: GEOMETRY_DOMINANT
- text_anchor_absence_expected: true

## 2. Anchor Independence
- raw / deduplicated / independent: 23 / 22 / 14
- independent anchor types: {"unique_block_insertion": 1, "rectangle_center": 7, "long_line_midpoint": 6}
- all_from_one_block_reference: true
- exclusion_reasons: {"derived_corner_shares_line_entity": 8, "identical_coordinate_pair": 1}

## 3. Spatial Coverage
- occupied / total cells: 3 / 4
- coverage ratio: 0.75
- maximum cluster ratio: 0.5
- passed: true

## 4. Independent Validation
- deterministic holdouts passed: true
- leave-one-type-out passed: true
- leave-one-spatial-cell-out passed: true

## 5. Directional Geometry Overlap
- target_to_reference_overlap: 1.0
- reference_to_target_overlap: 0.679487
- orientation_agreement: 1.0
- line_length_agreement: 1.0
- directional_overlap_score: 1.0

## 6. Transform and Decision
[redacted: drawing-derived numeric geometry/evidence removed; not_rerun]
- rotation_radians: 0.0
- scale: 1.0
- confidence: 0.806478 (threshold 0.72)
- final_status: PARTIAL_GEOMETRY_EVIDENCE_CORRELATED
- stage3_2_allowed: false
- blockers: ["all independent anchors originate from one top-level BlockReference pair"]

## 7. Safety
- autocad_connected: false
- dwg_opened: false
- dwg_rescanned: false
- safe_copy_created: false
- dwg_saved: false
- entities_created: false
- entities_modified: false
- entities_deleted: false
- sendcommand_used: false
- lisp_executed: false
- netload_used: false
- tianzheng_command_executed: false
- repair_task_generated: false
- stage3_2_executed: false
- production_d1_allowed: false

## 8. Tests
- stage3_1_r2_targeted: 14 passed in 0.27s (final rerun)
- stage3_1_r1_regression: 21 passed in 0.48s
- stage3_1_regression: 18 passed in 0.52s
- backend_safety_regression: 64 passed in 0.87s
- stage1_regression: 21 passed in 0.39s
- total: 138 passed
- static_forbidden_call_audit: no matches
- report_schema_safety_assertions: passed
