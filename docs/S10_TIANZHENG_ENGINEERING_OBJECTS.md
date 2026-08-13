# S10 — Tianzheng native engineering objects

S10 asked one question of each object family: **can MCP create a genuine Tianzheng native
object, deterministically, without a human at the keyboard?**

The answer differs per family, and the differences are the substance of this document. The
recurring mistake this stage exists to prevent is treating *"the runtime class exists"* as
*"we can build one"*. They are not the same claim, and for valves they are opposite.

## Status by object family

| Family | Runtime class | DXF | Status |
|---|---|---|---|
| Pipe | `TDbPipe` | `TCH_PIPE` | **VERIFIED** |
| Valve | `TDbPipeValve` | `TCH_PIPEVALVE` | **BLOCKED_BY_INTERACTIVE_INPUT_SURFACE** |
| Fitting | `TDbPipeFitting` | `TCH_PIPEFITTING` | **ACTIVE_CREATION_NOT_AVAILABLE** |
| Pump (equipment) | `TDbPump` | `TCH_PUMP` | **VERIFIED** |
| Pipe diameter annotation | carried by `TDbPipe` | `TCH_PIPE` | **VERIFIED** — `MODEL_B_PIPE_OWNED_STATE` |

## The three-layer capability model

A single boolean cannot describe an object family honestly, so the registry
(`mcp_nextgen/s10/capabilities.py`) records three:

| Family | `runtime_available` | `manual_creation_available` | `automation_available` |
|---|---|---|---|
| Pipe | ✅ | ✅ | ✅ |
| Valve | ✅ | ✅ | ❌ |
| Fitting | ✅ | ✅ | ❌ (side-effect only) |
| Pump | ✅ | ✅ | ✅ |
| Pipe annotation | ✅ | ✅ | ✅ |

Only `automation_available` may become a published capability. The flat `{name: status}` table
the planner consumes is **derived** from this table, so the two cannot drift apart.

**Valve is the cautionary case.** `TDbPipeValve` resolves, a human can place one through
Tianzheng's UI, and every attempt to drive `FMFJ` from managed code stalls in its interactive
input surface. Publishing "valve capability available" because the class exists would be a lie
that only surfaces in a real drawing.

**Fitting is the subtle case.** Endpoint fittings genuinely appear — but only as a *side
effect* of `HZGX` creating a pipe. `DXJT` rejects `TDbPipe` outright (an object-family
mismatch, not an input-surface problem) and `GXLJ` needs a prerequisite capability that does
not exist. So there is no way to insert a fitting deliberately, and a task that asks for one
blocks. A task that merely creates a pipe does **not** require the fitting capability.

## Published capability registry

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

`NOT_APPLICABLE` is deliberate and is not a synonym for `NOT_IMPLEMENTED`: there is no
annotation entity to create, so "unfinished" would wrongly imply that finishing it is the plan.

A family capability does not cover every member of the family. `tianzheng_native_equipment_create`
being available says only that *some* equipment can be built; a `water_tank` request blocks
with `PLAN_BLOCKED_BY_UNSUPPORTED_EQUIPMENT_TYPE` and is **never** rerouted to the pump adapter.

## Pipe diameter annotation is not entity creation

Settled S10.4 evidence, reproduced across three adapter-driven runs and taken only after the
command's own lifecycle event:

```
entity count      3 -> 3        new objects: []      deleted: []
target TDbPipe    xdata_apps      [] -> [TG_PIPELABEL_THICK_SHOW]
                  xdata_item_count 0  -> 2
```

`DGGJ` creates **no object**. It writes XData onto the `TDbPipe`, and the pipe draws its own
label — Tianzheng's own application name, `TG_PIPELABEL_THICK_SHOW`, says so. This is
`MODEL_B_PIPE_OWNED_STATE`: a **modified-object** operation.

Consequences that are enforced in code, not merely documented:

- the MCP tool is `cad.tianzheng.annotate_pipe_diameter`, never `create_annotation_entity`;
- the verifier re-reads the **pipe** and checks its XData. A rule that hunted for an annotation
  `DBObject` would fail on a *correct* drawing;
- an ordinary `AcDbText` reading "DN20" does **not** satisfy the rule, however similar it looks
  on screen;
