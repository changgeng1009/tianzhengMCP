from pathlib import Path

class TestD462NoExec:
    def test_lisp_no_create_entity(self):
        t = Path('autocad_lisp/d46_anchor_capture.lsp').read_text(encoding='utf-8')
        for kw in ['entmake','vla-add','_line','_circle','_pline']:
            assert kw not in t.lower()

    def test_runner_no_production(self):
        from mcp.alignment.d46_anchor_calibration_runner import run_d4_6_2_calibration
        r = run_d4_6_2_calibration()
        assert r.get('production_d1_allowed', True) is False
        assert r.get('sendcommand_used', True) is False

    def test_loader_source_safe(self):
        from mcp.alignment.anchor_json_loader import load_anchors
        a = load_anchors()
        if a: assert a.get('source_dwg_opened', True) is False
