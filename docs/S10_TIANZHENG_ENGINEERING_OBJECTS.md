# S10 — Tianzheng native engineering objects

**Final status: `S10_TIANZHENG_ENGINEERING_OBJECTS_CORE_COMPLETE_WITH_BLOCKED_OBJECTS_AND_EXISTING_TEST_DEBT`**

## 1. Executive summary

S10 asked one question of each object family: **can MCP create a genuine Tianzheng native
object, deterministically, without a human at the keyboard?**

The answer differs per family, and those differences are the substance of this stage. Two new
engineering capabilities were added on top of the S9 closed loop, both automated, persistent and
idempotent:

1. **native `TDbPump`**
2. **native `TDbPipe` diameter annotation state**

The existing **native `TDbPipe`** capability remains available. A real multi-object engineering
task — pipe + pump + diameter annotation — passed end to end through planner, validator,
approval, MCP, the real Tianzheng backend, persistence, idempotency and verification.

**Valve** and **active fitting creation** remain explicitly blocked. That is why this is *core
complete with blocked objects* and not "S10 complete".

The recurring mistake this stage exists to prevent is treating *"the runtime class exists"* as
*"we can build one"*. For valves those two statements are opposite.

## 2. S9 baseline

S10 started from `S9-engineering-task-loop-mvp`: an engineering task closed loop
(task → planner → validation → approval → MCP → execution → verification) that could create,
persist and verify one native `TDbPipe`. S10 did not rewrite that loop; it extended the
semantic model, the capability registry and the verifier, and left the planner architecture
intact.

## 3. Native object discovery matrix

| Family | Runtime | DXF | Runtime avail. | Manual creation | Automation | Status |
|---|---|---|---|---|---|---|
| Pipe | `TDbPipe` | `TCH_PIPE` | ✅ | ✅ | ✅ | **VERIFIED** |
| Valve | `TDbPipeValve` | `TCH_PIPEVALVE` | ✅ | ✅ | ❌ | **BLOCKED** |
| Fitting | `TDbPipeFitting` | `TCH_PIPEFITTING` | ✅ | ✅ | ❌ | **ACTIVE_CREATION_NOT_AVAILABLE** |
| Pump | `TDbPump` | `TCH_PUMP` | ✅ | ✅ | ✅ | **VERIFIED** |
| Pipe annotation | carried by `TDbPipe` | `TCH_PIPE` | ✅ | ✅ | ✅ | **VERIFIED** |

Only `automation_available` may become a published capability. The flat `{name: status}` table
the planner consumes is **derived** from this family table (`mcp_nextgen/s10/capabilities.py`),
so the two cannot drift.

## 4. Pipe

| | |
|---|---|
| Runtime / DXF | `TDbPipe` / `TCH_PIPE` |
| Creation | `AVAILABLE_SANDBOX_MVP` |
| Automation | true |
| Persistence | PASS |
| Idempotency | PASS |
| MCP / Planner / Verifier | AVAILABLE |
| **Status** | **VERIFIED** |

## 5. Valve

| | |
|---|---|
| Runtime / DXF | `TDbPipeValve` / `TCH_PIPEVALVE` |
| Runtime available | true |
| Manual native creation | true |
| Automation | **false** |
| Creation command | `FMFJ` |
| Blocker | **`BLOCKED_BY_INTERACTIVE_INPUT_SURFACE`** |
| Persistence / Idempotency | NOT_REACHED |
| Public capability | `NOT_IMPLEMENTED` |
| **Status** | **BLOCKED** |

`FMFJ` holds the input device in its own interactive loop; queued input did not advance it.

**Wording discipline:** a Tianzheng custom jig or sampler is a *supporting hypothesis* for why
this happens. There is no direct evidence of an `FMFJ → TEdJig` linkage, and that linkage is
**not** stated as proven. The blocker names the observed behaviour, not an internal
implementation.

## 6. Fitting

