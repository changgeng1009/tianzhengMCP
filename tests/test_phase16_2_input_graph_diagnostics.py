from __future__ import annotations

import json


def test_dwg_source_without_semantic_graph_outputs_empty_reason() -> None:
    from mcp.diagnostics.input_graph import diagnose_dwg_source

    result = diagnose_dwg_source({"type": "dwg", "path": "target.dwg"})

    assert result["diagnostics"]["loader_strategy"] == "semantic_graph_only"
    assert result["diagnostics"]["semantic_graph_provided"] is False
    assert result["diagnostics"]["cad_reader_attempted"] is False
    assert result["diagnostics"]["empty_reason"] == "dwg_loader_strategy=semantic_graph_only"
    assert result["graph"]["metadata"]["empty_reason"] == "dwg_loader_strategy=semantic_graph_only"


class _FakeCadReader:
    available = True

    def inspect(self, path: str) -> dict:
        return {
            "document_resolved": True,
            "modelspace_entity_count": 2,
            "paperspace_entity_count": 0,
            "entity_type_histogram": {"Line": 1, "Polyline": 1},
            "t30_object_count": 0,
            "primitive_object_count": 2,
            "block_reference_count": 0,
            "layers": ["W-PIPE"],
            "primitives": [
                {"type": "Line", "start": [0, 0, 0], "end": [100, 0, 0], "layer": "W-PIPE"},
                {"type": "Polyline", "points": [[100, 0, 0], [100, 50, 0]], "layer": "W-PIPE"},
            ],
            "block_references": [],
            "warnings": [],
            "errors": [],
        }


def test_dwg_primitive_fallback_generates_low_confidence_candidates() -> None:
    from mcp.diagnostics.input_graph import diagnose_dwg_source

    result = diagnose_dwg_source(
        {"type": "dwg", "path": "target.dwg", "enable_cad_reader": True},
        cad_reader=_FakeCadReader(),
    )
    graph = result["graph"]

    assert result["diagnostics"]["loader_strategy"] == "cad_reader_primitive_fallback"
    assert result["diagnostics"]["graph_nodes"] == 2
    assert graph["metadata"]["source"] == "dwg_primitive_fallback"
    assert graph["metadata"]["not_t30_semantic"] is True
    assert graph["metadata"]["confidence"] == 0.35
    assert all(pipe["confidence"] < 0.6 for pipe in graph["pipes"])


def test_dwg_fallback_candidates_do_not_auto_execute() -> None:
    from mcp.diagnostics.input_graph import diagnose_dwg_source

    result = diagnose_dwg_source(
        {"type": "dwg", "path": "target.dwg", "enable_cad_reader": True},
        cad_reader=_FakeCadReader(),
    )

    assert all(pipe["metadata"]["auto_execute_allowed"] is False for pipe in result["graph"]["pipes"])


