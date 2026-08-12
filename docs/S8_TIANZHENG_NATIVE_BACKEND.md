# S8 — Tianzheng native object backend

Status: **S8.1 complete** (`S8_1_NATIVE_TDBPIPE_POC_COMPLETE`). No S8 tag yet; the final tag is
reserved for S8.7.

The goal of S8 is to create and durably persist genuine Tianzheng **native** objects. An ordinary
AutoCAD entity dressed up to look like a pipe does not count and is rejected by rule, not by
judgement — see `mcp_nextgen/s8/native_identity.py`.

## Running the Tianzheng environment

Tianzheng must be started through its own launcher. Starting `acad.exe` and hand-loading a couple of
`.arx` modules does **not** produce a Tianzheng runtime and will not register the custom classes.

```
D:\Tangent\TwtT30V1\TGStart.exe
```

No arguments; working directory `D:\Tangent\TwtT30V1`. It spawns `acad.exe` and exits. A correct
session reports `T30天正给排水软件 V1.0公测版 For Autodesk AutoCAD 2026` and loads ~39 Tangent
modules, including `tch_pipewire.arx`, `tch_pipebase.arx` and `twt_pipecmd.arx`.

The plugin reads its auth token from the environment at load time, so inject it into the process
that launches `TGStart.exe`; the child `acad.exe` inherits it.

## What is proven

`TDbPipe` is a real registered ObjectARX class:

```
TDbPipe → TDbPipePrototype → TDbCurveEntity → AcDbCurve
        → AcDbEntity → AcDbObject → AcGiDrawable → AcRxObject
DXF name: TCH_PIPE
```

Creating one through Tianzheng's own command produces three objects — the pipe plus two
`TDbPipeFitting` end nodes — on Tianzheng's auto-created `PIPE-给水` layer.

## Why the creation path is a fixed command

`TDbPipe`'s default constructor is genuinely exported (`??0TDbPipe@@QEAA@XZ`, `tch_pipewire.arx`),
and the pipe modules export thousands of C++ symbols. That surface is nevertheless unusable here:
there are no headers, no import library, no managed wrapper, and no protocol-extension creation
entry. More importantly a bare constructed pipe would carry none of the node linkage and system
state that make it a real Tianzheng object.

So creation goes through Tianzheng's own command, which runs the complete lifecycle:

| | |
|---|---|
| Command | `HZGX` |
| Group | `TWT_PIPECMD` |
| Module | `twt_pipecmd.arx` |
| Interaction | `HZGX` → start point → end point → ENTER |
| Palette | 管线设置 opens **modeless**, so the command line stays scriptable |

### Boundaries of that decision

The command name is a compile-time constant (`NativePipePoc.TianzhengPipeCommand`). Callers supply
two coordinates and nothing else. There is deliberately **no** `run_any_command`, no raw
`SendCommand`, no arbitrary LISP and no request passthrough — a general command-execution interface
is exactly what S8 forbids.

## Plugin operations added

All are on the existing S7 transport and operation whitelist; there is no second server or protocol.

| Operation | Mutating | Purpose |
|---|---|---|
| `diagnostic_query_rxclass` | no | Resolve a runtime class by name from the live process |
| `diagnostic_scan_database` | no | Snapshot model space (handles + runtime classes) |
| `diagnostic_create_native_pipe` | yes | Run the fixed creation command with code-generated points |
| `diagnostic_native_pipe_result` | no | Read the outcome of the queued creation |

Creation is queued rather than executed inline: `Editor.Command` is only usable inside AutoCAD's own
command context, so the work happens in a registered `CommandMethod` and the transport polls for the
result. Blocking the main thread while waiting would deadlock the command it just queued.

One trap worth remembering: AutoCAD's command registration walks *instantiable* types. A
`[CommandMethod]` on a static class is silently never registered and only shows up as
`未知命令` at run time. That is why `NativePipeCommands` exists.

## How a creation is judged

Never by the command reporting success, and never by what appeared on screen.

1. Scan model space before. A fresh Tianzheng `Drawing1` already contains ~10 template objects, so
   an absolute count proves nothing.