| | |
|---|---|
| Runtime / DXF | `TDbPipeFitting` / `TCH_PIPEFITTING` |
| Runtime available | true |
| `HZGX` endpoint fittings | `AVAILABLE_AS_PIPE_SIDE_EFFECT` |
| Active creation | `NOT_IMPLEMENTED` |
| `DXJT` | `BLOCKED_BY_OBJECT_FAMILY_MISMATCH` |
| `GXLJ` | `BLOCKED_BY_MISSING_PREREQUISITE_CAPABILITY` |
| Prerequisite | programmatic Tianzheng pipe-system control |
| Current pipe-system control | `NOT_AVAILABLE` |
| **Status** | **ACTIVE_CREATION_NOT_AVAILABLE** |

**Native node reuse observed:** two `TDbPipe` sharing the endpoint (1500,0,0) produced **3**
endpoint fittings, not 4 — pipe B contributed only one new `TDbPipeFitting`. Tianzheng reuses
the existing node at a coincident endpoint, so `HZGX` already performs node sharing
automatically. This is evidence about native behaviour; it is **not** an active fitting
capability, and it does not make one available.

A task that merely creates a pipe does **not** require the fitting capability, so ordinary pipe
work is unaffected. A task that asks to insert a fitting deliberately blocks.

## 7. Pump / Equipment

| | |
|---|---|
| Runtime / DXF | `TDbPump` / `TCH_PUMP` |
| Ancestry | `TDbPump` → `TDbEquipment` → `TDbPipeNode` → `TDbEntity` → `AcDbEntity` |
| Creation command | `HZSB` |
| Automation | true |
| Caller-controlled | **`position` only** |
| Not available | rotation, pump type, base size, inlet/outlet elevation, pump height |
| Creation / Query / Persistence / Idempotency | PASS |
| Helper objects | 0 |
| MCP / Planner / Verifier | AVAILABLE |
| **Status** | **VERIFIED** |

```
tianzheng_native_pump_create      = AVAILABLE_SANDBOX_MVP
tianzheng_native_equipment_create = AVAILABLE_SANDBOX_MVP
supported_equipment_types         = ["pump"]
```

The unimplemented fields are absent from the MCP schema entirely. Accepting them would promise
control that does not exist.

## 8. Pipe diameter annotation

| | |
|---|---|
| Semantic capability | Pipe diameter annotation |
| Command | `DGGJ` (单管管径) |
| Interaction profile | `STANDARD_POINT` — a point Tianzheng hit-tests itself |
| **Storage model** | **`MODEL_B_PIPE_OWNED_STATE`** |
| Annotation DBObject created | **none** |
| Target | an existing `TDbPipe` |
| Native state evidence | XData application `TG_PIPELABEL_THICK_SHOW` |
| Entity count | unchanged |
| Automation / Persistence / Idempotency | true / PASS / PASS |
| MCP / Planner / Verifier | AVAILABLE |
| **Status** | **VERIFIED** |

```
tianzheng_pipe_annotation_control   = AVAILABLE_SANDBOX_MVP
tianzheng_pipe_diameter_annotation  = AVAILABLE_SANDBOX_MVP
tianzheng_native_annotation_create  = NOT_APPLICABLE
display_text_read                   = NOT_AVAILABLE
```

Settled evidence, reproduced across three adapter-driven runs, each diffed only after the
command's own lifecycle event:

```
entity count   3 -> 3      new objects []      deleted []
target pipe    xdata_apps      [] -> [TG_PIPELABEL_THICK_SHOW]
               xdata_item_count 0  -> 2
```

`NOT_APPLICABLE` is deliberate and is **not** a synonym for `NOT_IMPLEMENTED`: there is no
annotation entity to create, so "unfinished" would wrongly imply that finishing it is the plan.

`display_text_read` stays `NOT_AVAILABLE`. The DN20 string was confirmed **on screen**; no
native query has been shown to return it, and a screen observation is not an API read
capability.

## 9. Command interaction profiles

Adapter metadata recording what was measured. Nothing dispatches on it; its job is to stop the
next adapter reusing a driver already proven wrong for a given prompt shape.