def test_pdf_rendered_but_zero_visual_elements_outputs_empty_reason(tmp_path, monkeypatch) -> None:
    from mcp.diagnostics import input_graph
    from mcp.vision.models import SemanticGraph, VisionParseResult

    class EmptyProvider:
        def parse_pdf(self, path: str):
            graph = {
                "buildings": [],
                "pipes": [],
                "valves": [],
                "sprinklers": [],
                "texts": [],
                "symbols": [],
                "metadata": {"confidence": 0.0, "warnings": ["CVVisionProvider detected no visual elements"]},
            }
            return VisionParseResult(path, "pdf", 0, [], ["CVVisionProvider detected no visual elements"], 0.0, SemanticGraph(**graph))

        def to_semantic_graph(self, result):
            return result.semantic_graph.to_dict()

    monkeypatch.setattr(
        input_graph,
        "render_pdf_to_images",
        lambda path, output_dir=None: {
            "status": "success",
            "images": [{"path": str(tmp_path / "page.png"), "page_index": 0}],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        input_graph,
        "analyze_image_diagnostics",
        lambda path: {
            "image_size": [1000, 800],
            "preprocess_steps": ["grayscale", "edge_detection"],
            "edge_pixel_count": 0,
            "line_candidate_count": 0,
            "contour_candidate_count": 0,
            "symbol_candidate_count": 0,
            "text_candidate_count": 0,
            "warnings": [],
            "errors": [],
        },
    )

    result = input_graph.diagnose_pdf_source({"type": "pdf", "path": "ref.pdf"}, vision_provider=EmptyProvider())

    assert result["diagnostics"]["pdf_rendered"] is True
    assert result["diagnostics"]["empty_reason"] == "pdf_rendered_but_no_visual_elements"
    assert result["graph"]["metadata"]["empty_reason"] == "pdf_rendered_but_no_visual_elements"


def test_pdf_line_fallback_generates_only_low_confidence_candidate(tmp_path, monkeypatch) -> None:
    from mcp.diagnostics import input_graph
    from mcp.vision.models import SemanticGraph, VisionParseResult

    class EmptyProvider:
        def parse_pdf(self, path: str):
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

    monkeypatch.setattr(
        input_graph,
        "render_pdf_to_images",
        lambda path, output_dir=None: {
            "status": "success",
            "images": [{"path": str(tmp_path / "page.png"), "page_index": 0}],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        input_graph,
        "analyze_image_diagnostics",
        lambda path: {
            "image_size": [1200, 900],
            "preprocess_steps": ["grayscale", "canny", "hough_lines_p"],
            "edge_pixel_count": 5000,
            "line_candidate_count": 0,
            "contour_candidate_count": 0,
            "symbol_candidate_count": 0,
            "text_candidate_count": 0,
            "detector_thresholds": {"hough_threshold": 80, "min_line_length": 80},
            "warnings": ["line detector returned 0 candidates"],
            "errors": [],
        },
    )

    result = input_graph.diagnose_pdf_source({"type": "pdf", "path": "ref.pdf"}, vision_provider=EmptyProvider())
    symbols = result["graph"]["symbols"]

    assert symbols[0]["symbol_type"] == "drawing_content_candidate"
    assert symbols[0]["confidence"] == 0.45
    assert symbols[0]["metadata"]["auto_execute_allowed"] is False


def test_input_readiness_status_variants() -> None:
    from mcp.diagnostics.input_graph import input_readiness_status

    empty = {"pipes": [], "symbols": [], "buildings": [], "valves": [], "sprinklers": [], "texts": []}
    non_empty = {**empty, "pipes": [{"id": "p1"}]}

    assert input_readiness_status(empty, empty) == "both_empty"
    assert input_readiness_status(empty, non_empty) == "target_empty"
    assert input_readiness_status(non_empty, empty) == "reference_empty"
    assert input_readiness_status(non_empty, non_empty) == "ready_for_alignment"


def test_diagnostics_cli_outputs_json(tmp_path, monkeypatch) -> None:
    from mcp.diagnostics import input_graph_diagnostics

    output = tmp_path / "diag.json"
    monkeypatch.setattr(
        input_graph_diagnostics,
        "run_input_graph_diagnostics",
        lambda target_dwg, reference_pdf: {
            "target": {"diagnostics": {"source_type": "dwg"}, "graph": {"pipes": []}},
            "reference": {"diagnostics": {"source_type": "pdf"}, "graph": {"pipes": []}},
            "input_readiness_status": "both_empty",
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
            "--output",
            str(output),
        ]
    )

    assert code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["input_readiness_status"] == "both_empty"


def test_loader_and_report_include_input_graph_diagnostics(tmp_path) -> None:
    from mcp.acceptance.acceptance_report import generate_acceptance_report
    from mcp.acceptance.models import AcceptanceRunResult
    from mcp.source_loader import MultiSourceSemanticLoader

    loader = MultiSourceSemanticLoader()
    loaded = loader.load_sources([{"type": "dwg", "role": "target", "path": "target.dwg"}])

    assert loaded["target_graph_diagnostics"]["empty_reason"] == "dwg_loader_strategy=semantic_graph_only"

    result = AcceptanceRunResult(
        run_id="diag",
        status="warning",
        e2e_result={
            "pipeline_result": {
                "data": {
                    "report": {
                        "target_graph_diagnostics": loaded["target_graph_diagnostics"],
                        "reference_graph_diagnostics": {},
                        "target_graph_empty_reason": "dwg_loader_strategy=semantic_graph_only",
                        "reference_graph_empty_reason": "",
                        "input_readiness_status": "target_empty",
                    }
                }
            }
        },
    )
    generate_acceptance_report(result, str(tmp_path))
    markdown = (tmp_path / "diag.md").read_text(encoding="utf-8")

    assert "## 输入图诊断" in markdown
    assert "target_empty" in markdown
