import json, pytest
from pathlib import Path

class TestD10Source:
    def test_hash_unchanged(self):
        r = json.loads(Path('reports/phase_d10_auto_qa.json').read_text(encoding='utf-8'))
        assert r['source_hash_unchanged'] is True

    def test_source_never_opened(self):
        r = json.loads(Path('reports/phase_d10_auto_qa.json').read_text(encoding='utf-8'))
        assert r['source_dwg_opened'] is False
        assert r['source_dwg_saved'] is False

    def test_d1_blocked(self):
        r = json.loads(Path('reports/phase_d10_auto_qa.json').read_text(encoding='utf-8'))
        assert r['d1_allowed'] is False
        assert r['production_d1_allowed'] is False
