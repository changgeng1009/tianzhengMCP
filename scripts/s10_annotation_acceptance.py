"""S10.4 native pipe annotation (DGGJ, 单管管径): automation, storage model, persistence, idempotency.

DGGJ was chosen by measured interaction discovery, not by name. Its prompt is a single POINT that
Tianzheng hit-tests itself, so the adapter drives it with the SendStringToExecute pattern already
proven for the pump - not with the SelectionSet path that GJBZ ignored.

The database diff is taken only after DGGJ's own lifecycle event reports it finished, so the
storage-model verdict comes from a SETTLED database rather than a mid-command scan.
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


def main() -> int:
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT required", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("annotation_%Y%m%dT%H%M%SZ")
    out = Path("artifacts/s10_tianzheng_engineering_objects") / run_id
    out.mkdir(parents=True, exist_ok=True)
    job = f"s10-ann-{uuid.uuid4().hex[:8]}"
    pipe_key = f"s10-ann-pipe-{uuid.uuid4().hex[:12]}"
    ann_key = f"s10-ann-{uuid.uuid4().hex[:12]}"
    sandbox = f"s10_annotation_{uuid.uuid4().hex[:8]}.dwg"

    client = PluginTransportClient(
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)
    summary: dict[str, Any] = {"run_id": run_id, "command": "DGGJ", "stages": {}}

    def write(name: str, payload: Any) -> None:
        (out / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    def call(op: str, *, mutating: bool, **kw: Any) -> dict[str, Any]:
        r = client.call(op, mutating=mutating, job_id=job, **kw)
        if not r.get("success"):
            raise RuntimeError(f"{op}: {r.get('error_code')} {r.get('sanitized_message')}")
        return r.get("result") or {}

    def poll_pipe() -> dict[str, Any]:
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(2)
            p = call("diagnostic_native_pipe_result", mutating=False, parameters={})
            if p.get("available") and not p.get("running"):
                return p.get("result") or {}
        raise RuntimeError("timed out waiting for the pipe result")

    def poll_annotation() -> dict[str, Any]:
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(2)
            p = call("tianzheng_annotation_result", mutating=False, parameters={})
            if p.get("available") and not p.get("running"):
                return p.get("result") or {}
        raise RuntimeError("timed out waiting for the annotation result")

    try:
        hs = dict(client.connect().to_dict())
        if not hs.get("tianzheng_loaded"):
            raise RuntimeError("tianzheng_loaded=false")
        summary["handshake"] = hs

        doc = call("create_synthetic_document", mutating=True, parameters={})
        ctx = {"document_token": doc["document_token"]}

        # --- fixture: one native pipe -------------------------------------------------
        call("tianzheng_create_pipe", mutating=True,
             parameters={"start": [0.0, 0.0, 0.0], "end": [3000.0, 0.0, 0.0],
                         "idempotency_key": pipe_key},
             document_context=ctx, idempotency_key=pipe_key)
        fixture = poll_pipe()
        pipe_handle = fixture["primary_handle"]
        write("annotation_fixture_pipe.json", fixture)
        print(f"fixture pipe: handle={pipe_handle} class={fixture.get('primary_runtime_class')}")

        # --- the annotation itself ----------------------------------------------------
        call("tianzheng_annotate_pipe", mutating=True,
             parameters={"target_pipe_handle": pipe_handle, "idempotency_key": ann_key},
             document_context=ctx, idempotency_key=ann_key)
        ann = poll_annotation()
        write("annotation_dggj_automation_result.json", ann)
        summary["stages"]["automation"] = {
            "status": ann.get("status"),
            "storage_model": ann.get("storage_model"),
            "command_observed_start": ann.get("command_observed_start"),
            "command_end_kind": ann.get("command_end_kind"),
            "command_terminated_cleanly": ann.get("command_terminated_cleanly"),
        }
        print(f"annotation: status={ann.get('status')} storage_model={ann.get('storage_model')} "
              f"end_kind={ann.get('command_end_kind')} clean={ann.get('command_terminated_cleanly')}")
        print(f"  new_objects={[o.get('runtime_class') for o in (ann.get('new_objects') or [])]}")
        print(f"  target_differences={ann.get('target_differences')}")

        write("annotation_settled_diff.json", {
            "before_entity_count": ann.get("before_entity_count"),
            "after_entity_count": ann.get("after_entity_count"),
            "new_objects": ann.get("new_objects"),
            "deleted_handles": ann.get("deleted_handles"),
            "target_before": ann.get("target_before"),
            "target_after": ann.get("target_after"),
            "target_differences": ann.get("target_differences"),
            "storage_model": ann.get("storage_model"),
            "note": "taken only after DGGJ's own lifecycle event reported the command finished",
        })

        if ann.get("status") in (None, "failed", "no_effect"):
            raise RuntimeError(f"annotation status={ann.get('status')} {ann.get('warnings')}")

        # --- query --------------------------------------------------------------------
        snap_before = call("tianzheng_query_pipe", mutating=False,
                           parameters={"handle": pipe_handle}, document_context=ctx)
        write("annotation_query_before_save.json", snap_before)

        # --- persistence: save / close / reopen ---------------------------------------
        saved = call("save", mutating=True, parameters={"file_name": sandbox}, document_context=ctx)
        call("close", mutating=True, parameters={}, document_context=ctx)
        reopened = call("reopen", mutating=True, parameters={}, document_context=ctx)
        ctx2 = {"document_token": reopened.get("document_token") or ctx["document_token"]}

        snap_after = call("tianzheng_query_pipe", mutating=False,
                          parameters={"handle": pipe_handle}, document_context=ctx2)
        scan_after = call("diagnostic_scan_database", mutating=False,
                          parameters={"read_geometry": True})
        write("annotation_persistence.json", {
            "saved": saved, "reopened": reopened,
            "snapshot_before_save": snap_before, "snapshot_after_reopen": snap_after,
            "scan_after_reopen": scan_after,
        })
        survived = snap_after.get("native_identity_confirmed") is True
        summary["stages"]["persistence"] = {
            "pipe_survived": survived,
            "histogram_after_reopen": scan_after.get("class_histogram"),
            "entity_count_after_reopen": scan_after.get("entity_count"),
        }
        print(f"persistence: pipe_survived={survived} "
              f"histogram={scan_after.get('class_histogram')}")

        # --- idempotency: replay the SAME key ------------------------------------------
        call("tianzheng_annotate_pipe", mutating=True,
             parameters={"target_pipe_handle": pipe_handle, "idempotency_key": ann_key},
             document_context=ctx2, idempotency_key=ann_key)
        replay = poll_annotation()
        write("annotation_idempotency_replay.json", replay)
        scan_replay = call("diagnostic_scan_database", mutating=False,
                           parameters={"read_geometry": False})
        # The replay path re-captures the target's fingerprint, so it doubles as the proof that
        # the Model-B label state itself survived save/close/reopen - not merely the pipe.
        label_xdata = ((replay.get("target_after") or {}).get("x_data_applications")) or []
        summary["stages"]["persistence"]["label_xdata_after_reopen"] = label_xdata
        summary["stages"]["persistence"]["label_state_survived"] = (
            "TG_PIPELABEL_THICK_SHOW" in label_xdata)
        print(f"label state after reopen: {label_xdata}")

        summary["stages"]["idempotency"] = {
            "replay_status": replay.get("status"),
            "replayed_from_record": replay.get("replayed_from_record"),
            "histogram_after_replay": scan_replay.get("class_histogram"),
            "entity_count_after_replay": scan_replay.get("entity_count"),
            "no_duplicate": scan_replay.get("entity_count") == scan_after.get("entity_count"),
        }
        print(f"idempotency: status={replay.get('status')} "
              f"replayed={replay.get('replayed_from_record')} "
              f"count {scan_after.get('entity_count')}->{scan_replay.get('entity_count')}")

        summary["verdict"] = "PASS"
    except Exception as exc:  # noqa: BLE001 - the run's outcome is the artifact
        summary["verdict"] = "FAIL"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        write("annotation_acceptance_summary.json", summary)
        print(f"\nartifacts -> {out}")

    return 0 if summary.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
