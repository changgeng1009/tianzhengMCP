import json
from pathlib import Path


class TestD462NoExec:
    def test_lisp_no_create_entity(self):
        text = Path('autocad_lisp/d46_anchor_capture.lsp').read_text(encoding='utf-8')
        for keyword in ['entmake', 'vla-add', '_line', '_circle', '_pline']:
            assert keyword not in text.lower()

    def test_runner_no_production(self, tmp_path):
        from mcp.alignment.d46_anchor_calibration_runner import run_d4_6_2_calibration

        anchors = tmp_path / 'anchors.json'
        anchors.write_text(json.dumps({
            'anchor_count': 3,
            'reference_anchor_points': [[0, 0, 0], [100, 0, 0], [0, 100, 0]],
            'sandbox_anchor_points': [[0, 0, 0], [150, 0, 0], [0, 150, 0]],
        }), encoding='utf-8')
        result = run_d4_6_2_calibration(anchors, tmp_path / 'calibration.json')
        assert result.get('production_d1_allowed', True) is False
        assert result.get('sendcommand_used', True) is False

    def test_loader_source_safe(self):
        from mcp.alignment.anchor_json_loader import load_anchors

        anchors = load_anchors()
        if anchors:
            assert anchors.get('source_dwg_opened', True) is False