- `display_text_read` stays `NOT_AVAILABLE`. The DN string was confirmed on **screen**; screen
  confirmation is not an API read capability, and the two are kept apart.

## Command interaction profiles

Adapter metadata, recording what was measured. Nothing dispatches on it; its job is to stop the
next adapter from reusing a driver already proven wrong for a given prompt shape.

| Command | Label | Profile | Automatable |
|---|---|---|---|
| `HZGX` | 绘制管线 | `STANDARD_POINT` | ✅ |
| `HZSB` | 绘制水泵 | `MIXED` | ✅ (owned cancel) |
| `DGGJ` | 单管管径 | `STANDARD_POINT` | ✅ |
| `GJBZ` | 管径标注 | `NATIVE_SELECTION` | ❌ |
| `FMFJ` | 阀门附件 | `INTERACTIVE_SAMPLER` | ❌ |
| `DXJT` / `GXLJ` | — | `NATIVE_SELECTION` | ❌ |

`GJBZ` and `DGGJ` are both diameter annotation and do **not** share an input surface: `GJBZ`
asks for an entity multi-selection (it ignored a managed `SelectionSet`, and read a typed
coordinate as a crossing-window corner), while `DGGJ` asks for a single point it hit-tests
itself. That is precisely why each command is pre-tested rather than assumed to behave like its
neighbour.

Two properties of `DGGJ` the adapter must respect, both found by measurement:

1. **It hit-tests against what is on screen.** A point lying exactly on the pipe axis still
   misses if the pipe is not in the current view, so the adapter frames the target first.
2. **Terminator order matters.** After a hit, only its own Enter-default closes it; but an
   Enter arriving after it has already closed (the miss case) repeats the command. The queued
   sequence is therefore command → point → Enter → ESC.

### `Editor.Command` is blocking

`Editor.Command` does not return until the command it launched completes. A Tianzheng command
that stops in its own input loop therefore never yields control, and **code placed after the
call cannot terminate that same command**. Adapters drive such commands through the document
queue instead. This is a constraint to respect — not a reason to introduce multi-threaded or
arbitrary command machinery.

## MCP surface

| Tool | Input beyond the common envelope |
|---|---|
| `cad.tianzheng.create_pump` | `document_token`, `position` |
| `cad.tianzheng.query_pump` | `document_token`, `handle` |
| `cad.tianzheng.annotate_pipe_diameter` | `document_token`, `target_pipe_handle` |
| `cad.tianzheng.native_capabilities` | — (read-only, answers even with no backend) |

All schemas are strict. There is no `command`, `command_text`, `script`, `lisp`, `keystroke`,
`raw`, selection-keyword, arbitrary `ObjectId` or file-path field anywhere, and the Tianzheng
command name never crosses the boundary.

The annotation tool takes **no** `pick_point`: the adapter derives the point from the target
pipe's own geometry, because only it knows what the hit test requires.

Pump fields that are *not implemented* — rotation, pump type, base size, inlet/outlet elevation,
pump height — are **not exposed**. Accepting them would promise control that does not exist.

## Planner and verifier

The planner speaks **capabilities**; `HZGX`, `HZSB` and `DGGJ` appear in no plan. It emits
`PipeIntent → create native pipe`, `EquipmentIntent(pump) → create native pump`, and
`AnnotationIntent(pipe_diameter) → modify native pipe annotation state`. The storage model does
not leak upward: the plan asks for the pipe to be annotated, not for XData to be written.

Two verification rules read the drawing back, never the execution result:

- **`PumpNativeIdentityRule`** — `runtime_class = TDbPump`, `dxf = TCH_PUMP`,
  `native_identity_confirmed`, position within tolerance. A backend that returns success having
  inserted an `AcDbBlockReference` makes the **task** fail.
- **`PipeAnnotationStateRule`** — re-queries the target `TDbPipe` and requires
  `TG_PIPELABEL_THICK_SHOW` in its actual XData. No new object is expected, and ordinary text
  does not count.

## Scope

Everything above is **sandbox only**. No user DWG is read or written, production write is not
available, and the default test suite launches no AutoCAD, Tianzheng, COM, network or LLM.
