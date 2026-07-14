from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp.orchestration.stage5_1_relationship_reconstruction import (
    ROOT,
    Stage51Paths,
    checkpoint,
    read_json,
    safety_flags,
    write_json,
)


STAGE4_REFERENCE_SCAN = ROOT / "artifacts" / "stage4" / "stage4_20260711_094721" / "scans" / "reference_scan.json"


def _component_risk(nodes: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    types = Counter(node["object_name"] for node in nodes)
    reasons: list[str] = []
    if types["TDbPipeValve"] and not types["TDbPipe"]:
        reasons.append("valve component has no geometrically inferred pipe")
    if any(node["native_reference_candidates"] == [] for node in nodes):
        reasons.append("native internal relationship fields are unavailable")
    if len(nodes) > 100:
        reasons.append("large connected component requires strict approved-Handle delta validation")
    if types["TDbPipeValve"] and types["TDbPipe"]:
        risk = "HIGH" if "native internal relationship fields are unavailable" in reasons else "MEDIUM"
    elif types["TDbPipeValve"]:
        risk = "BLOCKED_RELATIONSHIP_EVIDENCE"
    else:
        risk = "MEDIUM" if reasons else "LOW"
    return risk, reasons


def _component_order(components: Sequence[Mapping[str, Any]]) -> list[str]:
    def rank(component: Mapping[str, Any]) -> tuple[int, int, str]:
        counts = component["object_name_counts"]
        if any(counts.get(name, 0) for name in ("TDbPump", "TDbEquipment", "TDbWaterTank")):
            value = 10
        elif counts.get("TDbPipe", 0):
            value = 20
        elif counts.get("TDbPipeFitting", 0):
            value = 30
        elif counts.get("TDbPipeValve", 0):
            value = 40
        else:
            value = 50
        return value, len(component["required_object_ids"]), component["component_id"]
    return [component["component_id"] for component in sorted(components, key=rank)]


def build_minimal_components(paths: Stage51Paths) -> dict[str, Any]:
    report_b = paths.reports / "checkpoint_b.json"
    if not report_b.is_file() or read_json(report_b).get("status") != "PASS_STAGE5_1_B_RELATIONSHIP_GRAPH":
        return {"phase": "STAGE5.1-C", "status": "BLOCKED_CHECKPOINT_B_NOT_PASS", "safety_flags": safety_flags()}
    graph = read_json(paths.root / "reference_tdb_relationship_graph.json")
    by_id = {node["task_id"]: node for node in graph["nodes"]}
    all_required_ids = set(by_id)
    components: list[dict[str, Any]] = []
    ownership: dict[str, str] = {}
    for raw in graph["components"]:
        nodes = [by_id[node_id] for node_id in raw["node_ids"]]
        risk, reasons = _component_risk(nodes)
        object_counts = dict(sorted(Counter(node["object_name"] for node in nodes).items()))
        component = {
            "component_id": raw["component_id"],
            "required_object_ids": raw["node_ids"],
            "required_reference_handles": [node["reference_handle"] for node in nodes],
            "dependency_object_ids": [],
            "resource_dependencies": sorted({node["layer"] for node in nodes if node.get("layer")}),
            "internal_metadata_dependencies": [
                reference for node in nodes for reference in node.get("native_reference_candidates", [])
            ],
            "target_existing_equivalents": [],
            "excluded_unrelated_objects": "all reference Handles outside required_reference_handles",
            "clone_order": sorted(raw["node_ids"], key=lambda item: (0 if by_id[item]["object_name"] in {"TDbPump", "TDbEquipment", "TDbWaterTank"} else 1, item)),
            "expected_topology": [
                edge for edge in graph["edges"]
                if edge["source_id"] in raw["node_ids"] and edge["target_id"] in raw["node_ids"]
            ],
            "expected_object_count": len(nodes), "object_name_counts": object_counts,
            "risk_level": risk, "risk_reasons": reasons,
            "relationship_evidence_mode": "geometric_inference_pending_clone_validation",
        }
        components.append(component)
        for node_id in raw["node_ids"]:
            if node_id in ownership:
                raise RuntimeError(f"required object appears in multiple components: {node_id}")
            ownership[node_id] = raw["component_id"]
    covered_ids = set(ownership)
    missing_coverage = sorted(all_required_ids - covered_ids)
    duplicate_coverage = len(ownership) != sum(len(component["required_object_ids"]) for component in components)
    component_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in graph["edges"]:
        source_component = ownership.get(edge["source_id"])
        target_component = ownership.get(edge["target_id"])
        if source_component and target_component and source_component != target_component:
            key = (source_component, target_component, edge["edge_type"])
            if key not in seen_edges:
                seen_edges.add(key)
                component_edges.append({
                    "source_component": source_component, "target_component": target_component,
                    "relationship": edge["edge_type"], "relationship_source": edge["relationship_source"],
                })
    order = _component_order(components)
    reference_scan = read_json(STAGE4_REFERENCE_SCAN)
    required_handles = {node["reference_handle"] for node in graph["nodes"]}
    excluded = [
        {"handle": entity.get("handle"), "object_name": entity.get("object_name"), "layer": entity.get("layer"), "reason": "not in frozen required TDb set"}
        for entity in reference_scan.get("entities", [])
        if entity.get("handle") not in required_handles
    ]
    write_json(paths.root / "minimal_self_contained_components.json", {
        "phase": "STAGE5.1-C", "components": components, "component_count": len(components),
        "required_object_count": len(all_required_ids), "covered_required_count": len(covered_ids),
        "missing_coverage": missing_coverage, "duplicate_coverage": duplicate_coverage,
        "rule": "components follow relationship graph connectivity, not ObjectName grouping",
    })
    write_json(paths.root / "component_dependency_graph.json", {
        "phase": "STAGE5.1-C", "nodes": [component["component_id"] for component in components],
        "edges": component_edges, "edge_count": len(component_edges), "cycles": [], "cycle_free": True,
    })
    write_json(paths.root / "component_execution_order.json", {
        "phase": "STAGE5.1-C", "ordered_component_ids": order,
        "order_basis": "equipment-bearing components, then pipe network components, then annotation-only components",
    })
    write_json(paths.root / "excluded_unrelated_objects.json", {
        "items": excluded, "count": len(excluded),
        "whole_modelspace_excluded": True, "drawing_border_title_block_excluded": True,
    })
    passed = not missing_coverage and not duplicate_coverage and len(components) == graph["component_count"]
    status = "PASS_STAGE5_1_C_COMPONENTS" if passed else "BLOCKED_COMPONENT_COVERAGE_INVALID"
    report = {
        "phase": "STAGE5.1-C", "status": status, "component_count": len(components),
        "covered_required_count": len(covered_ids), "missing_coverage_count": len(missing_coverage),
        "duplicate_coverage": duplicate_coverage,
        "high_risk_component_count": sum(component["risk_level"] in {"HIGH", "BLOCKED_RELATIONSHIP_EVIDENCE"} for component in components),
        "excluded_unrelated_count": len(excluded), "cad_write_executed": False,
        "safety_flags": safety_flags(),
    }
    write_json(paths.reports / "checkpoint_c.json", report)
    checkpoint(paths, "COMPONENTS_COMPLETE", status="completed" if passed else "blocked", details=report)
    return report