| Profile | Meaning |
|---|---|
| `STANDARD_POINT` | ordinary point prompt; a queued coordinate is read as a point |
| `STANDARD_SELECTION` | ordinary selection prompt honouring normal selection mechanisms |
| `NATIVE_SELECTION` | selection serviced by Tianzheng itself; managed SelectionSets ignored |
| `INTERACTIVE_SAMPLER` | the command holds the input device in its own loop |
| `MIXED` | more than one of the above in sequence |
| `UNKNOWN` | not yet measured |

| Command | Observed |
|---|---|
| `HZGX` | verified pipe route; two queued coordinates create one pipe plus endpoint fittings |
| `HZSB` | structured placement point, then continued prompting; terminated through the owned document queue |
| `DGGJ` | point-input hit-test; deterministic **after view framing** |
| `GJBZ` | native/entity selection surface, not consumable through the current managed SelectionSet path |
| `FMFJ` | interactive input surface, not consumable through current deterministic command automation |
| `DXJT` | selection-based, but the wrong pipe family |
| `GXLJ` | selection-based, but a prerequisite system control is unavailable |

Two `DGGJ` properties the adapter must respect, both measured:

1. **It hit-tests against what is on screen.** A point exactly on the pipe axis still misses if
   the pipe is not in the current view, so the adapter frames the target first.
2. **Terminator order matters.** After a hit only its own Enter-default closes it; but an Enter
   arriving after it has already closed repeats the command. The sequence is
   command → point → Enter → ESC.

`GJBZ` and `DGGJ` are both diameter annotation and do **not** share an input surface. That is
exactly why each command is pre-tested rather than assumed to behave like its neighbour.

## 10. Command termination findings

UI keyboard ESC is **not** a reliable cancellation mechanism for a Tianzheng command's own
prompt loop.

For fixed commands suited to document-queue driving, a controlled `0x03` termination sequence
makes the command report `CommandEnded` / `CommandCancelled`, return to idle, and allow a
graceful shutdown.

**Do not generalise this.** S10 proved the command contracts differ: `DGGJ` has its own
order-sensitive sequence, and `FMFJ` is not consumable at all. There is no single Tianzheng
termination contract.

No public `send_escape`, `send_key`, `cancel_any_command`, `run_command`, `send_command` or
`execute_lisp` surface exists, and none may be introduced to work around this.

### `Editor.Command` is blocking

`Editor.Command` does not return until the command it launched completes. A Tianzheng command
that stops in its own input loop therefore never yields control, and **code placed after the
call cannot terminate that same command**. Adapters drive such commands through the document
queue instead. This is a constraint to respect — not a reason to introduce multi-threaded or
arbitrary command machinery.

## 11. Capability registry

| Capability | Status |
|---|---|
| `tianzheng_native_pipe_create` | `AVAILABLE_SANDBOX_MVP` |
| `tianzheng_native_pipe_query` / `_identity_validation` / `_persistence` / `_idempotency` | `AVAILABLE_SANDBOX_MVP` |
| `tianzheng_native_pump_create` | `AVAILABLE_SANDBOX_MVP` |
| `tianzheng_native_equipment_create` | `AVAILABLE_SANDBOX_MVP` |
| `tianzheng_native_equipment_query` | `AVAILABLE_SANDBOX_MVP` |
| `tianzheng_pipe_annotation_control` | `AVAILABLE_SANDBOX_MVP` |
| `tianzheng_pipe_diameter_annotation` | `AVAILABLE_SANDBOX_MVP` |
| `tianzheng_native_valve_create` | `NOT_IMPLEMENTED` |
| `tianzheng_native_fitting_create` | `NOT_IMPLEMENTED` |
| `tianzheng_native_annotation_create` | `NOT_APPLICABLE` |

`supported_equipment_types = ["pump"]`.

A family capability does not cover every member of the family:
`tianzheng_native_equipment_create` being available says only that *some* equipment can be
built. A `water_tank` request blocks with `PLAN_BLOCKED_BY_UNSUPPORTED_EQUIPMENT_TYPE` and is
**never** rerouted to the pump adapter.

