"""S8.1 RXClass probe — machine-readable proof of Tianzheng native class registration.

Drives the existing S7 plugin transport (no second protocol, no second server) and asks the
live AutoCAD process to resolve Tianzheng runtime classes by name.

Read-only: creates nothing, opens no document, mutates no database.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_nextgen.backends.plugin_transport import (
    PluginTransportClient,
    PluginTransportConfig,
    redact_token,
)

#: S8 acceptance target plus diagnostic companions.
TARGET_CLASS = "TDbPipe"
COMPANION_CLASSES = ["TDbPipeNode", "TDbPipeFitting", "TDbPipeValve", "TDbPipeBase"]
#: Controls: a class that must exist, and one that must not.
CONTROL_PRESENT = "AcDbLine"
CONTROL_ABSENT = "TDbDefinitelyNotARealClass"


def main() -> int:
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT required", file=sys.stderr)
        return 2

    out = sys.argv[1] if len(sys.argv) > 1 else None
    client = PluginTransportClient(
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)

    try:
        capabilities = client.connect()
        response = client.call(
            "diagnostic_query_rxclass",
            mutating=False,
            parameters={
                "class_names": [TARGET_CLASS, *COMPANION_CLASSES, CONTROL_PRESENT, CONTROL_ABSENT],
                "list_prefix": "TDb",
            },
        )
    finally:
        client.disconnect()

    result = response.get("result") or {}
    # The plugin serializes with snake_case naming; accept that plus defensive variants.
    def key_of(c):
        return (c.get("requested_class_name") or c.get("RequestedClassName")
                or c.get("requestedClassName"))

    by_name = {key_of(c): c for c in (result.get("classes") or [])}

    def entry(name: str) -> dict[str, Any]:
        return by_name.get(name) or {}

    def field(name: str, *keys: str) -> Any:
        e = entry(name)
        for k in keys:
            if k in e:
                return e[k]
        # snake_case fallback derived from the PascalCase name
        for k in keys:
            snake = "".join("_" + ch.lower() if ch.isupper() else ch for ch in k).lstrip("_")
            if snake in e:
                return e[snake]
        return None

    target = entry(TARGET_CLASS)
    report: dict[str, Any] = {
        "probe": "s8_1_rxclass_probe",
        "runtime_query_method": field(TARGET_CLASS, "RuntimeQueryMethod", "runtimeQueryMethod"),
        "autocad_version": result.get("autocad_version") or result.get("autocadVersion"),
        "plugin_version": result.get("plugin_version") or result.get("pluginVersion"),
        "plugin_protocol_version": capabilities.protocol_version,
        "tianzheng_loaded": result.get("tianzheng_loaded") or result.get("tianzhengLoaded"),
        "token_digest": redact_token(token),
        "TDbPipe": {
            "found": field(TARGET_CLASS, "Found", "found"),
            "runtime_class": field(TARGET_CLASS, "RuntimeClassName", "runtimeClassName"),
            "dxf_name": field(TARGET_CLASS, "DxfName", "dxfName"),
            "app_name": field(TARGET_CLASS, "AppName", "appName"),
            "parent_class": field(TARGET_CLASS, "ParentClass", "parentClass"),
            "ancestry": field(TARGET_CLASS, "Ancestry", "ancestry"),
            "is_derived_from_dbobject": entry(TARGET_CLASS).get("is_derived_from_db_object"),
            "is_entity": field(TARGET_CLASS, "IsEntity", "isEntity"),
            "runtime_query_method": field(TARGET_CLASS, "RuntimeQueryMethod", "runtimeQueryMethod"),
        },
        "companions": {n: {"found": field(n, "Found", "found"),
                           "runtime_class": field(n, "RuntimeClassName", "runtimeClassName"),
                           "parent_class": field(n, "ParentClass", "parentClass")}
                       for n in COMPANION_CLASSES},
        "controls": {
            "must_exist": {"class": CONTROL_PRESENT, "found": field(CONTROL_PRESENT, "Found", "found")},
            "must_not_exist": {"class": CONTROL_ABSENT, "found": field(CONTROL_ABSENT, "Found", "found")},
        },
        "tdb_prefix_matches": result.get("prefix_matches") or result.get("prefixMatches") or [],
        "available_runtime_api": result.get("available_runtime_api") or result.get("availableRuntimeApi") or [],
        "raw_classes": result.get("classes") or [],
    }

    found = bool(report["TDbPipe"]["found"])
    control_ok = (report["controls"]["must_exist"]["found"] is True
                  and report["controls"]["must_not_exist"]["found"] is False)

    report["assertions"] = {
        "probe_succeeded": bool(response.get("success")),
        "control_present_class_found": report["controls"]["must_exist"]["found"] is True,
        "control_absent_class_not_found": report["controls"]["must_not_exist"]["found"] is False,
        "probe_is_trustworthy": control_ok,
        "tdbpipe_rxclass_found": found,
    }
    report["status"] = (
        "S8_1_TIANZHENG_RUNTIME_AVAILABLE" if (found and control_ok)
        else "TDBPIPE_RXCLASS_NOT_RESOLVED"
    )

    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if (found and control_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
