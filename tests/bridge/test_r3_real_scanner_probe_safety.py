import pytest
from pathlib import Path
S = Path('mcp/bridge/real_scanner_probe.py')

class TestR3Safety:
    def setup_method(self):
        t = S.read_text(encoding='utf-8')
        self.code = '\n'.join(l for l in t.splitlines() if not l.strip().startswith('#'))
    def test_exists(self): assert S.exists()
    def test_no_sendcommand(self): assert 'SendCommand' not in self.code
    def test_no_save(self): assert '.Save(' not in self.code and 'SaveAs' not in self.code
    def test_no_qsave(self): assert 'QSAVE' not in self.code.upper()
    def test_no_close_true(self): assert 'Close(True)' not in self.code
    def test_no_add(self): assert 'ModelSpace.Add' not in self.code and 'PaperSpace.Add' not in self.code
    def test_no_del(self): assert 'Delete' not in self.code and 'Erase' not in self.code
    def test_no_tg(self):
        for kw in ['hsxg','TPIPE','PC2T20','NETLOAD']: assert kw not in self.code
    def test_no_http(self): assert '127.0.0.1' not in self.code and 'localhost' not in self.code
    def test_has_safety(self):
        for f in ['source_dwg_opened','sendcommand_used','dwg_opened','entity_created','document_saved']:
            assert f in self.code
