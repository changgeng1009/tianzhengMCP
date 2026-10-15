# External run configuration for historical CAD workflows

The public source no longer bundles private sample hashes, fixed translations, region bindings, or cloned dependency handles. These are runtime inputs, not acceptance evidence.

## Setup and safety

Store your JSON configuration **outside this repository** and set `TIANZHENG_RUN_CONFIG` to its absolute path. A config inside the public repository is rejected. Do not commit private config, input drawings, or derived output. The loader does not connect to CAD, authorize writes, grant permissions, or relax any existing safety/acceptance threshold. Supplying config is not user authorization for CAD writes.

Missing configuration, missing required parameters, malformed hashes/transforms, and incomplete/duplicate region bindings stop the dependent workflow. Stage 4/5 requires both original input hashes and its translation before any dependent function can proceed. Actual input hashes are compared before copy/CAD actions in the checked execution entries. Source integrity, immutable-plan and acceptance gates remain mandatory.

Old module constants remain `None` only to preserve imports for offline algorithm users; do not read them as active run configuration. Consumers obtain values through `require_parameter`. Existing tests now supply original synthetic configurations explicitly.

## Complete synthetic configuration shape

The example below is original synthetic data and cannot validate any historical drawing. Its hash strings are digests of descriptive synthetic labels, **not bundled real inputs**. To run a legitimate task, provide independently verified hashes for your authorized local inputs and frozen plan files, measured/approved transforms and region bindings. A wrong but well-formed hash still fails the existing input comparison. Do not replace a failed expected hash with the current hash merely to pass a gate.

For a Stage 4/5-only run, only the two `mcp.orchestration.stage4_mvp.*` keys and `stage45.translation` are needed from this shape. Other workflows require the corresponding hash group; P2.6 requires both binding maps and both translations before output begins. Shared hash keys across scripts deliberately identify the same frozen input/plan.

```json
{
  "schema_version": 1,
  "parameters": {
    "mcp.acceptance.stage1_final_acceptance.expected_source_sha256": "943ec3ffe56eb5b4e6cf649553c0759796b0617904d0b6df1a3ea3f4cbf39f73",
    "mcp.orchestration.stage4_mvp.reference_sha256": "b40b9c6c2b52363c1e850cf228677f2162fffad1fe8a214faf1b6bd4eb155e98",
    "mcp.orchestration.stage4_mvp.target_sha256": "021a28b71a9d3e1e86a2e5bb15e01ddabc455adc8dc59ecf44f9c1b49e047979",
    "mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256": "795b43a8894f481ce9c6e1332d30130eafec2bd3a92b649cb32fd474ec24cc0d",
    "mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_file_sha256": "1b728588db8b956b3b6bf63c7f7c49bbcaf6125a755faa2fe2f112501cfceb1b",
    "mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256": "f30cd78d5528054596950420337895216aafa34e4f7aac5cfe392be4ef9fff9a",
    "mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256": "87e3ba4aa0142a41b412362ea172031f4a7f62dc023ca0876c8671b6558c8f7c",
    "scripts.finalize_stage6_p3_p4_blocked.expected_reference": "720a532e2eeb47214d7c4ac2c5cbac5f18dbe6489293cc53e37c61dc0096b20a",
    "scripts.finalize_stage6_p3_p4_blocked.expected_target": "d273f4aed024ba515066e6791f55441120bdd68949e4baa9b6109b7db7cd9746",
    "scripts.run_stage6_p1_accelerated_r4.expected_batch_plan_file_sha256": "9214ac9fdd1441fa4214a45a693855f20d097bcba4bb5f19b3ea775fecaff30e",
    "stage45.translation": [
      12,
      24,
      0
    ],
    "stage6_p2_6.actual_bindings": {
      "basement": [
        "synthetic_ref_0",
        "synthetic_target_0"
      ],
      "first_floor": [
        "synthetic_ref_1",
        "synthetic_target_1"
      ],
      "floors_6_to_16": [
        "synthetic_ref_2",
        "synthetic_target_2"
      ],
      "floor_19_and_roof": [
        "synthetic_ref_3",
        "synthetic_target_3"
      ],
      "water_tank_and_tank_roof": [
        "synthetic_ref_4",
        "synthetic_target_4"
      ],
      "domestic_water_and_drainage_system": [
        "synthetic_ref_5",
        "synthetic_target_5"
      ],
      "fire_hydrant_and_sprinkler_system": [
        "synthetic_ref_6",
        "synthetic_target_6"
      ]
    },
    "stage6_p2_6.old_bindings": {
      "basement": [
        "synthetic_ref_0",
        "synthetic_target_0"
      ],
      "first_floor": [
        "synthetic_ref_1",
        "synthetic_target_1"
      ],
      "floors_6_to_16": [
        "synthetic_ref_2",
        "synthetic_target_2"
      ],
      "floor_19_and_roof": [
        "synthetic_ref_3",
        "synthetic_target_3"
      ],
      "water_tank_and_tank_roof": [
        "synthetic_ref_4",
        "synthetic_target_4"
      ],
      "domestic_water_and_drainage_system": [
        "synthetic_ref_5",
        "synthetic_target_5"
      ],
      "fire_hydrant_and_sprinkler_system": [
        "synthetic_ref_6",
        "synthetic_target_6"
      ]
    },
    "stage6_p2_6.basement_translation": [
      12,
      24
    ],
    "stage6_p2_6.floors_translation": [
      12,
      24
    ]
  }
}
```

