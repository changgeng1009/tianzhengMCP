# AutoCAD Managed .NET Plugin (S7)

In-process AutoCAD 2026 plugin backend for the Tianzheng CAD MCP interface.

> **Stage: S7.2 — synthetic-sandbox entity MVP.**
> Verified against a real AutoCAD 2026 session: the plugin creates its own job-owned
> synthetic document, takes a `DocumentLock`, runs **one** AutoCAD `Transaction` per batch
> on the main thread, creates layers/lines/circles/polylines, queries them back out of the
> database, and enforces `all_or_nothing` by aborting the real transaction.
>
> **Not implemented:** save, close, reopen, persistence, persistent idempotency, any other
> S6 entity type or modify/delete operation, the Python backend, MCP routing, Tianzheng.
> This is a synthetic sandbox MVP — **not** production-safe.

## Layout

| Project | TFM | AutoCAD ref | Purpose |
|---|---|---|---|
| `src/TianzhengCadPlugin.Protocol` | `net8.0` | none | Framing, request/response DTOs, validation, error model |
| `src/TianzhengCadPlugin.Transport` | `net8.0` | none | Loopback TCP listener, token auth, operation queue, router |
| `src/TianzhengCadPlugin` | `net8.0-windows` | acmgd / acdbmgd / accoremgd | `IExtensionApplication`, main-thread dispatcher |
| `tests/TianzhengCadPlugin.Tests` | `net8.0` | none | Isolated unit tests (no AutoCAD) |

The AutoCAD-coupled project is deliberately thin, so that framing, validation, auth,
queueing and routing are all unit-testable without AutoCAD installed.

## Prerequisites

- **AutoCAD 2026** (managed API `acmgd.dll` / `acdbmgd.dll` / `accoremgd.dll`, v25.1.60.0.0, `net8.0`)
- **.NET 8 SDK** — required to build. The .NET 8 *runtime* alone is not enough.
  Verify with `dotnet --list-sdks`; if it prints nothing, install the SDK from
  <https://dotnet.microsoft.com/download/dotnet/8.0>.

## Configuring the AutoCAD DLL path

Reference assemblies are resolved from a configurable directory — never a single
hardcoded path — in this order:

1. `dotnet build -p:AutoCadManagedDir="E:\AutoCAD 2026"`
2. environment variable `ACAD_MANAGED_DIR`
3. local `plugin/AutoCadDllPath.props` (copy from `AutoCadDllPath.props.sample`; git-ignored)
4. fallback default `E:\AutoCAD 2026`

The AutoCAD DLLs are referenced with `Private=false`: they are **not** copied to the
plugin output and **must never** be committed to the repository.

## Build

```bash
dotnet build plugin/TianzhengCadPlugin.sln -c Release
```

Run the isolated unit tests (no AutoCAD started):

```bash
dotnet test plugin/tests/TianzhengCadPlugin.Tests/TianzhengCadPlugin.Tests.csproj
```

## Injecting the auth token

The plugin **refuses to listen** unless a token is injected. There is no default and no
hardcoded token. Set one of the following **in the environment of the AutoCAD process**
before loading the plugin:

- `TIANZHENG_PLUGIN_TOKEN` — the token value (minimum 32 characters)
- `TIANZHENG_PLUGIN_TOKEN_FILE` — path to a local, git-ignored file holding the token

Optional: `TIANZHENG_PLUGIN_PORT` (default `5987`).

Tokens are never logged in full — only a short SHA-256 prefix is recorded.

## Loading in AutoCAD (development)

Loading is performed **manually by a human operator**; the plugin never modifies AutoCAD
security settings, trusted paths, `SECURELOAD`, or the registry.

1. Start AutoCAD 2026 with the token environment variable set.
2. Run the `NETLOAD` command.
3. Select `plugin/src/TianzhengCadPlugin/bin/Release/net8.0-windows/TianzhengCadPlugin.dll`.
4. The plugin prints its listening endpoint, or a message explaining that no token was injected.

Operator commands (all read-only; none touch a drawing):

| Command | Effect |
|---|---|
| `TZPLUGINSTATUS` | Print state, endpoint, protocol version, queue depth, dispatcher thread |
| `TZPLUGINSTART` | Start the listener after injecting a token |
| `TZPLUGINSTOP` | Stop the listener gracefully |

An `ApplicationPlugins` `.bundle` deliverable is planned for a later S7 stage; it is not
part of S7.1-A.

## Protocol

Framing: `[4-byte unsigned big-endian payload length][UTF-8 JSON payload]`.
The length is a **byte** count (not a character count) and is validated against the 1 MiB
cap **before** any body byte is read. Reading "JSON until the socket closes" is never used.

### Authentication wire flow

The token travels **only** in a connection-level handshake — never in a business request.

```
client                                   plugin
  │  frame 1: {"type":"auth","auth_token":"…","protocol_version":"1.0.0"}
  │ ─────────────────────────────────────────►
  │            {"success":true,"stage":"authentication"}
  │ ◄─────────────────────────────────────────
  │  frame 2..n: business requests (NO token field)
```

- The **first** frame on every connection must be the auth frame.
- Until it is accepted, **no business validation runs at all**. An unauthenticated caller
  receives a fixed, starved response (`"authentication required"`, empty
  `plugin_version` / `capability_version` / `plugin_state`, no `result`), so it cannot
  enumerate fields or operations, read capabilities, or probe plugin state. A bad token
  and a malformed frame are indistinguishable.
