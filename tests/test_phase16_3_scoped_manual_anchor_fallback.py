from __future__ import annotations

import json


def _graph() -> dict:
    return {
        "buildings": [],
        "pipes": [
            {"id": "inside", "start": [10, 10, 0], "end": [20, 10, 0], "confidence": 0.4},
            {"id": "outside", "start": [100, 100, 0], "end": [120, 100, 0], "confidence": 0.4},
        ],
        "valves": [],
        "sprinklers": [],
        "texts": [],
        "symbols": [{"id": "sym", "bbox": [5, 5, 15, 15], "confidence": 0.45}],
        "metadata": {"confidence": 0.4},
    }


def test_scope_disabled_keeps_old_behavior() -> None:
    from mcp.diagnostics.input_graph import apply_scope_to_graph

    scoped, summary = apply_scope_to_graph(_graph(), {"enabled": False}, "reference")

    assert len(scoped["pipes"]) == 2
    assert summary["enabled"] is False
    assert summary["filtered_out_count"] == 0


def test_scope_bbox_filters_reference_elements() -> None:
    from mcp.diagnostics.input_graph import apply_scope_to_graph

    scoped, summary = apply_scope_to_graph(
        _graph(),
        {"enabled": True, "mode": "bbox", "reference_bbox": [0, 0, 50, 50]},
        "reference",
    )

    assert [pipe["id"] for pipe in scoped["pipes"]] == ["inside"]
    assert summary["before_count"] == 3
    assert summary["after_count"] == 2
    assert summary["filtered_out_count"] == 1


def test_scope_bbox_filters_target_elements() -> None:
    from mcp.diagnostics.input_graph import apply_scope_to_graph

    scoped, summary = apply_scope_to_graph(
        _graph(),
        {"enabled": True, "mode": "bbox", "target_bbox": [0, 0, 50, 50]},
        "target",
    )

    assert [pipe["id"] for pipe in scoped["pipes"]] == ["inside"]
    assert summary["side"] == "target"


def test_invalid_bbox_outputs_warning_without_crashing() -> None:
    from mcp.diagnostics.input_graph import apply_scope_to_graph

    scoped, summary = apply_scope_to_graph(
        _graph(),
        {"enabled": True, "mode": "bbox", "reference_bbox": [0, 0, 0, 50]},
        "reference",
    )

    assert len(scoped["pipes"]) == 2
    assert any("invalid bbox" in warning for warning in summary["warnings"])


def test_manual_anchor_pairs_create_anchor_pairs_with_new_format() -> None:
    from mcp.spatial.spatial_alignment import manual_anchor_pairs_from_scenario

    pairs, summary = manual_anchor_pairs_from_scenario(
        [
            {
                "reference_point": [10, 20],
                "reference_space": "image_pixel",
                "target_point": [1000, 2000],
                "target_space": "cad_modelspace",
                "label": "corner",
                "confidence": 0.95,
            }
        ],
        reference_graph={"metadata": {"image_size": [100, 100]}},
    )

    assert len(pairs) == 1
    assert pairs[0].reference_anchor.point.x == 10
    assert pairs[0].target_anchor.point.y == 2000
    assert summary["used_manual_anchors"] is True


def test_manual_anchor_takes_priority_over_auto_matching() -> None:
    from mcp.spatial.spatial_alignment import align_reference_graph_to_target

    result = align_reference_graph_to_target(
        {"pipes": [{"id": "p", "start": [0, 0, 0], "end": [10, 0, 0], "confidence": 0.9}]},
        {"pipes": []},
        manual_anchor_pairs=[
            {
                "reference_point": [0, 0],
                "target_point": [100, 200],
                "label": "manual",
                "confidence": 0.95,
            }
        ],
    ).to_dict()

    assert result["transform"]["transform_type"] == "translation"
    assert result["transform"]["matrix"][0][2] == 100
    assert result["metadata"]["manual_anchor_summary"]["used_manual_anchors"] is True


class _EmptyProvider:
    def parse_pdf(self, path: str):
        from mcp.vision.models import SemanticGraph, VisionParseResult

        graph = {
            "buildings": [],
            "pipes": [],
            "valves": [],
            "sprinklers": [],
            "texts": [],
            "symbols": [],
            "metadata": {"confidence": 0.0, "warnings": []},
        }
        return VisionParseResult(path, "pdf", 0, [], [], 0.0, SemanticGraph(**graph))

    def to_semantic_graph(self, result):
        return result.semantic_graph.to_dict()


def test_pdf_line_candidates_convert_to_pipe_candidate(tmp_path, monkeypatch) -> None:
    from mcp.diagnostics import input_graph

    monkeypatch.setattr(
        input_graph,
        "render_pdf_to_images",
        lambda path, output_dir=None: {"status": "success", "images": [{"path": str(tmp_path / "p.png")}], "warnings": []},
    )
    monkeypatch.setattr(
        input_graph,
        "analyze_image_diagnostics",
        lambda path: {
            "image_size": [1000, 1000],
            "edge_pixel_count": 2000,
            "line_candidate_count": 2,
            "line_candidates": [
                {"points": [[10, 10], [200, 10]], "length": 190, "angle": 0},
                {"points": [[20, 20], [20, 220]], "length": 200, "angle": 90},
            ],
            "warnings": [],
            "errors": [],
        },
    )

    result = input_graph.diagnose_pdf_source(
        {"type": "pdf", "path": "ref.pdf", "max_line_candidates": 10},
        vision_provider=_EmptyProvider(),
    )

    assert len(result["graph"]["pipes"]) == 2
    assert result["diagnostics"]["pdf_line_candidate_summary"]["generated_pipe_candidates"] == 2


