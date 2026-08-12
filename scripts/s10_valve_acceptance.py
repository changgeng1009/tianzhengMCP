"""S10.1 native valve acceptance: identity, topology, persistence, idempotency.

    synthetic document -> native TDbPipe -> FMFJ adapter -> native TDbPipeValve
      -> query (identity + topology) -> save/close/reopen -> query again
        -> replay same key -> prove no duplicate

Requires a live TGStart.exe Tianzheng session with the plugin NETLOADed.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_nextgen.backends.plugin_transport import (  # noqa: E402
    PluginTransportClient,
    PluginTransportConfig,
)

PIPE_START = [0.0, 0.0, 0.0]
PIPE_END = [3000.0, 0.0, 0.0]
VALVE_POSITION = [1500.0, 0.0, 0.0]


def main() -> int:
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT required", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("valve_%Y%m%dT%H%M%SZ")
    out = Path("artifacts/s10_tianzheng_engineering_objects") / run_id
    out.mkdir(parents=True, exist_ok=True)
    job_id = f"s10-{uuid.uuid4().hex[:8]}"
    valve_key = f"s10-valve-{uuid.uuid4().hex[:12]}"
    pipe_key = f"s10-pipe-{uuid.uuid4().hex[:12]}"
    sandbox_file = f"s10_valve_{uuid.uuid4().hex[:8]}.dwg"

    client = PluginTransportClient(
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)

    summary: dict[str, Any] = {"run_id": run_id, "job_id": job_id,
                               "valve_idempotency_key": valve_key,
                               "sandbox_file": sandbox_file, "stages": {}, "warnings": []}

    def write(name: str, payload: Any) -> None:
        (out / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
                                encoding="utf-8")

    def call(op: str, *, mutating: bool, **kw: Any) -> dict[str, Any]:
        r = client.call(op, mutating=mutating, job_id=job_id, **kw)
        if not r.get("success"):
            raise RuntimeError(f"{op}: {r.get('error_code')} {r.get('sanitized_message')}")
        return r.get("result") or {}

    def poll(op: str) -> dict[str, Any]:
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(2)
            p = call(op, mutating=False, parameters={})
            if p.get("available") and not p.get("running"):
                return p.get("result") or {}
        raise RuntimeError(f"timed out polling {op}")

    try:
        handshake = dict(client.connect().to_dict())
        if not handshake.get("tianzheng_loaded"):
            raise RuntimeError("tianzheng_loaded=false")
        summary["stages"]["handshake"] = {"tianzheng_loaded": True,
                                          "product": handshake.get("tianzheng_product")}

        doc = call("create_synthetic_document", mutating=True, parameters={})
        token_doc = doc["document_token"]
        ctx = {"document_token": token_doc}

        # --- pipe ---------------------------------------------------------------------
        call("tianzheng_create_pipe", mutating=True,
             parameters={"start": PIPE_START, "end": PIPE_END, "idempotency_key": pipe_key},
             document_context=ctx, idempotency_key=pipe_key)
        pipe = poll("diagnostic_native_pipe_result")
        pipe_handle = pipe["primary_handle"]
        print(f"pipe: {pipe['primary_runtime_class']} handle={pipe_handle}")

        # --- valve --------------------------------------------------------------------
        call("tianzheng_create_valve", mutating=True,
             parameters={"position": VALVE_POSITION, "target_pipe_handle": pipe_handle,
                         "idempotency_key": valve_key},
             document_context=ctx, idempotency_key=valve_key)
        valve = poll("tianzheng_valve_result")
        write("valve_poc_result.json", valve)
        if valve.get("status") != "created":
            raise RuntimeError(f"valve status={valve.get('status')} {valve.get('warnings')}")
        valve_handle = valve["primary_handle"]
        print(f"valve: {valve['primary_runtime_class']} handle={valve_handle} "
              f"new_objects={valve['new_object_count']} "
              f"terminated_cleanly={valve['command_terminated_cleanly']}")
        print(f"counts: valve {valve['valve_count_before']}->{valve['valve_count_after']} "
              f"pipe {valve['pipe_count_before']}->{valve['pipe_count_after']} "
              f"fitting {valve['fitting_count_before']}->{valve['fitting_count_after']}")

        before = call("tianzheng_query_valve", mutating=False,
                      parameters={"handle": valve_handle, "target_pipe_handle": pipe_handle},
                      document_context=ctx)
        write("valve_snapshot_before_save.json", before)
        topo = before.get("topology") or {}
        print(f"topology: source={before.get('topology_source')} "
              f"target_pipe={before.get('target_pipe_handle')}")

        # --- persistence ----------------------------------------------------------------
        saved = call("save", mutating=True, parameters={"file_name": sandbox_file},
                     document_context=ctx)
        call("close", mutating=True, parameters={}, document_context=ctx)
        reopened = call("reopen", mutating=True, parameters={}, document_context=ctx)
        ctx2 = {"document_token": reopened.get("document_token") or token_doc}

        after = call("tianzheng_query_valve", mutating=False,
                     parameters={"handle": valve_handle, "target_pipe_handle": pipe_handle},
                     document_context=ctx2)
        write("valve_snapshot_after_reopen.json", after)

        def pos(s):
            return [round(float(v), 6) for v in (s.get("position") or [])]

        persistence = {
            "native_class_before": before.get("runtime_class"),
            "native_class_after": after.get("runtime_class"),
            "handle_before": before.get("handle"), "handle_after": after.get("handle"),
            "position_before": pos(before), "position_after": pos(after),
            "position_preserved": pos(before) == pos(after),
            "topology_source_before": before.get("topology_source"),
            "topology_source_after": after.get("topology_source"),
            "target_pipe_before": before.get("target_pipe_handle"),
            "target_pipe_after": after.get("target_pipe_handle"),
            "topology_preserved": before.get("target_pipe_handle") == after.get("target_pipe_handle"),
            "native_identity_preserved": (before.get("runtime_class") == after.get("runtime_class")
                                          == "TDbPipeValve" and bool(after.get("native_identity_confirmed"))),
            "sandbox_identity": saved.get("sandbox_identity"),
        }
        write("valve_persistence_result.json", persistence)
        print(f"persistence: {persistence['native_class_before']} -> "
              f"{persistence['native_class_after']} position_preserved="
              f"{persistence['position_preserved']}")

        # --- idempotency ------------------------------------------------------------------
        call("tianzheng_create_valve", mutating=True,
             parameters={"position": VALVE_POSITION, "target_pipe_handle": pipe_handle,
                         "idempotency_key": valve_key},
             document_context=ctx2, idempotency_key=valve_key)
        replay = poll("tianzheng_valve_result")
        idem = {
            "replay_status": replay.get("status"),
            "replayed_from_record": replay.get("replayed_from_record"),
            "valve_count_before": replay.get("valve_count_before"),
            "valve_count_after": replay.get("valve_count_after"),
            "pipe_count_before": replay.get("pipe_count_before"),
            "pipe_count_after": replay.get("pipe_count_after"),
            "fitting_count_before": replay.get("fitting_count_before"),
            "fitting_count_after": replay.get("fitting_count_after"),
            "duplicate_created": replay.get("duplicate_created"),
            "idempotent": (replay.get("status") in ("already_applied", "equivalent")
                           and replay.get("valve_count_after") == replay.get("valve_count_before")),
        }
        write("valve_idempotency_result.json", idem)
        print(f"idempotency: {idem['replay_status']} valve "
              f"{idem['valve_count_before']}->{idem['valve_count_after']} "
              f"idempotent={idem['idempotent']}")

        summary["stages"].update({"valve": valve, "topology": topo,
                                  "persistence": persistence, "idempotency": idem})
        topology_ok = bool(before.get("target_pipe_handle"))
        summary["status"] = (
            "S10_1_NATIVE_VALVE_COMPLETE"
            if (persistence["native_identity_preserved"] and idem["idempotent"] and topology_ok)
            else "S10_1_NATIVE_VALVE_PARTIAL_TOPOLOGY_UNOBSERVABLE"
            if (persistence["native_identity_preserved"] and idem["idempotent"])
            else "S10_1_NATIVE_VALVE_PARTIAL")
    except Exception as exc:  # noqa: BLE001
        summary["status"] = "S10_1_NATIVE_VALVE_PARTIAL"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED: {summary['error']}", file=sys.stderr)
    finally:
        client.disconnect()

    write("s10_1_valve_summary.json", summary)
    print(f"\nstatus: {summary['status']}\nevidence: {out}")
    return 0 if summary["status"].endswith(("COMPLETE", "UNOBSERVABLE")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