- `PluginRequest` has **no** `auth_token` field; sending one is rejected as `UNKNOWN_FIELD`.
  A token therefore can never reach business metadata, the queue, or the main thread.

### Session nonce

- A fresh `session_nonce` is generated on every plugin start.
- `health` and `capabilities` require the token but **not** the nonce.
- **`capabilities` returns the current `session_nonce`**; `health` does not.
- Every other operation must present a matching nonce, else `SESSION_NONCE_REQUIRED`
  (absent) or `SESSION_NONCE_INVALID` (mismatched or from a previous session).
- The nonce is not a secret and never substitutes for the token.

Request fields (all required unless noted): `protocol_version`, `request_id`, `job_id`,
`operation_id`, `operation_type`, `document_context`, `parameters`, `idempotency_key`,
`expected_capability`, `dry_run`, `timeout_ms`, `metadata`, and `session_nonce`
(optional for the handshake, required otherwise). **Unknown fields are rejected.**

### Protocol version history

| Version | Change | Breaking |
|---|---|---|
| `1.0.0` | Initial: framing, auth handshake, health/capabilities | — |
| **`2.0.0`** | `readiness` **string → boolean**; added `readiness_state`, `batch_transaction_mode`, `document_ownership_support`; `transaction_support` / `batch_support` / `dry_run_support` **string → boolean** | **Yes** |

`2.0.0` is a **MAJOR** bump because a 1.x client that parsed `readiness` as a string cannot
read a 2.x response. Requests declaring a 1.x `protocol_version` are rejected outright with
`INCOMPATIBLE_PROTOCOL_VERSION` rather than served a response they cannot parse. Compatibility
is decided on the MAJOR component only.

This version covers the **plugin transport only**. The S6 Contract has its own, independent
schema version and is unchanged.

### Document ownership

Writes require a `document_context.document_token` obtained from `create_synthetic_document`.
The token is 256-bit random, bound to the plugin session, the job, and the database
fingerprint, and dies with the session. A drawing the user already had open is never
registered, so it has no token and cannot be addressed. `MdiActiveDocument` is **never** a
write target and there is no fallback to it.

Ownership failures: `DOCUMENT_TOKEN_REQUIRED`, `DOCUMENT_TOKEN_INVALID`,
`DOCUMENT_SESSION_MISMATCH`, `DOCUMENT_JOB_MISMATCH`, `DOCUMENT_DATABASE_MISMATCH`,
`DOCUMENT_NOT_JOB_OWNED`.

### Batch semantics — `all_or_nothing`

One batch = one `DocumentLock` + one AutoCAD `Transaction`. All operations commit together,
or the transaction aborts and nothing persists.

**`success` means "this operation's effect is COMMITTED"** — not "this operation ran without
raising. Therefore, after an abort, **every** operation in the batch reports `success: false`,
including ones that executed cleanly beforehand. `execution_status` preserves the detail:

| Situation | `success` | `entity_status` | `execution_status` |
|---|---|---|---|
| Committed | `true` | `CREATED` | `EXECUTED_AND_COMMITTED` |
| Ran, then batch aborted | `false` | `ROLLED_BACK` | `EXECUTED_THEN_ROLLED_BACK` |
| Caused the abort | `false` | `FAILED` | `EXECUTION_FAILED` |
| Dry run | `false` | `NOT_CREATED` | `DRY_RUN_VALIDATED_NOT_EXECUTED` |

A rolled-back operation reports empty `handles` / `entity_ids` and zero
`created_count` / `modified_count`, so a client cannot mistake it for a durable write.
Batch level on abort: `transaction_status: ABORTED`, `rollback_status: ROLLED_BACK`,
`partial_commit_status: false`, `created_count: 0`.

### Dry run

`dry_run: true` performs ownership resolution, structural parsing and semantic geometry
validation, then stops. It takes **no** write `DocumentLock`, starts **no** write
`Transaction`, and creates **no** entity. It returns
`transaction_status: DRY_RUN_NOT_STARTED` and `created_count: 0`.

Responses always carry: `success`, `error_code`, `stage`, `request_id`, `operation_id`,
`entity_ids`, `handles`, `created_count`, `modified_count`, `skipped_count`,
`idempotency_status`, `warnings`, `duration_ms`, `plugin_version`, `capability_version`,
`retryable`, `transaction_status`, `document_status`, `plugin_state`, `sanitized_message`.

## Security boundaries

- Binds **only** `127.0.0.1`; non-loopback peers are refused even so.
- Token injected, never hardcoded, never committed, compared in constant time, redacted in logs.
- A fresh `session_id` is generated on every plugin start.
- Strict operation whitelist; there is no command/eval/LISP/script/passthrough field in
  the accepted schema, so arbitrary execution cannot be expressed by a valid request.
- Unknown fields, unknown operations, missing fields, incompatible protocol versions,
  oversized frames and out-of-range timeouts are all rejected.
- Concurrency limit, idle read timeout and per-request timeout are enforced.
- The transport thread never calls the AutoCAD API; CAD work is only ever run by the
  main-thread dispatcher via `Application.Idle`.

`tianzheng_support` is always `NOT_AVAILABLE`. This is a synthetic-sandbox MVP, **not**
a production-safe capability.
