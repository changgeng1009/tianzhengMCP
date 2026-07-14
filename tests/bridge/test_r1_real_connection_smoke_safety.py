import pytest
from pathlib import Path

SMOKE_SCRIPT = Path('mcp/bridge/real_connection_smoke_test.py')

class TestSmokeTestSafety:
    def test_script_exists(self):
        assert SMOKE_SCRIPT.exists()

    def test_no_sendcommand(self):
        text = SMOKE_SCRIPT.read_text(encoding='utf-8')
        lines = [l for l in text.splitlines() if not l.strip().startswith('#')]; clean = '\n'.join(lines); assert 'SendCommand' not in clean

    def test_no_documents_open(self):
        text = SMOKE_SCRIPT.read_text(encoding='utf-8')
        assert 'Documents.Open' not in text

    def test_no_save(self):
        text = SMOKE_SCRIPT.read_text(encoding='utf-8')
        assert '.Save(' not in text
        assert 'SaveAs' not in text

    def test_no_close_true(self):
        text = SMOKE_SCRIPT.read_text(encoding='utf-8')
        assert 'Close(True)' not in text
        assert 'Close( False)' not in text

    def test_no_model_space_add(self):
        text = SMOKE_SCRIPT.read_text(encoding='utf-8')
        assert 'ModelSpace.Add' not in text

    def test_no_tianzheng_commands(self):
        text = SMOKE_SCRIPT.read_text(encoding='utf-8')
        assert 'hsxg' not in text
        assert 'TPIPE' not in text
        assert 'PC2T20' not in text

    def test_no_localhost(self):
        text = SMOKE_SCRIPT.read_text(encoding='utf-8')
        assert 'localhost' not in text
        assert '127.0.0.1' not in text

    def test_has_safety_flags(self):
        text = SMOKE_SCRIPT.read_text(encoding='utf-8')
        assert 'sendcommand_used' in text
        assert 'dwg_opened_by_script' in text
        assert 'dwg_saved' in text
        assert 'source_dwg_opened' in text
