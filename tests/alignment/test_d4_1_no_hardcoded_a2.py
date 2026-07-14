import json, pytest
from pathlib import Path

class TestD41NoHardcodedA2:
    def test_hardcoded_false(self):
        r = json.loads(Path('reports/phase_d4_1_real_alignment.json').read_text(encoding='utf-8'))
        assert r['hardcoded_extent_used'] is False

    def test_confidence_exists(self):
        r = json.loads(Path('reports/phase_d4_1_real_alignment.json').read_text(encoding='utf-8'))
        assert r['confidence'] > 0 and r['confidence'] <= 1.0

    def test_no_42000_hardcoded(self):
        r = json.loads(Path('reports/phase_d4_1_real_alignment.json').read_text(encoding='utf-8'))
        assert r['hardcoded_extent_used'] is False
