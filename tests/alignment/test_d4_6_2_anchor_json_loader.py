import json, pytest
from pathlib import Path
from mcp.alignment.anchor_json_loader import load_anchors

class TestD462Loader:
    def test_load_sample(self):
        sample = {'phase':'D4.6.2','anchor_count':3,
            'reference_anchor_points':[[0,0,0],[100,0,0],[0,100,0]],
            'sandbox_anchor_points':[[0,0,0],[150,0,0],[0,150,0]],
            'source_dwg_opened':False}
        Path('artifacts/alignment/anchors_d4_6.json').parent.mkdir(parents=True,exist_ok=True)
        json.dump(sample, open('artifacts/alignment/anchors_d4_6.json','w',encoding='utf-8'))
        a = load_anchors()
        assert a is not None and a['anchor_count'] == 3

    def test_lisp_has_getpoint(self):
        t = Path('autocad_lisp/d46_anchor_capture.lsp').read_text(encoding='utf-8')
        assert 'getpoint' in t.lower()

    def test_runner_calibrates(self):
        from mcp.alignment.d46_anchor_calibration_runner import run_d4_6_2_calibration
        r = run_d4_6_2_calibration()
        assert r['phase'] == 'D4.6.2' and 'confidence' in r

    def test_lisp_no_exec_drawing(self):
        t = Path('autocad_lisp/d46_anchor_capture.lsp').read_text(encoding='utf-8')
        for kw in ['entmake','vla-addline','vla-addcircle','_line','_circle']:
            assert kw not in t.lower()
