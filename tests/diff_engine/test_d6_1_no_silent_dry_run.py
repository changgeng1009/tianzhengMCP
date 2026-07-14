import json, pytest
from pathlib import Path

class TestD61NoSilentDryRun:
    def test_dry_run_false(self):
        r = json.loads(Path('reports/phase_d6_1_real_diff.json').read_text(encoding='utf-8'))
        assert r['dry_run_mode'] is False

    def test_models_loaded(self):
        r = json.loads(Path('reports/phase_d6_1_real_diff.json').read_text(encoding='utf-8'))
        assert r['reference_model_loaded'] is True
        assert r['target_model_loaded'] is True

    def test_blocked_reason_none(self):
        r = json.loads(Path('reports/phase_d6_1_real_diff.json').read_text(encoding='utf-8'))
        assert r['blocked_reason'] is None

    def test_diff_has_data(self):
        r = json.loads(Path('reports/phase_d6_1_real_diff.json').read_text(encoding='utf-8'))
        assert r['matched_count'] + r['missing_count'] + r['extra_count'] > 0
