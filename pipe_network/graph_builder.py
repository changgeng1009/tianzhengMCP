from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from pipe_network.models import (
    Point3D,
    diameter_source,
    distance,
    entity_center,
    entity_handle,
    normalized_diameter,
    pipe_endpoints,
    point_to_list,
    semantic_type,
)


NODE_PRIORITY = {"junction": 0, "endpoint": 1, "valve": 2, "fitting": 3}


class PipeNetworkGraphBuilder:
    def __init__(self, node_tolerance: float = 50.0) -> None:
        self.node_tolerance = float(node_tolerance)

    def build(self, semantic_model: dict[str, Any]) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        diagnostics = {"skipped_entities": []}

        for entity in semantic_model.get("entities", []):
            if semantic_type(entity) != "pipe":
                continue
            endpoints = pipe_endpoints(entity)
            if endpoints is None:
                diagnostics["skipped_entities"].append(
                    {
                        "handle": entity_handle(entity),
                        "semantic_type": semantic_type(entity),
                        "reason": "missing_pipe_endpoints",
                    }
                )
                continue
            start_node = self._get_or_create_node(nodes, endpoints[0], entity, "endpoint")
            end_node = self._get_or_create_node(nodes, endpoints[1], entity, "endpoint")
            edge_id = f"edge_{len(edges) + 1:04d}"
            edges.append(
                {
                    "id": edge_id,
                    "semantic_type": "pipe",
                    "source_handle": entity_handle(entity),
                    "object_name": entity.get("object_name"),
                    "system_type": entity.get("system_type") or "unknown",
                    "layer": entity.get("layer"),
                    "diameter": normalized_diameter(entity),
                    "diameter_source": diameter_source(entity),
                    "start_node_id": start_node["id"],
                    "end_node_id": end_node["id"],
                    "length": _edge_length(entity, endpoints),
                    "geometry": {
                        "start_point": point_to_list(endpoints[0]),
                        "end_point": point_to_list(endpoints[1]),
                        "source": entity.get("inferred_geometry", {}).get(
                            "source", "semantic_model"
                        ),
                    },
                    "source_entity": {
                        "handle": entity_handle(entity),
                        "object_name": entity.get("object_name"),
                        "semantic_type": semantic_type(entity),
                    },
                }
            )

        for entity in semantic_model.get("entities", []):
            kind = semantic_type(entity)
            if kind not in {"valve", "fitting"}:
                continue
            center = entity_center(entity)
            if center is None:
                diagnostics["skipped_entities"].append(
                    {
                        "handle": entity_handle(entity),
                        "semantic_type": kind,
                        "reason": "missing_entity_center",
                    }
                )
                continue
            self._get_or_create_node(nodes, center, entity, kind)

        self._finalize_node_degrees(nodes, edges)
        systems = self._build_systems(nodes, edges)
        subgraphs = self._build_subgraphs(nodes, edges)
        return {
            "nodes": nodes,
            "edges": edges,
            "systems": systems,
            "subgraphs": subgraphs,
            "diagnostics": diagnostics,
        }

    def _get_or_create_node(
        self,
        nodes: list[dict[str, Any]],
        point: Point3D,
        entity: dict[str, Any],
        node_type: str,
    ) -> dict[str, Any]:
        existing = self._find_nearby_node(nodes, point)
        if existing is not None:
            _merge_node_entity(existing, point, entity, node_type)
            return existing

        node = {
            "id": f"node_{len(nodes) + 1:04d}",
            "node_type": node_type,
            "position": point_to_list(point),
            "system_type": entity.get("system_type") or "unknown",
            "source_handles": [entity_handle(entity)],
            "source_semantic_types": [semantic_type(entity)],
            "connected_edge_ids": [],
            "degree": 0,
            "confidence": 0.85,
            "evidence": "merged_by_endpoint_or_center_with_tolerance",
        }
        nodes.append(node)
        return node

    def _find_nearby_node(self, nodes: list[dict[str, Any]], point: Point3D) -> dict[str, Any] | None:
        for node in nodes:
            node_point = tuple(node["position"])  # type: ignore[arg-type]
            if distance(point, (float(node_point[0]), float(node_point[1]), float(node_point[2]))) <= self.node_tolerance:
                return node
        return None

    def _finalize_node_degrees(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        node_by_id = {node["id"]: node for node in nodes}
        for edge in edges:
            for node_id in (edge["start_node_id"], edge["end_node_id"]):
                node = node_by_id[node_id]
                node["connected_edge_ids"].append(edge["id"])
        for node in nodes:
            node["connected_edge_ids"] = sorted(set(node["connected_edge_ids"]))
            node["degree"] = len(node["connected_edge_ids"])

    def _build_systems(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        node_by_id = {node["id"]: node for node in nodes}
        by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            by_system[str(edge.get("system_type") or "unknown")].append(edge)

        systems = []
        for system_type, system_edges in sorted(by_system.items()):
            node_ids = {
                node_id
                for edge in system_edges
                for node_id in (edge["start_node_id"], edge["end_node_id"])
            }
            diameters = sorted({edge["diameter"] for edge in system_edges if edge.get("diameter")})
            systems.append(
                {
                    "system_type": system_type,
                    "edge_count": len(system_edges),
                    "node_count": len(node_ids),
                    "diameters": diameters,
                    "source_handles": sorted(edge["source_handle"] for edge in system_edges),
                    "node_ids": sorted(node_id for node_id in node_ids if node_id in node_by_id),
                }
            )
        return systems

    def _build_subgraphs(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        edge_by_id = {edge["id"]: edge for edge in edges}
        adjacency: dict[str, set[str]] = defaultdict(set)
        edge_lookup: dict[tuple[str, str], set[str]] = defaultdict(set)
        for edge in edges:
            a = edge["start_node_id"]
            b = edge["end_node_id"]
            adjacency[a].add(b)
            adjacency[b].add(a)
            edge_lookup[(a, b)].add(edge["id"])
            edge_lookup[(b, a)].add(edge["id"])

        node_systems: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            system_type = str(edge.get("system_type") or "unknown")
            node_systems[edge["start_node_id"]].add(system_type)
            node_systems[edge["end_node_id"]].add(system_type)

        subgraphs: list[dict[str, Any]] = []
        visited: set[tuple[str, str]] = set()
        for node in nodes:
            for system_type in sorted(node_systems.get(node["id"], {"unknown"})):
                key = (system_type, node["id"])
                if key in visited:
                    continue
                component_nodes, component_edges = _walk_component(
                    node["id"], system_type, adjacency, edge_lookup, edge_by_id, visited
                )
                if not component_edges:
                    continue
                subgraphs.append(
                    {
                        "id": f"subgraph_{len(subgraphs) + 1:04d}",
                        "system_type": system_type,
                        "node_ids": sorted(component_nodes),
                        "edge_ids": sorted(component_edges),
                        "node_count": len(component_nodes),
                        "edge_count": len(component_edges),
                    }
                )
        return subgraphs


def _merge_node_entity(
    node: dict[str, Any],
    point: Point3D,
    entity: dict[str, Any],
    node_type: str,
) -> None:
    handle = entity_handle(entity)
    if handle not in node["source_handles"]:
        node["source_handles"].append(handle)
    kind = semantic_type(entity)
    if kind not in node["source_semantic_types"]:
        node["source_semantic_types"].append(kind)
    if NODE_PRIORITY.get(node_type, 0) > NODE_PRIORITY.get(node["node_type"], 0):
        node["node_type"] = node_type
        node["position"] = point_to_list(point)
    if node.get("system_type") in {None, "unknown"} and entity.get("system_type"):
        node["system_type"] = entity.get("system_type")


def _edge_length(entity: dict[str, Any], endpoints: tuple[Point3D, Point3D]) -> float:
    length = entity.get("inferred_geometry", {}).get("length")
    try:
        return float(length)
    except (TypeError, ValueError):
        return round(distance(endpoints[0], endpoints[1]), 6)


def _walk_component(
    start_node_id: str,
    system_type: str,
    adjacency: dict[str, set[str]],
    edge_lookup: dict[tuple[str, str], set[str]],
    edge_by_id: dict[str, dict[str, Any]],
    visited: set[tuple[str, str]],
) -> tuple[set[str], set[str]]:
    queue: deque[str] = deque([start_node_id])
    component_nodes: set[str] = set()
    component_edges: set[str] = set()
    while queue:
        node_id = queue.popleft()
        visit_key = (system_type, node_id)
        if visit_key in visited:
            continue
        visited.add(visit_key)
        component_nodes.add(node_id)
        for neighbor in adjacency.get(node_id, set()):
            connecting_edges = [
                edge_by_id[edge_id]
                for edge_id in edge_lookup.get((node_id, neighbor), set())
                if str(edge_by_id[edge_id].get("system_type") or "unknown") == system_type
            ]
            if not connecting_edges:
                continue
            component_edges.update(edge["id"] for edge in connecting_edges)
            queue.append(neighbor)
    return component_nodes, component_edges
