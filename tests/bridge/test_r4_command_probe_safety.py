import pytest
from pathlib import Path
S = Path('mcp/bridge/tianzheng_command_availability_probe.py')

class TestR4Safety:
    def setup_method(self):
        t = S.read_text(encoding='utf-8')
        self.code = '\n'.join(l for l in t.splitlines() if not l.strip().startswith('#'))

    def test_exists(self): assert S.exists()
    def test_whitelist(self): assert 'WHITELIST' in self.code and 'FORBIDDEN' in self.code
    def test_no_tsaveas(self):
        for kw in ['TSaveAs','SaveAs','QSAVE']:
            assert kw not in self.code
    def test_close_false(self): assert 'Close(False)' in self.code
    def test_no_http(self): assert '127.0.0.1' not in self.code and 'localhost' not in self.code
    def test_has_safety(self):
        for f in ['source_dwg_opened','dwg_saved','production_d1_allowed','d1_allowed','sendcommand_used']:
            assert f in self.code
