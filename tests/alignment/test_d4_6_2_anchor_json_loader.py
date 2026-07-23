import json
from pathlib import Path

from mcp.alignment.anchor_json_loader import load_anchors


class TestD462Loader:
    @staticmethod
    def _sample_path(tmp_path: Path) -> Path:
        sample = {
            'phase': 'D4.6.2',
            'anchor_count': 3,
            'reference_anchor_points': [[0, 0, 0], [100, 0, 0], [0, 100, 0]],
            'sandbox_anchor_points': [[0, 0, 0], [150, 0, 0], [0, 150, 0]],
            'source_dwg_opened': False,
        }
        path = tmp_path / 'anchors_d4_6.json'
        path.write_text(json.dumps(sample), encoding='utf-8')
        return path

    def test_load_sample(self, tmp_path):
        anchors = load_anchors(self._sample_path(tmp_path))
        assert anchors is not None and anchors['anchor_count'] == 3

    def test_lisp_has_getpoint(self):
        text = Path('autocad_lisp/d46_anchor_capture.lsp').read_text(encoding='utf-8')
        assert 'getpoint' in text.lower()

    def test_runner_calibrates(self, tmp_path):
        from mcp.alignment.d46_anchor_calibration_runner import run_d4_6_2_calibration

        result = run_d4_6_2_calibration(self._sample_path(tmp_path), tmp_path / 'calibration.json')
        assert result['phase'] == 'D4.6.2' and 'confidence' in result

    def test_lisp_no_exec_drawing(self):
        text = Path('autocad_lisp/d46_anchor_capture.lsp').read_text(encoding='utf-8')
        for keyword in ['entmake', 'vla-addline', 'vla-addcircle', '_line', '_circle']:
            assert keyword not in text.lower()
