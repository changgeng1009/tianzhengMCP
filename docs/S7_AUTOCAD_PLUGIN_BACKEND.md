# S7 — AutoCAD .NET Plugin Backend (synthetic sandbox MVP)

Status: `S7_AUTOCAD_PLUGIN_BACKEND_MVP_COMPLETE`
Capability: `autocad_plugin_backend = AVAILABLE_SANDBOX_MVP`

MCP can drive an in-process AutoCAD 2026 plugin through the existing unified backend
architecture and an authenticated local Protocol 2.0, executing supported ordinary CAD
operations inside a job-owned synthetic document, with transaction, save/close/reopen,
persistence and idempotency all verified.

**This is a synthetic sandbox MVP.** It is not production-ready, does not support Tianzheng,
does not modify user drawings, and covers only a subset of S6 operations.

---

## 1. Architecture

```
AI Agent
  └─ MCP Server
       └─ Control Plane / Approval
            └─ Capability Router            (Mock | Real-COM | Plugin)
                 └─ ICadBackend
                      ├── MockCadBackend            (pure memory)
                      ├── RealAutoCadComBackend     (COM automation, best-effort)
                      └── AutoCadPluginBackend      (S7)
                            └─ PluginTransportClient
                                 └─ Protocol 2.0 over 127.0.0.1 TCP
                                      └─ AutoCAD Managed Plugin (net8.0-windows)
                                           └─ Application.Idle main-thread dispatcher
                                                └─ Job-owned synthetic document
                                                     └─ DocumentLock
                                                          └─ Transaction
                                                               └─ AutoCAD Database
```

MCP never sees a socket, a frame, or a plugin document token. The wire protocol is an
implementation detail of `AutoCadPluginBackend`.

## 2. Component responsibilities

| Component | Responsibility |
|---|---|
| `plugin/src/TianzhengCadPlugin.Protocol` | Framing, DTOs, validation, geometry, sandbox path policy. `net8.0`, no AutoCAD reference. |
| `plugin/src/TianzhengCadPlugin.Transport` | Loopback listener, token auth, operation queue, router, ownership policy, plan parsing/hash. `net8.0`, no AutoCAD reference. |
| `plugin/src/TianzhengCadPlugin` | `IExtensionApplication`, `Application.Idle` dispatcher, `CadOperationExecutor`, document factory, idempotency store. `net8.0-windows`, references acmgd/acdbmgd/accoremgd. |
| `mcp_nextgen/backends/plugin_transport.py` | The only Python module that speaks the wire protocol. |
| `mcp_nextgen/backends/autocad_plugin.py` | `ICadBackend` implementation + S6→plugin mapping + error taxonomy. |
| `mcp_nextgen/backends/capability_router.py` | Selects Mock/COM/Plugin; always reports `actual_backend_used`. |
| `mcp_nextgen/s7/plugin_route.py` | The sanctioned MCP structured route. |

## 3. Protocol 2.0

Framing: `[4-byte unsigned big-endian payload length][UTF-8 JSON]`. The declared length is
validated against a 1 MiB cap **before** any body byte is read. Reading "JSON until the
socket closes" is never used.

`1.0.0 → 2.0.0` was a MAJOR bump because `readiness` changed from string to boolean — a
breaking change for any 1.x reader. 1.x requests are rejected with
`INCOMPATIBLE_PROTOCOL_VERSION` rather than served a response they cannot parse.

**Request** (all required unless noted): `protocol_version`, `request_id`, `job_id`,
`operation_id`, `operation_type`, `document_context`, `parameters`, `idempotency_key`,
`expected_capability`, `dry_run`, `timeout_ms`, `metadata`, `session_nonce` (required
except for the handshake). Unknown fields are rejected.

**Response** always carries: `success`, `error_code`, `stage`, `request_id`, `operation_id`,
`entity_ids`, `handles`, `created_count`, `modified_count`, `skipped_count`,
`idempotency_status`, `warnings`, `duration_ms`, `plugin_version`, `capability_version`,
`retryable`, `transaction_status`, `document_status`, `plugin_state`, `sanitized_message`.

## 4. Authentication and session

The token travels **only** in a connection-level auth frame — never in a business request.
`PluginRequest` has no `auth_token` field, so a token can never reach business metadata or
the operation queue.

Until the handshake succeeds no business validation runs at all: an unauthenticated caller
receives a fixed, starved response and cannot enumerate fields, operations or state. A bad
token and a malformed frame are indistinguishable.

A fresh `session_id` and `session_nonce` are generated on every plugin start. `capabilities`
discloses the nonce; `health` does not. Every non-handshake operation must present a
matching nonce. A nonce from a previous session cannot match.

Token rules: injected only (`TIANZHENG_PLUGIN_TOKEN` / `TIANZHENG_PLUGIN_TOKEN_FILE`),
minimum 32 characters, SHA-256 digest retained, constant-time comparison, redacted in all
logs and reprs, never committed.

## 5. Threading

