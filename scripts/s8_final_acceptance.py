"""S8.7 final acceptance — the Tianzheng native pipe chain, entered from MCP.

The Tianzheng capability (capabilities / create / query / validate identity) is exercised
through ``dispatch_tool`` on the real control-plane dispatcher, not by calling the backend
directly. Document lifecycle (create synthetic / save / close / reopen) is an S7
plugin-transport concern and is not an MCP tool; that boundary is recorded as-is rather than
papered over.

Requires a live Tianzheng session started by TGStart.exe with the plugin NETLOADed.
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
from mcp_nextgen.control_server.dispatcher import (  # noqa: E402
    configure_tianzheng_route_service,
    dispatch_tool,
)
from mcp_nextgen.protocol.version import PROTOCOL_VERSION  # noqa: E402
from mcp_nextgen.s8.persistence import compare_roundtrip, evaluate_replay  # noqa: E402
from mcp_nextgen.s8.tianzheng_backend import TianzhengBackend  # noqa: E402
from mcp_nextgen.s8.tianzheng_route import build_tianzheng_route_service  # noqa: E402

START = [0.0, 0.0, 0.0]
END = [3000.0, 0.0, 0.0]


def main() -> int:
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT required", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("final_%Y%m%dT%H%M%SZ")
    out = Path("artifacts/s8_tianzheng_native_backend") / run_id
    out.mkdir(parents=True, exist_ok=True)

    job_id = f"s8final-{uuid.uuid4().hex[:8]}"
    idempotency_key = f"s8final-key-{uuid.uuid4().hex[:12]}"
    sandbox_file = f"s8_final_{uuid.uuid4().hex[:8]}.dwg"

    def write(name: str, payload: Any) -> None:
        (out / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8")

    def mcp(tool: str, **fields: Any) -> dict[str, Any]:
        payload = {
            "schema_version": PROTOCOL_VERSION,
            "request_id": f"req-{uuid.uuid4().hex[:8]}",
            "idempotency_key": idempotency_key,
            **fields,
        }
        return dispatch_tool(tool, payload)

    client = PluginTransportClient(
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)

    summary: dict[str, Any] = {
        "run_id": run_id, "job_id": job_id, "idempotency_key": idempotency_key,
        "token_digest": redact_token(token), "sandbox_file": sandbox_file,
        "entry_point": "mcp_nextgen.control_server.dispatcher.dispatch_tool",
        "steps": {}, "warnings": [],
    }

    def plugin(op: str, *, mutating: bool, **kwargs: Any) -> dict[str, Any]:
        response = client.call(op, mutating=mutating, job_id=job_id, **kwargs)
        if not response.get("success"):
            raise RuntimeError(f"{op}: {response.get('error_code')} "
                               f"{response.get('sanitized_message')}")
        return response.get("result") or {}

    try:
        handshake = client.connect()
        raw_handshake = dict(handshake.to_dict())
        summary["steps"]["handshake"] = {
            "tianzheng_loaded": raw_handshake.get("tianzheng_loaded"),
            "tianzheng_product": raw_handshake.get("tianzheng_product"),
            "tianzheng_version": raw_handshake.get("tianzheng_version"),
            "tianzheng_runtime_available": raw_handshake.get("tianzheng_runtime_available"),
            "tdbpipe_rxclass_available": raw_handshake.get("tdbpipe_rxclass_available"),
            "supported_tianzheng_operations": raw_handshake.get("supported_tianzheng_operations"),
            "protocol_version": handshake.protocol_version,
        }
        print(f"handshake: tianzheng_loaded={raw_handshake.get('tianzheng_loaded')}")
        if not raw_handshake.get("tianzheng_loaded"):
            raise RuntimeError("this session reports tianzheng_loaded=false; aborting")

        # --- wire the MCP route to the real backend --------------------------------------
        backend = TianzhengBackend(client, job_id=job_id)
        configure_tianzheng_route_service(
            build_tianzheng_route_service(backend, handshake=raw_handshake))

        # --- 5. MCP capability query ------------------------------------------------------
        # capabilities takes no job_id: its schema is strict and read-only.
        capability = mcp("cad.tianzheng.capabilities")
        write("capability_result.json", capability)
        caps = capability["data"]["capabilities"]["capabilities"]
        print(f"mcp capabilities: create={caps['tianzheng_native_pipe_create']} "
              f"diameter_read={caps['tianzheng_pipe_diameter_read']}")

        # --- document lifecycle (S7 transport; not an MCP tool) ---------------------------
        document = plugin("create_synthetic_document", mutating=True, parameters={})
        document_token = document["document_token"]

        # --- 6-12. MCP create -------------------------------------------------------------
        created = mcp("cad.tianzheng.create_pipe", job_id=job_id,
                      document_token=document_token, start=START, end=END)
        write("mcp_route_result.json", created)
        write("native_creation_result.json", created["data"])
        if created["status"] != "OK":
            raise RuntimeError(f"create failed: {created['error_code']}")
        creation = created["data"]
        handle = creation["primary_handle"]
        print(f"mcp create: backend={creation['actual_backend_used']} handle={handle} "
              f"related={creation['related_runtime_classes']}")

        # --- 11/13/14/15. MCP validate + query --------------------------------------------
        identity = mcp("cad.tianzheng.validate_pipe_identity", job_id=job_id,
                       document_token=document_token, handle=handle)
        write("native_identity_result.json", identity)

        queried = mcp("cad.tianzheng.query_pipe", job_id=job_id,
                      document_token=document_token, handle=handle,
                      related_handles=creation["related_handles"])
        write("query_result.json", queried)
        before = queried["data"]["snapshot"]
        print(f"mcp query: class={before['runtime_class']} dxf={before['dxf_name']} "
              f"diameter={before['properties']['diameter']['source']}")

        # --- 16-18. save / close / reopen --------------------------------------------------
        saved = plugin("save", mutating=True, parameters={"file_name": sandbox_file},
                       document_context={"document_token": document_token})
        plugin("close", mutating=True, parameters={},
               document_context={"document_token": document_token})
        reopened = plugin("reopen", mutating=True, parameters={},
                          document_context={"document_token": document_token})
        reopen_token = reopened.get("document_token") or document_token
        print(f"saved/closed/reopened: {saved.get('sandbox_identity')}")

        # --- 19-20. MCP query after reopen -------------------------------------------------
        requeried = mcp("cad.tianzheng.query_pipe", job_id=job_id,
                        document_token=reopen_token, handle=handle,
                        related_handles=creation["related_handles"])
        after = requeried["data"]["snapshot"]
        persistence = compare_roundtrip(before, after)
        persistence["sandbox_identity"] = saved.get("sandbox_identity")
        persistence["related_runtime_classes_after"] = after.get("related_runtime_classes")
        write("persistence_result.json", persistence)
        print(f"persistence: preserved={persistence['native_identity_preserved']} "
              f"class {persistence['native_class_before']}->{persistence['native_class_after']}")

        # --- 21-22. replay the same idempotency key through MCP -----------------------------
        inventory_before = backend.inventory(reopen_token)
        replay = mcp("cad.tianzheng.create_pipe", job_id=job_id,
                     document_token=reopen_token, start=START, end=END)
        inventory_after = backend.inventory(reopen_token)
        replay_data = replay.get("data", {})
        idempotency = evaluate_replay(inventory_before, inventory_after, replay_data)
        idempotency["mcp_status"] = replay["status"]
        idempotency["replayed_from_record"] = replay_data.get("replayed_from_record")
        write("idempotency_result.json", idempotency)
        print(f"idempotency: idempotent={idempotency['idempotent']} "
              f"pipes {idempotency['pipe_count_before']}->{idempotency['pipe_count_after']} "
              f"fittings {idempotency['fitting_count_before']}->{idempotency['fitting_count_after']}")

        summary["steps"]["capabilities"] = caps
        summary["steps"]["creation"] = creation
        summary["steps"]["identity"] = identity["data"]
        summary["steps"]["persistence"] = persistence
        summary["steps"]["idempotency"] = idempotency
        summary["status"] = (
            "S8_TIANZHENG_NATIVE_BACKEND_MVP_COMPLETE"
            if persistence["native_identity_preserved"] and idempotency["idempotent"]
            else "S8_TIANZHENG_NATIVE_BACKEND_PARTIAL")
    except Exception as exc:  # noqa: BLE001 - always leave evidence behind
        summary["status"] = "S8_TIANZHENG_NATIVE_BACKEND_PARTIAL"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED: {summary['error']}", file=sys.stderr)
    finally:
        configure_tianzheng_route_service(None)
        client.disconnect()

    (out / "s8_final_execution_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"\nstatus: {summary['status']}\nevidence: {out}")
    return 0 if summary["status"] == "S8_TIANZHENG_NATIVE_BACKEND_MVP_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
