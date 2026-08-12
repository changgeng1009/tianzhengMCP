"""S8.1 native TDbPipe creation proof-of-concept.

Drives the existing S7 plugin transport (no second protocol, no second server) to:
  1. snapshot model space,
  2. ask the plugin to run Tianzheng's own fixed pipe-creation command,
  3. snapshot model space again,
  4. decide native identity from the before/after difference.

The verdict comes from the database diff, never from the command reporting success and
never from what appeared on screen.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_nextgen.backends.plugin_transport import (  # noqa: E402
    PluginTransportClient,
    PluginTransportConfig,
    redact_token,
)
from mcp_nextgen.s8.native_identity import (  # noqa: E402
    confirm_native_identity,
    diff_objects,
    properties_actually_read,
)

TARGET_CLASS = "TDbPipe"
START = [0.0, 0.0, 0.0]
END = [3000.0, 0.0, 0.0]
ARTIFACTS = Path("artifacts/s8_tianzheng_native_backend")


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

    client = PluginTransportClient(
        # The plugin caps per-request timeout at ProtocolConstants.MaxTimeoutMs (120s).
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)

    warnings: list[str] = []
    try:
        capabilities = client.connect()

        before = client.call("diagnostic_scan_database", mutating=False,
                             parameters={"read_geometry": False}).get("result") or {}
        write(ARTIFACTS / "native_creation_database_before.json", before)
        print(f"before: {before.get('entity_count')} model-space objects")

        start_response = client.call("diagnostic_create_native_pipe", mutating=True,
                                     parameters={"start": START, "end": END}).get("result") or {}
        print(f"creation queued: {start_response}")
        if not start_response.get("started"):
            warnings.append("plugin reported the PoC was already running")

        # The command runs in AutoCAD's own command context, so poll rather than block it.
        poc: dict[str, Any] = {}
        deadline = time.time() + 120.0
        while time.time() < deadline:
            time.sleep(2.0)
            payload = client.call("diagnostic_native_pipe_result",
                                  mutating=False, parameters={}).get("result") or {}
            if payload.get("available") and not payload.get("running"):
                poc = payload.get("result") or {}
                break
        else:
            warnings.append("timed out waiting for the creation command to finish")

        after = client.call("diagnostic_scan_database", mutating=False,
                            parameters={"read_geometry": True}).get("result") or {}
        write(ARTIFACTS / "native_creation_database_after.json", after)
        print(f"after: {after.get('entity_count')} model-space objects")
    finally:
        client.disconnect()

    # Authoritative diff: the plugin's own scans bracket the command exactly.
    plugin_before = poc.get("before_objects") or []
    plugin_after = poc.get("after_objects") or []
    new_objects = poc.get("new_objects")
    if not new_objects:
        new_objects = diff_objects(plugin_before, plugin_after)

    verdict = confirm_native_identity(new_objects, TARGET_CLASS)
    pipe = next((o for o in new_objects
                 if str(o.get("runtime_class") or o.get("RuntimeClass")) == TARGET_CLASS), None)

    if poc.get("error"):
        warnings.append(f"plugin reported: {poc['error']}")
    for w in poc.get("warnings") or []:
        warnings.append(str(w))

    report = {
        "probe": "s8_1_native_pipe_poc",
        "creation_method": poc.get("creation_method") or "tianzheng_fixed_command",
        "creation_entry_point": poc.get("creation_entry_point"),
        "requested_start": poc.get("requested_start") or START,
        "requested_end": poc.get("requested_end") or END,
        "document_name": poc.get("document_name"),
        "plugin_protocol_version": capabilities.protocol_version,
        "token_digest": redact_token(token),
        "before_entity_count": poc.get("before_entity_count", before.get("entity_count")),
        "after_entity_count": poc.get("after_entity_count", after.get("entity_count")),
        "new_object_count": len(new_objects),
        "new_objects": new_objects,
        "tdbpipe_object_id": (pipe or {}).get("object_id") or (pipe or {}).get("ObjectId"),
        "tdbpipe_handle": (pipe or {}).get("handle") or (pipe or {}).get("Handle"),
        "runtime_class": (pipe or {}).get("runtime_class") or (pipe or {}).get("RuntimeClass"),
        "dxf_name": (pipe or {}).get("dxf_name") or (pipe or {}).get("DxfName"),
        "rxclass_ancestry": (pipe or {}).get("ancestry") or (pipe or {}).get("Ancestry"),
        "native_identity_confirmed": verdict["native_identity_confirmed"],
        "identity_verdict": verdict,
        "properties_actually_read_from_object": properties_actually_read(pipe or {}),
        "plugin_status": poc.get("status"),
        "warnings": warnings,
    }

    write(ARTIFACTS / "native_pipe_poc_result.json", report)
    print(json.dumps({k: report[k] for k in (
        "creation_method", "creation_entry_point", "before_entity_count",
        "after_entity_count", "new_object_count", "runtime_class", "dxf_name",
        "tdbpipe_handle", "native_identity_confirmed", "plugin_status", "warnings",
    )}, indent=2, ensure_ascii=False, default=str))

    return 0 if report["native_identity_confirmed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
