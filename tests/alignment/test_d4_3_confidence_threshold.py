import json, pytest
from pathlib import Path

class TestD43Confidence:
    def test_report_exists(self):
        r = json.loads(Path('reports/phase_d4_3_auto_anchor_discovery.json').read_text(encoding='utf-8'))
        assert r['phase'] == 'D4.3'

    def test_confidence_capped(self):
        r = json.loads(Path('reports/phase_d4_3_auto_anchor_discovery.json').read_text(encoding='utf-8'))
        assert r['confidence'] <= 0.70

    def test_hardcoded_false(self):
        r = json.loads(Path('reports/phase_d4_3_auto_anchor_discovery.json').read_text(encoding='utf-8'))
        assert r['hardcoded_extent_used'] is False

    def test_inliers_min(self):
        r = json.loads(Path('reports/phase_d4_3_auto_anchor_discovery.json').read_text(encoding='utf-8'))
        assert r['inlier_count'] >= 2

    def test_cannot_enter_d9_1(self):
        r = json.loads(Path('reports/phase_d4_3_auto_anchor_discovery.json').read_text(encoding='utf-8'))
        assert r['can_enter_d9_1'] is False

    def test_source_safe(self):
        r = json.loads(Path('reports/phase_d4_3_auto_anchor_discovery.json').read_text(encoding='utf-8'))
        assert r['source_dwg_opened'] is False
        assert r['d1_allowed'] is False
