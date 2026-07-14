import pytest
from pathlib import Path
S = Path('mcp/bridge/manual_command_diff_probe.py')

class TestR5Safety:
    def setup_method(self):
        t = S.read_text(encoding='utf-8')
        self.code = '\n'.join(l for l in t.splitlines() if not l.strip().startswith('#'))

    def test_exists(self): assert S.exists()
    def test_no_sendcommand(self): assert 'SendCommand' not in self.code
    def test_no_save(self):
        for kw in ['.Save(','SaveAs','QSAVE']: assert kw not in self.code
    def test_no_close_true(self): assert 'Close(True)' not in self.code
    def test_no_add(self):
        for kw in ['ModelSpace.Add','PaperSpace.Add']: assert kw not in self.code
    def test_no_del(self):
        for kw in ['Delete','Erase']: assert kw not in self.code
    def test_no_tg(self):
        for kw in ['TPIPE','PC2T20','TSaveAs','NETLOAD']: assert kw not in self.code
    def test_no_http(self): assert '127.0.0.1' not in self.code and 'localhost' not in self.code
    def test_has_safety(self):
        for f in ['script_sendcommand_used','dwg_saved','production_d1_allowed','d1_allowed','source_dwg_opened']:
            assert f in self.code