The transport runs on thread-pool threads and contains **zero** AutoCAD API calls. It only
enqueues. `MainThreadDispatcher` drains the queue from `Application.Idle`, which AutoCAD
raises on its own main thread. Every response carries a runtime marker
(`executing_thread`, `initialize_main_thread`, `on_main_thread`, `idle_ticks`) so the
threading claim is evidenced, not asserted.

## 6. Document ownership

A document becomes writable **only** by being registered, and the only caller that registers
is the plugin's own `create_synthetic_document`. Therefore a user's open drawing is never
registered, has no token, and cannot be addressed. `MdiActiveDocument` confers nothing;
there is no fallback to the active document anywhere in the write path.

Tokens are 256-bit random, bound to session + job + database fingerprint, and die with the
session. Every write calls `Resolve()`, which fails closed on: missing token, unknown token,
session mismatch, job mismatch, closed document, dead document, fingerprint mismatch.

## 7. Transaction and batch semantics

One batch = one `DocumentLock` = one AutoCAD `Transaction`. `all_or_nothing` is the only
supported mode and is enforced by the transaction itself: on failure `Commit()` is simply
never called, so AutoCAD discards every change including entities created by earlier
operations in the same batch.

Semantic validation (degenerate line, non-positive radius, vertex count) deliberately runs
**inside** the transaction so a failure aborts a real transaction — a pre-pass that rejected
the batch before opening a transaction could never demonstrate rollback.

## 8. Result semantics

`success == true` means **the effect is committed**. It does not mean "ran without raising".
When a batch aborts, every operation reports `success=false`; operations that had executed
are marked `entity_status=ROLLED_BACK`, `execution_status=EXECUTED_THEN_ROLLED_BACK`, with
all handles, entity ids and counts cleared. The Python mapping preserves this: a rolled-back
operation never becomes an S6 success.

## 9. Python backend

`AutoCadPluginBackend` implements `ICadBackend`:

