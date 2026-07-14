from pathlib import Path

class TestD46Safety:
    def test_click_script_no_sendcommand(self):
        t = Path('mcp/alignment/click_anchor_capture.py').read_text(encoding='utf-8')
        assert 'SendCommand' not in t

    def test_calib_script_no_sendcommand(self):
        t = Path('mcp/alignment/click_anchor_calibration_runner.py').read_text(encoding='utf-8')
        assert 'SendCommand' not in t

    def test_no_save(self):
        t = Path('mcp/alignment/click_anchor_capture.py').read_text(encoding='utf-8')
        assert 'Save' not in t

    def test_no_tg_commands(self):
        t = Path('mcp/alignment/click_anchor_capture.py').read_text(encoding='utf-8')
        for kw in ['hsxg','TPIPE','TSaveAs','NETLOAD']:
            assert kw not in t