## 12. MCP

| Tool | Input beyond the common envelope |
|---|---|
| `cad.tianzheng.create_pump` | `document_token`, `position` |
| `cad.tianzheng.query_pump` | `document_token`, `handle` |
| `cad.tianzheng.annotate_pipe_diameter` | `document_token`, `target_pipe_handle` |
| `cad.tianzheng.native_capabilities` | — (read-only; answers even with no backend configured) |

All schemas are strict. There is no `command`, `command_text`, `script`, `lisp`, `keystroke`,
`raw`, selection-keyword, arbitrary `ObjectId` or file-path field anywhere, and the Tianzheng
command name never crosses the boundary.

The annotation tool takes **no `pick_point`**: the adapter derives the point from the target
pipe's own geometry, because only it knows what the hit test requires.

## 13. Planner integration

The planner speaks **capabilities**; `HZGX`, `HZSB` and `DGGJ` appear in no plan. It emits:

- `PipeIntent` → create native pipe
- `EquipmentIntent(pump)` → create native pump
- `AnnotationIntent(pipe_diameter)` → modify native pipe annotation state

The storage model does not leak upward: the plan asks for the pipe to be annotated, not for
XData to be written. `EquipmentIntent` and `AnnotationIntent` were promoted from S9's
`ReservedIntent` extension point; the planner architecture was not rewritten.

## 14. Validator architecture

`EngineeringPlanValidator` keeps its own `KNOWN_BACKEND_CAPABILITIES` whitelist, so an
operation naming a capability the system does not recognise never reaches a backend.

**Defect found by the first real S10.6 run.** S10.5 added the pump and annotation operations to
the planner without extending that whitelist, so every real multi-object plan was rejected as
`INVALID` before it could execute:

```
op-eq1-create-native-equipment names unknown backend capability 'tianzheng_native_pump_create'
op-eq1-validate-identity        names unknown backend capability 'tianzheng_native_equipment_query'
op-an1-annotate-pipe-diameter   names unknown backend capability 'tianzheng_pipe_diameter_annotation'
```

- **Root cause:** two independent lists of the same fact — the planner's emitted capabilities
  and the validator's accepted capabilities — maintained by hand.
- **Impact:** the integration was broken end to end while the entire test suite was green. The
  mock end-to-end test drove the planner and the executor but never the validator, so nothing
  caught it until a real run.
- **Fix:** the S10 portion of the whitelist is **derived from the authoritative registry**
  rather than retyped, removing the class of drift.
- **Still enforced:** an invented or unknown capability is rejected exactly as before.
- **Regression test:** `tests/s10/test_plan_validation_capabilities.py` asserts every capability
  the planner can emit is one the validator accepts.

This is the most important architecture hardening in S10.

## 15. Result verifier

Two rules read the drawing back; neither trusts an execution result.

- **`PumpNativeIdentityRule`** — `runtime_class = TDbPump`, `dxf = TCH_PUMP`,
  `native_identity_confirmed`, position within tolerance. A backend that returns success having
  inserted an `AcDbBlockReference` makes the **task** fail.
- **`PipeAnnotationStateRule`** — re-queries the target `TDbPipe` and requires
  `TG_PIPELABEL_THICK_SHOW` in its actual XData. It deliberately does **not** hunt for an
  annotation object, which would fail a correct drawing, and an ordinary `AcDbText` reading
  "DN20" does not satisfy it.

## 16. S10.6 real multi-object engineering task

Run `s10_6_20260813T163121Z`, full Tianzheng session, entered at the **task layer**.

| | logical | handle | class |
|---|---|---|---|
| pipe | `intent-pipe` | `9D` | `TDbPipe` / `TCH_PIPE` |
| pump | `intent-pump` | `64E` | `TDbPump` / `TCH_PUMP` |
| annotation | target `intent-pipe` | resolved → `9D` | `TDbPipe` |

