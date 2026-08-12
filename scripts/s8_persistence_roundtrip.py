"""S8.2-S8.5 native pipe persistence and idempotency round trip.

Opt-in integration run. Requires a live Tianzheng session started by TGStart.exe with the
plugin NETLOADed, and TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT in the environment.

    create synthetic document
      -> create native pipe (idempotency_key K)
        -> snapshot
          -> save to sandbox -> close -> reopen
            -> snapshot again and compare
              -> replay the SAME key
                -> prove no duplicate pipe and no duplicate fittings

Nothing here decides anything from the screen: every verdict comes from the database.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_nextgen.backends.plugin_transport import (  # noqa: E402
    PluginTransportClient,
    PluginTransportConfig,
    redact_token,
)
from mcp_nextgen.s8.persistence import compare_roundtrip, evaluate_replay  # noqa: E402
from mcp_nextgen.s8.tianzheng_backend import (  # noqa: E402
    TianzhengBackend,
    TianzhengBackendError,
    TianzhengPipeSpec,
)

SPEC = TianzhengPipeSpec(start=(0.0, 0.0, 0.0), end=(3000.0, 0.0, 0.0))
SANDBOX_FILE = "s8_persistence_roundtrip.dwg"


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
                    encoding="utf-8")


def main() -> int:
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT required", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    out = Path("artifacts/s8_tianzheng_native_backend") / run_id
    idempotency_key = f"s8-pipe-{uuid.uuid4().hex[:12]}"

    client = PluginTransportClient(
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)
    backend = TianzhengBackend(client, job_id="s8-persistence-roundtrip")

    summary: dict[str, Any] = {
        "run_id": run_id,
        "idempotency_key": idempotency_key,
        "token_digest": redact_token(token),
        "spec": {"start": list(SPEC.start), "end": list(SPEC.end)},
        "stages": {},
        "warnings": [],
    }

    def raw(op: str, *, mutating: bool, **kwargs: Any) -> dict[str, Any]:
        response = client.call(op, mutating=mutating, job_id="s8-persistence-roundtrip", **kwargs)
        if not response.get("success"):
            raise RuntimeError(f"{op} failed: {response.get('error_code')} "
                               f"{response.get('sanitized_message')}")
        return response.get("result") or {}

    try:
        capabilities = client.connect()
        summary["plugin_protocol_version"] = capabilities.protocol_version

        # --- S8.2: synthetic, job-owned document (never a user drawing) ------------------
        document = raw("create_synthetic_document", mutating=True, parameters={})
        document_token = document["document_token"]
        summary["stages"]["document"] = {
            "document_token_present": bool(document_token),
            "synthetic": document.get("synthetic"),
            "creation_method": document.get("creation_method"),
        }
        print(f"synthetic document created ({document.get('creation_method')})")

        # --- S8.2/S8.3: create one native pipe ------------------------------------------
        creation = backend.create_pipe(document_token, SPEC, idempotency_key=idempotency_key)
        write(out / "tianzheng_backend_result.json", creation.to_dict())
        write(out / "related_entities_result.json", {
            "primary_handle": creation.primary_handle,
            "primary_runtime_class": creation.primary_runtime_class,
            "related_handles": creation.related_handles,
            "related_runtime_classes": creation.related_runtime_classes,
            "native_object_count": creation.native_object_count,
            "database_diff": creation.database_diff,
        })
        print(f"created pipe handle={creation.primary_handle} "
              f"related={creation.related_runtime_classes}")
        if not creation.primary_handle:
            raise RuntimeError("no primary handle returned")

        # --- snapshot before save --------------------------------------------------------
        before = backend.query_pipe(document_token, creation.primary_handle,
                                    creation.related_handles)
        write(out / "native_pipe_snapshot_before_save.json", before)
        write(out / "property_access_result.json", {
            "handle": creation.primary_handle,
            "properties": before.get("properties"),
            "note": "every entry carries its own source; values with source "
                    "NOT_READABLE_WITH_CURRENT_SURFACE are never filled in from the request",
        })

        # --- S8.4: save -> close -> reopen ----------------------------------------------
        saved = raw("save", mutating=True,
                    parameters={"file_name": SANDBOX_FILE},
                    document_context={"document_token": document_token})
        print(f"saved: {saved.get('sandbox_identity')}")

        raw("close", mutating=True, parameters={},
            document_context={"document_token": document_token})
        print("closed")

        reopened = raw("reopen", mutating=True, parameters={},
                       document_context={"document_token": document_token})
        reopen_token = reopened.get("document_token") or document_token
        print(f"reopened (token {'rotated' if reopen_token != document_token else 'unchanged'})")

        after = backend.query_pipe(reopen_token, creation.primary_handle,
                                   creation.related_handles)
        write(out / "native_pipe_snapshot_after_reopen.json", after)

        persistence = compare_roundtrip(before, after)
        persistence["sandbox_identity"] = saved.get("sandbox_identity")
        persistence["reopen_status"] = reopened.get("lifecycle_stage")
        write(out / "persistence_result.json", persistence)
        print(f"persistence: native_identity_preserved={persistence['native_identity_preserved']} "
              f"({'; '.join(persistence['reasons'])})")

        # --- S8.5: replay the same key in the REOPENED document -------------------------
        inventory_before = backend.inventory(reopen_token)
        try:
            replay = backend.create_pipe(reopen_token, SPEC, idempotency_key=idempotency_key)
            replay_payload = replay.to_dict()
        except TianzhengBackendError as exc:
            replay_payload = {"status": "failed", "error_code": exc.error_code,
                              "message": str(exc)}
        inventory_after = backend.inventory(reopen_token)

        idempotency = evaluate_replay(inventory_before, inventory_after, replay_payload)
        idempotency["replay_result"] = replay_payload
        idempotency["replayed_from_record"] = replay_payload.get("replayed_from_record")
        write(out / "idempotency_replay_result.json", idempotency)
        print(f"idempotency: idempotent={idempotency['idempotent']} "
              f"pipes {idempotency['pipe_count_before']}->{idempotency['pipe_count_after']} "
              f"fittings {idempotency['fitting_count_before']}->{idempotency['fitting_count_after']}")

        summary["stages"]["creation"] = creation.to_dict()
        summary["stages"]["persistence"] = persistence
        summary["stages"]["idempotency"] = idempotency
        summary["status"] = (
            "S8_5_TDBPIPE_PERSISTENCE_IDEMPOTENCY_COMPLETE"
            if persistence["native_identity_preserved"] and idempotency["idempotent"]
            else "S8_4_TDBPIPE_NATIVE_PERSISTENCE_COMPLETE"
            if persistence["native_identity_preserved"]
            else "S8_TIANZHENG_NATIVE_BACKEND_PARTIAL"
        )
    except Exception as exc:  # noqa: BLE001 - the run must always leave evidence behind
        summary["status"] = "S8_TIANZHENG_NATIVE_BACKEND_PARTIAL"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED: {summary['error']}", file=sys.stderr)
    finally:
        client.disconnect()

    write(out / "s8_5_execution_summary.json", summary)
    print(f"\nstatus: {summary['status']}\nevidence: {out}")
    return 0 if summary["status"] == "S8_5_TDBPIPE_PERSISTENCE_IDEMPOTENCY_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
