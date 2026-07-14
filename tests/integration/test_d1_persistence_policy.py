import json, pytest
from pathlib import Path

class TestD1PersistencePolicy:
    def test_sandbox_save_policy_exists(self):
        r = json.loads(Path('artifacts/t30_r6_persistence.json').read_text(encoding='utf-8'))
        assert r['save_called_on_sandbox'] is True
        assert r['save_called_on_source'] is False

    def test_source_never_saved(self):
        r = json.loads(Path('artifacts/t30_r6_persistence.json').read_text(encoding='utf-8'))
        assert r['save_called_on_source'] is False
        assert r['source_dwg_opened'] is False

    def test_persistence_successful(self):
        r = json.loads(Path('artifacts/t30_r6_persistence.json').read_text(encoding='utf-8'))
        assert r['persistence_success'] is True

    def test_safety_flags_in_D1_report(self):
        r = json.loads(Path('reports/phase_d1_real_aware_dry_run_acceptance.json').read_text(encoding='utf-8'))
        assert r['d1_allowed'] is False
        assert r['source_modification_allowed'] is False
