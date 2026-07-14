from __future__ import annotations


def _phase8_graph(building_id: str, pipe_ids: list[str], confidence: float = 0.9) -> dict:
    return {
        "buildings": [
            {
                "id": building_id,
                "label": building_id,
                "pipe_ids": pipe_ids,
                "valve_ids": ["v1"] if pipe_ids else [],
                "sprinkler_ids": ["s1", "s2"] if pipe_ids else [],
            }
        ],
        "pipes": [
            {
                "id": pipe_id,
                "building_id": building_id,
                "start": [index * 100.0, 0.0, 0.0],
                "end": [(index + 1) * 100.0, 0.0, 0.0],
                "dn": 50,
                "system_type": "给水",
                "confidence": confidence,
            }
            for index, pipe_id in enumerate(pipe_ids)
        ],
        "valves": [
            {
                "id": "v1",
                "building_id": building_id,
                "position": [50.0, 0.0, 0.0],
                "confidence": confidence,
            }
        ]
        if pipe_ids
        else [],
        "sprinklers": [
            {
                "id": "s1",
                "building_id": building_id,
                "position": [25.0, 25.0, 0.0],
                "confidence": confidence,
            },
            {
                "id": "s2",
                "building_id": building_id,
                "position": [75.0, 25.0, 0.0],
                "confidence": confidence,
            },
        ]
        if pipe_ids
        else [],
    }


def test_multi_source_loader_normalizes_pdf_png_and_dwg_graphs() -> None:
    from mcp.source_loader import MultiSourceSemanticLoader

    loader = MultiSourceSemanticLoader()
    result = loader.load_sources(
        [
            {"type": "pdf", "path": "reference.pdf", "semantic_graph": _phase8_graph("A栋", ["p1"])},
            {"type": "png", "path": "reference.png", "semantic_graph": _phase8_graph("A栋", ["p2"])},
            {"type": "dwg", "path": "target.dwg", "semantic_graph": _phase8_graph("Bldg_03", [])},
        ]
    )

    graph = result["semantic_graph"]
    assert result["status"] == "success"
    assert result["confidence"] >= 0.8
    assert result["source_types"] == ["pdf", "png", "dwg"]
    assert {building["id"] for building in graph["buildings"]} == {"A栋", "Bldg_03"}
    assert {pipe["id"] for pipe in graph["pipes"]} == {"p1", "p2"}
    assert "warnings" in result


def test_structural_fingerprint_alignment_maps_reference_to_target() -> None:
    from mcp.alignment_v2 import BuildingAlignmentV2, StructuralFingerprintBuilder

    reference = _phase8_graph("A栋", ["p1", "p2"])
    target = _phase8_graph("Bldg_03", ["t1", "t2"])

    fingerprints = StructuralFingerprintBuilder().build_graph_fingerprints(reference)
    result = BuildingAlignmentV2().align(reference, target)

    assert fingerprints["A栋"]["pipe_density"] == 2.0
    assert fingerprints["A栋"]["valve_distribution"]["count"] == 1
    assert fingerprints["A栋"]["sprinkler_layout_pattern"] == "2-point-linear"
    assert fingerprints["A栋"]["topology_hash"]
    assert result["mapping"][0]["reference_building"] == "A栋"
    assert result["mapping"][0]["target_building"] == "Bldg_03"
    assert result["mapping"][0]["confidence"] > 0.85
    assert "pipe_density_match" in result["mapping"][0]["reason"]
    assert "system_structure_match" in result["mapping"][0]["reason"]


def test_semantic_diff_v2_and_confidence_repair_gate() -> None:
    from mcp.diff_v2 import SemanticDiffV2
    from mcp.repair_v2 import ConfidenceAwareRepairEngine

    reference = _phase8_graph("A栋", ["high", "review", "blocked"])
    reference["pipes"][0]["confidence"] = 0.92
    reference["pipes"][1]["confidence"] = 0.72
    reference["pipes"][2]["confidence"] = 0.55
    target = _phase8_graph("Bldg_03", [])

    diff = SemanticDiffV2().compare(reference, target, alignment_confidence=0.94)
    plan = ConfidenceAwareRepairEngine().generate(diff)

    assert [item["reference_id"] for item in diff["true_missing"]] == ["high"]
    assert [item["reference_id"] for item in diff["design_variation"]] == ["review"]
    assert [item["reference_id"] for item in diff["uncertain"]] == ["blocked"]
    actions = {action["source_id"]: action for action in plan["actions"]}
    assert actions["high"]["auto_execute"] is True
    assert actions["high"]["execution_decision"] == "auto_execute"
    assert actions["review"]["auto_execute"] is False
    assert actions["review"]["execution_decision"] == "needs_review"
    assert actions["blocked"]["auto_execute"] is False
    assert actions["blocked"]["execution_decision"] == "blocked"


def test_repair_optimizer_removes_duplicates_and_keeps_shorter_path() -> None:
    from mcp.repair_v2 import RepairPlanOptimizer

    plan = {
        "actions": [
            {
                "action_id": "long",
                "type": "add_pipe",
                "start": [0.0, 0.0, 0.0],
                "end": [200.0, 0.0, 0.0],
                "dn": 50,
                "system_type": "给水",
                "confidence": 0.91,
                "auto_execute": True,
            },
            {
                "action_id": "short",
                "type": "add_pipe",
                "start": [0.0, 0.0, 0.0],
                "end": [100.0, 0.0, 0.0],
                "dn": 50,
                "system_type": "给水",
                "confidence": 0.93,
                "auto_execute": True,
            },
        ]
    }

    optimized = RepairPlanOptimizer().optimize(plan)

    assert [action["action_id"] for action in optimized["actions"]] == ["short"]
    assert optimized["optimization"]["removed_duplicates"] == ["long"]
