# S9 — Engineering task closed loop

Status: **`S9_ENGINEERING_TASK_CLOSED_LOOP_MVP_COMPLETE_WITH_EXISTING_TEST_DEBT`**.

S5–S8 answered *"can the system draw?"*. S9 answers a different question: **does the system know
what to draw, where, in what order — and can it prove the result satisfies the task?**

## Architecture

```
raw user intent              Layer A   free text, recorded, never executed
   ↓ normalization
EngineeringTaskSpec          Layer B   structured, reviewable, still not executable
   ↓ planner (+ context + semantic model + capability snapshot)
EngineeringOperationPlan     Layer C   produced only after validation
   ↓ dry run → validator → approval
EngineeringTaskExecutor
   ↓ existing MCP cad.tianzheng.* tools
TianzhengBackend → S7 plugin → AutoCAD / Tianzheng
   ↓ post-execution re-query
EngineeringResultVerifier → PASS / FAILED / BLOCKED / PARTIAL
```

## Task contract

`EngineeringTaskSpec` carries `task_id`, `task_type`, `discipline`, `intent`, source/target
context, constraints, required capabilities, expected outputs, verification requirements,
approval level, metadata and schema version.

Constraints are split by concern: `GeometricConstraint`, `CapabilityConstraint`,
`SafetyConstraint`, `ExecutionConstraint`, `VerificationConstraint`. A task that sets
`allow_production_write` or `allow_user_dwg_write` is rejected at construction.

## Context and semantic model

`DrawingContextSnapshot` is what the planner may know: bounds, layers, entities, anchors,
obstacles, existing native objects, source type, confidence, warnings. It exposes no COM object,
no `DBObject` and no `ObjectId` — a test asserts that.

`EngineeringSemanticModel` is the engineering layer: `AnchorPoint`, `Zone` (allowed/forbidden),
`RouteIntent`, `VerificationRule`, plus reserved `ValveIntent` / `EquipmentIntent` /
`AnnotationIntent` for S10.

The separation is the point:

```
PipeRouteIntent   ≠   Polyline   ≠   TDbPipe
```

`RouteIntent → planner → EngineeringOperation → backend selection → TDbPipe`. S10 can add
`ValveIntent → TDbValve` without touching the planner.

## Planner

Provider-neutral: `EngineeringPlanner` is a Protocol. `MockEngineeringPlanner` is deterministic
and is what the default tests use — no LLM, no network. An agent-backed planner would implement
the same interface and its output would pass through the same validator.

It is **capability-aware**. Before emitting anything it checks the live capability snapshot, and
if something is missing it returns a blocked plan with `operations=[]`:

```
PLAN_BLOCKED_BY_MISSING_CAPABILITY   missing_capabilities: ["tianzheng_valve"]
```

It never downgrades a native requirement. If `TDbPipe` is required and the capability is absent,
the answer is `REQUIRED_NATIVE_CAPABILITY_UNAVAILABLE` — not a quietly substituted Polyline.
Ordinary CAD fallback happens only when a task sets `allow_ordinary_cad_fallback=true`.

Every operation carries structured reason codes: `why_this_operation`,
`what_requirement_it_satisfies`, `what_constraint_it_obeys`, `what_result_is_expected`.

## Dry run, validation, approval

Dry run performs no CAD work at all. `EngineeringPlanValidator` re-checks schema, capabilities,
safety, dependency ordering, idempotency keys, geometry and expected counts, returning
`PASS` / `PASS_WITH_WARNINGS` / `BLOCKED` / `INVALID` with errors, warnings, missing
capabilities, unsafe operations and geometry conflicts.

Geometry checks in the MVP: segment vs forbidden rectangle (touching counts), route inside the
allowed region, zero-length segments, duplicate segments, endpoints against the task.

An operation naming a capability the system has never heard of — say `create_tianzheng_valve` —
is rejected here and never reaches a backend.

Approval reuses the existing control-plane sandbox level. No second approval system, and S9 does
not open production write, user DWG write or L4.

## Execution

`EngineeringTaskExecutor` orchestrates only. It walks the plan, honours `depends_on` (a skipped
dependency skips its dependents rather than silently continuing), and calls an
`EngineeringGateway` backed by the existing MCP tools. There is no `EngineeringDirectComBackend`.

Task-level idempotency rides on the existing operation-level mechanism rather than being a fourth
system: the planner derives each key deterministically from `task_id`, so resubmitting the same
task produces the same keys and the S8 in-document record makes it a no-op.

## Verification

The part that matters. `EngineeringResultVerifier` takes the task, plan, execution result and a
**post-execution snapshot re-queried from the database**, and checks:

- structural — operation count, no unexpected failure, correct backend
- native identity — runtime class really is `TDbPipe`, not a proxy or ordinary entity
- geometry — start/end/length read back from the object, within tolerance
- constraints — the **built** route re-checked against forbidden/allowed zones
- persistence — survived save/close/reopen
- idempotency — replay created no duplicate pipe and no duplicate fittings

`backend returned success` is never sufficient. A test proves that a run where every operation
succeeds but returns `AcDbLine` fails verification.

## MCP tools

| Tool | Read-only | Notes |
|---|---|---|
| `cad.engineering.plan` | yes | task → plan + dry run, touches no CAD |
| `cad.engineering.validate_plan` | yes | deterministic validation |

Execution is deliberately not a tool: the executor is a client of `cad.tianzheng.*`, so exposing
it would make the dispatcher re-enter itself. The schemas are strict and accept a task descriptor
— never free text, never an operation list — so the planner's capability gate cannot be bypassed.

## S10 boundary

Reserved intents exist; backends do not. `tianzheng_valve`, `tianzheng_equipment` and
`tianzheng_annotation` are `NOT_IMPLEMENTED`, and a task needing them is blocked with the
capability named. That rejection is the contract S10 will fulfil — S10 adds native objects behind
the *existing* planner rather than redesigning it.

## Known limitations

- **One straight route per task.** The S8 adapter creates one straight pipe per call, so the
  scenario is a straight A→B run that constraints genuinely gate. Multi-segment Tianzheng
  networks are future work; S8 was not refactored for S9.
- **Diameter and system** come from Tianzheng's palette defaults — neither readable nor settable.
- **Synthetic sandbox only.** User DWG write and production write remain unavailable.
- Document lifecycle (create synthetic / save / close / reopen) is an S7 plugin-transport concern
  with no MCP tool.
- Context adapters for PDF- and image-derived drawings are architectural placeholders; the MVP
  runs on structured and synthetic-DWG context.

## What S9 does not claim

Not a complete engineering-design AI. No automatic code compliance, hydraulic calculation, pipe
sizing, pump selection, full pipe network, BIM, PDF reproduction or construction-drawing
production.

What it does claim: a constrained water-supply engineering task can be turned into a structured
plan, validated and approved, executed through MCP against real AutoCAD/Tianzheng, and then
automatically verified against the original task.

## Reproducing

```bash
python scripts/s9_final_acceptance.py
```

Needs `TIANZHENG_PLUGIN_TOKEN` / `TIANZHENG_PLUGIN_PORT` and a live `TGStart.exe` session with
the plugin NETLOADed. Default tests launch AutoCAD, Tianzheng, COM and the network zero times.
