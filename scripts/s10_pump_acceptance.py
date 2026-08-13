"""S10.3 native pump: automated creation, identity, persistence, idempotency.

Also carries the command-termination evidence: the adapter appends an owned cancel to its own
queued sequence, and the database diff is taken only after HZSB itself reports it finished, so
this run answers whether the pump SURVIVES that cancel.
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

POSITION = [0.0, 0.0, 0.0]


def main() -> int:
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT required", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("pump_%Y%m%dT%H%M%SZ")
    out = Path("artifacts/s10_tianzheng_engineering_objects") / run_id
    out.mkdir(parents=True, exist_ok=True)
    job = f"s10-pump-{uuid.uuid4().hex[:8]}"
    key = f"s10-pump-{uuid.uuid4().hex[:12]}"
    sandbox = f"s10_pump_{uuid.uuid4().hex[:8]}.dwg"

    client = PluginTransportClient(
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)
    summary: dict[str, Any] = {"run_id": run_id, "idempotency_key": key, "stages": {}}

    def write(name: str, payload: Any) -> None:
        (out / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    def call(op: str, *, mutating: bool, **kw: Any) -> dict[str, Any]:
        r = client.call(op, mutating=mutating, job_id=job, **kw)
        if not r.get("success"):
            raise RuntimeError(f"{op}: {r.get('error_code')} {r.get('sanitized_message')}")
        return r.get("result") or {}

    def poll() -> dict[str, Any]:
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(2)
            p = call("tianzheng_pump_result", mutating=False, parameters={})
            if p.get("available") and not p.get("running"):
                return p.get("result") or {}
        raise RuntimeError("timed out waiting for the pump result")

    try:
        hs = dict(client.connect().to_dict())
        if not hs.get("tianzheng_loaded"):
            raise RuntimeError("tianzheng_loaded=false")

        doc = call("create_synthetic_document", mutating=True, parameters={})
        tok = doc["document_token"]
        ctx = {"document_token": tok}

        before = call("diagnostic_scan_database", mutating=False, parameters={"read_geometry": False})
        write("equipment_hzsb_before.json", before)

        call("tianzheng_create_pump", mutating=True,
             parameters={"position": POSITION, "idempotency_key": key},
             document_context=ctx, idempotency_key=key)
        pump = poll()
        write("equipment_hzsb_automation_result.json", pump)
        write("equipment_hzsb_diff.json", {"new_objects": pump.get("new_objects"),
                                           "new_object_count": pump.get("new_object_count")})
        write("equipment_hzsb_command_lifecycle.json", {
            "command_observed_start": pump.get("command_observed_start"),
            "command_end_kind": pump.get("command_end_kind"),
            "command_terminated_cleanly": pump.get("command_terminated_cleanly"),
            "cancel_sequence_issued": pump.get("cancel_sequence_issued"),
            "note": "the diff is taken only after HZSB itself reported it finished, so a pump "
                    "present here survived the owned cancel",
        })
        print(f"command: start={pump.get('command_observed_start')} "
              f"end_kind={pump.get('command_end_kind')} clean={pump.get('command_terminated_cleanly')}")
        print(f"pump: status={pump.get('status')} class={pump.get('primary_runtime_class')} "
              f"handle={pump.get('primary_handle')} new_objects={pump.get('new_object_count')} "
              f"count {pump.get('pump_count_before')}->{pump.get('pump_count_after')}")
        if pump.get("status") != "created":
            raise RuntimeError(f"pump status={pump.get('status')} {pump.get('warnings')}")

        handle = pump["primary_handle"]
        snap_before = call("tianzheng_query_equipment", mutating=False,
                           parameters={"handle": handle}, document_context=ctx)
        write("equipment_snapshot_before_save.json", snap_before)

        saved = call("save", mutating=True, parameters={"file_name": sandbox}, document_context=ctx)
        call("close", mutating=True, parameters={}, document_context=ctx)
        re = call("reopen", mutating=True, parameters={}, document_context=ctx)
        ctx2 = {"document_token": re.get("document_token") or tok}

        snap_after = call("tianzheng_query_equipment", mutating=False,
                          parameters={"handle": handle}, document_context=ctx2)
        write("equipment_snapshot_after_reopen.json", snap_after)

        def pos(s):
            return [round(float(v), 6) for v in (s.get("position") or [])]

        persistence = {
            "native_class_before": snap_before.get("runtime_class"),
            "native_class_after": snap_after.get("runtime_class"),
            "handle_before": snap_before.get("handle"), "handle_after": snap_after.get("handle"),
            "position_before": pos(snap_before), "position_after": pos(snap_after),
            "position_preserved": pos(snap_before) == pos(snap_after),
            "layer_before": snap_before.get("layer"), "layer_after": snap_after.get("layer"),
            "native_identity_preserved": (snap_before.get("runtime_class")
                                          == snap_after.get("runtime_class") == "TDbPump"
                                          and bool(snap_after.get("native_identity_confirmed"))),
            "sandbox_identity": saved.get("sandbox_identity"),
        }
        write("equipment_persistence_result.json", persistence)
        print(f"persistence: {persistence['native_class_before']} -> "
              f"{persistence['native_class_after']} pos_preserved={persistence['position_preserved']}")

        call("tianzheng_create_pump", mutating=True,
             parameters={"position": POSITION, "idempotency_key": key},
             document_context=ctx2, idempotency_key=key)
        replay = poll()
        idem = {
            "replay_status": replay.get("status"),
            "replayed_from_record": replay.get("replayed_from_record"),
            "pump_count_before": replay.get("pump_count_before"),
            "pump_count_after": replay.get("pump_count_after"),
            "duplicate_created": replay.get("duplicate_created"),
            "idempotent": (replay.get("status") in ("already_applied", "equivalent")
                           and replay.get("pump_count_after") == replay.get("pump_count_before")),
        }
        write("equipment_idempotency_result.json", idem)
        print(f"idempotency: {idem['replay_status']} pump "
              f"{idem['pump_count_before']}->{idem['pump_count_after']} "
              f"idempotent={idem['idempotent']}")

        summary["stages"] = {"pump": pump, "persistence": persistence, "idempotency": idem}
        summary["status"] = ("S10_3_NATIVE_EQUIPMENT_COMPLETE"
                             if persistence["native_identity_preserved"] and idem["idempotent"]
                             else "S10_3_NATIVE_EQUIPMENT_PARTIAL")
    except Exception as exc:  # noqa: BLE001
        summary["status"] = "S10_3_NATIVE_EQUIPMENT_PARTIAL"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED: {summary['error']}", file=sys.stderr)
    finally:
        client.disconnect()

    write("s10_3_pump_summary.json", summary)
    print(f"\nstatus: {summary['status']}\nevidence: {out}")
    return 0 if summary["status"].endswith("COMPLETE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
