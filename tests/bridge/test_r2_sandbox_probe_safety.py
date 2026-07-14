import pytest
from pathlib import Path

SCRIPT = Path('mcp/bridge/sandbox_dwg_probe.py')

class TestR2Safety:
    def setup_method(self):
        self.text = SCRIPT.read_text(encoding='utf-8')
        self.code = '\n'.join(l for l in self.text.splitlines() if not l.strip().startswith('#'))

    def test_exists(self): assert SCRIPT.exists()
    def test_no_sendcommand(self): assert 'SendCommand' not in self.code
    def test_no_save(self): assert '.Save(' not in self.code
    def test_no_saveas(self): assert 'SaveAs' not in self.code
    def test_no_qsave(self): assert 'QSAVE' not in self.code.upper()
    def test_no_close_true(self): assert 'Close(True)' not in self.code
    def test_no_add(self): assert 'ModelSpace.Add' not in self.code and 'PaperSpace.Add' not in self.code
    def test_no_tiangong(self):
        for kw in ['hsxg','TPIPE','PC2T20','NETLOAD']:
            assert kw not in self.code
    def test_no_http(self): assert '127.0.0.1' not in self.code and 'localhost' not in self.code
    def test_rejects_source(self):
        assert 'source_modification_allowed' not in self.code or 'source_dwg_opened' in self.text
    def test_has_safety_flags(self):
        for flag in ['source_dwg_opened','sendcommand_used','dwg_saved','entity_created','document_saved']:
            assert flag in self.text
