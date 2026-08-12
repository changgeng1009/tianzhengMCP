"""S10.0 native object discovery.

Asks the LIVE AutoCAD process which Tianzheng runtime classes exist, for every object family
S10 targets. Nothing here is inferred from a layer, a block name or an icon: a class counts as
present only when the runtime class registry resolves it.

Read-only. Creates nothing, opens no document, mutates no database.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_nextgen.backends.plugin_transport import (  # noqa: E402
    PluginTransportClient,
    PluginTransportConfig,
)

#: Candidate runtime classes per logical family, drawn from the exported C++ symbols in the
#: Tianzheng pipe modules. Presence here is a QUESTION, never an assertion.
CANDIDATES: dict[str, list[str]] = {
    "pipe": ["TDbPipe", "TDbPipePrototype", "TDbPipeBase", "TDbDoubleLinePipe"],
    "valve": ["TDbPipeValve", "TDbPipeAttachment"],
    "fitting": ["TDbPipeFitting", "TDbPipeNode", "TDbDoubleLinePipeReducer"],
    "equipment": ["TDbEEquipment", "TDbEquipment", "TDbPump", "TDbWaterTank", "TDbWell",
                  "TDbSumpPit", "TDbPool", "TDbFireExtinguisher", "TDbSanitary",
                  "TDbEquRelativeDim", "TDbSprinkler"],
    "annotation": ["TDbPipeLabel", "TDbPipeText", "TDbPipeMultDim", "TDbVPipeDim",
                   "TDbWellDim", "TDbCableDim", "TDbMText", "TDbText"],
    "controls": ["AcDbLine", "TDbDefinitelyNotARealClass"],
}


def main() -> int:
    token = os.environ.get("TIANZHENG_PLUGIN_TOKEN", "")
    port = int(os.environ.get("TIANZHENG_PLUGIN_PORT", "0") or 0)
    if not token or not port:
        print("TIANZHENG_PLUGIN_TOKEN / TIANZHENG_PLUGIN_PORT required", file=sys.stderr)
        return 2

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "artifacts/s10_tianzheng_engineering_objects/native_class_inventory.json")

    every = [name for names in CANDIDATES.values() for name in names]
    client = PluginTransportClient(
        PluginTransportConfig(host="127.0.0.1", port=port, timeout_seconds=120.0),
        auth_token=token)
    try:
        capabilities = client.connect()
        response = client.call("diagnostic_query_rxclass", mutating=False,
                               parameters={"class_names": every})
    finally:
        client.disconnect()

    result = response.get("result") or {}
    by_name = {c.get("requested_class_name"): c for c in (result.get("classes") or [])}

    families: dict[str, Any] = {}
    for family, names in CANDIDATES.items():
        rows = []
        for name in names:
            entry = by_name.get(name) or {}
            rows.append({
                "class_name": name,
                "found": bool(entry.get("found")),
                "runtime_class": entry.get("runtime_class_name") or "",
                "dxf_name": entry.get("dxf_name") or "",
                "parent_class": entry.get("parent_class") or "",
                "ancestry": entry.get("ancestry") or [],
                "is_entity": bool(entry.get("is_entity")),
            })
        families[family] = {
            "candidates": rows,
            "found": [r["class_name"] for r in rows if r["found"]],
            "absent": [r["class_name"] for r in rows if not r["found"]],
        }

    controls = families["controls"]
    trustworthy = ("AcDbLine" in controls["found"]
                   and "TDbDefinitelyNotARealClass" in controls["absent"])

    report = {
        "probe": "s10_0_native_class_inventory",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "autocad_version": result.get("autocad_version"),
        "plugin_version": result.get("plugin_version"),
        "tianzheng_loaded": bool(result.get("tianzheng_loaded")),
        "handshake": {
            "tianzheng_product": capabilities.tianzheng_product,
            "tianzheng_version": capabilities.tianzheng_version,
            "tdbpipe_rxclass_available": capabilities.tdbpipe_rxclass_available,
        },
        "source_of_truth": "live AutoCAD runtime class registry via "
                           "SystemObjects.ClassDictionary.At(string)",
        "controls_behaved_correctly": trustworthy,
        "families": families,
        "note": "A resolved runtime class proves the object model exists. It does NOT mean the "
                "object can be created: capability stays NOT_IMPLEMENTED until creation, "
                "persistence and idempotency are all demonstrated.",
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
                   encoding="utf-8")

    for family, data in families.items():
        print(f"{family:<12} found={data['found']}")
    print(f"\ncontrols trustworthy: {trustworthy}\nwritten: {out}")
    return 0 if trustworthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