| ICadBackend | Plugin |
|---|---|
| `get_capabilities` | live handshake → per-S6-operation `BackendCapability` |
| `list_documents` | only documents this backend created |
| `open_document` | `create_synthetic_document`, or reopen if previously closed |
| `inspect_document` | cached S6 identity |
| `list_entities` | `query_entities` |
| `execute_batch` / `execute_cad_plan` | one S6 plan → one `batch_execute` |
| `save_document` | `save` (backend-generated sandbox file name) |
| `close_document` | `close` |
| `reopen_document` | `reopen` (exact sandbox path recovered from the plugin's own record) |

**Unknown outcome rule:** if a write is sent but no response arrives, the client raises
`PLUGIN_EXECUTION_OUTCOME_UNKNOWN` and never auto-resends — re-sending could duplicate
entities. Only read-only calls recover from a stale nonce by reconnecting.

## 10. Operation mapping

| S6 operation | Plugin | Status |
|---|---|---|
| `ENSURE_LAYER` | `create_layer` | supported |
| `CREATE_LINE` | `create_line` | supported |
| `CREATE_CIRCLE` | `create_circle` | supported |
| `CREATE_POLYLINE` | `create_polyline` | supported |
| `QUERY_ENTITIES` | `query_entities` | supported |
| `SAVE/CLOSE/REOPEN_SYNTHETIC_DOCUMENT` | `save`/`close`/`reopen` | supported (lifecycle) |
| `CREATE_ARC/RECTANGLE/TEXT/MTEXT/BLOCK_*`, `MOVE/COPY/ROTATE/SCALE/DELETE_ENTITY`, `ENSURE_TEXT_STYLE`, `ENSURE_DIMENSION_STYLE` | — | **unsupported** |

A plan containing **any** unsupported operation is rejected in Python **before anything is
sent** with `UNSUPPORTED_OPERATION_BY_PLUGIN_BACKEND`, so no partial execution can occur.

## 11. MCP routing

The sanctioned path is `MCP tool → validated structured request → S6 CadOperationPlan →
approval/control plane → CapabilityRouter → AutoCadPluginBackend → plugin`. There is no
`plugin_send`, `raw_socket`, `send_autocad_command`, `plugin_request` or arbitrary-operation
tool, and a unit test asserts none is exported.

The router preserves Mock and COM. It reports `actual_backend_used` on every decision, and
when the plugin is unavailable or cannot support a plan it is simply not selected — it is
never made to look as though the plugin ran work another backend performed.

## 12. Save / close / reopen

Save is a **lifecycle stage**, never part of a batch's atomicity claim. The caller supplies
no path: the backend generates a bare file name and the plugin resolves it against a sandbox
root taken from its own launch configuration (`TIANZHENG_PLUGIN_SANDBOX_ROOT`).

`SandboxPathPolicy` rejects separators, drive letters, `..`, UNC, alternate data streams,
reserved device names, non-`.dwg` extensions and anything whose canonicalised path is not
directly inside the root. Only the bare file name crosses the wire.

Close refuses an unsaved document, moves MDI focus to another already-open document (AutoCAD
cannot close the active document), then discards. Reopen re-opens the exact recorded path,
issues a **new** token and permanently invalidates the old one.

## 13. Persistent idempotency

Records live in the drawing's Named Objects Dictionary under `TIANZHENG_S7_IDEMPOTENCY`, as
an `Xrecord` holding the plan hash, created count and handles. Because they are written with
the **same transaction** as the entities, entities and idempotency record commit together or
abort together — a rolled-back batch can never leave a record claiming success.

The plan hash is recomputed by the plugin from the parsed payload (excluding batch id and
document token), so the same key with a different payload is detected and refused with
`IDEMPOTENCY_CONFLICT` **without executing**.

Verified: create → save → close → reopen → replay same key ⇒ `ALREADY_APPLIED`, created 0,
entity total unchanged; same key + changed radius ⇒ `IDEMPOTENCY_CONFLICT`, nothing executed.

## 14. Capability matrix

| Capability | Value |
|---|---|
| `readiness` / `readiness_state` | `true` / `AVAILABLE_SANDBOX_ENTITY_MVP` |
| `supported_entity_types` | `line`, `circle`, `polyline` |
| `transaction_support` / `batch_support` | `true` / `true` (`all_or_nothing`) |
| `dry_run_support` / `document_ownership_support` | `true` / `true` |
| `persistence_support` | `true` |
| `idempotency_support` | `AVAILABLE_SANDBOX_MVP` |
| `tianzheng_support` | `NOT_AVAILABLE` |
| production / user-DWG write | forbidden |

## 15. COM vs Plugin

| | Real-COM | Plugin |
|---|---|---|
| Atomic batch | **No** — COM has no database transaction; best-effort only | **Yes** — one AutoCAD Transaction |
| Rollback | not available | real abort, prior entities discarded |
| Persistent idempotency | not available | in-document, transaction-atomic |
| Threading | out-of-process automation | in-process, main-thread dispatch |

This is a genuine capability difference and is reported as `CAPABILITY_DIFFERENCE`, never
smoothed over. The router refuses COM when `require_atomic_batch` is set.

## 16. Build

Requires the **.NET 8 SDK** (the runtime alone cannot compile) and AutoCAD 2026.

```bash
dotnet build plugin/TianzhengCadPlugin.sln -c Release
dotnet test plugin/tests/TianzhengCadPlugin.Tests/TianzhengCadPlugin.Tests.csproj -c Release
```

AutoCAD reference DLLs resolve from a configurable directory (`-p:AutoCadManagedDir=…`,
`ACAD_MANAGED_DIR`, local `AutoCadDllPath.props`, or the fallback default). They are
referenced with `Private=false`, are never copied to output, and are never committed.

## 17. NETLOAD development workflow

1. Start AutoCAD 2026 with `TIANZHENG_PLUGIN_TOKEN`, `TIANZHENG_PLUGIN_PORT` and
   `TIANZHENG_PLUGIN_SANDBOX_ROOT` in its environment.
2. Run `NETLOAD` and select
   `plugin/src/TianzhengCadPlugin/bin/Release/net8.0-windows/TianzhengCadPlugin.dll`.
3. At the SECURELOAD prompt choose **Load once** — never "Always load", which would persist
   a trusted-path change.

Read-only operator commands: `TZPLUGINSTATUS`, `TZPLUGINSTART`, `TZPLUGINSTOP`.

The plugin never modifies SECURELOAD, trusted paths or the registry.

## 18. Sandbox testing

Default `pytest` starts no AutoCAD. The real integration is opt-in via
`scripts/s7_real_acceptance.py`, which drives the official backend path (not a diagnostic
probe) and writes sanitized evidence to `artifacts/s7_plugin/`.

All CAD writes are confined to `TIANZHENG_PLUGIN_SANDBOX_ROOT`. Evidence records only bare
file names and digests, never absolute user paths or tokens.

## 19. Known limitations

- Entity coverage is **line, circle, polyline** only — no arc, rectangle, text, mtext, block,
  or any move/copy/rotate/scale/delete.
- Synthetic sandbox only. User DWG/DXF access is forbidden by construction.
- No Tianzheng: no TDbPipe, no Tianzheng ObjectARX/Managed API, no Tianzheng objects.
- Loopback only. No remote transport exists and none is safe to assume.
- The plugin DLL is unsigned; each NETLOAD requires an operator "Load once" decision.
- Save targets a single flat sandbox directory; no nested layout.
- Single-node, single-session; no concurrent-batch or soak testing.
- **Not production ready.**

## 20. Security boundaries

- Binds `127.0.0.1` only; non-loopback peers refused; the Python client fails closed on any
  non-loopback host and deliberately rejects `localhost` (DNS-resolvable).
- Injected token, constant-time compare, redacted, never committed.
- Strict operation whitelist. No command/eval/LISP/script/passthrough field exists in the
  accepted schema, so arbitrary execution cannot be expressed by a valid request.
- Unknown fields, unknown operations, missing fields, incompatible versions, oversized
  frames and out-of-range timeouts are all rejected.
- Path traversal, UNC, absolute paths and non-DWG extensions are rejected by
  `SandboxPathPolicy`, then re-verified against the canonicalised root.
- Responses carry no token, secret, absolute user path, Autodesk stack trace or drawing
  content — only sanitized messages and error codes.
