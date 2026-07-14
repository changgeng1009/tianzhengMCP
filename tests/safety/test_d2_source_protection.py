import json, pytest
from pathlib import Path

class TestD2SourceProtection:
    def test_source_never_opened(self):
        r = json.loads(Path('reports/phase_d2_reference_file_intake.json').read_text(encoding='utf-8'))
        assert r['source_dwg_opened'] is False

    def test_source_never_saved(self):
        r = json.loads(Path('reports/phase_d2_reference_file_intake.json').read_text(encoding='utf-8'))
        assert r['source_dwg_saved'] is False

    def test_source_mod_forbidden(self):
        r = json.loads(Path('reports/phase_d2_reference_file_intake.json').read_text(encoding='utf-8'))
        assert r['source_modification_allowed'] is False

    def test_d1_blocked(self):
        r = json.loads(Path('reports/phase_d2_reference_file_intake.json').read_text(encoding='utf-8'))
        assert r['d1_allowed'] is False
        assert r['production_d1_allowed'] is False

    def test_no_sendcommand_in_modules(self):
        import mcp.intake.file_fingerprint as ff
        import mcp.intake.reference_file_intake as ri
        for mod in [ff, ri]:
            src = str(mod.__dict__)
            assert 'SendCommand' not in src
            assert 'Save' not in src