```
histogram   {TDbPipe: 1, TDbPipeFitting: 2, TDbPump: 1}
pipe 9D     xdata = [TG_PIPELABEL_THICK_SHOW]
verifier    ENGINEERING_TASK_PASS   15/15
```

All seven handle-binding assertions passed, including `annotation_target_is_not_the_pump` and
`equipment_bucket_holds_only_the_pump`. The pump was deliberately placed at (4500,1000,0), well
off the pipe and its axis, so a target mix-up could not have produced a plausible drawing.

## 17. Persistence

Save → close → reopen the same sandbox DWG:

```
pipe   TDbPipe   survived
pump   TDbPump   survived
histogram unchanged
annotation TG_PIPELABEL_THICK_SHOW still on handle 9D — the ORIGINAL target
```

## 18. Idempotency

Same `task_id`, same `plan_id`, same operation keys, whole task resubmitted:

| operation | result |
|---|---|
| pipe | `already_applied` |
| pump | `already_applied` |
| annotation | `already_applied` |

Histogram unchanged; annotation state present before and after and not duplicated. Model B has
no annotation object to count, so the invariant is that the target pipe carries the state
exactly once.

## 19. Safety

**Final acceptance run (S10.6):**

```
user DWG read/write   0 / 0        user DXF read/write   0 / 0
production write      0            sandbox outside write 0
FILEDIA  baseline 1 → 0 for NETLOAD only → verified 1 at end
force termination     0            acad.exe at end       0
license / Tianzheng binary / registry modification   0
Trusted Paths persistent change 0   SECURELOAD weakened  false
NETLOAD               加载一次 only
```

**Historical discovery runs** did include force terminations — during valve and `GJBZ`
investigation, where a Tianzheng command held its own prompt loop and no owned cancel applied.
Those are recorded in the per-run artifacts. It would be wrong to state "S10 force_termination
= 0" for the whole stage; the correct statement is that the **final acceptance run** was clean
and the historical deviations are recorded.

### Development environment note

Plugin staging is an **assembly set, not a single DLL**. `tz.dll` alone is insufficient: its
`TianzhengCadPlugin.Protocol` and `TianzhengCadPlugin.Transport` assemblies must be staged
alongside it. `NETLOAD` accepts the path without an error and the assembly silently fails to
load otherwise — `TZPLUGINSTART` returning `未知命令` is what identifies this. A silent NETLOAD
is a failed NETLOAD. Staged binaries under `C:\p` are never committed.

## 20. Known limitations

- Everything is **sandbox only**. No user DWG is read or written; production write is unavailable.
- Pump exposes `position` only.
- Pipe diameter is not readable through a native query; `display_text_read` is `NOT_AVAILABLE`.
- Pipe `diameter` and `system` remain `NOT_READABLE_WITH_CURRENT_SURFACE` (native C++ members
  with no managed wrapper).
- Only one annotation kind (`pipe_diameter`) has an adapter.
- Only one equipment type (`pump`) is supported.

## 21. Blocked capabilities

| Capability | Status | Reason |
|---|---|---|
| Valve creation | `NOT_IMPLEMENTED` | `BLOCKED_BY_INTERACTIVE_INPUT_SURFACE` (`FMFJ`) |
| Active fitting creation | `NOT_IMPLEMENTED` | `DXJT` family mismatch; `GXLJ` missing prerequisite |
| Annotation entity creation | `NOT_APPLICABLE` | no annotation entity exists (Model B) |
| Unsupported equipment types | blocked | `supported_equipment_types = ["pump"]` |
| Pipe diameter / system read | `NOT_AVAILABLE` | no managed surface |

## 22. Future work

Recommended next stage: **S11 — Real engineering DWG read-only understanding.**

Read-only comprehension of real engineering drawings, with no write path, before any
copy-on-write or user-DWG modification is considered. Valve and active fitting automation would
need a different input-surface strategy than anything S10 established, and should not be
reopened without new evidence.

**Not implemented, and not to be started without explicit approval.**
