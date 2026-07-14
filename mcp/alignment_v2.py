from __future__ import annotations

import hashlib
from typing import Any


class StructuralFingerprintBuilder:
    def build_graph_fingerprints(self, semantic_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
        fingerprints: dict[str, dict[str, Any]] = {}
        for building in semantic_graph.get("buildings", []):
            building_id = str(building.get("id") or building.get("label") or "")
            pipes = _entities_for_building(semantic_graph.get("pipes", []), building, "pipe_ids")
            valves = _entities_for_building(semantic_graph.get("valves", []), building, "valve_ids")
            sprinklers = _entities_for_building(
                semantic_graph.get("sprinklers", []), building, "sprinkler_ids"
            )
            systems = sorted({str(pipe.get("system_type") or "unknown") for pipe in pipes})
            topology_text = "|".join(
                [
                    str(len(pipes)),
                    str(len(valves)),
                    str(len(sprinklers)),
                    ",".join(systems),
                ]
            )
            fingerprints[building_id] = {
                "building_id": building_id,
                "pipe_density": float(len(pipes)),
                "valve_distribution": {
                    "count": len(valves),
                    "positions": [valve.get("position") for valve in valves if valve.get("position")],
                },
                "sprinkler_layout_pattern": _sprinkler_pattern(sprinklers),
                "systems": systems,
                "topology_hash": hashlib.sha1(topology_text.encode("utf-8")).hexdigest()[:12],
            }
        return fingerprints


class BuildingAlignmentV2:
    def __init__(self, fingerprint_builder: StructuralFingerprintBuilder | None = None) -> None:
        self.fingerprint_builder = fingerprint_builder or StructuralFingerprintBuilder()

    def align(self, reference_graph: dict[str, Any], target_graph: dict[str, Any]) -> dict[str, Any]:
        reference_fingerprints = self.fingerprint_builder.build_graph_fingerprints(reference_graph)
        target_fingerprints = self.fingerprint_builder.build_graph_fingerprints(target_graph)
        reference_labels = _building_labels(reference_graph)
        target_labels = _building_labels(target_graph)
        mapping: list[dict[str, Any]] = []

        for reference_id, reference_fp in reference_fingerprints.items():
            best_target_id = None
            best_score = -1.0
            best_reason: list[str] = []
            for target_id, target_fp in target_fingerprints.items():
                score, reason = _fingerprint_similarity(reference_fp, target_fp)
                if reference_labels.get(reference_id) and reference_labels.get(reference_id) == target_labels.get(target_id):
                    score = max(score, 0.94)
                    if "label_match" not in reason:
                        reason.append("label_match")
                if score > best_score:
                    best_score = score
                    best_target_id = target_id
                    best_reason = reason
            if best_target_id is not None:
                mapping.append(
                    {
                        "reference_building": reference_id,
                        "target_building": best_target_id,
                        "confidence": round(best_score, 4),
                        "reason": best_reason,
                    }
                )

        return {
            "mapping": mapping,
            "reference_fingerprints": reference_fingerprints,
            "target_fingerprints": target_fingerprints,
        }


def _entities_for_building(
    entities: list[dict[str, Any]],
    building: dict[str, Any],
    id_field: str,
) -> list[dict[str, Any]]:
    building_id = building.get("id")
    explicit_ids = set(building.get(id_field, []))
    return [
        entity
        for entity in entities
        if entity.get("building_id") == building_id or entity.get("id") in explicit_ids
    ]


def _building_labels(graph: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for building in graph.get("buildings", []):
        building_id = str(building.get("id") or building.get("label") or "")
        label = str(building.get("label") or building_id)
        labels[building_id] = label
    return labels


def _sprinkler_pattern(sprinklers: list[dict[str, Any]]) -> str:
    count = len(sprinklers)
    if count == 0:
        return "none"
    if count == 1:
        return "1-point"
    return f"{count}-point-linear"


def _fingerprint_similarity(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, list[str]]:
    scores: list[float] = []
    reasons: list[str] = []

    pipe_score = _ratio_similarity(left["pipe_density"], right["pipe_density"])
    scores.append(pipe_score)
    if pipe_score >= 0.8:
        reasons.append("pipe_density_match")

    valve_score = _ratio_similarity(
        left["valve_distribution"]["count"],
        right["valve_distribution"]["count"],
    )
    scores.append(valve_score)
    if valve_score >= 0.8:
        reasons.append("layout_similarity")

    sprinkler_score = 1.0 if left["sprinkler_layout_pattern"] == right["sprinkler_layout_pattern"] else 0.5
    scores.append(sprinkler_score)
    if sprinkler_score >= 0.8:
        reasons.append("sprinkler_layout_match")

    system_score = 1.0 if set(left["systems"]) == set(right["systems"]) else 0.6
    scores.append(system_score)
    if system_score >= 0.8:
        reasons.append("system_structure_match")

    return sum(scores) / len(scores), reasons


def _ratio_similarity(left: float, right: float) -> float:
    larger = max(float(left), float(right), 1.0)
    return 1.0 - abs(float(left) - float(right)) / larger
