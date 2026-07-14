from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


def extract_dwg_geometry(path: str | None = None, *, entities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """汇总 backend 已扫描的序列化实体；本模块不连接或打开 CAD。"""
    if path is None or entities is None:
        return {
            "phase": "D3",
            "source": path,
            "status": "BLOCKED",
            "errors": ["explicit path and backend-provided serialized entities are required"],
            "autocad_connected": False,
            "source_dwg_opened": False,
            "dwg_saved": False,
        }

    object_names = [str(item.get("object_name") or item.get("ObjectName") or "unknown") for item in entities]
    layers = [str(item.get("layer") or item.get("Layer") or "") for item in entities]
    counts = dict(Counter(object_names))
    sample = []
    for index, entity in enumerate(entities[:8]):
        sample.append({
            "i": index,
            "ObjectName": object_names[index],
            "Handle": str(entity.get("handle") or entity.get("Handle") or ""),
            "Layer": layers[index],
            "DNDiameter": entity.get("diameter") or entity.get("DNDiameter"),
            "SysType": entity.get("system_type") or entity.get("SysType"),
            "StartPoint": entity.get("start_point") or entity.get("StartPoint"),
            "EndPoint": entity.get("end_point") or entity.get("EndPoint"),
        })
    return {
        "phase": "D3",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": path,
        "status": "PASS",
        "modelspace_count": len(entities),
        "total_entities": len(entities),
        "object_name_counts": counts,
        "layer_counts": dict(Counter(layers)),
        "tdb_pipe_count": counts.get("TDbPipe", 0),
        "tdb_valve_count": counts.get("TDbPipeValve", 0),
        "tdb_fitting_count": counts.get("TDbPipeFitting", 0),
        "tdb_double_line_pipe_count": counts.get("TDbDoubleLinePipe", 0),
        "sample_objects": sample,
        "source_dwg_opened": False,
        "dwg_saved": False,
    }
