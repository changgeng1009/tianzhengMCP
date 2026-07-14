from __future__ import annotations

from typing import Any


def build_water_network(objects: list[dict[str, Any]]) -> dict[str, Any]:
    """保留对象级连接关系；真实容差和楼层规则由后续样本配置提供。"""
    nodes = []
    edges = []
    for obj in objects:
        object_id = str(obj.get("object_id") or obj.get("handle") or "")
        geometry = obj.get("geometry") or {}
        if geometry.get("start_point") and geometry.get("end_point"):
            edges.append({"object_id": object_id, "start": geometry["start_point"], "end": geometry["end_point"]})
        else:
            nodes.append({"object_id": object_id, "point": geometry.get("insert_point") or geometry.get("center")})
    return {"nodes": nodes, "edges": edges, "connection_validation_completed": False}