2. Run the creation.
3. Scan again and diff on database **handle**.
4. Require at least one new object whose runtime class *is* `TDbPipe` and which derives from
   `AcDbObject`.

Ordinary entities, proxies/zombies, and same-named classes with the wrong ancestry are all rejected.
Extra companion objects are expected and do not affect the verdict.

Properties are reported only when read back from the object itself. `start`/`end`/`length` are
reachable through the `AcDbCurve` interface; `diameter`, `system` and `elevation` are not reachable
from managed code and are recorded as unread rather than echoed from the request. Reading them is
S8.3 work.

## Reproducing

```bash
python scripts/s8_rxclass_probe.py artifacts/s8_tianzheng_native_backend/rxclass_probe_result.json
```

```bash
python scripts/s8_native_pipe_poc.py
```

Both need `TIANZHENG_PLUGIN_TOKEN` and `TIANZHENG_PLUGIN_PORT`, and a live Tianzheng session with
the plugin NETLOADed. Default tests never launch AutoCAD or Tianzheng.

## TianzhengBackend (S8.2)

`mcp_nextgen/s8/tianzheng_backend.py` is a thin layer over the existing S7 transport — not a
rewrite of it. It reuses `job_id`, `operation_id`, `idempotency_key`, structured results and
errors, the capability registry and the plugin's main-thread scheduling.

It declares exactly three capabilities — `create_native_pipe`, `query_native_pipe`,
`validate_native_pipe_identity`. Valves, fittings-as-first-class, equipment, annotation and
network editing are **absent rather than declared-and-broken**.

```
CreateTianzhengPipe (spec: start, end)
  → TianzhengBackend
    → plugin op tianzheng_create_pipe
      → TianzhengPipeCreationAdapter   ← the only place a command name exists
        → fixed HZGX execution
          → database diff
            → native identity validation
```

A creation reports the **primary** object and its **related** objects separately, because one
HZGX yields a `TDbPipe` plus two `TDbPipeFitting` nodes. Idempotency keys off the pipe, but the
fittings are counted too — a replay that held the pipe count steady while doubling the nodes
would still be broken.

## Property access (S8.3)

Every property carries its own source. Nothing is echoed back from the request.

| Property | Source |
|---|---|
| `start`, `end`, `length` | `AcDbCurve` interface on the object |
| `elevation` | Z of the object's start point |
| `diameter` | `NOT_READABLE_WITH_CURRENT_SURFACE` |
| `system` | `NOT_READABLE_WITH_CURRENT_SURFACE` |

`GetDnDiameter`, `GetSysType` and `GetPipeSystemName` exist as native C++ members with no managed
wrapper. XData and the extension dictionary were probed and did not carry them. The layer
Tianzheng assigns (`PIPE-给水`) does encode the system, but it is reported as
`system_layer_indicator` — an indirect hint, deliberately not the `system` property.

**Debt:** reading diameter and system needs a route into the native property surface.

## Persistence round trip (S8.4)

```bash
python scripts/s8_persistence_roundtrip.py
```

create synthetic document → create pipe → snapshot → SaveAs to sandbox → close → reopen from the
exact recorded path → snapshot again → compare.

`reopen` calls `DocumentManager.Open` on the on-disk file after the original was closed, so the
reopened `Database` really is rebuilt from the DWG. The verdict requires the runtime class, the
geometry and every *comparable* property to match. A property that was unreadable on either side
is excluded rather than compared as null-equals-null.

A proxy on the way back is treated as an environment fault, not a destroyed object: it means the
Tianzheng module was not loaded in the reading session. The round trip is only valid inside a
full `TGStart.exe` session.

Handle stability is recorded, but semantic equivalence never rests on the handle alone —
`TianzhengPipeSignature` is native class + geometry + whichever properties were genuinely readable.

## Persistent idempotency (S8.5)

Reuses the S7 in-document store (`TIANZHENG_S7_IDEMPOTENCY`, a Named Objects Dictionary entry
holding an `Xrecord`) — no third idempotency system.