## Key types

- `mcp.acceptance.stage1_final_acceptance.expected_source_sha256`: `sha256`
- `mcp.orchestration.stage4_mvp.reference_sha256`: `sha256`
- `mcp.orchestration.stage4_mvp.target_sha256`: `sha256`
- `mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_embedded_sha256`: `sha256`
- `mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_plan_file_sha256`: `sha256`
- `mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_reference_sha256`: `sha256`
- `mcp.orchestration.stage6_p1_accelerated_tdb_r5.expected_target_sha256`: `sha256`
- `scripts.finalize_stage6_p3_p4_blocked.expected_reference`: `sha256`
- `scripts.finalize_stage6_p3_p4_blocked.expected_target`: `sha256`
- `scripts.run_stage6_p1_accelerated_r4.expected_batch_plan_file_sha256`: `sha256`
- `stage45.translation`: `translation3`
- `stage6_p2_6.actual_bindings`: `bindings`
- `stage6_p2_6.old_bindings`: `bindings`
- `stage6_p2_6.basement_translation`: `translation2`
- `stage6_p2_6.floors_translation`: `translation2`

`sha256` is 64 lowercase hexadecimal characters. Translations are finite numeric arrays of length 2 or 3 (booleans are invalid). Binding maps contain exactly the seven semantic keys shown; each pair is `[reference_region_id, target_region_id]`, with unique IDs on each side.

## PoC dependency evidence

Fresh component PoC results include `dependency_mappings`, with `task_id`, `reference_handle`, `target_handle`, and `object_name`. These come from the existing unique type/geometry matching of observed PoC records, not hardcoded sample handles. The finalizer requires an exact one-to-one cover of `approved_dependency_task_ids`, approved source handles, known created target handles, and `TDbPipe` type. Missing or partial mappings block finalization. This checks evidence consistency; it is not independent authentication of a supplied JSON report. Old reports without mapping evidence must be re-established through an authorized run rather than filled with invented records.

## Verification limits

Synthetic unit tests validate configuration rejection and pre-copy/pre-connection gates. They do not establish real AutoCAD or Tianzheng acceptance. Historical one-shot report writers such as `_f1_f3.py` are not executed or used as test evidence by this cleanup; their unverified PASS behavior is a separate issue.
