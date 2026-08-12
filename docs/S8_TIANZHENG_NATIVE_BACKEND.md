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

## Not yet done

Persistence across save/close/reopen, idempotency, a full `TianzhengBackend`, MCP tool exposure,
update/delete, and valve/fitting/equipment as first-class operations.