def test_pipe_candidate_confidence_is_conservative_and_review_only(tmp_path, monkeypatch) -> None:
    from mcp.diagnostics import input_graph

    monkeypatch.setattr(
        input_graph,
        "render_pdf_to_images",
        lambda path, output_dir=None: {"status": "success", "images": [{"path": str(tmp_path / "p.png")}], "warnings": []},
    )
    monkeypatch.setattr(
        input_graph,
        "analyze_image_diagnostics",
        lambda path: {
            "image_size": [500, 500],
            "edge_pixel_count": 2000,
            "line_candidate_count": 1,
            "line_candidates": [{"points": [[10, 10], [200, 10]], "length": 190, "angle": 0}],
            "warnings": [],
            "errors": [],
        },
    )

    pipe = input_graph.diagnose_pdf_source({"type": "pdf", "path": "ref.pdf"}, vision_provider=_EmptyProvider())["graph"]["pipes"][0]

    assert 0.35 <= pipe["confidence"] <= 0.55
    assert pipe["metadata"]["not_confirmed_pipe"] is True
    assert pipe["metadata"]["auto_execute_allowed"] is False


class _FakeCadReader:
    available = True

    def inspect(self, path: str) -> dict:
        return {
            "document_resolved": True,
            "modelspace_entity_count": 1,
            "entity_type_histogram": {"Line": 1},
            "t30_object_count": 0,
            "primitive_object_count": 1,
            "block_reference_count": 0,
            "layers": ["PIPE"],
            "primitives": [
                {"type": "Line", "start": [0, 0, 0], "end": [100, 0, 0], "layer": "PIPE", "handle": "A1"}
            ],
            "warnings": [],
            "errors": [],
        }


def test_dwg_primitive_line_converts_to_pipe_like_candidate() -> None:
    from mcp.diagnostics.input_graph import diagnose_dwg_source

    pipe = diagnose_dwg_source(
        {"type": "dwg", "path": "target.dwg", "enable_cad_reader": True},
        cad_reader=_FakeCadReader(),
    )["graph"]["pipes"][0]

    assert pipe["type"] == "pipe_like_candidate"
    assert pipe["geometry"]["type"] == "line"
    assert pipe["metadata"]["handle"] == "A1"
    assert pipe["metadata"]["not_t30_semantic"] is True


def test_readiness_status_can_enter_ready_for_manual_anchor_alignment() -> None:
    from mcp.diagnostics.input_graph import input_readiness_status

    graph = {**_graph(), "metadata": {"confidence": 0.4}}

    assert (
        input_readiness_status(
            graph,
            graph,
            manual_anchor_pairs=[{"reference_point": [0, 0], "target_point": [1, 1]}],
        )
        == "ready_for_manual_anchor_alignment"
    )


def test_low_confidence_repair_actions_are_review_required() -> None:
    from mcp.repair_actions.action_builder import build_review_only_repair_actions

    plan = build_review_only_repair_actions(
        {
            "uncertain": [
                {
                    "element_type": "pipe",
                    "element": {
                        "id": "p1",
                        "source_element_id": "p1",
                        "mapped_geometry": {"start": [0, 0, 0], "end": [100, 0, 0]},
                        "confidence": 0.45,
                    },
                    "confidence": 0.45,
                    "reason": "low confidence reference element",
                }
            ]
        },
        {"pipes": []},
        {"pipes": []},
    ).to_dict()

    assert plan["review_actions"][0]["auto_execute"] is False
    assert plan["review_actions"][0]["validation_status"] == "review_required"
    assert plan["review_actions"][0]["confidence"] < 0.85
    assert "manual review required" in plan["review_actions"][0]["reason"]


def test_diagnostics_cli_accepts_scope_and_manual_anchors(tmp_path, monkeypatch) -> None:
    from mcp.diagnostics import input_graph_diagnostics

    output = tmp_path / "diag.json"
    monkeypatch.setattr(
        input_graph_diagnostics,
        "run_input_graph_diagnostics",
        lambda target_dwg, reference_pdf, scope=None, manual_anchor_pairs=None: {
            "target": {"diagnostics": {}},
            "reference": {"diagnostics": {}},
            "scope_summary": {"enabled": True},
            "manual_anchor_summary": {"used_manual_anchors": True},
            "input_readiness_status": "ready_for_manual_anchor_alignment",
            "warnings": [],
            "errors": [],
        },
    )

    code = input_graph_diagnostics.main(
        [
            "--target-dwg",
            "target.dwg",
            "--reference-pdf",
            "ref.pdf",
            "--scope-json",
            json.dumps({"enabled": True}),
            "--manual-anchors-json",
            json.dumps([{"reference_point": [0, 0], "target_point": [1, 1]}]),
            "--output",
            str(output),
        ]
    )

    assert code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["input_readiness_status"] == "ready_for_manual_anchor_alignment"
