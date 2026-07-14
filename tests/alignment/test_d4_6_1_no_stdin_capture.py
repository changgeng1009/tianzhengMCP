from pathlib import Path

class TestD461NoStdin:
    def test_capture_script_no_input(self):
        t = Path('mcp/alignment/click_anchor_capture.py').read_text(encoding='utf-8')
        assert 'input(' not in t
        assert 'raw_input' not in t
        assert 'continue' not in t.lower() or 'continue' in t.lower()[:100]

    def test_runner_script_no_input(self):
        t = Path('mcp/alignment/click_anchor_calibration_runner.py').read_text(encoding='utf-8')
        assert 'input(' not in t

    def test_no_sendcommand(self):
        for fn in ['mcp/alignment/click_anchor_capture.py','mcp/alignment/click_anchor_calibration_runner.py']:
            t = Path(fn).read_text(encoding='utf-8')
            assert 'SendCommand' not in t

    def test_no_forbidden_terms(self):
        t = Path('mcp/alignment/click_anchor_capture.py').read_text(encoding='utf-8')
        for kw in ['TSaveAs','tgbatplots','dcsz','SaveAs','CopyObjects']:
            assert kw not in t

    def test_has_stdin_false(self):
        t = Path('mcp/alignment/click_anchor_capture.py').read_text(encoding='utf-8')
        assert 'stdin_used' in t
        assert 'input_function_used' in t

    def test_compile(self):
        import py_compile
        py_compile.compile('mcp/alignment/click_anchor_capture.py', doraise=True)
        py_compile.compile('mcp/alignment/click_anchor_calibration_runner.py', doraise=True)