There is no in-memory key registry anywhere in the plugin; `IdempotencyStore` only reads and
writes the NOD. So when a replay after close/reopen resolves to `already_applied`, the record can
only have come out of the DWG file.

On replay the stored handles are **re-resolved and their runtime classes re-read** from the
current database. A record alone is never trusted — if the pipe is gone, creation runs again.

## MCP integration (S8.6)

```
MCP tool → Control Plane dispatcher → S8 route service
        → TianzhengBackend → S7 plugin transport → Tianzheng pipe adapter
```

No second MCP server. Four tools, registered on the same `dispatch_tool` main path:

| Tool | Read-only |
|---|---|
| `cad.tianzheng.capabilities` | yes |
| `cad.tianzheng.create_pipe` | no |
| `cad.tianzheng.query_pipe` | yes |
| `cad.tianzheng.validate_pipe_identity` | yes |

Create accepts `start`, `end`, `job_id`, `document_token`, `operation_id`, `idempotency_key` and
nothing else. The schemas are strict, so an extra `command` field is rejected as `INVALID_PARAMS`
before dispatch, and a test asserts no schema mentions command/lisp/sendcommand/script/keystroke/hzgx.

`NEXTGEN_TOOLS` stays Mock-only; the Tianzheng tools live in `S8_TIANZHENG_TOOLS` and join only
`ALL_DISPATCHABLE_TOOLS`, so the S4 registry self-check is unaffected.

### Handshake

The plugin probes for Tianzheng at start by resolving `TDbPipe` in the runtime class registry —
never from configuration or an environment variable — and reports `tianzheng_loaded`,
`tianzheng_product`, `tianzheng_version`, `tianzheng_runtime_available`,
`tdbpipe_rxclass_available` and `supported_tianzheng_operations`.

A plain AutoCAD session reports `tianzheng_loaded=false`, every `AVAILABLE_SANDBOX_MVP` capability
collapses to `NOT_AVAILABLE`, and creation returns **`TIANZHENG_NOT_LOADED`**. It never falls back
to an ordinary Polyline.

### Error codes

`TIANZHENG_NOT_LOADED`, `TIANZHENG_NATIVE_CLASS_NOT_FOUND`, `TIANZHENG_PIPE_CREATE_FAILED`,
`TIANZHENG_PIPE_NOT_FOUND`, `TIANZHENG_PIPE_NATIVE_IDENTITY_MISMATCH`,
`TIANZHENG_PIPE_PROPERTY_UNAVAILABLE`, `TIANZHENG_PIPE_PERSISTENCE_FAILED`,
`TIANZHENG_PIPE_IDEMPOTENCY_CONFLICT` all survive to the MCP caller. Nothing collapses into
`INTERNAL_ERROR`; an unrecognised code stays visible rather than being flattened.

## Supported / not supported

**Supported:** native `TDbPipe` creation, native identity validation, geometry query,
save/reopen persistence, persistent idempotency, MCP routing.

**Not supported:** reliable diameter read, reliable system read, arbitrary diameter/system
assignment, valve, equipment, annotation, user DWG editing, production write.

HZGX takes diameter and system from Tianzheng's own palette defaults (给水 / DN25 / elevation 0).
Those observed defaults are **not** an API capability: the registry reports
`tianzheng_pipe_diameter_control=NOT_AVAILABLE` and `tianzheng_pipe_system_control=NOT_AVAILABLE`.

This is a native pipe MVP, **not** full Tianzheng water-supply-and-drainage support.

## Final acceptance

```bash
python scripts/s8_final_acceptance.py
```

Enters through `dispatch_tool`. Document lifecycle (create synthetic / save / close / reopen) is an
S7 plugin-transport concern and is not an MCP tool.

## Not yet done

Update/delete, valve/fitting/equipment as first-class operations, and a process-restart replay.
The last one is `PROCESS_RESTART_PERSISTENCE_NOT_AUTOMATED`: `reopen` requires the token's session
id to match the current plugin session and no operation accepts a path, both deliberate S7 safety
properties. The proven boundary is document close + reopen-from-disk.
