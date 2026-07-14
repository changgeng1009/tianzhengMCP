from pathlib import Path

class TestD461NoExec:
    def test_no_save_in_scripts(self):
        for fn in ['mcp/alignment/click_anchor_capture.py','mcp/alignment/click_anchor_calibration_runner.py']:
            t = Path(fn).read_text(encoding='utf-8')
            assert '.Save(' not in t
            assert 'SaveAs' not in t

    def test_has_safety_flags(self):
        t = Path('mcp/alignment/click_anchor_capture.py').read_text(encoding='utf-8')
        assert 'source_dwg_opened' in t
        assert 'production_d1_allowed' in t
        assert 'sendcommand_used' in t
